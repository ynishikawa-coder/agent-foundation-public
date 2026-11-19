"""入れて起動する試験（scripts/plugin_smoke.py）の歯: 届かない物をわざと入れた土台の写しで赤になるか。

土台は main の先端をそのまま配るので、合流の前の CI の job `plugin-smoke` が、使う側と同じ入れ方で入れて起動する。
ここはその試験自身が「壊すと赤・戻すと緑」かを、作り物の写しで見る（注入の試験）。
claude の命令が無い所（手元）では飛ばす。CI の job `plugin-smoke` は AF_REQUIRE_CLAUDE=1 で回し、無ければ赤にする。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SMOKE = ROOT / "scripts" / "plugin_smoke.py"

if not shutil.which("claude"):
    if os.environ.get("AF_REQUIRE_CLAUDE") == "1":
        pytest.fail("claude の命令が無い（CI の job plugin-smoke では入れてから回す）", pytrace=False)
    pytest.skip("claude の命令が無い所では入れて起動する試験を飛ばす（CI の job plugin-smoke が回す）",
                allow_module_level=True)


def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def copy_of_foundation(tmp_path, breaks=None):
    """git の追跡する file だけを写した土台の作り物（窓の作業の跡を混ぜない）に、壊す手を当てて commit する。"""
    dst = tmp_path / "foundation"
    for rel in _git(ROOT, "ls-files", "-z").split("\0"):
        if not rel or not (ROOT / rel).is_file():
            continue
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst / rel)
    if breaks:
        breaks(dst)
    _git(dst, "init", "-q", "-b", "main")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-q", "-m", "作り物")
    return dst, _git(dst, "rev-parse", "HEAD")


def smoke(src, sha):
    p = subprocess.run([sys.executable, str(SMOKE), "--source", str(src), "--expect-sha", sha, "--repo", str(ROOT)],
                       capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def test_そのままの土台は緑(tmp_path):
    src, sha = copy_of_foundation(tmp_path)
    code, out = smoke(src, sha)
    assert code == 0 and out.strip().endswith("plugin-smoke: 緑"), out


def _drop_skill(d):
    (d / "plugins" / "docs-kit" / "skills" / "qa-html" / "SKILL.md").unlink()


def _break_core_hook(d):
    f = d / "plugins" / "core" / "hooks" / "hooks.json"
    f.write_text(f.read_text(encoding="utf-8").replace("kaku.py\\\" inject", "kaku.py\\\" injct"), encoding="utf-8")


def _drop_from_market(d):
    f = d / ".claude-plugin" / "marketplace.json"
    m = json.loads(f.read_text(encoding="utf-8"))
    m["plugins"] = [p for p in m["plugins"] if p["name"] != "guard"]
    f.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")


def _guard_never_denies(d):
    f = d / "plugins" / "guard" / "scripts" / "guard.py"
    text = f.read_text(encoding="utf-8")
    broken = re.sub(r'"pre": \[[^\]]*\],', '"pre": [],', text, count=1)
    assert broken != text, "guard.py の止める一覧の形が変わった（この注入を合わせる）"
    f.write_text(broken, encoding="utf-8")


def _drop_furumai_from_inject(d):
    f = d / "plugins" / "core" / "scripts" / "kaku.py"
    text = f.read_text(encoding="utf-8")
    broken = text.replace("return (KAKU, FURUMAI)", "return (KAKU,)")
    assert broken != text, "kaku.py の injected() の形が変わった（この注入を合わせる）"
    f.write_text(broken, encoding="utf-8")


@pytest.mark.parametrize("breaks,want", [
    (_drop_skill, "skill docs-kit:qa-html"),
    (_break_core_hook, "核が起動した窓に差し込まれていない"),
    (_drop_from_market, "plugin guard を入れられない"),
    (_guard_never_denies, "止めるべき作り物の入力を止めない"),
    (_drop_furumai_from_inject, "振る舞い.md が起動した窓に差し込まれていない"),
], ids=["skill が欠ける", "核の hook が壊れる", "配りの器から plugin が落ちる", "守りが止めない", "振る舞いの既定が届かない"])
def test_届かない物を入れた土台は赤(tmp_path, breaks, want):
    src, sha = copy_of_foundation(tmp_path, breaks)
    code, out = smoke(src, sha)
    assert code == 1 and want in out, out


def test_試したい先端と違う物が入れば赤(tmp_path):
    src, _ = copy_of_foundation(tmp_path)
    code, out = smoke(src, "0" * 40)
    assert code == 1 and "試したい先端" in out, out
