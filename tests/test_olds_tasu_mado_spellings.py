"""古い形 tasu-mado-heading（PR 本文の欄「他の窓へ回す」）は、欄の名の飾り方（見出しの # ・かぎ括弧の中の # ・太字）に
よらず当たる。注入: pixel-office の PR のレビューで漏れた形「「## 他の窓へ回す」」を置くと olds が拾う。"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kaku_tasu", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)
ROW = next(r for r in kaku.olds_table() if r["id"] == "tasu-mado-heading")


@pytest.mark.parametrize("text", [
    "## 他の窓へ回す",
    "### 他の窓へ回す（担当の外）",
    "本文の欄「## 他の窓へ回す」に書く",
    "欄「他の窓へ回す」",
    "**他の窓へ回す**",
    "『## 他の窓へ回す』",
])
def test_欄の名は飾り方によらず古い形に当たる(text):
    assert ROW["re"].search(text), text


@pytest.mark.parametrize("text", [
    "## 残り（原因の台帳の行）",
    "前は他の窓へ回すと書いていたが台帳にした",  # 地の文の経緯は欄の名ではない
])
def test_今の欄と地の文の経緯は当たらない(text):
    assert not ROW["re"].search(text), text


def test_かぎ括弧の中に見出しの印が付いた欄を_olds_が名指す(tmp_path):
    repo = tmp_path / "使う側"
    repo.mkdir()
    (repo / "型.md").write_text("PR の本文は「## 他の窓へ回す」の欄に残りを書く\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    found = kaku.find_olds(repo)
    assert ("tasu-mado-heading", "型.md") in {(r["id"], f) for r, f in found}, found
