"""並ぶ PR が同じ大きな file を取り合って衝突しない形を照らす（細目を節ごとの file に・試験で守らない文を 1 件 1 file に）。

意図: 並べた窓の PR が、main に先に入った PR と衝突せずに入る（衝突を解く往復でレビューを回し直さない）。
課題: 開いた PR の多くが、約 2.4 万字 1 枚の 細目.md と、全 PR が末尾へ足す 1 枚の 試験で守らない文.txt を同時に触り、
1 本入るたびに残りが衝突した。
原因: 別々の話の文が 1 枚の file に集まり、全部の PR が同じ所（同じ file・同じ末尾）へ足す形だった。
解決: 細目は節ごとの file（plugins/core/細目/<番号>-<名>.md）、守らない文は 1 件 1 file の dir（CHANGELOG.d と同じ形）。
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from saimoku import DIR, kaku

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "tests" / "data" / "試験で守らない文"
_HEAD = re.compile(r"^## (?:(\d+)\.\s+)?(.+?)\s*$", re.M)


def 節の形の外れ(d):
    """節ごとの file の形から外れた物の並び: 1 つの file に節が 2 つ以上・名の番号と見出しの番号が違う・頭の file 以外に節が無い。"""
    bad = []
    for f in sorted(d.glob("*.md")):
        heads = _HEAD.findall(f.read_text(encoding="utf-8"))
        no = f.name.split("-", 1)[0]
        if no == "00":
            if heads:
                bad.append(f"{f.name}: 頭の file に節が在る")
            continue
        if len(heads) != 1:
            bad.append(f"{f.name}: 節が {len(heads)} 個（1 file に 1 節）")
        elif heads[0][0] and int(heads[0][0]) != int(no):
            bad.append(f"{f.name}: 名の番号 {no} と見出しの番号 {heads[0][0]} が違う")
    return bad


def test_細目は_1_節_1_file():
    assert 節の形の外れ(DIR) == []
    assert not (DIR.parent / "細目.md").exists(), "割る前の 1 枚が戻った（節ごとの file と 2 つの正本になる）"


def test_注入_2_つの節を_1_file_に入れると赤(tmp_path):
    d = tmp_path / "細目"
    shutil.copytree(DIR, d)
    three, four = d / "03-直すは根治.md", d / "04-聞き方.md"
    three.write_text(three.read_text(encoding="utf-8") + "\n" + four.read_text(encoding="utf-8"), encoding="utf-8")
    four.unlink()
    assert any("03-直すは根治.md: 節が 2 個" in b for b in 節の形の外れ(d))


def _git(cwd, *a, check=True):
    return subprocess.run(["git", "-c", "core.quotepath=off", *a], cwd=cwd, check=check, capture_output=True, text=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _commit(cwd, msg):
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-q", "-m", msg)


def _append(f, line):
    f.write_text(f.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")


def _row_file(d, rel, s):
    holes = __import__("test_rule_holes")
    (d / holes.表の名(rel, s)).write_text(f"{rel}\t{s}\n", encoding="utf-8")


def test_合格_別々の節に_1_行ずつ足した_2_本の枝は衝突せずに入る(tmp_path):
    """2 本の枝が細目の別々の節の末尾に 1 行ずつ、守らない文に 1 件ずつ足しても、git merge が衝突しない。"""
    repo = _repo(tmp_path)
    sai = repo / "plugins/core/細目"
    tab = repo / "tests/data/試験で守らない文"
    shutil.copytree(DIR, sai)
    shutil.copytree(TABLE, tab)
    _commit(repo, "元")
    _git(repo, "switch", "-q", "-c", "a")
    _append(sai / "03-直すは根治.md", "- **作り物の甲** — 枝 a が足した文。")
    _row_file(tab, "plugins/core/細目/03-直すは根治.md", "- **作り物の甲** — 枝 a が足した文。")
    _commit(repo, "a")
    _git(repo, "switch", "-q", "main")
    _git(repo, "switch", "-q", "-c", "b")
    _append(sai / "04-聞き方.md", "- **作り物の乙** — 枝 b が足した文。")
    _row_file(tab, "plugins/core/細目/04-聞き方.md", "- **作り物の乙** — 枝 b が足した文。")
    _commit(repo, "b")
    _git(repo, "switch", "-q", "main")
    _git(repo, "merge", "-q", "--no-edit", "a")
    r = _git(repo, "merge", "--no-edit", "b", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    text = kaku.saimoku_text(sai)
    assert "枝 a が足した文。" in text and "枝 b が足した文。" in text
    assert len(list(tab.glob("*.txt"))) == len(list(TABLE.glob("*.txt"))) + 2


def test_注入_守らない文を_1_枚の末尾へ足す古い形は衝突する(tmp_path):
    """古い形（全部の PR が 1 枚の表の末尾へ行を足す）を作り物で入れると、2 本目の merge が衝突する＝上の合格が形の効き目を見ている。"""
    repo = _repo(tmp_path)
    one = repo / "試験で守らない文.txt"
    one.write_text("".join(p.read_text(encoding="utf-8") for p in sorted(TABLE.glob("*.txt"))), encoding="utf-8")
    _commit(repo, "元")
    _git(repo, "switch", "-q", "-c", "a")
    _append(one, "plugins/core/細目/03-直すは根治.md\t- 枝 a の文。")
    _commit(repo, "a")
    _git(repo, "switch", "-q", "main")
    _git(repo, "switch", "-q", "-c", "b")
    _append(one, "plugins/core/細目/04-聞き方.md\t- 枝 b の文。")
    _commit(repo, "b")
    _git(repo, "switch", "-q", "main")
    _git(repo, "merge", "-q", "--no-edit", "a")
    r = _git(repo, "merge", "--no-edit", "b", check=False)
    assert r.returncode != 0 and "CONFLICT" in r.stdout, r.stdout + r.stderr
