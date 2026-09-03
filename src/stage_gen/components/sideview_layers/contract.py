"""Vertical placement vocabulary shared by the map graph, producer, and runtime manifest."""

from __future__ import annotations

from typing import Literal, Protocol

from stage_gen.media import (
    LOOP_METHODS,
    SEAM_REGISTRATION_VERSION,
    LoopConstruction,
    content_bottom_offset_fraction,
    seal_offset_fraction,
    top_seal_offset_fraction,
)

LAYER_PLACEMENT_CANONICALIZER = "prepared-map-layer-placement-v1"

LayerVerticalAnchor = Literal["canvas_cover", "screen_top", "screen_bottom", "walk_surface"]

#: Anchors whose offset the producer measures rather than trusting an authored guess. They do not
#: share a registration rule: `screen_bottom` seals the frame edge and needs a row every column
#: spans, while `walk_surface` meets the ground and registers on the row the content rests on,
#: because a midground layer is legitimately sparse between its subjects.
BOTTOM_REGISTERED_ANCHORS: frozenset[str] = frozenset({"screen_bottom", "walk_surface"})

#: The top edge is measured by the mirror of the bottom seal. A canopy hung from the screen top
#: has a ragged upper edge too - vine tips reach above the bar they hang from - and registering
#: the alpha box puts that sparse fringe against the edge with sky showing through it. The seal is
#: the first row every column spans, lifted above the edge. A layer with no such row is a fringe
#: rather than a ceiling and keeps its alpha-box registration: sky through hanging vines is the
#: picture, not a gap.
TOP_REGISTERED_ANCHORS: frozenset[str] = frozenset({"screen_top"})

#: Fields that describe where or how a generated layer is consumed rather than what the image
#: model should paint. They are excluded from generation cache identity so adjusting placement or
#: runtime depth treatment never re-bills an image.
NON_GENERATIVE_LAYER_FIELDS: frozenset[str] = frozenset(
    {"vertical_anchor", "vertical_offset", "presentation", "loop_construction"}
)

#: Presentation does not alter local canonicalization or repeat admission either. It is projected
#: only into the prepared runtime manifest and applied by the consumer.
RUNTIME_ONLY_LAYER_FIELDS: frozenset[str] = frozenset({"presentation"})

#: The ground equivalent: authored geometry and vertical fit select cells and placement
#: downstream without changing the appearance request sent to the provider.
#: Ground fields that place the atlas without changing what is painted. Geometry used to live
#: here too; it is now a generated artifact the map does not carry, so the material atlas cannot
#: depend on terrain shape even by accident.
PLACEMENT_ONLY_GROUND_FIELDS: frozenset[str] = frozenset({"vertical_fit"})

#: Climbable placement moved out of the authored document entirely, so the atlas image can no
#: longer see it. Nothing needs excluding; the roster the map declares is all that reaches the
#: image call.
PLACEMENT_ONLY_CLIMBABLE_FIELDS: frozenset[str] = frozenset()

#: Deterministic geometry for the generated-bridge loop construction. The context spans are what
#: the provider sees on each side of the editable bridge; the bridge span is what it paints and
#: what the period grows by.
LOOP_BRIDGE_CONTEXT_SPAN_PX = 384
LOOP_BRIDGE_SPAN_PX = 384
#: Geometry for the repaint constructions. The window is the whole canvas the provider sees,
#: centred on the join it is repairing; the span is the editable middle of that window. The window
#: is deliberately wider than the bridge's total canvas: the repaint constructions spend their
#: budget on context rather than on painted width, because they are repairing a join rather than
#: inventing a span.
LOOP_REPAINT_WINDOW_PX = 1536
LOOP_REPAINT_SPAN_PX = 384
#: Columns over which a returned span is eased onto its exact neighbours. The endpoint does not
#: honour a mask, and registration correction shifts the span vertically, so an edited span always
#: arrives misaligned with whatever it is written next to.
LOOP_ANCHOR_BAND_PX = 24
#: Identity of the brief the provider is given for a bridge. It is versioned separately from the
#: layer's own generation brief because the two ask for different things: the layer brief composes
#: a strip, the bridge brief joins one. Sending the composing brief here is what makes the model
#: invent landmarks across the cut.
LOOP_BRIDGE_BRIEF_VERSION = "loop-bridge-brief-v2"
#: Identity of the brief for the repaint constructions. Separate from the bridge brief because the
#: request is materially different: a repaint asks for continuity through a region the provider can
#: already see both sides of, where a bridge asks it to invent one between two ends it cannot.
LOOP_REPAINT_BRIEF_VERSION = "loop-repaint-brief-v1"

#: How a generative loop brief frames the request. `join` is what ships today. `restoration` asks
#: the provider to restore a region described as mistakenly removed, which replicated better at
#: n=7 (median residual 12.73 -> 8.17, join step 1.0 -> 0.0, drift outliers eliminated). Both are
#: carried so the framing is a bound, reviewable choice rather than an untracked prompt edit;
#: selecting `restoration` is a separate decision from promoting the constructions themselves.
LoopBriefFraming = Literal["join", "restoration"]
LOOP_BRIDGE_BRIEF_FRAMING: LoopBriefFraming = "join"
LOOP_REPAINT_BRIEF_FRAMING: LoopBriefFraming = "join"


def loop_method_identity(
    construction: LoopConstruction, *, fallback: LoopConstruction | None = None
) -> dict[str, object]:
    """Cache identity for one loop construction, media facts plus this recipe's constants.

    Scoped to the selected construction on purpose. Binding every construction's identity into one
    digest, as the graph used to, means revising any single construction re-runs the loop node for
    every layer whichever construction it actually selected.
    """

    method = LOOP_METHODS[construction]
    identity: dict[str, object] = dict(method.identity())
    if not method.is_generative:
        # A deterministic construction has no provider return to register or anchor, and no
        # failure path that could reach the fallback, so binding any of that would invalidate it
        # every time an unrelated generative construction or fallback was revised.
        return identity
    if fallback is not None:
        identity["fallback"] = fallback
    identity["registration"] = SEAM_REGISTRATION_VERSION
    identity["anchor_band"] = LOOP_ANCHOR_BAND_PX
    if construction == "generated_bridge":
        identity["brief"] = LOOP_BRIDGE_BRIEF_VERSION
        identity["framing"] = LOOP_BRIDGE_BRIEF_FRAMING
        identity["context_span"] = LOOP_BRIDGE_CONTEXT_SPAN_PX
        identity["bridge_span"] = LOOP_BRIDGE_SPAN_PX
    elif construction in ("seam_repaint", "fold_repaint"):
        identity["brief"] = LOOP_REPAINT_BRIEF_VERSION
        identity["framing"] = LOOP_REPAINT_BRIEF_FRAMING
        identity["window_span"] = LOOP_REPAINT_WINDOW_PX
        identity["repaint_span"] = LOOP_REPAINT_SPAN_PX
    return identity


class PlacedLayer(Protocol):
    """The three authored facts placement resolution reads, whichever genre owns the layer."""

    @property
    def layer_id(self) -> str: ...

    @property
    def vertical_anchor(self) -> str: ...

    @property
    def vertical_offset(self) -> float | None: ...


def resolve_layer_placement(layer: PlacedLayer, trim: dict[str, object]) -> dict[str, object]:
    """Resolve one layer's vertical placement from its declared anchor and measured raster.

    The author declares intent from a closed vocabulary; the fraction is measured here, because an
    authored fraction would be a prediction about pixels that did not exist when it was written. An
    explicit override is honoured, and at a bottom-registered anchor one that cannot reach the seal
    line is rejected against the exact measured value rather than silently leaving a gap the runtime
    would fill with whatever sits behind the layer. The top edge is not the mirror of that: what a
    gap reveals there is the map's one opaque canvas_cover base, which is sky above a horizon and
    not a hole, so the top measurement is a default and not a floor. Shared by every recipe that
    places a layer, so the runner and the platformer cannot drift into two meanings of one anchor
    name.
    """

    seal: float | None = None
    if layer.vertical_anchor == "screen_bottom":
        # Sealing the frame edge is the one case that needs every column covered: a gap between
        # content shows whatever sits behind the layer, which at the screen edge is the sky plate.
        seal = seal_offset_fraction(trim)
        if seal is None:
            raise ValueError(
                f"layer {layer.layer_id} anchors to screen_bottom but no row is spanned by "
                "every column, so it can never seal"
            )
    elif layer.vertical_anchor == "walk_surface":
        # Meeting the ground is a different question. A midground layer is legitimately sparse -
        # a village has sky between its buildings - so it registers on the row its content rests
        # on rather than on a full-coverage row it may not have.
        seal = content_bottom_offset_fraction(trim)
    elif layer.vertical_anchor == "screen_top":
        # The mirror, but only as a DEFAULT. Lifting the sparse upper fringe so the first row
        # every column spans meets the edge is the right guess for a cloud band, and it is a
        # poor one for a horizon: it pushes the peaks, the clouds and the castle off the top
        # and leaves a flat plate of sky where the distance should be.
        #
        # It cannot be a floor the way the bottom seal is, because the two edges are not
        # symmetric. Every map declares exactly one opaque layer and the contract makes it
        # canvas_cover, so whatever a top-edge gap reveals is that full-bleed backdrop -- sky
        # above a mountain, which is what should be there. At the bottom edge the same gap is
        # a hole in the world. So an author who has looked at the composite may place this
        # layer lower, and only the measurement stands in when no one has.
        seal = top_seal_offset_fraction(trim)
    resolved = seal if seal is not None else 0.0
    source = "measured"
    if layer.vertical_offset is not None:
        if (
            seal is not None
            and layer.vertical_anchor in BOTTOM_REGISTERED_ANCHORS
            and layer.vertical_offset < seal
        ):
            raise ValueError(
                f"layer {layer.layer_id} declares vertical_offset "
                f"{layer.vertical_offset} but sealing requires at least {seal}"
            )
        resolved = layer.vertical_offset
        source = "authored"
    return {
        "schema_version": 1,
        "kind": LAYER_PLACEMENT_CANONICALIZER,
        "vertical_anchor": layer.vertical_anchor,
        "vertical_offset": resolved,
        "vertical_offset_source": source,
        "minimum_seal_offset": seal,
        "source_height": trim["source_height"],
        "trimmed_height": trim["trimmed_height"],
        "trimmed_top": trim["trimmed_top"],
        "trimmed_bottom": trim["trimmed_bottom"],
        "bounds": trim["bounds"],
    }
