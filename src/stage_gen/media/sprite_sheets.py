"""Deterministic native-alpha sprite instance extraction and canonical repacking."""

from __future__ import annotations

import io
from array import array
from collections import deque
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from PIL import Image, ImageChops

from gnode import inspect_image

ALPHA_COMPONENT_REPACK_VERSION = "alpha-component-repack-v3"
ALPHA_GROUND_CONTACT_VERSION = "alpha-ground-contact-v1"


@dataclass(frozen=True, slots=True)
class AlphaComponentRepackContract:
    """The intentionally simple alpha-connected-component repacking policy."""

    rows: int
    columns: int
    required_cells: int
    gutter: int = 12
    alpha_threshold: int = 16
    minimum_component_fraction: float = 0.02
    minimum_component_area: int = 32
    #: Which edge of a cell every crop is registered against. `bottom` suits an actor standing on
    #: a surface, where the feet are the stable point. `top` suits one hanging from its hands,
    #: where the grip is stable and the feet move: bottom-anchoring such a pose pins the feet and
    #: throws the head up and down instead, which reads as bouncing.
    anchor: Literal["center", "bottom", "top"] = "bottom"
    #: A strict atlas source may require one principal connected component in every authored
    #: source slot and refuse every other meaningful component. This is appropriate when a
    #: detached component could be part of the subject rather than a disposable effect.
    source_slot_policy: Literal["largest_required", "exact_required_slots"] = "largest_required"

    def __post_init__(self) -> None:
        if self.rows <= 0 or self.columns <= 0:
            raise ValueError("sprite repack rows and columns must be positive")
        if not 0 < self.required_cells <= self.rows * self.columns:
            raise ValueError("sprite repack required cells must fit the declared topology")
        if self.gutter <= 0:
            raise ValueError("sprite repack gutter must be positive")
        if not 0 <= self.alpha_threshold < 255:
            raise ValueError("sprite repack alpha threshold must be between 0 and 254")
        if not 0 < self.minimum_component_fraction <= 1:
            raise ValueError("sprite repack component fraction must be in (0, 1]")
        if self.minimum_component_area <= 0:
            raise ValueError("sprite repack minimum component area must be positive")
        if self.source_slot_policy not in {"largest_required", "exact_required_slots"}:
            raise ValueError("sprite repack source slot policy is unsupported")


def measure_alpha_ground_contact(
    data: bytes,
    *,
    alpha_threshold: int = 16,
    minimum_component_fraction: float = 0.02,
    minimum_component_area: int = 32,
) -> dict[str, object]:
    """Measure the bottom contact of meaningful native-alpha components.

    Tiny detached or low-alpha contamination does not define where an isolated object meets the
    ground. All principal components remain eligible so legitimate detached object parts can
    extend the contact lower than the largest component alone.
    """

    if not 0 <= alpha_threshold < 255:
        raise ValueError("ground contact alpha threshold must be between 0 and 254")
    if not 0 < minimum_component_fraction <= 1:
        raise ValueError("ground contact component fraction must be in (0, 1]")
    if minimum_component_area <= 0:
        raise ValueError("ground contact minimum component area must be positive")
    facts = inspect_image(data, expected_media_type="image/png")
    if not facts.has_alpha:
        raise ValueError("ground contact measurement requires an alpha-bearing PNG")
    with Image.open(io.BytesIO(data)) as opened:
        source = opened.convert("RGBA")
    components, _runs = _connected_components(
        source.getchannel("A").tobytes(),
        width=source.width,
        height=source.height,
        threshold=alpha_threshold,
    )
    visible_area = sum(component.area for component in components)
    threshold_area = max(
        minimum_component_area,
        round(visible_area * minimum_component_fraction),
    )
    principal = [component for component in components if component.area >= threshold_area]
    if not principal:
        raise ValueError("ground contact measurement found no principal alpha component")
    ground_contact_y_pixels = max(component.bbox[3] for component in principal)
    return {
        "schema_version": 1,
        "kind": ALPHA_GROUND_CONTACT_VERSION,
        "alpha_threshold": alpha_threshold,
        "minimum_component_area": threshold_area,
        "principal_component_count": len(principal),
        "ground_contact_y_pixels": ground_contact_y_pixels,
        "ground_contact_y_normalized": ground_contact_y_pixels / source.height,
        "bottom_padding_pixels": source.height - ground_contact_y_pixels,
        "source_width": source.width,
        "source_height": source.height,
    }


@dataclass(frozen=True, slots=True)
class _Run:
    y: int
    start: int
    end: int
    label: int


@dataclass(frozen=True, slots=True)
class _Component:
    root: int
    area: int
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]


@dataclass(frozen=True, slots=True)
class _FusedComponentRecovery:
    components: tuple[_Component, ...]
    runs: tuple[_Run, ...]
    source_roots: frozenset[int]
    core_alpha_threshold: int
    core_source_slots: tuple[int, ...]


@dataclass(slots=True)
class _UnionFind:
    parent: list[int]
    size: list[int]

    @classmethod
    def empty(cls) -> _UnionFind:
        return cls(parent=[], size=[])

    def add(self) -> int:
        label = len(self.parent)
        self.parent.append(label)
        self.size.append(1)
        return label

    def find(self, label: int) -> int:
        root = label
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[label] != label:
            parent = self.parent[label]
            self.parent[label] = root
            label = parent
        return root

    def union(self, left: int, right: int) -> int:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return left_root
        if self.size[left_root] < self.size[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        self.size[left_root] += self.size[right_root]
        return left_root


def repack_alpha_components(
    data: bytes, contract: AlphaComponentRepackContract
) -> tuple[bytes, dict[str, object]]:
    """Repack policy-admitted native-alpha components into canonical cells.

    The v3 processor does not infer compound-frame ownership. Its permissive default may drop
    detached effects and records that loss; ``exact_required_slots`` instead requires one
    principal component per authored source slot and refuses every unassigned meaningful
    component.
    """

    facts = inspect_image(data, expected_media_type="image/png")
    if not facts.has_alpha:
        raise ValueError("sprite component repack requires an alpha-bearing PNG")
    with Image.open(io.BytesIO(data)) as opened:
        source = opened.convert("RGBA")
    alpha = source.getchannel("A")
    alpha_bytes = alpha.tobytes()
    components, base_runs = _connected_components(
        alpha_bytes,
        width=source.width,
        height=source.height,
        threshold=contract.alpha_threshold,
    )
    visible_area = sum(component.area for component in components)
    minimum_area = max(
        contract.minimum_component_area,
        round(visible_area * contract.minimum_component_fraction),
    )
    candidates = [component for component in components if component.area >= minimum_area]
    recovery: _FusedComponentRecovery | None = None
    if len(candidates) < contract.required_cells:
        recovery = _recover_fused_components(
            alpha_bytes,
            width=source.width,
            height=source.height,
            contract=contract,
            base_runs=base_runs,
            base_candidates=candidates,
        )
        if recovery is None:
            raise ValueError(
                "sprite component repack found "
                f"{len(candidates)} principal components for "
                f"{contract.required_cells} required cells"
            )
        selected = list(recovery.components)
        selected_runs = recovery.runs
        selected_source_roots = recovery.source_roots
    else:
        if contract.source_slot_policy == "exact_required_slots":
            source_slots = tuple(
                sorted(
                    _component_source_slot(
                        component,
                        rows=contract.rows,
                        columns=contract.columns,
                        source_width=source.width,
                        source_height=source.height,
                    )
                    for component in candidates
                )
            )
            if source_slots != tuple(range(contract.required_cells)):
                raise ValueError(
                    "sprite component repack exact source-slot policy requires exactly one "
                    "principal component in every required source slot"
                )
        selected_by_area = sorted(candidates, key=lambda component: component.area, reverse=True)[
            : contract.required_cells
        ]
        selected = sorted(
            selected_by_area,
            key=lambda component: _component_order(
                component,
                rows=contract.rows,
                source_height=source.height,
            ),
        )
        selected_runs = tuple(base_runs)
        selected_source_roots = frozenset(component.root for component in selected)
    rejected = [
        component
        for component in components
        if component.root not in selected_source_roots
        and component.area >= contract.minimum_component_area
    ]
    if contract.source_slot_policy == "exact_required_slots" and rejected:
        raise ValueError(
            "sprite component repack exact source-slot policy refuses unassigned meaningful "
            "alpha components"
        )
    runs_by_root: dict[int, list[_Run]] = {}
    for run in selected_runs:
        runs_by_root.setdefault(run.label, []).append(run)
    crops = [
        _component_crop(source, runs_by_root[component.root], component) for component in selected
    ]
    cell_width = max(crop.width for crop in crops) + contract.gutter * 2
    cell_height = max(crop.height for crop in crops) + contract.gutter * 2
    output = Image.new(
        "RGBA",
        (cell_width * contract.columns, cell_height * contract.rows),
        (0, 0, 0, 0),
    )
    placements: list[dict[str, object]] = []
    for index, (component, crop) in enumerate(zip(selected, crops, strict=True)):
        row, column = divmod(index, contract.columns)
        cell_left = column * cell_width
        cell_top = row * cell_height
        x = cell_left + (cell_width - crop.width) // 2
        if contract.anchor == "bottom":
            y = cell_top + cell_height - contract.gutter - crop.height
        elif contract.anchor == "top":
            y = cell_top + contract.gutter
        else:
            y = cell_top + (cell_height - crop.height) // 2
        output.alpha_composite(crop, (x, y))
        placements.append(
            {
                "index": index,
                "row": row,
                "column": column,
                "source_bbox": list(component.bbox),
                "source_area": component.area,
                "source_centroid": [round(value, 6) for value in component.centroid],
                "target_bbox": [x, y, x + crop.width, y + crop.height],
            }
        )

    _validate_repacked_output(output, contract, cell_width=cell_width, cell_height=cell_height)
    output_data = _png_bytes(output)
    component_stats = _component_alpha_stats(alpha_bytes, source.width, base_runs)
    source_alpha_mass = sum(alpha_bytes)
    retained_alpha_mass = sum(output.getchannel("A").tobytes())
    warnings: list[str] = []
    if recovery is not None:
        warnings.append("fused_components_recovered_from_high_alpha_cores")
    if len(candidates) > contract.required_cells:
        warnings.append("principal_component_count_exceeded_required_cells")
    if rejected:
        warnings.append("unselected_alpha_components_were_dropped")
    if any(component_stats[component.root]["maximum_alpha"] >= 240 for component in rejected):
        warnings.append("opaque_unselected_components_were_dropped")
    report: dict[str, object] = {
        "schema_version": 3,
        "kind": "alpha-component-sprite-repack-v3",
        "processor_version": ALPHA_COMPONENT_REPACK_VERSION,
        "source_sha256": sha256(data).hexdigest(),
        "output_sha256": sha256(output_data).hexdigest(),
        "source_width": source.width,
        "source_height": source.height,
        "output_width": output.width,
        "output_height": output.height,
        "rows": contract.rows,
        "columns": contract.columns,
        "required_cells": contract.required_cells,
        "source_slot_policy": contract.source_slot_policy,
        "connectivity": 8,
        "alpha_predicate": f"alpha > {contract.alpha_threshold}",
        "minimum_component_fraction": contract.minimum_component_fraction,
        "minimum_component_area": minimum_area,
        "detected_component_count": len(components),
        "principal_candidate_count": len(candidates),
        "recovery_mode": (
            "high_alpha_core_partition" if recovery is not None else "base_alpha_components"
        ),
        "core_alpha_threshold": (recovery.core_alpha_threshold if recovery is not None else None),
        "core_principal_candidate_count": (
            len(recovery.components) if recovery is not None else None
        ),
        "core_source_slots": recovery.core_source_slots if recovery is not None else None,
        "selected_component_count": len(selected),
        "rejected_component_count": len(rejected),
        "selection_policy": (
            "high_alpha_cores_then_base_support_partition"
            if recovery is not None
            else "largest_required_components_after_threshold"
        ),
        "partition_policy": (
            "deterministic_multi_source_8_neighbor_geodesic_nearest_core"
            if recovery is not None
            else None
        ),
        "ordering": "source_row_then_centroid_x",
        "anchor": contract.anchor,
        "gutter_pixels": contract.gutter,
        "source_alpha_mass": source_alpha_mass,
        "retained_alpha_mass": retained_alpha_mass,
        "retained_alpha_fraction": round(retained_alpha_mass / source_alpha_mass, 9),
        "placements": placements,
        "rejected_components": [
            {
                "area": component.area,
                "bbox": list(component.bbox),
                "centroid": [round(value, 6) for value in component.centroid],
                **component_stats[component.root],
            }
            for component in rejected
        ],
        "warnings": warnings,
        "known_caveat": (
            "Detached effects and small fragments are not assigned to a principal frame and may "
            "be dropped. Fused base-threshold frames recover only when exactly the required "
            "number of higher-alpha principal cores occupy the expected source lattice slots "
            "and cover every base principal component; otherwise repacking fails."
        ),
        "boundaries_isolated": True,
    }
    return output_data, report


def _recover_fused_components(
    alpha: bytes,
    *,
    width: int,
    height: int,
    contract: AlphaComponentRepackContract,
    base_runs: list[_Run],
    base_candidates: list[_Component],
) -> _FusedComponentRecovery | None:
    """Split low-alpha-fused support only when higher-alpha cores prove the frame count.

    The ordinary base-threshold path is intentionally untouched. This fallback raises the alpha
    threshold one value at a time until exactly the requested number of meaningful cores exists.
    Those cores seed a deterministic multi-source flood over the original base-threshold support,
    so antialiasing and other meaningful low-alpha pixels stay with one frame instead of being
    discarded with the bridge.
    """

    if not base_candidates:
        return None
    for core_threshold in range(contract.alpha_threshold + 1, 255):
        core_components, core_runs = _connected_components(
            alpha,
            width=width,
            height=height,
            threshold=core_threshold,
        )
        core_visible_area = sum(component.area for component in core_components)
        core_minimum_area = max(
            contract.minimum_component_area,
            round(core_visible_area * contract.minimum_component_fraction),
        )
        core_candidates = [
            component for component in core_components if component.area >= core_minimum_area
        ]
        if len(core_candidates) != contract.required_cells:
            continue
        ordered_cores = sorted(
            core_candidates,
            key=lambda component: _component_order(
                component,
                rows=contract.rows,
                source_height=height,
            ),
        )
        core_source_slots = tuple(
            _component_source_slot(
                component,
                rows=contract.rows,
                columns=contract.columns,
                source_width=width,
                source_height=height,
            )
            for component in ordered_cores
        )
        if core_source_slots != tuple(range(contract.required_cells)):
            # Frame count alone is not identity. Four opaque fragments clustered
            # inside one atlas cell cannot stand in for four authored poses even
            # when low-alpha support extends across every cell.
            continue
        partition = _partition_support_from_cores(
            width=width,
            height=height,
            base_runs=base_runs,
            base_candidates=base_candidates,
            core_runs=core_runs,
            ordered_cores=ordered_cores,
        )
        if partition is None:
            continue
        recovered_components, recovered_runs, source_roots = partition
        return _FusedComponentRecovery(
            components=recovered_components,
            runs=recovered_runs,
            source_roots=source_roots,
            core_alpha_threshold=core_threshold,
            core_source_slots=core_source_slots,
        )
    return None


def _partition_support_from_cores(
    *,
    width: int,
    height: int,
    base_runs: list[_Run],
    base_candidates: list[_Component],
    core_runs: list[_Run],
    ordered_cores: list[_Component],
) -> tuple[tuple[_Component, ...], tuple[_Run, ...], frozenset[int]] | None:
    pixel_count = width * height
    base_root_by_pixel = array("i", [-1]) * pixel_count
    for run in base_runs:
        offset = run.y * width
        for index in range(offset + run.start, offset + run.end + 1):
            base_root_by_pixel[index] = run.label

    core_runs_by_root: dict[int, list[_Run]] = {}
    for run in core_runs:
        core_runs_by_root.setdefault(run.label, []).append(run)

    candidate_roots = frozenset(component.root for component in base_candidates)
    core_source_roots: set[int] = set()
    owners = array("i", [-1]) * pixel_count
    frontier: deque[int] = deque()
    for owner, core in enumerate(ordered_cores):
        mapped_roots: set[int] = set()
        for run in core_runs_by_root[core.root]:
            offset = run.y * width
            for index in range(offset + run.start, offset + run.end + 1):
                mapped_roots.add(base_root_by_pixel[index])
                owners[index] = owner
                frontier.append(index)
        if len(mapped_roots) != 1 or -1 in mapped_roots:
            return None
        core_source_roots.update(mapped_roots)

    # Every principal component observed at the base threshold must own at least one stronger
    # core. Otherwise the higher threshold has replaced a legitimate faint frame with a fragment
    # from another frame, which is not evidence for safe recovery.
    if core_source_roots != candidate_roots:
        return None

    while frontier:
        index = frontier.popleft()
        owner = owners[index]
        y, x = divmod(index, width)
        for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
            row_offset = neighbor_y * width
            for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                neighbor = row_offset + neighbor_x
                if neighbor == index:
                    continue
                if base_root_by_pixel[neighbor] < 0 or owners[neighbor] >= 0:
                    continue
                owners[neighbor] = owner
                frontier.append(neighbor)

    partition_runs: list[_Run] = []
    for y in range(height):
        offset = y * width
        x = 0
        while x < width:
            owner = owners[offset + x]
            if owner < 0:
                x += 1
                continue
            start = x
            while x + 1 < width and owners[offset + x + 1] == owner:
                x += 1
            partition_runs.append(_Run(y=y, start=start, end=x, label=owner))
            x += 1

    recovered_by_owner = {
        component.root: component for component in _components_from_partition_runs(partition_runs)
    }
    if set(recovered_by_owner) != set(range(len(ordered_cores))):
        return None
    recovered = tuple(recovered_by_owner[index] for index in range(len(ordered_cores)))
    return recovered, tuple(partition_runs), frozenset(core_source_roots)


def _components_from_partition_runs(runs: list[_Run]) -> list[_Component]:
    stats: dict[int, list[float]] = {}
    for run in runs:
        run_width = run.end - run.start + 1
        record = stats.setdefault(
            run.label,
            [
                0.0,
                float(run.start),
                float(run.y),
                float(run.end + 1),
                float(run.y + 1),
                0.0,
                0.0,
            ],
        )
        record[0] += run_width
        record[1] = min(record[1], run.start)
        record[2] = min(record[2], run.y)
        record[3] = max(record[3], run.end + 1)
        record[4] = max(record[4], run.y + 1)
        record[5] += (run.start + run.end) * run_width / 2
        record[6] += run.y * run_width
    return [
        _Component(
            root=root,
            area=int(record[0]),
            bbox=(int(record[1]), int(record[2]), int(record[3]), int(record[4])),
            centroid=(record[5] / record[0], record[6] / record[0]),
        )
        for root, record in stats.items()
    ]


def _row_runs(alpha: bytes, *, offset: int, width: int, threshold: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    x = 0
    while x < width:
        while x < width and alpha[offset + x] <= threshold:
            x += 1
        if x == width:
            break
        start = x
        while x + 1 < width and alpha[offset + x + 1] > threshold:
            x += 1
        runs.append((start, x))
        x += 1
    return runs


def _connected_components(
    alpha: bytes, *, width: int, height: int, threshold: int
) -> tuple[list[_Component], list[_Run]]:
    union_find = _UnionFind.empty()
    all_runs: list[_Run] = []
    previous: list[_Run] = []
    for y in range(height):
        current: list[_Run] = []
        previous_index = 0
        for start, end in _row_runs(alpha, offset=y * width, width=width, threshold=threshold):
            while previous_index < len(previous) and previous[previous_index].end < start - 1:
                previous_index += 1
            overlap_index = previous_index
            overlapping: list[int] = []
            while overlap_index < len(previous) and previous[overlap_index].start <= end + 1:
                overlapping.append(previous[overlap_index].label)
                overlap_index += 1
            if overlapping:
                label = overlapping[0]
                for other in overlapping[1:]:
                    label = union_find.union(label, other)
            else:
                label = union_find.add()
            run = _Run(y=y, start=start, end=end, label=label)
            current.append(run)
            all_runs.append(run)
        previous = current

    stats: dict[int, list[float]] = {}
    rooted_runs: list[_Run] = []
    for run in all_runs:
        root = union_find.find(run.label)
        rooted_runs.append(_Run(y=run.y, start=run.start, end=run.end, label=root))
        run_width = run.end - run.start + 1
        record = stats.setdefault(
            root,
            [
                0.0,
                float(run.start),
                float(run.y),
                float(run.end + 1),
                float(run.y + 1),
                0.0,
                0.0,
            ],
        )
        record[0] += run_width
        record[1] = min(record[1], run.start)
        record[2] = min(record[2], run.y)
        record[3] = max(record[3], run.end + 1)
        record[4] = max(record[4], run.y + 1)
        record[5] += (run.start + run.end) * run_width / 2
        record[6] += run.y * run_width
    components = [
        _Component(
            root=root,
            area=int(record[0]),
            bbox=(int(record[1]), int(record[2]), int(record[3]), int(record[4])),
            centroid=(record[5] / record[0], record[6] / record[0]),
        )
        for root, record in stats.items()
    ]
    return components, rooted_runs


def _component_order(component: _Component, *, rows: int, source_height: int) -> tuple[int, float]:
    if rows == 1:
        return 0, component.centroid[0]
    row = min(rows - 1, int(component.centroid[1] / (source_height / rows)))
    return row, component.centroid[0]


def _component_source_slot(
    component: _Component,
    *,
    rows: int,
    columns: int,
    source_width: int,
    source_height: int,
) -> int:
    row = min(rows - 1, int(component.centroid[1] / (source_height / rows)))
    column = min(columns - 1, int(component.centroid[0] / (source_width / columns)))
    return row * columns + column


def _component_crop(source: Image.Image, runs: list[_Run], component: _Component) -> Image.Image:
    left, top, _right, _bottom = component.bbox
    subject = source.crop(component.bbox)
    mask_data = bytearray(subject.width * subject.height)
    for run in runs:
        row_offset = (run.y - top) * subject.width
        start = row_offset + run.start - left
        end = row_offset + run.end - left + 1
        mask_data[start:end] = b"\xff" * (end - start)
    mask = Image.frombytes("L", subject.size, bytes(mask_data))
    subject.putalpha(ImageChops.multiply(subject.getchannel("A"), mask))
    return subject


def _component_alpha_stats(alpha: bytes, width: int, runs: list[_Run]) -> dict[int, dict[str, int]]:
    stats: dict[int, dict[str, int]] = {}
    for run in runs:
        values = alpha[run.y * width + run.start : run.y * width + run.end + 1]
        record = stats.setdefault(run.label, {"alpha_mass": 0, "maximum_alpha": 0})
        record["alpha_mass"] += sum(values)
        record["maximum_alpha"] = max(record["maximum_alpha"], max(values))
    return stats


def _validate_repacked_output(
    output: Image.Image,
    contract: AlphaComponentRepackContract,
    *,
    cell_width: int,
    cell_height: int,
) -> None:
    alpha = output.getchannel("A")
    for index in range(contract.required_cells):
        row, column = divmod(index, contract.columns)
        cell = alpha.crop(
            (
                column * cell_width,
                row * cell_height,
                (column + 1) * cell_width,
                (row + 1) * cell_height,
            )
        )
        if cell.getbbox() is None:
            raise ValueError(f"repacked sprite cell {index} is empty")
        boundary = cell.copy()
        boundary.paste(
            0,
            (
                contract.gutter,
                contract.gutter,
                cell_width - contract.gutter,
                cell_height - contract.gutter,
            ),
        )
        if boundary.getbbox() is not None:
            raise ValueError(f"repacked sprite cell {index} touches its boundary")


def _png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def split_atlas_columns(data: bytes, columns: int, rows: int = 1) -> tuple[bytes, ...]:
    """Split one animation atlas into its cells, left to right and top to bottom.

    Cells are returned as encoded PNGs rather than decoded images so a caller can bind each one
    by digest to whatever it composites them into.
    """

    if columns <= 0 or rows <= 0:
        raise ValueError("an atlas grid needs a positive column and row count")
    source = _decode_atlas(data)
    if source.width % columns or source.height % rows:
        raise ValueError(
            f"atlas {source.width}x{source.height} does not divide into {columns}x{rows} cells"
        )
    cell_width = source.width // columns
    cell_height = source.height // rows
    cells: list[bytes] = []
    for row in range(rows):
        for column in range(columns):
            box = (
                column * cell_width,
                row * cell_height,
                (column + 1) * cell_width,
                (row + 1) * cell_height,
            )
            cells.append(_png_bytes(source.crop(box)))
    return tuple(cells)


def _decode_atlas(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as opened:
        return opened.convert("RGBA")


def measure_alpha_subjects(
    data: bytes,
    *,
    alpha_threshold: int = 16,
    minimum_component_fraction: float = 0.02,
    minimum_component_area: int = 32,
) -> dict[str, object]:
    """Count the meaningful native-alpha subjects in one image, and describe the largest.

    "Meaningful" is the same two-part filter the ground-contact measurement uses: a component
    counts when it is both large in absolute terms and a real share of the painted pixels, so a
    stray antialiased speck or a faint halo is not a second subject.

    The question this answers is one nothing else in the pipeline asks. Every isolation check so
    far has been about the *canvas* - is there alpha, is the border clean, is the subject large
    enough - and all of them pass an image holding one object plus a detached spark, speed line, or
    painted trail. For most families that is a cosmetic flaw. For an object the runtime rotates and
    scales as a unit it is not: a second blob moves the measured bounding box, so the object draws
    at the wrong size and pivots around a point that is not inside it.
    """

    if not 0 <= alpha_threshold < 255:
        raise ValueError("subject alpha threshold must be between 0 and 254")
    if not 0 < minimum_component_fraction <= 1:
        raise ValueError("subject component fraction must be in (0, 1]")
    if minimum_component_area <= 0:
        raise ValueError("subject minimum component area must be positive")

    image = _decode_atlas(data)
    width, height = image.size
    alpha = image.getchannel("A").tobytes()
    components, _ = _connected_components(
        alpha, width=width, height=height, threshold=alpha_threshold
    )
    painted = sum(component.area for component in components)
    if painted <= 0:
        raise ValueError("image has no painted pixels above the alpha threshold")
    principal = [
        component
        for component in components
        if component.area >= minimum_component_area
        and component.area / painted >= minimum_component_fraction
    ]
    if not principal:
        # Reachable: an image whose paint is spread across many specks, none of which clears both
        # thresholds. The sibling guards above all name what was wrong, and a bare
        # "max() arg is an empty sequence" from here would be the one failure a reader could not
        # act on.
        raise ValueError(
            "image has no component large enough to be a subject at the declared thresholds"
        )
    largest = max(principal, key=lambda component: component.area)
    left, top, right, bottom = largest.bbox
    return {
        "width": width,
        "height": height,
        "subject_count": len(principal),
        "painted_pixels": painted,
        "largest_area": largest.area,
        "largest_bbox": [left, top, right, bottom],
        "largest_width": right - left,
        "largest_height": bottom - top,
        "largest_share": round(largest.area / painted, 6),
    }
