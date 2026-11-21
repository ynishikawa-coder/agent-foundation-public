"""書いた窓の正本は PR の commit の `Claude-Session:` だけ（PR 本文に写しの欄を置かない）の注入の試験。

前の形: PR 本文の頭の `書いた窓:` を最初に PR を出した窓が手で写し、直しの往復で別の窓が commit すると写しがずれて
CI の job check（scripts/checks/pr_writer.sh）が赤になった。本文の頭の塊を読む head_block は guard の pr_text と
checker の pr_writer に写しで 2 つ在った（plugin を跨いで import しない作りのため）。
今の形: 写しの欄を PR の型から畳み、書いた窓の組は commit の記録だけから作る（pr_writer.py --writers・guard の pr_text）。
本文を読む道は無いので head_block も要らない（どの plugin にも置かない）。
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "checker" / "scripts" / "pr_writer.py"
A, B = "session_01AAAAAAAAAAAAAAAAAAAAAAAA", "session_01BBBBBBBBBBBBBBBBBBBBBBBB"
BRANCH = "claude/20261119-test"


def git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                          check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, name, session=None):
    (repo / name).write_text(name, encoding="utf-8")
    git(repo, "add", "-A")
    msg = f"{name}\n\nCo-Authored-By: t <t@example.invalid>\n"
    if session:
        msg += f"Claude-Session: https://claude.ai/code/{session}\n"
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


def repo_with(tmp_path, sessions):
    """main に 1 commit、枝に sessions の順で commit（None は Claude-Session の無い commit）。"""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, "base")
    git(r, "checkout", "-qb", BRANCH)
    head = ""
    for i, s in enumerate(sessions):
        head = commit(r, f"f{i}", s)
    return r, head


def writers(repo, head, *extra):
    p = subprocess.run([sys.executable, str(TOOL), "--writers", "--repo", str(repo), "--head", head, "--base", "main",
                        *extra], capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def test_合格_直しの往復で別の窓が_commit_しても組に両方が入る(tmp_path):
    repo, head = repo_with(tmp_path, [A, None, B])
    code, out = writers(repo, head)
    assert code == 0 and sorted(out.split(",")) == [A, B], out


def test_注入_Claude_Session_の無い_PR_は組を出さない(tmp_path):
    repo, head = repo_with(tmp_path, [None])
    code, out = writers(repo, head)
    assert code == 2 and "Claude-Session" in out, out


def test_注入_本文を渡す道が無い(tmp_path):
    """前の形の本文の照らし（--body-file・--branch）を渡すと道具が受けない＝写しを材料にする道が戻らない。"""
    repo, head = repo_with(tmp_path, [A])
    body = tmp_path / "body.md"
    body.write_text(f"書いた窓: {B}\n", encoding="utf-8")
    code, out = writers(repo, head, "--body-file", str(body))
    assert code == 2 and "--body-file" in out, out
    p = subprocess.run([sys.executable, str(TOOL), "--repo", str(repo), "--head", head, "--base", "main"],
                       capture_output=True, text=True)
    assert p.returncode == 2 and "--writers" in p.stderr, p.stderr


def test_注入_PR_の型に書いた窓の欄を置かない():
    t = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert not re.search(r"(?m)^\s*書いた窓\s*[:：]", t)
    assert not (ROOT / "scripts" / "checks" / "pr_writer.sh").exists()
    assert "PR_BODY" not in (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_使う側の型に残る書いた窓の欄は古い形として名指す():
    """壊れる（1 段目）: 土台の型から畳み、使う側の型に残る欄は古い形の一覧で起動の hook が名指す。"""
    olds = json.loads((ROOT / "plugins" / "core" / "古い形.json").read_text(encoding="utf-8"))["olds"]
    row = next(o for o in olds if o["id"] == "pr-writer-field")
    assert ".github/pull_request_template.md" in row["files"]
    assert re.search(row["pattern"], "job: x\n" + row["example"] + "\n")


def _defs(path):
    return {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef)}


def test_注入_本文の頭の塊を読む関数をどの_plugin_にも写さない():
    """前の形は head_block が pr_text と pr_writer に 2 つ在った。本文を読む道を畳んだので、どこにも置かない。"""
    found = [str(p.relative_to(ROOT)) for p in (ROOT / "plugins").rglob("*.py") if "head_block" in _defs(p)]
    assert found == [], found


def test_注入_guard_の書いた窓の組は本文の欄を足さない(tmp_path, monkeypatch):
    """本文の頭に commit を書いていない窓を `書いた窓:` で書いても、組に入らない（その窓の判定を止める側に数えない）。"""
    import importlib.util
    monkeypatch.syspath_prepend(str(ROOT / "plugins" / "guard" / "scripts"))
    spec = importlib.util.spec_from_file_location("pr_text_writer", ROOT / "plugins" / "guard" / "scripts" / "pr_text.py")
    pt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pt)

    class R:
        def __init__(self, out):
            self.returncode, self.stdout, self.stderr = 0, out, ""

    msg = json.dumps(f"x\n\nClaude-Session: https://claude.ai/code/{A}\n", ensure_ascii=False)
    calls = []

    def fake(args):
        calls.append(args)
        if args[0] == "--paginate":
            return R(msg + "\n")
        out = "a" * 40 + "\n1"
        if ".body" in " ".join(args):     # 本文を問う形（前の形）なら、commit を書いていない窓の欄を返す
            out += "\n" + f"書いた窓: {B}"
        return R(out + "\n")

    monkeypatch.setattr(pt, "_gh", fake)
    head, ws, err = pt.pr_facts("o/r", {"pullNumber": 1})
    assert err == "" and ws == [A], (ws, err)
    assert not any(".body" in " ".join(c) for c in calls), calls
