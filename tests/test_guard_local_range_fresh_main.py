"""公開の検査（public-guard/guard.py）が手元で回す時の既定の範囲の元を、出所の今の main にする約束。

手元の origin/main は fetch しなければ古い。古いまま `origin/main..HEAD` を照らすと、main で入った commit（枝の物でない）を
枝の物として照らし、枝に無い物で赤になる。元は scripts/pr_shape.py の fresh_main（出所へ先端を聞き、違えば取り直す）。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "public-guard" / "guard.py"
MAIL = "1+someone@users.noreply.github.com"
TOKEN = "ghp_" + "b" * 36  # 秘密の形（作り物）
DROP = ("AF_DENY_WORDS", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE", "GITHUB_ACTIONS", "GITHUB_EVENT_PATH")


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL=MAIL, GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL=MAIL)
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=env).stdout.strip()


def commit(repo, name, text, msg):
    path = Path(repo) / name
    if text is None:
        path.unlink()
    else:
        path.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def guard(repo):
    env = {k: v for k, v in os.environ.items() if k not in DROP}
    env["AF_DENY_WORDS"] = "置かない作り物の語"  # 顧客の語の照らしも回す（当たらない語）
    return subprocess.run([sys.executable, str(GUARD), "--repo", str(repo)], capture_output=True, text=True, env=env, timeout=120)


def setup(tmp_path):
    """出所（bare）・main で鍵を足して消した commit・その main を取り込んだ枝。手元の origin/main は古い所へ戻す。"""
    up = tmp_path / "up.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(up))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(up), str(work))
    old = commit(work, "README.md", "見本\n", "base")
    git(work, "push", "-q", "origin", "HEAD:main")
    commit(work, "a.md", f"鍵 {TOKEN}\n", "main で足した")  # main の歴史に在る当たり（この枝の物でない）
    commit(work, "a.md", None, "main で消した")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "checkout", "-q", "-b", "claude/20261120-x")
    commit(work, "b.md", "枝の物\n", "枝で足した")
    git(work, "update-ref", "refs/remotes/origin/main", old)  # 注入: 手元の origin/main を古く置く
    return work, old


def test_手元の_origin_main_が古くても_main_で入った_commit_を照らさない(tmp_path):
    work, old = setup(tmp_path)
    r = guard(work)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "置かない物 0" in r.stdout
    # 比べる元を取り直した（出所の今の main に揃った）
    assert git(work, "rev-parse", "refs/remotes/origin/main") != old


def test_枝で足した当たりは照らす(tmp_path):
    """取り直した元からの範囲でも、枝の物は照らす（範囲を縮めて黙らせたのでない）。"""
    work, _ = setup(tmp_path)
    commit(work, "c.md", f"鍵 {TOKEN}\n", "枝で鍵を足した")
    commit(work, "c.md", None, "枝で消した")
    r = guard(work)
    assert r.returncode == 1 and "GitHub のトークン" in r.stdout, r.stdout + r.stderr


def test_出所に聞けない時は古い手元の_origin_main_で比べず止める(tmp_path):
    work, _ = setup(tmp_path)
    git(work, "remote", "set-url", "origin", str(tmp_path / "無い出所.git"))
    r = guard(work)
    assert r.returncode == 2 and "照らせない" in r.stdout, r.stdout + r.stderr
    assert "置かない物 0" not in r.stdout
