"""Private collection adapter for the dialogue-scene review.

The scene itself builds with gnode from its game folder (``pipeline/workflow.py:scene``);
what is left here is the local, digest-bound review of a delivered bundle.
"""

from __future__ import annotations

import argparse
import json
from typing import TextIO

from stage_gen.config import StageGenConfig
from the_grain_pipeline.dialogue_scene.review import transition_dialogue_review


async def _dispatch_dialogue_scene(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    stdout: TextIO,
) -> int:
    del config
    review_result = await transition_dialogue_review(
        {
            "bundle_path": args.bundle_path,
            "review_path": args.review_path,
            "acceptance_spec_path": args.acceptance_spec_path,
            "usage": args.usage,
        }
    )
    stdout.write(f"{json.dumps(review_result, separators=(',', ':'))}\n")
    return 0
