"""公開の検査（public-guard/guard.py）を作り物の repo で回す小箱の 1 か所（tests/test_public_guard_<話題>.py が使う）。

秘密・個人の情報の形は字のまま書かず、作り物を組み立てる（字のまま書くとこの file が公開の検査に当たる）。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "public-guard" / "guard.py"
sys.path.insert(0, str(ROOT / "public-guard"))
import guard  # noqa: E402,F401

MAIL = "1+someone@users.noreply.github.com"
ENV_KEYS = ("AF_DENY_WORDS", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE", "GITHUB_ACTIONS", "GITHUB_EVENT_PATH")
TOKEN = "ghp_" + "b" * 36                       # 秘密の形（作り物）
PHONE = "03" + "-1234-" + "5678"                # 個人の情報の形（作り物）
CUSTOMER = "作り物ノ客"                          # 顧客の語（作り物）
CLEAN_CUSTOMER = "zzq" + "作り物ノ当たらない語"     # どこにも無い顧客の語（照合を回すため）


def wide(text):
    """ASCII を全角の字にする（NFKC で元に戻る互換の字）。"""
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL=MAIL, GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL=MAIL)
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout.strip()


def make_repo(path):
    repo = Path(path)
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("見本\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    return repo


def commit(repo, files=None, msg="直した", remove=()):
    """files の値が bytes ならそのまま書く。"""
    for name, body in (files or {}).items():
        p = Path(repo) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body) if isinstance(body, bytes) else p.write_text(body, encoding="utf-8")
    for name in remove:
        (Path(repo) / name).unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def cli(repo, *args, env_extra=None, cwd=None):
    """guard.py を CLI で回す（環境の顧客の語・CI の印は外してから env_extra を足す）。"""
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env.update(env_extra or {})
    cmd = [sys.executable, str(GUARD)] + (["--repo", str(repo)] if repo else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd, timeout=120)
