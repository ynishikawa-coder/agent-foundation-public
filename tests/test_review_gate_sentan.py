"""レビューの関所（plugins/checker/scripts/review_gate.py）が、窓の持つ古い版のままでは判定せず、main の先端の版へ寄るか止まるか。

意図: レビューの関所はいつも main の先端の決まりで判定する。依頼に「先に fetch して checkout して」と書かせない。
課題: レビューの窓が立った時の版の関所が、main の守りの決まりを読めず 403 で止まった（main の先端では直っていた）。
原因: skill は窓が立った時の plugin の dir（${CLAUDE_PLUGIN_ROOT}）を指し、hook と違って先端の版へ寄せる入口が無かった。
ここでは手元の土台の取り出し・origin を仮に作り、わざと古い版を回して、先端へ寄る・寄れない時は止まるを見る。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "plugins" / "checker" / "scripts" / "review_gate.py"
REL = "plugins/checker/scripts/review_gate.py"
MARK = "TIP-MARKER-先端の版"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(*a, cwd=None):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, env={**os.environ, **GIT_ENV})


def lay(tmp: Path, tip_text: str) -> Path:
    """origin（main の先端に tip_text の関所）と、その取り出し（~/.claude/plugins/marketplaces/agent-foundation）を置く。"""
    home = tmp / "home"
    origin, work = tmp / "origin.git", tmp / "work"
    git("init", "-q", "--bare", "-b", "main", str(origin))
    git("init", "-q", "-b", "main", str(work))
    (work / REL).parent.mkdir(parents=True)
    (work / REL).write_text(tip_text, encoding="utf-8")
    (work / "plugins/checker/README.md").write_text("checker\n", encoding="utf-8")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "tip", cwd=work)
    git("push", "-q", str(origin), "main", cwd=work)
    market = home / ".claude/plugins/marketplaces/agent-foundation"
    market.parent.mkdir(parents=True)
    git("clone", "-q", str(origin), str(market))
    return home


def run(home: Path, **extra):
    env = {k: v for k, v in os.environ.items() if k not in ("AF_REVIEW_GATE_TIP", "CLAUDE_PLUGIN_ROOT")}
    env.update(GIT_ENV, HOME=str(home), **extra)
    return subprocess.run([sys.executable, str(GATE), "--repo", "bad", "--pr", "1"],
                          capture_output=True, text=True, env=env, timeout=120)


def newer():
    s = GATE.read_text(encoding="utf-8")
    return s.replace('\nif __name__ == "__main__":', '\nprint("%s")\n\nif __name__ == "__main__":' % MARK, 1)


def test_古い版を回すと_main_の先端の版で回り直す(tmp_path):
    home = lay(tmp_path, newer())
    r = run(home)
    assert "先端の版で回す" in r.stdout and MARK in r.stdout, r.stdout + r.stderr
    assert "--repo は owner/name の形で渡す" in r.stdout and r.returncode == 2
    # 回し直した先は先端の版の dir（skill の ${CLAUDE_PLUGIN_ROOT} もそこへ替わる）
    assert list((home / ".claude/af-foundation/checker-tip").glob("*/" + REL))


def test_先端を取れない時は古い版で判定せず止まる(tmp_path):
    home = lay(tmp_path, newer())
    git("remote", "set-url", "origin", str(tmp_path / "無い.git"), cwd=home / ".claude/plugins/marketplaces/agent-foundation")
    r = run(home)
    assert r.returncode == 2 and "main の先端の版を取れない" in r.stdout, r.stdout + r.stderr
    assert MARK not in r.stdout and "--repo は owner/name" not in r.stdout   # 古い版の判定に入らない


def test_土台の取り出しが無い窓でも古い版で判定せず止まる(tmp_path):
    (tmp_path / "home").mkdir()
    r = run(tmp_path / "home")
    assert r.returncode == 2 and "main の先端の版を取れない" in r.stdout, r.stdout + r.stderr
    assert "--repo は owner/name" not in r.stdout


def test_先端と同じ版ならそのまま回る(tmp_path):
    home = lay(tmp_path, GATE.read_text(encoding="utf-8"))
    r = run(home)
    assert "先端の版で回す" not in r.stdout and "--repo は owner/name の形で渡す" in r.stdout, r.stdout + r.stderr


def test_回し直した後もまだ違えば回り続けず止まる(tmp_path):
    home = lay(tmp_path, newer())
    r = run(home, AF_REVIEW_GATE_TIP="0" * 40)
    assert r.returncode == 2 and "回し直した後もまだ中身が違う" in r.stdout, r.stdout + r.stderr
    assert MARK not in r.stdout
