"""見回りは公開の repo の呼び口を雛形と一字ずつ比べ、ずれを外れにする。"""
from __future__ import annotations

import pytest

from test_public_guard import (  # noqa: F401
    CALLER,
    CI_TEXT,
    FakeGitHub,
    _routes,
    guard,
    patrol,
)


@pytest.mark.parametrize("label, old, new", [
    ("on の edited が落ちた", "types: [opened, edited, synchronize, reopened]", "types: [opened, synchronize, reopened]"),
    ("permissions が広い", "contents: read", "contents: write"),
    ("with の入力名がずれた", "deny-source-token:", "deny-token:"),
    ("正本の鍵を渡していない（古い雛形の写し）", "          deny-source-token: ${{ secrets.AF_DENY_SOURCE_TOKEN }}\n", ""),
    ("job の名が違う", "    name: public-guard", "    name: guard"),
    ("行が足された", "    runs-on: ubuntu-latest", "    runs-on: ubuntu-latest\n    continue-on-error: true"),
])
def test_見回り_呼び口が雛形と違えば外れ(label, old, new):
    """写した呼び口の on・permissions・with がずれたら、@main でも外れ（注入の試験）。"""
    assert old in CALLER, label
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER.replace(old, new), rules=["public-guard"])), ["o"])
    assert any("雛形と違う" in p for p in found["o/x"]), label


def test_見回り_呼び口の注釈と行末の空白は比べない():
    text = "# 自分の注釈\n" + CALLER.replace("name: public-guard\n", "name: public-guard   \n", 1).replace("\n", "\r\n")
    assert patrol.patrol(FakeGitHub(_routes("o/x", text, rules=["public-guard"])), ["o"]) == {}


def test_見回り_呼び口が決まった名のfileに無ければ外れ():
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER, rules=["public-guard"], name="guard.yml")), ["o"])
    assert any("呼び口 .github/workflows/public-guard.yml が無い" in p for p in found["o/x"])


def test_見回り_ほかの_workflow_で版の印で呼んでも外れ():
    extra = {"other.yml": "      - uses: ynishikawa-coder/agent-foundation-public/public-guard@v0.4.2\n"}
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER, rules=["public-guard"], extra=extra)), ["o"])
    assert any("@v0.4.2" in p for p in found["o/x"])


@pytest.mark.parametrize("old, new", [
    ("types: [opened, edited, synchronize, reopened]", "types: [opened, synchronize, reopened]"),
    ("          deny-source-token: ${{ secrets.AF_DENY_SOURCE_TOKEN }}\n", ""),
    ("  contents: read\n", "  contents: write\n"),
])
def test_見回り_土台の_ci_が雛形とずれたら外れ(old, new):
    """土台そのものの呼び口（ci.yml）も、雛形の on・permissions・with を外れたら外れ（注入の試験）。"""
    full = patrol.FOUNDATION
    assert old in CI_TEXT
    found = patrol.patrol(FakeGitHub(_routes(full, CI_TEXT.replace(old, new), rules=["public-guard", "plugin-smoke"],
                                             name="ci.yml")), [full.split("/")[0]])
    assert found.get(full), "外れにならない"


def test_見回り_土台の_ci_の_with_は_public_guard_の_step_の中で見る():
    """雛形の with の行が別の job にあるだけでは足りない（注入の試験）。"""
    full = patrol.FOUNDATION
    line = "          deny-source-token: ${{ secrets.AF_DENY_SOURCE_TOKEN }}\n"
    moved = CI_TEXT.replace(line, "") + "\n  other:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: x/y@v1\n        with:\n" + line
    found = patrol.patrol(FakeGitHub(_routes(full, moved, rules=["public-guard", "plugin-smoke"], name="ci.yml")),
                          [full.split("/")[0]])
    assert any("deny-source-token" in p for p in found.get(full, [])), found

