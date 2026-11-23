"""試験の作り物の「決まりの git」（verdict_form が版ごとの SKILL.md を読む取り出し）を一時の場所に組む 1 か所。

origin（bare）と取り出しを作り、review-pr の SKILL.md を commit して origin の main へ送る。
make() は (取り出しの path, 初めの版の SHA) を、push_version() は新しい版の SHA を返す。
試験は AF_RULES_GIT にこの取り出しを置いて、実の土台の取り出し（~/.claude/plugins/marketplaces）に触れない。
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_IN_REPO = "plugins/checker/skills/review-pr/SKILL.md"
SKILL = ROOT / SKILL_IN_REPO


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def push_version(clone, text):
    """SKILL.md を text にして commit し origin の main へ送る。返り: その commit の SHA（40 文字）。"""
    path = Path(clone) / SKILL_IN_REPO
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(clone, "add", SKILL_IN_REPO)
    _git(clone, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "--allow-empty", "-m", "版")
    _git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
    return _git(clone, "rev-parse", "HEAD")


def make(tmp_path, text=None):
    """返り: (取り出しの path, 初めの版の SHA)。text を省くと今の作業木の SKILL.md。"""
    origin, clone = Path(tmp_path) / "rules-origin.git", Path(tmp_path) / "rules"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(clone)], check=True)
    _git(clone, "remote", "add", "origin", str(origin))
    sha = push_version(clone, SKILL.read_text(encoding="utf-8") if text is None else text)
    return clone, sha
