"""本物の claude の命令を要る試験の印と、無い所での扱いの 1 か所。

本物の claude を要る試験は module に `pytestmark = pytest.mark.real_claude` を付けるだけにする（file ごとに飛ばす条件を書かない）。
- CI の job `plugin-smoke` は `bash scripts/pytest.sh -m real_claude tests/` でこの印の試験を全部拾って回す（file を手で並べない）。
- claude の命令が無い所（手元・job `check`）では印の試験だけを飛ばす。AF_REQUIRE_CLAUDE=1 の時は飛ばさず赤にする。
- 印の無い試験が claude を要ると、claude の無い job `check` で赤になる（黙って飛ばされる道が無い）。
"""
import os
import shutil

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "real_claude: 本物の claude の命令を要る（CI の job plugin-smoke が -m real_claude で回す）")


def pytest_runtest_setup(item):
    if item.get_closest_marker("real_claude") is None or shutil.which("claude"):
        return
    if os.environ.get("AF_REQUIRE_CLAUDE") == "1":
        pytest.fail("claude の命令が無い（CI の job plugin-smoke では入れてから回す）", pytrace=False)
    pytest.skip("claude の命令が無い所では飛ばす（CI の job plugin-smoke が -m real_claude で回す）")
