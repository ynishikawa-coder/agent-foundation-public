#!/usr/bin/env bash
# 公開される外側（commit の説明・名義と PR の題・本文）に置かない物が無いかを照らす（本体は scripts/hygiene.py）。
set -euo pipefail
cd "$(dirname "$0")/../.."
exec python3 scripts/hygiene.py meta
