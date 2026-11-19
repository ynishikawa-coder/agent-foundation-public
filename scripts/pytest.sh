#!/usr/bin/env bash
# 土台の試験を回す 1 つの入口（check_all・scripts/checks・CI の job はこれを呼ぶ。python3 -m pytest を直に呼ばない）。
# pytest の設定の file（pytest.ini・.pytest.ini・pyproject.toml・tox.ini・setup.cfg）と PYTEST_ADDOPTS を読まない。
# 設定の addopts（--co・-m・-k・--deselect・--ignore など）は試験を黙って減らし、何も回さないまま緑にできる。
# 試験を回す形は呼ぶ側の引数だけが決める（印の登録は tests/conftest.py）。
set -uo pipefail
cd "$(dirname "$0")/.."
exec env -u PYTEST_ADDOPTS python3 -m pytest -c /dev/null --rootdir=. --confcutdir=. "$@"
