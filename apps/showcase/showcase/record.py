"""The showcase record: one plain JSON document per workflow page, written by an adapter.

Components read only this record and their own props, so the same record can later feed MDX
components unchanged. Shape (showcase-record-v1):

    run        {path, graph_sha256, graph_kind, status}
    inputs     {name: {kind: text|image, text | picture}}
    outputs    {name: {kind: model|video|image, file, bytes, sha256, src, poster, clips}}
    metrics    {name: number}             raw measures; the suffix names the unit (_seconds, _usd)
    models     [{name, provider, roles, nodes, called_by}]
    tree       {path: {kind, bytes, files?, entries?}}   the run folder, "" is its root
    nodes      {id: {id, type_id, kind, description, provider, model, retry_owner, max_attempts,
                     depends_on, state, attempts, duration_ms, cost_usd, provider_operations, cache,
                     not_needed, verdict, checks, prompt, rationale, open_issues, record_ref, thumb,
                     pictures}}   build nodes with node() below

A picture is {src, width, height, bg, alpha}; `bg` is its plain ground colour, so a frame can match
it, and `alpha` asks for a checkerboard behind it.
The record holds values, never wording: pages and components decide what to say about them.
"""

from __future__ import annotations

RECORD_SCHEMA = "showcase-record-v1"

MODEL_NAMES = {
    "openai/gpt-6-astra": "GPT-6 Astra",
    "openai/gpt-image-2.5-sunburst": "GPT Image 2.5 Sunburst",
    "P2-20260801": "Tripo P2 mesh",
    "v1.0-20240301": "Tripo rig 1.0",
    "google/gemini-omni-flash/v1.1/image-to-video": "Gemini Omni Flash 1.1",
    "gpt-image-2.5-sunburst": "GPT Image 2.5 Sunburst",
    "gpt-image-2": "GPT Image 2",
    "openai/gpt-5.6-sol": "GPT-5.6 Sol",
}
PROVIDER_NAMES = {"openrouter": "OpenRouter", "tripo": "Tripo", "openai": "OpenAI", "fal": "fal"}


def model_name(model: str | None) -> str | None:
    return MODEL_NAMES.get(model, model) if model else None


def provider_name(provider: str | None) -> str | None:
    return PROVIDER_NAMES.get(provider, provider) if provider else None


def node(node_id: str, **fields) -> dict:
    """One record node with every field present, so adapters cannot drift apart."""
    base = {
        "id": node_id,
        "type_id": "",
        "kind": "Local",
        "description": "",
        "provider": None,
        "model": None,
        "retry_owner": None,
        "max_attempts": None,
        "depends_on": [],
        "state": "succeeded",
        "attempts": None,
        "duration_ms": None,
        "cost_usd": None,
        "provider_operations": None,
        "cache": None,
        "not_needed": None,
        "verdict": None,
        "checks": [],
        "prompt": None,
        "rationale": None,
        "open_issues": [],
        "record_ref": None,
        "thumb": None,
        "pictures": [],
    }
    unknown = set(fields) - set(base)
    if unknown:
        raise ValueError(f"unknown node fields {sorted(unknown)}")
    return {**base, **fields}
