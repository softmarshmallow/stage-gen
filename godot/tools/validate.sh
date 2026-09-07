#!/usr/bin/env bash
#
# The host's gate, end to end: the headless simulation tests, then every
# picture shot, then the diff against the web-viewer references.
#
#   tools/validate.sh --run <absolute run dir> --out <directory> \
#       [--ref <reference directory>] [--dpr 1] [--shots all] [--skip-tests]
#
# Nothing here is credentialed and nothing reaches a provider: it reads a run
# directory and writes PNGs. With no --ref the shots are captured and the diff
# is skipped (there is nothing to compare against), which is how you refresh a
# reference set of your own.
#
# GODOT overrides the engine binary; the default is the macOS app bundle.
set -euo pipefail

GODOT=${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}
PROJECT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

RUN=""
OUT=""
REF=""
DPR=1
SHOTS=all
SKIP_TESTS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --run) RUN=$2; shift 2;;
    --out) OUT=$2; shift 2;;
    --ref) REF=$2; shift 2;;
    --dpr) DPR=$2; shift 2;;
    --shots) SHOTS=$2; shift 2;;
    --skip-tests) SKIP_TESTS=1; shift;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}"; exit 0;;
    *) echo "validate: unknown argument $1" >&2; exit 2;;
  esac
done

if [ -z "$RUN" ] || [ -z "$OUT" ]; then
  echo "validate: --run <run dir> and --out <directory> are both required" >&2
  exit 2
fi
if [ ! -f "$RUN/manifest.json" ]; then
  echo "validate: no manifest.json in $RUN" >&2
  exit 2
fi
if [ ! -x "$GODOT" ]; then
  echo "validate: no Godot at $GODOT (set GODOT=<path>)" >&2
  exit 2
fi

mkdir -p "$OUT"

if [ "$SKIP_TESTS" -eq 0 ]; then
  echo "== headless tests"
  # --quit-after is the hang guard the capabilities map asks for.
  "$GODOT" --headless --path "$PROJECT" -s res://tests/run_tests.gd \
      --quit-after 3000 -- --run "$RUN"

  echo "== runner parity against the browser's own golden"
  # The runner's simulation replays the browser's scripted seed and must agree
  # with it on every one of six hundred frames. It reads a serialised fixture
  # rather than $RUN, because that is the manifest the golden was captured
  # against; nothing here touches the survival run.
  RUNNER_REPLAY="$PROJECT/tests/fixtures/sideview_runner/replay"
  "$GODOT" --headless --path "$PROJECT" --quit-after 100000 \
      -s res://tools/runner_parity.gd -- \
      --script "$RUNNER_REPLAY/01-golden-600.json" --out "$OUT/runner.godot.jsonl"
  diff "$OUT/runner.godot-frames.txt" "$RUNNER_REPLAY/01-golden-600.web-frames.txt" \
    && echo "   600 of 600 frames identical"
  python3 "$PROJECT/tools/runner_parity_diff.py" \
      "$RUNNER_REPLAY/01-golden-600.web.jsonl" "$OUT/runner.godot.jsonl"

  echo "== room parity against the browser's own golden"
  # A room has no clock, so this replays clicks rather than frames.
  ROOM_REPLAY="$PROJECT/tests/fixtures/pointclick_room/replay"
  "$GODOT" --headless --path "$PROJECT" --quit-after 1000 \
      -s res://tools/room_parity.gd -- \
      --script "$ROOM_REPLAY/01-room.json" --out "$OUT/room.godot.jsonl"
  diff "$OUT/room.godot-frames.txt" "$ROOM_REPLAY/01-room.web-frames.txt" \
    && echo "   14 of 14 clicks identical"
  python3 "$PROJECT/tools/runner_parity_diff.py" \
      "$ROOM_REPLAY/01-room.web.jsonl" "$OUT/room.godot.jsonl"
fi

echo "== capture ($SHOTS, dpr $DPR)"
# A real display server is required, so a small window opens and is minimised;
# the frames come out of an offscreen SubViewport at 1600x900 * dpr.
"$GODOT" --path "$PROJECT" --rendering-driver metal --disable-render-loop \
    --audio-driver Dummy -s res://tools/capture.gd -- \
    --run "$RUN" --capture "$SHOTS" --out "$OUT" --dpr "$DPR" \
  | grep -E '^\[capture\]' || true

if [ -z "$REF" ]; then
  echo "== compare skipped (no --ref); shots are in $OUT"
  exit 0
fi

echo "== compare against $REF"
python3 "$PROJECT/tools/compare.py" "$OUT" "$REF" \
    --sheet "$OUT/compare-sheet.jpg" --json "$OUT/compare.json"
