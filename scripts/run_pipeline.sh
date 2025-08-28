#!/usr/bin/env bash
set -euo pipefail

INPUT=${1:-/data/scan.e57}
OUTPUT=${2:-/output}
TARGET_FACES=${3:-500000}
TEXTURE_SIZE=${4:-4096}

python -m lidar_web_pipeline.cli \
  --input "$INPUT" \
  --output "$OUTPUT" \
  --target-faces "$TARGET_FACES" \
  --texture-size "$TEXTURE_SIZE"