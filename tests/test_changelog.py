"""変更の記録は 1 PR に 1 つの file（CHANGELOG.d/）。決まりの正本は CHANGELOG.d/README.md。

同じ所（CHANGELOG.md の先頭）へ全部の PR が行を足すと、1 本入るたびに残りが全部衝突する。
ここでは、①今の記録が形どおり ②古い形（CHANGELOG.md へ直に足す）を入れると赤
③2 本の PR が記録を足しても衝突しない（古い形なら衝突する）を、わざと入れて見る。
"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("changelog", ROOT / "scripts" / "changelog.py")
cl = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(cl)

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull}


def _copy(tmp_path: Path) -> Path:
    shutil.copy(ROOT / "CHANGELOG.md", tmp_path / "CHANGELOG.md")
    shutil.copytree(ROOT / "CHANGELOG.d", tmp_path / "CHANGELOG.d")
    return tmp_path


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=check)


def test_今の記録は形どおり():
    assert cl.check(ROOT) == []


def test_古い形で_CHANGELOG_md_へ直に足すと赤(tmp_path):
    root = _copy(tmp_path)
    main = root / "CHANGELOG.md"
    main.write_text(main.read_text(encoding="utf-8") + "\n## 合流ごと\n\n- 足した: 古い形の行\n", encoding="utf-8")
    errs = cl.check(root)
    assert errs and all("CHANGELOG.md:" in e and "CHANGELOG.d/" in e for e in errs), errs


@pytest.mark.parametrize("extra", ["\n## 合流ごと\n", "\n壊れる: 並びの印の無い地の文で足す\n", "\n1. 番号で足す\n"])
def test_CHANGELOG_md_へ見出しや地の文で足しても赤(tmp_path, extra):
    root = _copy(tmp_path)
    main = root / "CHANGELOG.md"
    main.write_text(main.read_text(encoding="utf-8") + extra, encoding="utf-8")
    assert any("CHANGELOG.md:" in e for e in cl.check(root))


def _old_form(lines: list[str]) -> str:
    """断片の形の前の CHANGELOG.md（「合流ごと」の先頭に新しい行）。"""
    old = (ROOT / "CHANGELOG.d" / cl.OLD_FILE).read_text(encoding="utf-8")
    return "# 変更の記録\n\n前置き\n\n## 合流ごと（v0.4.1 から・新しい物が上）\n\n" + "".join(l + "\n" for l in lines) + old


def test_並んでいた_PR_は_adopt_で自分の行だけを断片へ移せる(tmp_path):
    """この形が先に入った後: 古い形で足した枝が main を取り込み、自分の行を断片へ移すと緑。"""
    root = _copy(tmp_path)
    target = root / "CHANGELOG.d" / "20261119-queued.txt"
    moved = cl.adopt(_old_form(["- 足した: 並んでいた PR の行"]), target, root)
    assert moved == ["- 足した: 並んでいた PR の行"]          # 移す前の記録の行は移さない
    assert cl.check(root) == []


def test_この形が後に入る時は先に入った_PR_の行を移す前の記録へ_adopt_できる(tmp_path):
    """並んでいた PR が先に入った後: その行を移す前の記録の頭へ移すと、記録は欠けずに緑。"""
    root = _copy(tmp_path)
    old = root / "CHANGELOG.d" / cl.OLD_FILE
    lines = ["- 壊れる: 先に入った 2 本目", "- 足した: 先に入った 1 本目"]
    assert cl.adopt(_old_form(lines), old, root) == lines
    assert old.read_text(encoding="utf-8").splitlines()[:2] == lines
    assert cl.adopt(_old_form(lines), old, root) == []      # 2 度回しても重ならない
    assert cl.check(root) == []


@pytest.mark.parametrize("name,body", [
    ("20261119-x.txt", "- 足したよ: 札が無い\n"),                      # 知らない札
    ("20261119-x.txt", "壊れる: 頭の - が無い\n"),
    ("20261119-x.txt", "- 直した: 1 行目\n  続きの行で書く\n"),           # 1 項は 1 行
    ("20261119-x.txt", "\n"),                                         # 空
    ("20261119-x.md", "- 足した: 拡張子が違う\n"),
    ("話題だけ.txt", "- 足した: 日付が無い\n"),
])
def test_形の外の断片は赤(tmp_path, name, body):
    root = _copy(tmp_path)
    (root / "CHANGELOG.d" / name).write_text(body, encoding="utf-8")
    assert cl.check(root), (name, body)


def test_移す前の記録を消すと赤(tmp_path):
    root = _copy(tmp_path)
    (root / "CHANGELOG.d" / cl.OLD_FILE).unlink()
    assert any(cl.OLD_FILE in e for e in cl.check(root))


def _two_prs(tmp_path: Path, write) -> subprocess.CompletedProcess:
    """main から 2 本の枝を出し、それぞれが write(root, 話題) で記録を足して、順に main へ merge する。"""
    root = _copy(tmp_path)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    for topic in ("a", "b"):
        _git(root, "checkout", "-q", "-b", topic, "main")
        write(root, topic)
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", topic)
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--no-ff", "-m", "a", "a")
    return _git(root, "merge", "-q", "--no-ff", "-m", "b", "b", check=False)


def test_2_本の_PR_が記録を足しても衝突しない(tmp_path):
    def write(root, topic):
        (root / "CHANGELOG.d" / f"20261119-{topic}.txt").write_text(f"- 足した: {topic}\n", encoding="utf-8")
    r = _two_prs(tmp_path, write)
    assert r.returncode == 0, r.stdout + r.stderr
    assert cl.check(tmp_path) == []
    assert {"20261119-a.txt", "20261119-b.txt"} <= {n for n, _, _ in cl.entries(tmp_path)}


def test_古い形では_2_本目が衝突する_原因の見張り(tmp_path):
    """古い形（同じ見出しの直下へ 1 行足す）が衝突することを示す。これが緑になるなら原因の前提が変わった。"""
    def write(root, topic):
        p = root / "CHANGELOG.md"
        text = p.read_text(encoding="utf-8")
        p.write_text(text + f"\n## 合流ごと\n\n- 足した: {topic}\n", encoding="utf-8")
    r = _two_prs(tmp_path, write)
    assert r.returncode != 0 and "CONFLICT" in (r.stdout + r.stderr)


def test_束ねると_main_に入った順で新しい物が上(tmp_path):
    root = _copy(tmp_path)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    base = "2026-11-01T00:00:00+09:00"
    subprocess.run(["git", "commit", "-qm", "base", "--date", base], cwd=root,
                   env={**GIT_ENV, "GIT_COMMITTER_DATE": base}, check=True)
    # 名の日付は古いが後に入った物が上に来る（枝を立てた日でなく入った時で並べる）。
    for name, date in (("20261119-new-name.txt", "2026-11-02T00:00:00+09:00"),
                       ("20261101-old-name.txt", "2026-11-03T00:00:00+09:00")):
        (root / "CHANGELOG.d" / name).write_text("- 足した: x\n", encoding="utf-8")
        _git(root, "add", "-A")
        env = {**GIT_ENV, "GIT_COMMITTER_DATE": date}
        subprocess.run(["git", "commit", "-qm", name, "--date", date], cwd=root, env=env, check=True)
    (root / "CHANGELOG.d" / "20261120-mada.txt").write_text("- 足した: y\n", encoding="utf-8")
    names = [n for n, _, _ in cl.entries(root)]
    assert names[:3] == ["20261120-mada.txt", "20261101-old-name.txt", "20261119-new-name.txt"], names
    assert names[-1] == cl.OLD_FILE  # 同じ commit で入った物は名の逆順（移す前の記録が一番下）


def test_決まりの文が断片の形を指す():
    for rel in ["CONTRIBUTING.md", "docs/版の出し方.md"]:
        p = ROOT / rel
        if p.exists():
            text = p.read_text(encoding="utf-8")
            assert "CHANGELOG.d/" in text, f"{rel} が断片の置き場を指さない"
            assert "「合流ごと」に" not in text and "「合流ごと」へ" not in text, f"{rel} に古い書き方が残る"
