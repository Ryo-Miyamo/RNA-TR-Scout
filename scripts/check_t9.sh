#!/usr/bin/env bash
set -euo pipefail

T9_MOUNT="/media/tokushimaneuro02/T9"

if ! mountpoint -q "$T9_MOUNT"; then
  echo "ERROR: T9 is not mounted at $T9_MOUNT" >&2
  exit 1
fi

if [[ ! -w "$T9_MOUNT" ]]; then
  echo "ERROR: T9 is mounted but not writable" >&2
  exit 1
fi

echo "T9 mounted and writable: OK"
df -h "$T9_MOUNT"
