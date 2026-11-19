#!/usr/bin/env bash
# 衝突の印が残った file を拒む（scripts/conflict_markers.py）。
set -uo pipefail
cd "$(dirname "$0")/../.."
python3 scripts/conflict_markers.py
