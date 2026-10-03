"""The run's spending ceiling: reserve a node's worst case before it dispatches, settle after.

The ledger is the run record's own arithmetic. Every reservation, settlement and refusal
is an event in the run's log, and a resumed run rebuilds the ledger from the events its
earlier invocations wrote, so one ceiling covers the whole run however often it is
started. A reservation that was never settled - the process died with the call in
flight - stays charged at its full amount: nobody can say it did not bill.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Iterable, Mapping

from gnode.graph import Node, NodeExecutionError

#: The events this ledger writes into the run log, and reads back on resume.
BUDGET_RESERVED = "budget_reserved"
BUDGET_SETTLED = "budget_settled"
BUDGET_REFUSED = "budget_refused"


class CeilingExceeded(NodeExecutionError):
    """A node's worst case does not fit what is left under the run's ceiling.

    Raised before dispatch, so nothing was attempted and nothing was spent.
    """

    def __init__(self, node_id: str, *, needed_usd: float, remaining_usd: float) -> None:
        super().__init__(
            f"run ceiling reached: {node_id} needs up to ${needed_usd:.4f} "
            f"and ${remaining_usd:.4f} is left",
            attempts=0,
            provider_operations=0,
            known_cost_usd=0.0,
        )
        self.needed_usd = needed_usd
        self.remaining_usd = remaining_usd


def worst_case_usd(node: Node) -> float:
    """What a provider node may bill at most: every attempt at the route's high estimate."""

    if node.is_local:
        return 0.0
    return round(node.estimated_cost_high_usd * node.max_attempts, 6)


class CeilingLedger:
    """Reserve, settle and refuse against one optional ceiling, writing each as an event.

    ``ceiling_usd=None`` keeps the accounts without refusing anything. ``emit`` receives
    each event body; the runner stamps the run-level fields around it.
    """

    def __init__(
        self,
        ceiling_usd: float | None,
        *,
        emit: Callable[[Mapping[str, object]], None],
        prior_events: Iterable[Mapping[str, object]] = (),
    ) -> None:
        if ceiling_usd is not None and (not math.isfinite(ceiling_usd) or ceiling_usd < 0):
            raise ValueError("a run ceiling must be a finite, non-negative amount")
        self.ceiling_usd = ceiling_usd
        self._emit = emit
        self._lock = asyncio.Lock()
        self._open: dict[str, float] = {}
        self._charged = 0.0
        self._replay(prior_events)

    def _replay(self, events: Iterable[Mapping[str, object]]) -> None:
        open_reservations: dict[str, float] = {}
        for event in events:
            name = event.get("event")
            node_id = event.get("node_id")
            if not isinstance(node_id, str):
                continue
            if name == BUDGET_RESERVED:
                open_reservations[node_id] = _amount(event.get("amount_usd"))
            elif name == BUDGET_SETTLED:
                open_reservations.pop(node_id, None)
                self._charged += _amount(event.get("charged_usd"))
        # An earlier invocation that died between reserve and settle may have billed
        # all of it; that is charged, not released.
        self._charged += sum(open_reservations.values())

    @property
    def charged_usd(self) -> float:
        """Settled charges plus everything an earlier invocation left unsettled."""

        return round(self._charged, 6)

    @property
    def held_usd(self) -> float:
        return round(sum(self._open.values()), 6)

    @property
    def remaining_usd(self) -> float | None:
        if self.ceiling_usd is None:
            return None
        return round(max(0.0, self.ceiling_usd - self._charged - sum(self._open.values())), 6)

    async def reserve(self, node: Node) -> None:
        """Hold ``node``'s worst case, or refuse it before anything is dispatched."""

        await self.hold(node.node_id, worst_case_usd(node))

    async def hold(self, key: str, amount: float) -> None:
        """Hold ``amount`` under ``key``, or refuse before anything is spent.

        ``key`` names what is reserved for: a node, or one paid call of a step.
        """

        if amount == 0.0:
            return
        async with self._lock:
            if key in self._open:
                raise RuntimeError(f"{key} already holds a reservation")
            remaining = self.remaining_usd
            if remaining is not None and amount > remaining + 1e-9:
                self._emit(
                    {
                        "event": BUDGET_REFUSED,
                        "node_id": key,
                        "needed_usd": amount,
                        "remaining_usd": remaining,
                        "ceiling_usd": self.ceiling_usd,
                    }
                )
                raise CeilingExceeded(key, needed_usd=amount, remaining_usd=remaining)
            self._open[key] = amount
            self._emit({"event": BUDGET_RESERVED, "node_id": key, "amount_usd": amount})

    def charge(self, key: str, cost_usd: float | None) -> None:
        """Replace ``key``'s hold with a reported cost, or keep all of it when none was."""

        held = self._open.pop(key, None)
        charged = round(cost_usd if cost_usd is not None else (held or 0.0), 6)
        if held is None and charged == 0.0:
            return
        self._charged += charged
        self._emit(
            {
                "event": BUDGET_SETTLED,
                "node_id": key,
                "charged_usd": charged,
                "reported": cost_usd is not None,
                "provider_operations": None,
            }
        )

    def settle(
        self,
        node: Node,
        *,
        provider_operations: int | None,
        known_cost_usd: float | None,
    ) -> None:
        """Replace ``node``'s hold with what it cost.

        A reported cost is charged as reported. Operations whose cost nobody reported
        keep the route's high estimate per operation, never less. When not even the
        number of operations is known (a timeout, an error that says nothing), the whole
        hold stays charged.
        """

        held = self._open.pop(node.node_id, None)
        if known_cost_usd is not None:
            charged = known_cost_usd
        elif provider_operations is not None:
            charged = node.estimated_cost_high_usd * provider_operations
        else:
            charged = held or 0.0
        if held is None and charged == 0.0:
            return
        charged = round(charged, 6)
        self._charged += charged
        self._emit(
            {
                "event": BUDGET_SETTLED,
                "node_id": node.node_id,
                "charged_usd": charged,
                "reported": known_cost_usd is not None,
                "provider_operations": provider_operations,
            }
        )

    def release(self, node: Node) -> None:
        """Drop ``node``'s hold uncharged: its result came from the cache, so nothing ran."""

        if self._open.pop(node.node_id, None) is None:
            return
        self._emit(
            {
                "event": BUDGET_SETTLED,
                "node_id": node.node_id,
                "charged_usd": 0.0,
                "reported": True,
                "provider_operations": 0,
            }
        )


def _amount(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value) if math.isfinite(value) and value >= 0 else 0.0


__all__ = [
    "BUDGET_REFUSED",
    "BUDGET_RESERVED",
    "BUDGET_SETTLED",
    "CeilingExceeded",
    "CeilingLedger",
    "worst_case_usd",
]
