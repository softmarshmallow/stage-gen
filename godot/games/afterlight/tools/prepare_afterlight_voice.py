"""One local, manually invoked Afterlight voice pass; never imported by Godot.

Consumes the host's exported inventory. Existing speech service owns retries;
the wrapper only journals reservations and stops ambiguous requests. See
AFTERLIGHT_VOICE_PREPARATION.md. No provider call occurs without --live --yes.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from gnode import (
    AbortError,
    ArtifactProvenance,
    ArtifactRights,
    CancellationToken,
    SpeechGenerationRequest,
    SpeechGenerationService,
    atomic_write_json,
)
from gnode.providers.elevenlabs import ElevenLabsSpeechBackend
from stage_gen.components.speech import admit_speech_bytes, admit_speech_bytes_sync
from stage_gen.config import CapabilityName, load_config
from stage_gen.identity import SPEECH_GENERATION_COMPONENT, STAGE_GEN_TOOL

PROJECT = Path(__file__).resolve().parents[1]
MAX_ATTEMPTS = 6
LINE_ID = re.compile(r"^[a-z][a-z0-9_.]*$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def confined(root: Path, path: Path) -> Path:
    """Reject traversal and symlinks, including existing parent components."""
    root = root.resolve()
    candidate = path if path.is_absolute() else root / path
    if ".." in candidate.parts or not candidate.is_relative_to(root):
        raise ValueError("output must remain within the declared project root")
    cursor = root
    for part in candidate.relative_to(root).parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("output paths cannot contain symlinks")
    return candidate


def validate_inventory(value: dict[str, Any]) -> list[dict[str, Any]]:
    if value.get("schema_version") != 1 or not isinstance(value.get("lines"), list):
        raise ValueError("expected a version 1 exported voice inventory")
    lines, seen = [], set()
    for raw in value["lines"]:
        line = dict(raw)
        for key in (
            "line_id",
            "language",
            "speaker_id",
            "display_text",
            "speech_text",
            "voice_policy",
            "source_revision",
        ):
            if not isinstance(line.get(key), str):
                raise ValueError(f"inventory {key} must be a string")
        if not LINE_ID.fullmatch(line["line_id"]) or not LINE_ID.fullmatch(line["speaker_id"]):
            raise ValueError("line and speaker IDs must be stable lowercase identifiers")
        if line["language"] not in ("en", "ko"):
            raise ValueError("this local pass supports English and Korean")
        key = (line["language"], line["line_id"])
        if key in seen:
            raise ValueError("duplicate language/line ID")
        seen.add(key)
        if not DIGEST.fullmatch(line["source_revision"]):
            raise ValueError("source_revision must be a SHA-256 digest from the host")
        if line["voice_policy"] not in ("none", "generated"):
            raise ValueError("voice_policy must explicitly be none or generated")
        if line["speaker_id"] == "protagonist" and line["voice_policy"] != "none":
            raise ValueError("the protagonist is unvoiced in this pass")
        if line["voice_policy"] == "generated":
            if (
                not line["display_text"].strip()
                or not line["speech_text"].strip()
                or len(line["speech_text"]) > 5000
            ):
                raise ValueError("generated lines need display and nonempty speech text")
            profile = line.get("voice_profile")
            if not isinstance(profile, dict):
                raise ValueError("generated lines need a resolved voice_profile")
            if profile.get("provider") != "elevenlabs" or profile.get("model") != "eleven_v3":
                raise ValueError("this pass uses the existing ElevenLabs v3 speech route")
            if not re.fullmatch(r"[A-Za-z0-9_-]+", str(profile.get("provider_voice", ""))):
                raise ValueError("provider_voice must be an explicit provider ID")
            if profile.get("language_code") != line["language"]:
                raise ValueError("profile language_code must match the line language")
            if profile.get("output_format", "mp3_44100_192") != "mp3_44100_192":
                raise ValueError("this existing speech route output is mp3_44100_192")
            stability = profile.get("stability", 0.5)
            if isinstance(stability, bool) or stability not in (0.0, 0.5, 1.0):
                raise ValueError("ElevenLabs v3 stability must be 0, 0.5 or 1")
        line["preparation_revision"] = digest(
            {
                key: line.get(key)
                for key in (
                    "line_id",
                    "language",
                    "speaker_id",
                    "display_text",
                    "speech_text",
                    "voice_policy",
                    "source_revision",
                    "voice_profile",
                )
            }
        )
        lines.append(line)
    if not lines:
        raise ValueError("inventory is empty")
    return lines


def validate_quote(quote: dict[str, Any]) -> dict[str, Any]:
    if quote.get("schema_version") != 1 or not quote.get("pricing_basis"):
        raise ValueError("quote needs schema_version 1 and a documented pricing_basis")
    for key in ("budget_usd", "usd_per_character", "max_character_cost_multiplier"):
        number = quote.get(key)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError(f"quote {key} must be a positive finite number")
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"quote {key} must be a positive finite number")
    if quote["budget_usd"] > 10 or quote["max_character_cost_multiplier"] < 1:
        raise ValueError("pass budget cannot exceed $10; charge multiplier cannot be below 1")
    return quote


def estimate(line: dict[str, Any], quote: dict[str, Any]) -> float:
    return round(
        len(line["speech_text"])
        * quote["max_character_cost_multiplier"]
        * quote["usd_per_character"],
        10,
    )


class PassJournal:
    """One append-preserving attempt ledger, protected by the command's file lock."""

    def __init__(self, directory: Path, quote: dict[str, Any], project: Path = PROJECT):
        self.project = project.resolve()
        self.directory = confined(self.project, directory)
        self.path = confined(self.project, directory / "ledger.json")
        self.quote = validate_quote(quote)
        self.value = (
            read_json(self.path)
            if self.path.exists()
            else {
                "schema_version": 1,
                "quote": quote,
                "entries": {},
            }
        )
        if self.value.get("quote") != quote:
            raise ValueError("an existing pass cannot change its reserved pricing/budget quote")

    def save(self) -> None:
        atomic_write_json(self.path, self.value)

    def total(self) -> float:
        total = 0.0
        for entry in self.value["entries"].values():
            for attempt in entry["attempts"]:
                amount = attempt.get("accounted_usd", attempt["reserved_usd"])
                if (
                    isinstance(amount, bool)
                    or not isinstance(amount, (int, float))
                    or not math.isfinite(amount)
                    or amount < 0
                ):
                    raise ValueError("invalid amount in existing pass ledger")
                total += amount
        return total

    def entry(self, line: dict[str, Any]) -> dict[str, Any]:
        revision = line["preparation_revision"]
        return self.value["entries"].setdefault(
            revision,
            {
                "line_id": line["line_id"],
                "language": line["language"],
                "source_revision": line["source_revision"],
                "preparation_revision": revision,
                "attempts": [],
            },
        )

    def artifact(self, line: dict[str, Any]) -> Path:
        return confined(
            self.project,
            self.directory
            / "clips"
            / line["language"]
            / f"{line['line_id']}-{line['preparation_revision'][:16]}.mp3",
        )

    def reserve(self, line: dict[str, Any]) -> dict[str, Any]:
        entry = self.entry(line)
        if any(a["status"] in ("reserved", "uncertain") for a in entry["attempts"]):
            raise AbortError("uncertain request requires reconciliation; automatic resend refused")
        if len(entry["attempts"]) >= MAX_ATTEMPTS:
            raise AbortError("this line already exhausted its six technical attempts")
        reserved = estimate(line, self.quote)
        if self.total() + reserved > self.quote["budget_usd"] + 1e-9:
            raise AbortError("pass reservation would exceed its hard budget")
        attempt = {
            "attempt": len(entry["attempts"]) + 1,
            "status": "reserved",
            "reserved_usd": reserved,
            "submitted_characters": len(line["speech_text"]),
            "estimated_text_usd": round(
                len(line["speech_text"]) * self.quote["usd_per_character"], 10
            ),
        }
        entry["attempts"].append(attempt)
        self.save()  # Must finish before the network operation can begin.
        return attempt


class AccountedBackend:
    """Instrumentation around the existing adapter; not another retry owner."""

    spec_version = 1

    def __init__(
        self,
        backend: Any,
        journal: PassJournal,
        line: dict[str, Any],
        cancellation: CancellationToken,
    ):
        self.backend, self.journal, self.line = backend, journal, line
        self.cancellation = cancellation
        self.provider, self.model, self.secrets = backend.provider, backend.model, backend.secrets

    async def aclose(self) -> None:
        await self.backend.aclose()

    async def generate_once(self, request: SpeechGenerationRequest) -> Any:
        attempt = self.journal.reserve(self.line)
        try:
            result = await self.backend.generate_once(request)
        except BaseException as error:
            attempt.update(status="uncertain", error_type=type(error).__name__)
            self.journal.save()
            self.cancellation.cancel("uncertain provider outcome; reconciliation required")
            raise
        usage = result.response_metadata.usage or {}
        count = usage.get("character_cost")
        attempt.update(status="returned", request_id=result.response_metadata.request_id)
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            attempt["character_cost"] = count
            # This header reports subscription credits, not input characters or
            # dollars. Keep the conservative reservation for budget enforcement;
            # record actual credits and published text-rate estimates separately.
            attempt["accounted_usd"] = attempt["reserved_usd"]
            attempt["charge_basis"] = "conservative_reservation_reported_credits"
        else:
            attempt["accounted_usd"] = attempt["reserved_usd"]
            attempt["charge_basis"] = "conservative_reservation_missing_usage"
        self.journal.save()  # Charged rejected audio is accounted before admission.
        if isinstance(count, int) and count > (
            len(self.line["speech_text"]) * self.journal.quote["max_character_cost_multiplier"]
        ):
            self.cancellation.cancel("provider credit usage exceeded the quoted multiplier bound")
            raise AbortError("provider credit usage exceeded the quoted multiplier bound")
        return result


def verified_clip(
    journal: PassJournal, line: dict[str, Any], admit: Any = admit_speech_bytes_sync
) -> dict[str, Any] | None:
    path = journal.artifact(line)
    sidecar = confined(journal.project, Path(f"{path}.meta.json"))
    if not path.exists() and not sidecar.exists():
        return None
    if not path.is_file() or not sidecar.is_file():
        raise ValueError("partial artifact bundle requires reconciliation, not regeneration")
    raw_meta = read_json(sidecar)
    meta = ArtifactProvenance.model_validate(raw_meta)
    data = path.read_bytes()
    audio_digest = hashlib.sha256(data).hexdigest()
    profile = line["voice_profile"]
    expected = {
        "source_revision": line["source_revision"],
        "preparation_revision": line["preparation_revision"],
    }
    metadata = meta.params.get("metadata", {})
    if (
        meta.artifact is None
        or meta.artifact.sha256 != audio_digest
        or meta.artifact.bytes != len(data)
        or meta.artifact.media_type != "audio/mpeg"
        or meta.prompt != line["speech_text"]
        or meta.provider != profile["provider"]
        or meta.model != profile["model"]
        or meta.params.get("voice") != profile["provider_voice"]
        or meta.params.get("language_code") != profile["language_code"]
        or meta.params.get("stability") != profile.get("stability", 0.5)
        or any(metadata.get(k) != v for k, v in expected.items())
    ):
        raise ValueError("artifact source/digest mismatch; automatic regeneration refused")
    facts = admit(data)  # A matching header or sidecar alone is not a decode check.
    return {
        "status": "ready",
        "path": "res://" + path.relative_to(journal.project).as_posix(),
        **expected,
        "audio_sha256": audio_digest,
        "provenance_path": sidecar.relative_to(journal.project).as_posix(),
        "provenance_sha256": hashlib.sha256(sidecar.read_bytes()).hexdigest(),
        "duration_seconds": facts["duration_seconds"],
        "speaker_id": line["speaker_id"],
        "provider": meta.provider,
        "model": meta.model,
        "voice_profile": profile,
        "listening_verdict": "not_reviewed",
    }


def inspect_pass(
    lines: list[dict[str, Any]], journal: PassJournal, admit: Any = admit_speech_bytes_sync
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest: dict[str, Any] = {"schema_version": 1, "lines": {"en": {}, "ko": {}}}
    pending, blocked = [], []
    for line in lines:
        if line["voice_policy"] == "none":
            continue
        entry = journal.value["entries"].get(line["preparation_revision"], {})
        try:
            record = verified_clip(journal, line, admit)
            if record is None and entry.get("attempts"):
                raise ValueError("earlier attempt has no admitted bundle; reconciliation required")
        except (ValueError, OSError, RuntimeError) as error:
            record = {
                "status": "failed",
                "source_revision": line["source_revision"],
                "reason": f"prepared artifact needs reconciliation ({type(error).__name__})",
            }
            blocked.append(f"{line['language']}:{line['line_id']}")
        if record is None:
            record = {"status": "pending", "source_revision": line["source_revision"]}
            pending.append(line)
        manifest["lines"][line["language"]][line["line_id"]] = record
    reserved = sum(estimate(line, journal.quote) for line in pending)
    expected = sum(
        len(line["speech_text"]) * journal.quote["usd_per_character"] for line in pending
    )
    attempts = [
        attempt for entry in journal.value["entries"].values() for attempt in entry["attempts"]
    ]
    manifest["preparation"] = {
        "skipped_none": sum(line["voice_policy"] == "none" for line in lines),
        "ready": sum(
            row["status"] == "ready" for rows in manifest["lines"].values() for row in rows.values()
        ),
        "pending": len(pending),
        "blocked": blocked,
        "accounted_usd": round(journal.total(), 10),
        "accounting_basis": "conservative_budget_reservations_not_an_invoice",
        "reported_credits": sum(attempt.get("character_cost", 0) for attempt in attempts),
        "submitted_characters": sum(attempt.get("submitted_characters", 0) for attempt in attempts),
        "estimated_text_usd": round(
            sum(attempt.get("estimated_text_usd", 0) for attempt in attempts), 10
        ),
        "expected_remaining_usd": round(expected, 10),
        "single_attempt_reservation_usd": round(reserved, 10),
        "worst_case_remaining_usd": round(reserved * MAX_ATTEMPTS, 10),
        "budget_usd": journal.quote["budget_usd"],
    }
    return manifest, pending


async def generate_line(
    journal: PassJournal, line: dict[str, Any], backend: Any, validator: Any = admit_speech_bytes
) -> None:
    cancellation = CancellationToken(secrets=backend.secrets)
    service = SpeechGenerationService(
        AccountedBackend(backend, journal, line, cancellation),
        component=SPEECH_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
    )
    profile = line["voice_profile"]
    async with service:
        await service.generate(
            SpeechGenerationRequest(
                text=line["speech_text"],
                voice=profile["provider_voice"],
                artifact_path=journal.artifact(line),
                stability=profile.get("stability", 0.5),
                language_code=profile["language_code"],
                timeout_seconds=120,
                metadata={
                    "source": "afterlight-manual-voice-preparation",
                    "line_id": line["line_id"],
                    "speaker_id": line["speaker_id"],
                    "language": line["language"],
                    "display_text_sha256": digest(line["display_text"]),
                    "speech_text_sha256": digest(line["speech_text"]),
                    "source_revision": line["source_revision"],
                    "preparation_revision": line["preparation_revision"],
                },
                rights=ArtifactRights(
                    status="unreviewed", attribution=[], basis=[], reviewed_at=None
                ),
                cancellation=cancellation,
                validate=lambda artifact: validator(artifact.data),
            )
        )


async def run(args: argparse.Namespace) -> dict[str, Any]:
    lines = validate_inventory(read_json(args.inventory))
    quote = validate_quote(read_json(args.quote))
    directory = confined(PROJECT, args.pass_dir)
    manifest_path = confined(PROJECT, args.manifest)
    journal = PassJournal(directory, quote)
    manifest, pending = inspect_pass(lines, journal)
    if not args.live:
        return manifest  # plan/status are read-only and never load credentials.
    if not args.yes:
        raise ValueError("paid dispatch requires both --live and --yes")
    summary = manifest["preparation"]
    if summary["blocked"]:
        raise ValueError("earlier ambiguous/invalid artifacts block this pass; reconcile first")
    if journal.total() + summary["worst_case_remaining_usd"] > quote["budget_usd"] + 1e-9:
        raise ValueError("full six-attempt worst-case reservation exceeds pass budget")
    if not pending:
        atomic_write_json(manifest_path, manifest)
        return manifest
    config = load_config(require=[CapabilityName.SPEECH_GENERATION])
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = confined(PROJECT, directory / ".preparation.lock")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Refresh under the lock so concurrent commands cannot spend twice.
        journal = PassJournal(directory, quote)
        manifest, pending = inspect_pass(lines, journal)
        if manifest["preparation"]["blocked"]:
            raise ValueError("pass changed before dispatch; inspect status")
        if (
            journal.total() + manifest["preparation"]["worst_case_remaining_usd"]
            > quote["budget_usd"] + 1e-9
        ):
            raise ValueError("pass changed before dispatch; reservation exceeds budget")
        journal.save()
        for line in lines:
            if line["voice_policy"] == "none":
                entry = journal.entry(line)
                entry["status"] = "skipped_none"
        journal.save()
        for index, line in enumerate(pending):
            profile = line["voice_profile"]
            backend = ElevenLabsSpeechBackend(
                api_key=config.elevenlabs_api_key or "",
                model=profile["model"],
                base_url=config.elevenlabs_base_url or "https://api.elevenlabs.io/v1",
            )
            try:
                await generate_line(journal, line, backend)
            except Exception:
                # Do not emit raw provider errors or retry outside the service.
                journal.entry(line)["status"] = "blocked"
                journal.save()
                manifest, _ = inspect_pass(lines, journal)
                atomic_write_json(manifest_path, manifest)
                raise ValueError(
                    f"voice preparation stopped at {line['language']}:{line['line_id']}; "
                    "inspect ledger"
                ) from None
            journal.entry(line)["status"] = "ready"
            journal.save()
            record = verified_clip(journal, line)
            if record is None:
                raise ValueError("successful speech service returned without an artifact")
            manifest["lines"][line["language"]][line["line_id"]] = record
            summary = manifest["preparation"]
            summary["ready"] += 1
            summary["pending"] -= 1
            summary["accounted_usd"] = round(journal.total(), 10)
            attempts = [
                attempt
                for entry in journal.value["entries"].values()
                for attempt in entry["attempts"]
            ]
            summary["reported_credits"] = sum(
                attempt.get("character_cost", 0) for attempt in attempts
            )
            summary["submitted_characters"] = sum(
                attempt.get("submitted_characters", 0) for attempt in attempts
            )
            summary["estimated_text_usd"] = round(
                sum(attempt.get("estimated_text_usd", 0) for attempt in attempts), 10
            )
            remaining = pending[index + 1 :]
            summary["expected_remaining_usd"] = round(
                sum(len(item["speech_text"]) * quote["usd_per_character"] for item in remaining), 10
            )
            summary["single_attempt_reservation_usd"] = round(
                sum(estimate(item, quote) for item in remaining), 10
            )
            summary["worst_case_remaining_usd"] = round(
                summary["single_attempt_reservation_usd"] * MAX_ATTEMPTS, 10
            )
            atomic_write_json(manifest_path, manifest)
            print(
                json.dumps(
                    {
                        "ready": f"{line['language']}:{line['line_id']}",
                        "accounted_usd": round(journal.total(), 6),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--quote", type=Path, required=True)
    parser.add_argument("--pass-dir", type=Path, default=PROJECT / "art/voiceovers-p95")
    parser.add_argument(
        "--manifest", type=Path, default=PROJECT / "art/voiceovers-p95/manifest.json"
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except (ValueError, OSError) as error:
        parser.exit(2, f"Voice preparation: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
