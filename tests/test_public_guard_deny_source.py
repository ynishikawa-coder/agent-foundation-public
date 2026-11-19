"""公開の検査の顧客の語は、持ち主ごとに 1 か所の正本を読むだけの鍵で直に読む（写しへ黙って落ちない）。"""
from __future__ import annotations

import json
import pytest

from test_public_guard import (  # noqa: F401
    CI_TEXT,
    OWNER,
    ROOT,
    TEMPLATE_TEXT,
    _bundle_of,
    _commit,
    _main,
    _repo,
    _source,
    guard,
)


def test_正本の鍵があれば正本の束で照らし_古い写しは使わない(tmp_path, monkeypatch, capsys):
    """写しの secret に語が足されていなくても、正本に足した語で赤になる（注入の試験＝古い写しを置く）。"""
    repo = _repo(tmp_path)
    _commit(repo, {"a.md": "新しい顧客の新規商事へ行く\n"})
    seen = _source(monkeypatch, "# 正本\n" + _bundle_of(["見本商事", "新規商事"]) + "\n")
    monkeypatch.setenv("AF_DENY_SOURCE_TOKEN", "t")
    monkeypatch.setenv("AF_DENY_BUNDLE", _bundle_of(["見本商事"]))  # 古い写し
    code, out = _main(repo, capsys, "--owner", OWNER)
    assert code == 1 and "顧客の語" in out, out
    assert "新規商事" not in out
    assert seen[0][0]["repo"] and seen[0][1] == "t"


def test_正本の鍵があれば写しが無くてもCIで照らせる(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    _source(monkeypatch, _bundle_of(["見本商事"]))
    for k, v in {"AF_DENY_SOURCE_TOKEN": "t", "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY_OWNER": OWNER}.items():
        monkeypatch.setenv(k, v)
    code, out = _main(repo, capsys)
    assert code == 0 and "正本の置き場から直に読んだ" in out, out
    assert "写し" not in out.split("正本")[0]


def test_正本が読めなければ黙って通さず赤(tmp_path, monkeypatch, capsys):
    """鍵が切れた・置き場が無い時に写しへ落ちて緑にしない（注入の試験）。"""
    _source(monkeypatch, error=guard.SourceError("顧客の語の正本を読めない: HTTP 404"))
    monkeypatch.setenv("AF_DENY_SOURCE_TOKEN", "t")
    monkeypatch.setenv("AF_DENY_BUNDLE", _bundle_of(["見本商事"]))
    code, out = _main(_repo(tmp_path), capsys, "--owner", OWNER)
    assert code == 1 and "正本を読めない" in out, out


def test_正本の読み口は_HTTP_の誤りを名指しの誤りにする(monkeypatch):
    import urllib.error

    def boom(req, timeout):
        assert req.full_url.startswith(guard.API + "/repos/") and req.get_header("Authorization") == "Bearer t"
        raise urllib.error.HTTPError(req.full_url, 401, "x", {}, None)

    monkeypatch.setattr(guard.urllib.request, "urlopen", boom)
    with pytest.raises(guard.SourceError, match="HTTP 401"):
        guard.fetch_source_text({"repo": "o/s", "path": "b.txt", "ref": "main"}, "t")


def test_置き場の決まりの無い持ち主は止める(tmp_path, monkeypatch, capsys):
    _source(monkeypatch, _bundle_of(["見本商事"]))
    monkeypatch.setenv("AF_DENY_SOURCE_TOKEN", "t")
    code, out = _main(_repo(tmp_path), capsys, "--owner", "知らない持ち主")
    assert code == 2 and "deny-source.json に無い" in out, out


@pytest.mark.parametrize("text", ["", "pct1.壊れた.値", _bundle_of(["a"]) + "\n" + _bundle_of(["b"])])
def test_正本の中身が束の1行でなければ止める(tmp_path, monkeypatch, capsys, text):
    _source(monkeypatch, text)
    monkeypatch.setenv("AF_DENY_SOURCE_TOKEN", "t")
    code, out = _main(_repo(tmp_path), capsys, "--owner", OWNER)
    assert code == 2, out


def test_置き場の表に知らない鍵があれば止める(tmp_path, monkeypatch):
    table = tmp_path / "s.json"
    table.write_text(json.dumps({"owners": {"o": {"repo": "o/s", "path": "b", "branch": "x"}}}), encoding="utf-8")
    monkeypatch.setattr(guard, "SOURCES", table)
    with pytest.raises(guard.SourceError, match="知らない鍵"):
        guard.source_of("o")


def test_置き場の表は持ち主ごとに_repo_と_path_を持つ():
    table = json.loads((ROOT / "public-guard" / "deny-source.json").read_text(encoding="utf-8"))
    assert table["owners"], "置き場が 1 つも無い"
    for owner, entry in table["owners"].items():
        assert guard.source_of(owner)["repo"].startswith(owner + "/")


def test_CIで写しだけで照らした時は名指しで知らせる(tmp_path, monkeypatch, capsys):
    """2 段の 1 段目: 写しでも止めないが、写しである事を Actions の注記と要約に出す。"""
    summary = tmp_path / "summary.md"
    for k, v in {"GITHUB_ACTIONS": "true", "AF_DENY_BUNDLE": _bundle_of(["見本商事"]),
                 "GITHUB_STEP_SUMMARY": str(summary)}.items():
        monkeypatch.setenv(k, v)
    code, out = _main(_repo(tmp_path), capsys)
    assert code == 0, out
    assert "::warning title=顧客の語が写し::" in out and "AF_DENY_SOURCE_TOKEN" in out
    assert "写し" in summary.read_text(encoding="utf-8")


def test_action_と雛形と土台の_ci_は正本の鍵を渡す():
    action = (ROOT / "public-guard" / "action.yml").read_text(encoding="utf-8")
    assert "deny-source-token:" in action and "AF_DENY_SOURCE_TOKEN: ${{ inputs.deny-source-token }}" in action
    line = "deny-source-token: ${{ secrets.AF_DENY_SOURCE_TOKEN }}"
    assert line in TEMPLATE_TEXT and line in CI_TEXT


def test_正本を読めた時は壊れた写しの_secret_が残っていても止めない(tmp_path, monkeypatch, capsys):
    _source(monkeypatch, _bundle_of(["見本商事"]))
    monkeypatch.setenv("AF_DENY_SOURCE_TOKEN", "t")
    monkeypatch.setenv("AF_DENY_BUNDLE", "pct1.壊れた.値")
    code, out = _main(_repo(tmp_path), capsys, "--owner", OWNER)
    assert code == 0, out


def test_CIでは正本から読んだ束を_log_で伏せる(tmp_path, monkeypatch, capsys):
    good = _bundle_of(["見本商事"])
    _source(monkeypatch, good)
    for k, v in {"AF_DENY_SOURCE_TOKEN": "t", "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY_OWNER": OWNER}.items():
        monkeypatch.setenv(k, v)
    code, out = _main(_repo(tmp_path), capsys)
    assert code == 0 and f"::add-mask::{good}" in out, out


def test_正本の読み口は_repo_と_path_を_URL_の中で崩さない(monkeypatch):
    seen = []

    def grab(req, timeout):
        seen.append(req.full_url)
        raise guard.urllib.error.URLError("x")

    monkeypatch.setattr(guard.urllib.request, "urlopen", grab)
    with pytest.raises(guard.SourceError):
        guard.fetch_source_text({"repo": "o/s", "path": "a b/c?.txt", "ref": "main&x=1"}, "t")
    assert seen[0].endswith("/repos/o/s/contents/a%20b/c%3F.txt?ref=main%26x%3D1")

