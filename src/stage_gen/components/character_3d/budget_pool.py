"""Durable hierarchical USD reservations, independent of providers and callbacks.

One storage root is one inclusive ledger and lock. A session reserves a run's
entire ceiling once; the run account reserves its agent loop and individual
image/mesh operations. Parent liability remains at least the full slice until child
finalization; reported child overages immediately increase its liability. A historical
floor is retained liability, not a complete invoice reconciliation. No paths, prompts,
credentials or arbitrary metadata are stored.

Settlement is terminal and immutable. `completed` records known actual plus
unresolved liability; `interrupted` retains at least the original reservation;
`not_started` permits zero only before mark_started. Unknown terminal liability
cannot later be released by changing a settlement. Invoice reconciliation would
need a separate explicit future operation, not a silent overwrite here.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, cast

_NAME = re.compile("[a-z][a-z0-9_-]{0,95}")
_DIGEST = re.compile("[a-f0-9]{64}")
_STATES = {"reserved", "running", "settled"}
_OUTCOMES = {"completed", "interrupted", "not_started"}


class BudgetError(ValueError):
    """An invalid, exhausted or conflicting budget operation was refused."""


def _name(value: object) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value) or value.startswith("sk-"):
        raise BudgetError("Budget IDs must be non-path lowercase names")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise BudgetError("Identity requires a lowercase SHA-256 digest")
    return value


def _money(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise BudgetError("Use an exact decimal string, integer or Decimal for USD")
    if isinstance(value, str) and (not value or len(value) > 128 or value != value.strip()):
        raise BudgetError("USD value has invalid decimal text")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        raise BudgetError("USD value is not a finite nonnegative decimal") from None
    if not number.is_finite() or number < 0:
        raise BudgetError("USD value is not a finite nonnegative decimal")
    if len(number.as_tuple().digits) > 128 or abs(cast(int, number.as_tuple().exponent)) > 128:
        raise BudgetError("USD value exceeds the supported exact decimal precision")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if len(text) > 128:
        raise BudgetError("USD value exceeds the supported exact decimal precision")
    return "0" if number == 0 else text


def _sum(values: Iterable[str | int | Decimal]) -> str:
    with localcontext() as context:
        context.prec = 400
        return _money(sum((Decimal(value) for value in values), Decimal(0)))


def _difference(left: str | int | Decimal, right: str | int | Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 400
        return Decimal(left) - Decimal(right)


def _safe_root(value: str | Path) -> Path:
    root = Path(value).absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise BudgetError("Budget storage cannot contain symlinked path components")
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise BudgetError("Budget storage must be a directory")
    return root


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BudgetError("Budget ledger contains duplicate JSON keys")
        result[key] = value
    return result


def _sync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _save(root: Path, state: dict[str, Any]) -> None:
    destination = root / "budget_pool.json"
    if destination.is_symlink():
        raise BudgetError("Budget ledger cannot be a symlink")
    payload = json.dumps(state, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".budget-pending-", dir=root)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        _sync_directory(root)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _liability(reservation: dict[str, Any], state: dict[str, Any] | None = None) -> str:
    if reservation["status"] != "settled":
        amount = reservation["amount_usd"]
        child_id = reservation["child_account_id"]
        if child_id is not None and state is not None:
            child_total = _totals(state["accounts"][child_id], state)["liability_usd"]
            return _money(max(Decimal(amount), Decimal(child_total)))
        return cast(str, amount)
    return _sum(
        [
            reservation["settlement"]["known_actual_usd"],
            reservation["settlement"]["unresolved_liability_usd"],
        ]
    )


def _totals(account: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    known, unknown = ([], [account["historical_liability_usd"]])
    for item in account["reservations"].values():
        if item["status"] == "settled":
            known.append(item["settlement"]["known_actual_usd"])
            unknown.append(item["settlement"]["unresolved_liability_usd"])
        elif item["child_account_id"] is not None and state is not None:
            child = _totals(state["accounts"][item["child_account_id"]], state)
            held = _money(max(Decimal(item["amount_usd"]), Decimal(child["liability_usd"])))
            known.append(child["known_actual_usd"])
            unknown.append(_money(_difference(held, child["known_actual_usd"])))
        else:
            unknown.append(_liability(item, state))
    known_total, unknown_total = (_sum(known), _sum(unknown))
    liability = _sum([known_total, unknown_total])
    remaining = _difference(account["ceiling_usd"], liability)
    return {
        "known_actual_usd": known_total,
        "unresolved_liability_usd": unknown_total,
        "liability_usd": liability,
        "remaining_usd": _money(max(Decimal(0), remaining)),
        "over_ceiling": remaining < 0,
        "historical_floor_is_complete_reconciliation": False,
    }


def _validate_state(state: dict[str, Any]) -> None:
    if (
        not isinstance(state, dict)
        or set(state) != {"schema_version", "accounts"}
        or type(state["schema_version"]) is not int
        or (state["schema_version"] != 1)
    ):
        raise BudgetError("Budget ledger has an unsupported schema")
    if not isinstance(state["accounts"], dict):
        raise BudgetError("Budget accounts must be an object")
    for name, account in state["accounts"].items():
        _name(name)
        if not isinstance(account, dict) or set(account) != {
            "ceiling_usd",
            "historical_liability_usd",
            "parent",
            "closed",
            "reservations",
        }:
            raise BudgetError("Budget account fields changed")
        if Decimal(_money(account["ceiling_usd"])) <= 0 or type(account["closed"]) is not bool:
            raise BudgetError("Invalid account ceiling or lifecycle")
        _money(account["historical_liability_usd"])
        if not isinstance(account["reservations"], dict):
            raise BudgetError("Budget reservations must be an object")
        for reservation_id, item in account["reservations"].items():
            _name(reservation_id)
            if not isinstance(item, dict) or set(item) != {
                "identity_sha256",
                "amount_usd",
                "status",
                "dispatch_started",
                "child_account_id",
                "settlement",
            }:
                raise BudgetError("Reservation fields changed")
            _digest(item["identity_sha256"])
            if (
                Decimal(_money(item["amount_usd"])) <= 0
                or item["status"] not in _STATES
                or type(item["dispatch_started"]) is not bool
            ):
                raise BudgetError("Invalid reservation amount or lifecycle")
            if item["status"] == "settled":
                settlement = item["settlement"]
                if not isinstance(settlement, dict) or set(settlement) != {
                    "outcome",
                    "known_actual_usd",
                    "unresolved_liability_usd",
                    "declared_unresolved_liability_usd",
                }:
                    raise BudgetError("Invalid terminal settlement")
                if settlement["outcome"] not in _OUTCOMES | {"child_finalized"}:
                    raise BudgetError("Unsupported settlement outcome")
                for key in (
                    "known_actual_usd",
                    "unresolved_liability_usd",
                    "declared_unresolved_liability_usd",
                ):
                    _money(settlement[key])
                if settlement["outcome"] == "interrupted" and Decimal(_liability(item)) < Decimal(
                    item["amount_usd"]
                ):
                    raise BudgetError("Interrupted liability was released")
                if settlement["outcome"] == "not_started" and (
                    item["dispatch_started"] or Decimal(_liability(item))
                ):
                    raise BudgetError("Started or charged reservation claims not_started")
            elif item["settlement"] is not None:
                raise BudgetError("Nonterminal reservation has settlement data")
            if (item["status"] == "running") != (
                item["dispatch_started"] and item["status"] != "settled"
            ):
                raise BudgetError("Reservation started state is inconsistent")
        if account["closed"] and any(
            item["status"] != "settled" for item in account["reservations"].values()
        ):
            raise BudgetError("Closed account contains nonterminal allocations")
    if sum(account["parent"] is None for account in state["accounts"].values()) > 1:
        raise BudgetError("A ledger has exactly one inclusive root account")
    for name, account in state["accounts"].items():
        parent = account["parent"]
        seen = {name}
        current = account
        while current["parent"] is not None:
            link = current["parent"]
            if not isinstance(link, dict) or set(link) != {
                "account_id",
                "reservation_id",
                "identity_sha256",
            }:
                raise BudgetError("Invalid parent binding")
            _name(link["account_id"])
            _name(link["reservation_id"])
            _digest(link["identity_sha256"])
            if link["account_id"] in seen:
                raise BudgetError("Cyclic budget account hierarchy")
            seen.add(link["account_id"])
            current = state["accounts"].get(link["account_id"])
            if current is None:
                raise BudgetError("Missing parent account")
        if parent is not None:
            reservation = state["accounts"][parent["account_id"]]["reservations"].get(
                parent["reservation_id"]
            )
            if (
                reservation is None
                or reservation["identity_sha256"] != parent["identity_sha256"]
                or reservation["child_account_id"] != name
                or (reservation["amount_usd"] != account["ceiling_usd"])
            ):
                raise BudgetError("Parent reservation and child account disagree")
            if account["closed"] != (reservation["status"] == "settled"):
                raise BudgetError("Parent and child terminal states disagree")
        for reservation_id, item in account["reservations"].items():
            if item["child_account_id"] is not None:
                child = state["accounts"].get(item["child_account_id"])
                if child is None or child["parent"] != {
                    "account_id": name,
                    "reservation_id": reservation_id,
                    "identity_sha256": item["identity_sha256"],
                }:
                    raise BudgetError("Reservation child binding is missing or inconsistent")
    for account in state["accounts"].values():
        if account["closed"] and account["parent"] is not None:
            parent = account["parent"]
            reservation = state["accounts"][parent["account_id"]]["reservations"][
                parent["reservation_id"]
            ]
            totals = _totals(account, state)
            settlement = reservation["settlement"]
            if (
                settlement["outcome"] != "child_finalized"
                or settlement["known_actual_usd"] != totals["known_actual_usd"]
                or settlement["unresolved_liability_usd"] != totals["unresolved_liability_usd"]
            ):
                raise BudgetError("Finalized child totals and parent settlement disagree")


class BudgetPool:
    """One named account in a shared on-disk hierarchy. All methods are local."""

    def __init__(
        self,
        root: str | Path,
        account_id: str,
        ceiling_usd: str | int | Decimal,
        historical_liability_usd: str | int | Decimal = "0",
        *,
        parent_reservation: dict[str, Any] | None = None,
    ) -> None:
        self.root = _safe_root(root)
        self.account_id = _name(account_id)
        ceiling, history = (_money(ceiling_usd), _money(historical_liability_usd))
        if Decimal(ceiling) <= 0:
            raise BudgetError("Account ceiling must be positive")
        parent = copy.deepcopy(parent_reservation)
        if parent is not None:
            if not isinstance(parent, dict) or set(parent) != {
                "account_id",
                "reservation_id",
                "identity_sha256",
            }:
                raise BudgetError("Parent requires account_id, reservation_id and identity_sha256")
            _name(parent["account_id"])
            _name(parent["reservation_id"])
            _digest(parent["identity_sha256"])
        with self._locked() as state:
            account = state["accounts"].get(self.account_id)
            if account is not None:
                if (
                    account["ceiling_usd"],
                    account["historical_liability_usd"],
                    account["parent"],
                ) != (ceiling, history, parent):
                    raise BudgetError("Existing account ceiling, history or parent cannot change")
                return
            if parent is None and state["accounts"]:
                raise BudgetError("A ledger already has its inclusive root account")
            if parent is not None:
                ancestor = state["accounts"].get(parent["account_id"])
                if ancestor is None or ancestor["closed"]:
                    raise BudgetError("An open parent account is required")
                grant = self._reservation(
                    ancestor, parent["reservation_id"], parent["identity_sha256"]
                )
                if (
                    grant["status"] != "reserved"
                    or grant["child_account_id"] is not None
                    or grant["amount_usd"] != ceiling
                ):
                    raise BudgetError(
                        "Child must own one unused parent reservation of its exact ceiling"
                    )
                grant["child_account_id"] = self.account_id
            state["accounts"][self.account_id] = {
                "ceiling_usd": ceiling,
                "historical_liability_usd": history,
                "parent": parent,
                "closed": False,
                "reservations": {},
            }
            self._commit(state)

    @contextmanager
    def _locked(self) -> Iterator[dict[str, Any]]:
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            raise BudgetError("Budget root changed to a symlink")
        descriptor = os.open(
            self.root / "budget_pool.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            path = self.root / "budget_pool.json"
            if path.is_symlink():
                raise BudgetError("Budget ledger cannot be a symlink")
            if path.exists():
                try:
                    state = json.loads(path.read_text(), object_pairs_hook=_unique_object)
                except (ValueError, OSError):
                    raise BudgetError("Budget ledger is unreadable; it will not be reset") from None
                _validate_state(state)
            else:
                if os.fstat(descriptor).st_size:
                    raise BudgetError("Initialized budget ledger is missing; it will not be reset")
                state = {"schema_version": 1, "accounts": {}}
            yield state
        finally:
            try:
                if (self.root / "budget_pool.json").exists() and (not os.fstat(descriptor).st_size):
                    os.write(descriptor, b"budget_pool_v1\n")
                    os.fsync(descriptor)
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    def _commit(self, state: dict[str, Any]) -> None:
        _validate_state(state)
        _save(self.root, state)

    @staticmethod
    def _assert_ancestors_within_budget(account: dict[str, Any], state: dict[str, Any]) -> None:
        while account["parent"] is not None:
            account = state["accounts"][account["parent"]["account_id"]]
            if _totals(account, state)["over_ceiling"]:
                raise BudgetError("An ancestor account exceeds its inclusive ceiling")

    @staticmethod
    def _reservation(
        account: dict[str, Any], reservation_id: str, identity_sha256: str
    ) -> dict[str, Any]:
        _name(reservation_id)
        _digest(identity_sha256)
        item = account["reservations"].get(reservation_id)
        if item is None or item["identity_sha256"] != identity_sha256:
            raise BudgetError("Reservation is missing or belongs to a different identity")
        return cast(dict[str, Any], item)

    def reserve(
        self, reservation_id: str, identity_sha256: str, amount_usd: str | int | Decimal
    ) -> dict[str, Any]:
        reservation_id, identity_sha256 = (_name(reservation_id), _digest(identity_sha256))
        amount = _money(amount_usd)
        if Decimal(amount) <= 0:
            raise BudgetError("Reservation amount must be positive")
        with self._locked() as state:
            account = state["accounts"][self.account_id]
            existing = account["reservations"].get(reservation_id)
            if existing is not None:
                if (
                    existing["identity_sha256"] != identity_sha256
                    or existing["amount_usd"] != amount
                ):
                    raise BudgetError("Reservation ID cannot change identity or amount")
                return self._record(reservation_id, existing, state)
            if account["closed"]:
                raise BudgetError("Finalized accounts cannot admit reservations")
            self._assert_ancestors_within_budget(account, state)
            if Decimal(_sum([_totals(account, state)["liability_usd"], amount])) > Decimal(
                account["ceiling_usd"]
            ):
                raise BudgetError("Reservation exceeds remaining inclusive account budget")
            item = {
                "identity_sha256": identity_sha256,
                "amount_usd": amount,
                "status": "reserved",
                "dispatch_started": False,
                "child_account_id": None,
                "settlement": None,
            }
            account["reservations"][reservation_id] = item
            self._commit(state)
            return self._record(reservation_id, item, state)

    def mark_started(self, reservation_id: str, identity_sha256: str) -> dict[str, Any]:
        with self._locked() as state:
            account = state["accounts"][self.account_id]
            item = self._reservation(account, reservation_id, identity_sha256)
            if account["closed"] or item["status"] == "settled":
                raise BudgetError("Terminal reservations cannot start another dispatch")
            if item["child_account_id"] is not None:
                raise BudgetError("Start the child operation; parent lifecycle is aggregated")
            self._assert_ancestors_within_budget(account, state)
            if _totals(account, state)["over_ceiling"]:
                raise BudgetError("Account exceeds its inclusive ceiling")
            item.update(status="running", dispatch_started=True)
            while account["parent"] is not None:
                parent = account["parent"]
                account = state["accounts"][parent["account_id"]]
                ancestor = account["reservations"][parent["reservation_id"]]
                ancestor.update(status="running", dispatch_started=True)
            self._commit(state)
            return self._record(reservation_id, item, state)

    def settle(
        self,
        reservation_id: str,
        identity_sha256: str,
        *,
        known_actual_usd: str | int | Decimal,
        unresolved_liability_usd: str | int | Decimal,
        outcome: str,
    ) -> dict[str, Any]:
        known, declared = (_money(known_actual_usd), _money(unresolved_liability_usd))
        if outcome not in _OUTCOMES:
            raise BudgetError("Settlement outcome must be completed, interrupted or not_started")
        with self._locked() as state:
            account = state["accounts"][self.account_id]
            item = self._reservation(account, reservation_id, identity_sha256)
            if item["child_account_id"] is not None:
                raise BudgetError("A child allocation settles only through child.finalize()")
            if outcome == "not_started" and (
                item["dispatch_started"] or Decimal(known) or Decimal(declared)
            ):
                raise BudgetError(
                    "Only a never-started uncharged operation can release its full hold"
                )
            if outcome == "completed" and (not item["dispatch_started"]):
                raise BudgetError("Use not_started for an operation that never began")
            unresolved = declared
            if outcome == "interrupted":
                unresolved = _money(
                    max(Decimal(declared), _difference(item["amount_usd"], known), Decimal(0))
                )
            settlement = {
                "outcome": outcome,
                "known_actual_usd": known,
                "unresolved_liability_usd": unresolved,
                "declared_unresolved_liability_usd": declared,
            }
            if item["status"] == "settled":
                if item["settlement"] != settlement:
                    raise BudgetError(
                        "Terminal settlement is immutable; uncertain spend cannot be released"
                    )
                return self._record(reservation_id, item, state)
            if account["closed"]:
                raise BudgetError("Account is finalized")
            item.update(status="settled", settlement=settlement)
            self._commit(state)
            return self._record(reservation_id, item, state)

    def finalize(self) -> dict[str, Any]:
        """Close only terminal children; atomically settle this account's parent slice."""
        with self._locked() as state:
            account = state["accounts"][self.account_id]
            if any(item["status"] != "settled" for item in account["reservations"].values()):
                raise BudgetError("Cannot finalize while reservations remain nonterminal")
            if not account["closed"]:
                account["closed"] = True
                if account["parent"] is not None:
                    totals = _totals(account, state)
                    parent = account["parent"]
                    grant = state["accounts"][parent["account_id"]]["reservations"][
                        parent["reservation_id"]
                    ]
                    grant.update(
                        status="settled",
                        settlement={
                            "outcome": "child_finalized",
                            "known_actual_usd": totals["known_actual_usd"],
                            "unresolved_liability_usd": totals["unresolved_liability_usd"],
                            "declared_unresolved_liability_usd": totals["unresolved_liability_usd"],
                        },
                    )
                self._commit(state)
            return self._snapshot(account, state)

    def settle_parent(self) -> dict[str, Any]:
        return self.finalize()

    def snapshot(self) -> dict[str, Any]:
        with self._locked() as state:
            return self._snapshot(state["accounts"][self.account_id], state)

    def _snapshot(self, account: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "account_id": self.account_id,
            "ceiling_usd": account["ceiling_usd"],
            "historical_liability_usd": account["historical_liability_usd"],
            "parent": copy.deepcopy(account["parent"]),
            "closed": account["closed"],
            **_totals(account, state),
            "reservations": {
                name: self._record(name, item, state)
                for name, item in account["reservations"].items()
            },
        }

    @staticmethod
    def _record(
        reservation_id: str, item: dict[str, Any], state: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "reservation_id": reservation_id,
            **copy.deepcopy(item),
            "liability_usd": _liability(item, state),
        }
