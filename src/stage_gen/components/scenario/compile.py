"""Fold a parsed script into the program the runtime walks and the proof searches.

Almost every statement compiles one to one; the parser already emitted those as
their final models. This module exists for the single transform that is not local:
an ordered run of `if <condition>: jump <target>` followed by a bare `jump`
becomes one `branch`, with the trailing jump as its **mandatory default**.

That is why a branch cannot be written without a default. A block ending on a
failed `if` would not terminate, and "a block never falls through" is the property
the whole reachability proof rests on.
"""

from __future__ import annotations

from pydantic import ValidationError

from stage_gen.components.scenario.models import (
    Block,
    BranchEdge,
    BranchStatement,
    JumpStatement,
    ScenarioDeclarations,
    ScenarioProgram,
    Statement,
)
from stage_gen.components.scenario.parser import RawBlock, RawIf


class ScenarioCompileError(ValueError):
    """Raised when a syntactically valid script does not form a walkable program."""


def compile_scenario(
    declarations: ScenarioDeclarations,
    raw_blocks: tuple[RawBlock, ...],
) -> ScenarioProgram:
    """Bind the two authored halves into one program. Resolves no names."""

    blocks = tuple(_fold_block(raw) for raw in raw_blocks)
    try:
        return ScenarioProgram(
            game_id=declarations.game_id,
            scenario_id=declarations.scenario_id,
            display_name=declarations.display_name,
            revision=declarations.revision,
            script_sha256=declarations.script_sha256,
            entry=declarations.entry,
            cast=tuple(declarations.cast),
            stages=tuple(declarations.stages),
            tracks=tuple(declarations.tracks),
            flags=tuple(declarations.flags),
            endings=tuple(declarations.endings),
            blocks=blocks,
        )
    except ValidationError as error:
        raise ScenarioCompileError(f"invalid scenario program: {error}") from None


def _fold_block(raw: RawBlock) -> Block:
    statements: list[Statement] = []
    pending: list[RawIf] = []
    for statement in raw.statements:
        if isinstance(statement, RawIf):
            pending.append(statement)
            continue
        if pending:
            if not isinstance(statement, JumpStatement):
                raise ScenarioCompileError(
                    f"line {pending[-1].line}: an `if` run must be closed by a bare "
                    f"`jump <label>`, which becomes the branch default; found a "
                    f"`{statement.kind}` instead"
                )
            statements.append(
                BranchStatement(
                    edges=tuple(
                        BranchEdge(condition=entry.condition, target=entry.target)
                        for entry in pending
                    ),
                    default=statement.target,
                )
            )
            pending = []
            continue
        statements.append(statement)
    if pending:
        raise ScenarioCompileError(
            f"line {pending[-1].line}: block `{raw.label}` ends on an `if`; add the bare "
            "`jump <label>` that is its default, or the block cannot terminate"
        )
    try:
        return Block(label=raw.label, statements=tuple(statements))
    except ValidationError as error:
        raise ScenarioCompileError(f"line {raw.line}: {_first_message(error)}") from None


def _first_message(error: ValidationError) -> str:
    for detail in error.errors():
        message = str(detail.get("msg", ""))
        return message.removeprefix("Value error, ")
    return str(error)


__all__ = [
    "ScenarioCompileError",
    "compile_scenario",
]
