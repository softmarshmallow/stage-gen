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
