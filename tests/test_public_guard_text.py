"""PR の題・本文・コメントを出す前に、公開の検査と同じ照らしを当てる（guard.py --text）。"""
from __future__ import annotations

import pytest
import sys

from test_public_guard import (  # noqa: F401
    _bundle_of,
    _repo,
    guard,
)


@pytest.mark.parametrize("text, extra", [
    ("この PR は見本業務の件\n", {}),                       # repo の置かない語
    ("連絡は someone" + "@" + "gmail.com へ\n", {}),       # 個人の情報の形（字は組み立てる＝この file が検査に当たらない）
    ("新規商事の件\n", {"AF_DENY_BUNDLE": None}),          # 顧客の語（束）
])
def test_出す前の文を照らして置かない物があれば赤(tmp_path, monkeypatch, capsys, text, extra):
    """公開の repo へ PR の本文を出す前に、窓の手で同じ照らしを当てられる（注入の試験＝置かない語を入れた本文）。"""
    repo = _repo(tmp_path)
    (repo / "deny.txt").write_text("見本業務\n", encoding="utf-8")
    if "AF_DENY_BUNDLE" in extra:
        monkeypatch.setenv("AF_DENY_BUNDLE", _bundle_of(["新規商事"]))
    body = tmp_path / "body.md"
    body.write_text(text, encoding="utf-8")
    code = guard.main(["--repo", str(repo), "--deny-words-file", "deny.txt", "--text", str(body)])
    out = capsys.readouterr().out
    assert code == 1 and "出す前の文" in out, out
    assert "新規商事" not in out and "見本業務" not in out


def test_出す前の文に置かない物が無ければ緑_標準入力でも読める(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    monkeypatch.setenv("AF_DENY_BUNDLE", _bundle_of(["新規商事"]))
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("作り物の本文だけ\n"))
    assert guard.main(["--repo", str(repo), "--text", "-"]) == 0, capsys.readouterr().out


def test_出す前の文は顧客の語が無ければ手元でも緑にしない(tmp_path, capsys):
    """顧客の語を出さないための道なので、材料が欠けた時は語の表と形だけで緑を返さない（注入の試験）。"""
    body = tmp_path / "body.md"
    body.write_text("作り物の本文だけ\n", encoding="utf-8")
    code = guard.main(["--repo", str(_repo(tmp_path)), "--text", str(body)])
    out = capsys.readouterr().out
    assert code == 1 and "照らせない" in out and "当たりは 0" in out, out


def test_出す前の文は顧客の語が無くても語の表と形は照らして当たりを出す(tmp_path, capsys):
    """顧客の語が無い手元でも、置かない語・秘密の形の当たりは名指しで出す（照らさずに止まらない）。"""
    repo = _repo(tmp_path)
    (repo / "deny.txt").write_text("見本業務\n", encoding="utf-8")
    body = tmp_path / "body.md"
    body.write_text("見本業務の話\n", encoding="utf-8")
    code = guard.main(["--repo", str(repo), "--deny-words-file", "deny.txt", "--text", str(body)])
    out = capsys.readouterr().out
    assert code == 1 and "置かない物" in out and "当たりは 0" not in out, out

