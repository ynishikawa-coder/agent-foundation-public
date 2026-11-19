#!/usr/bin/env bash
# 土台の試験を回す 1 つの入口（check_all・scripts/checks・CI の job はこれを呼ぶ。python3 -m pytest を直に呼ばない）。
# pytest の設定の file（pytest.ini・.pytest.ini・pyproject.toml・tox.ini・setup.cfg）と PYTEST_ADDOPTS を読まない。
# 設定の addopts（--co・-m・-k・--deselect・--ignore など）は試験を黙って減らし、何も回さないまま緑にできる。
# 同じ道で試験を絞れる物も読まない: repo 根など tests/ の外の conftest.py（--confcutdir=tests）・
# 環境変数 PYTEST_PLUGINS・入れてある plugin の自動の読み込み（PYTEST_DISABLE_PLUGIN_AUTOLOAD）。
# 環境の側（PYTHONPATH・.pth・sitecustomize・cwd の pytest.py）も読まない＝python3 -I -S で scripts/pytest_plugin/af_run.py を起こす。
# 読まれた plugin・conftest の hook・集めた試験は af_tally が照らす（知らない plugin・結果を変える hook・集めていない試験は赤）。
# 試験を回す形は呼ぶ側の引数だけが決める（印の登録は tests/conftest.py）。
# 結果は scripts/pytest_plugin/af_tally.py が構造で残す（AF_PYTEST_TALLY=<file> の時。check_all は文を読まずにこれを数える）。
set -uo pipefail
cd "$(dirname "$0")/.."
exec env -u PYTEST_ADDOPTS -u PYTEST_PLUGINS PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -I -S scripts/pytest_plugin/af_run.py -c /dev/null --rootdir=. --confcutdir=tests -p af_tally "$@"
