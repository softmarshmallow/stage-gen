"""Write original geometric reference art and a self-contained storefront request."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw


def write_inputs(root: Path) -> None:
    """Create a new minimal package; no game files or external art are read."""
    root.mkdir(parents=True, exist_ok=True)
    members = ("references/orbit.png", "positioning.md", "storefront.toml")
    if any((root / member).exists() for member in members):
        raise ValueError("example input files already exist; choose a new output directory")
    (root / "references").mkdir(exist_ok=True)
    image = Image.new("RGB", (512, 512), (19, 31, 53))
    drawing = ImageDraw.Draw(image)
    drawing.ellipse((70, 178, 442, 334), outline=(89, 167, 165), width=18)
    drawing.ellipse((158, 158, 354, 354), fill=(246, 180, 74))
    drawing.ellipse((188, 179, 305, 290), fill=(255, 219, 129))
    reference = root / members[0]
    image.save(reference, format="PNG")
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    (root / "positioning.md").write_text(
        "# Quiet Orbit\n\nA calm visual puzzle about placing small worlds into balanced orbits. "
        "The audience enjoys readable shapes, warm focal points, and unhurried decisions. "
        "Use the original geometric reference as palette and shape evidence.\n",
        encoding="utf-8",
    )
    (root / "storefront.toml").write_text(
        f'''schema_version = 1
kind = "storefront-source-v1"
storefront_id = "quiet_orbit"
display_name = "Quiet Orbit"
revision = 1

[positioning]
source = "positioning.md"

[[references]]
reference_id = "orbit_style"
source = "references/orbit.png"
source_sha256 = "{digest}"
role = "visual_evidence_and_art_grammar_only"

[[surfaces]]
surface_id = "app_icon"
kind = "app_icon"
source = "generated"
brief = "One warm gold planet and a teal orbital ring against a deep blue field; no lettering."

[rights]
status = "unreviewed"
basis = ["Reference art is original procedural geometry authored by this example script."]
publication_authorized = false
''',
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    write_inputs(parser.parse_args().output)


if __name__ == "__main__":
    main()
