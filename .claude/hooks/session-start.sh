#!/bin/bash
# Prepares the container for the video-use skill: ffmpeg + Python helper deps.
# Idempotent and non-interactive; safe to re-run.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ffmpeg
fi

if ! python3 -c "import requests, numpy, matplotlib, PIL, librosa" >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install --system --quiet requests librosa matplotlib pillow numpy
  else
    python3 -m pip install --quiet requests librosa matplotlib pillow numpy
  fi
fi
