#!/usr/bin/env python3
"""Prepare this game's assets from its own inputs. Planning is offline by default."""

from pathlib import Path

from iron_petal_unit_pipeline.prepare import main

if __name__ == "__main__":
    raise SystemExit(main(Path(__file__).resolve().parents[1] / "inputs"))
