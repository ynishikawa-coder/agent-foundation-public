"""本物の claude で: 前の setup の目録の clone が残る箱に、出所が先へ進んだ後で使う側の塊（docs の 3 行）を回すと、
入った plugin が全部出所の先端の commit に揃い、足された plugin も入る。

作り物の claude（tests/test_setup_plugins_catalog_tip.py）が本物の振る舞い（marketplace add は既に在れば何もしない・
plugin update は目録を進めない）とずれていないかを見る歯。出所は手元の git の repo を https の名で見せる（鍵も外の網も要らない）。
claude の命令が無い所（手元）では飛ばす。CI の job plugin-smoke は AF_REQUIRE_CLAUDE=1 で回し、無ければ赤にする。
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "scripts" / "setup_plugins.py"
DOC = ROOT / "docs" / "核の届け方.md"
URL = "https://example.invalid/o/agent-foundation-public.git"

if not shutil.which("claude"):
    if os.environ.get("AF_REQUIRE_CLAUDE") == "1":
        pytest.fail("claude の命令が無い（CI の job plugin-smoke では入れてから回す）", pytrace=False)
    pytest.skip("claude の命令が無い所では飛ばす（CI の job plugin-smoke が回す）", allow_module_level=True)


def git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                          check=True, capture_output=True, text=True).stdout.strip()


def commit(up, names, msg):
    (up / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
        {"name": "agent-foundation", "owner": {"name": "t"},
         "plugins": [{"name": n, "source": f"./plugins/{n}"} for n in names]}), encoding="utf-8")
    for n in names:
        (up / "plugins" / n / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        (up / "plugins" / n / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": n}), encoding="utf-8")
        (up / "plugins" / n / "版.txt").write_text(msg, encoding="utf-8")
    git(up, "add", "-A")
    git(up, "commit", "-qm", msg)
    return git(up, "rev-parse", "HEAD")


def test_古い目録が残った箱で塊を回すと先端に揃う(tmp_path):
    up = tmp_path / "up"
    (up / "scripts").mkdir(parents=True)
    (up / ".claude-plugin").mkdir()
    shutil.copy2(ENTRY, up / "scripts" / "setup_plugins.py")
    git(tmp_path, "init", "-q", "-b", "main", str(up))
    commit(up, ["core"], "v1")
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), GIT_CONFIG_GLOBAL=str(tmp_path / "gitconfig"))
    for k, v in [(f"url.file://{up}.insteadOf", URL), ("protocol.file.allow", "always")]:
        subprocess.run(["git", "config", "--global", k, v], env=env, check=True)
    block = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", DOC.read_text(encoding="utf-8"), re.S).group(1)
    block = block.replace("ynishikawa-coder/agent-foundation-public", URL)

    def setup():
        r = subprocess.run(["bash", "-ec", block], capture_output=True, text=True, env=env, timeout=600)
        assert r.returncode == 0, r.stdout + r.stderr
        t = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        return {k: v[0].get("gitCommitSha") for k, v in t["plugins"].items()}

    v1 = git(up, "rev-parse", "HEAD")
    assert setup() == {"core@agent-foundation": v1}
    tip = commit(up, ["core", "added"], "v2")  # 出所が進む。箱には v1 の clone が残る
    assert setup() == {"core@agent-foundation": tip, "added@agent-foundation": tip}
    assert "af-plugin-missing" not in (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") \
        if (home / ".claude" / "CLAUDE.md").exists() else True
