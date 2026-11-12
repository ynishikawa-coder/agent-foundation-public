"""決まりの文書・PR の型・版の記録が、決まった形で置かれているかを見る。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_骨の物が全部ある():
    for rel in [
        "README.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "docs/版の出し方.md",
        "docs/版の印.md",
        ".github/workflows/tag.yml",
        "plugins/README.md",
        ".github/pull_request_template.md",
        ".github/workflows/ci.yml",
        "scripts/check_all.sh",
    ]:
        assert (ROOT / rel).is_file(), f"無い: {rel}"


def test_PR_の型の冒頭_5_行():
    lines = [l for l in read(".github/pull_request_template.md").splitlines() if l.strip()]
    heads = [l.split(":")[0] for l in lines[:5]]
    assert heads == ["親窓", "書いた窓", "job", "触る path", "検査"], heads
    body = read(".github/pull_request_template.md")
    for sec in ["何をどう変えたか", "畳んだ古い物", "検証", "他の窓へ回す"]:
        assert f"## {sec}" in body, f"PR の型に節が無い: {sec}"


def test_CHANGELOG_の形():
    text = read("CHANGELOG.md")
    heads = re.findall(r"^## (.+)$", text, flags=re.M)
    assert heads and heads[0] == "[Unreleased]", "先頭の節は ## [Unreleased]"
    versions = []
    for h in heads[1:]:
        m = re.fullmatch(r"\[v(\d+)\.(\d+)\.(\d+)\] - \d{4}-\d{2}-\d{2}", h)
        assert m, f"版の見出しの形が違う: {h}"
        versions.append(tuple(map(int, m.groups())))
    assert versions == sorted(versions, reverse=True), "版は新しい順に並べる"
    assert len(versions) == len(set(versions)), "同じ版が 2 つある"


def test_CI_の入口は_check_all_の_1_本():
    ci = read(".github/workflows/ci.yml")
    assert "bash scripts/check_all.sh" in ci
    assert re.search(r"^\s*pull_request:", ci, flags=re.M)
    assert re.search(r"branches:\s*\[\s*main\s*\]", ci)
