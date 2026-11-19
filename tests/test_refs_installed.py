"""refs.py が使う側の入れ方（plugin の cache・目録の clone）で、repo の形と同じ名で引けて照らせるか（PR #114 のレビュー）。

前は入れた形で回すと文書の鍵が `<版>/核.md` になり、`細目「まず構造を疑う」` が「土台に無い」と赤になり、見張りの出来事も空だった。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VER = "0123456789ab"


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def installed(tmp_path, with_clone=True):
    """作り物の HOME: cache/agent-foundation/<plugin>/<版>/ に土台の plugin を写し、入った台帳と目録を書く。"""
    home = tmp_path / "home"
    plugins = home / ".claude" / "plugins"
    rows = {}
    clone = tmp_path / "clone"
    sha = ""
    if with_clone:
        clone.mkdir()
        for rel in ("CONTRIBUTING.md", ".github/pull_request_template.md"):
            (clone / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, clone / rel)
        _git("init", "-q", cwd=clone)
        _git("add", "-A", cwd=clone)
        _git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "作り物", cwd=clone)
        sha = _git("rev-parse", "HEAD", cwd=clone)
    for d in sorted((ROOT / "plugins").iterdir()):
        if not (d / ".claude-plugin").is_dir():
            continue
        dst = plugins / "cache" / "agent-foundation" / d.name / VER
        shutil.copytree(d, dst, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
        rows[f"{d.name}@agent-foundation"] = [{"scope": "user", "installPath": str(dst), "version": VER,
                                               "gitCommitSha": sha, "lastUpdated": "2026-11-20T00:00:00Z"}]
    (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": rows}), encoding="utf-8")
    (plugins / "known_marketplaces.json").write_text(json.dumps({"agent-foundation": {
        "source": {"source": "github", "repo": "ynishikawa-coder/agent-foundation-public"},
        "installLocation": str(clone)}}), encoding="utf-8")
    return home, plugins / "cache" / "agent-foundation" / "core" / VER / "scripts" / "refs.py"


def run(home, tool, *args):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, "-B", str(tool), *map(str, args)], capture_output=True, text=True, env=env)


def test_入れた形でも名で引けて_鍵は_repo_の形と同じ(tmp_path):
    home, tool = installed(tmp_path)
    f = tmp_path / "使う側.md"
    f.write_text("原因は細目「まず構造を疑う」で探す。\nPR は CONTRIBUTING「枝と PR」の手順。\n", encoding="utf-8")
    res = run(home, tool, "check", f)
    assert res.returncode == 0, res.stdout
    c = json.loads(run(home, tool, "list").stdout)
    assert "plugins/core/細目.md" in c["docs"] and "CONTRIBUTING.md" in c["docs"]
    assert c["hooks"]["plugins/guard/scripts/values_keys.py"] == {"pre": "check", "start": "resurface"}
    assert c["unread"] == []


def test_入れた形で目録の_clone_が無い時は_repo_の根の文書の指しを照らせないと名指す(tmp_path):
    home, tool = installed(tmp_path, with_clone=False)
    f = tmp_path / "使う側.md"
    f.write_text("原因は細目「まず構造を疑う」で探す。\nPR は CONTRIBUTING「枝と PR」の手順。\n", encoding="utf-8")
    res = run(home, tool, "check", f)
    assert res.returncode == 2 and "照らせない" in res.stdout and "✗" not in res.stdout, res.stdout
    f.write_text("原因は細目「作り物の無い名」で探す。\n", encoding="utf-8")
    assert run(home, tool, "check", f).returncode == 1
