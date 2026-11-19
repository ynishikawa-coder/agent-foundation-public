"""値の表（使う側の repo の config/skill-values.json）に土台が読まない鍵を、守り values_keys が名指し・止めるかを見る。

知っている鍵の正本は各 SKILL.md の「repo ごとの値」の表と guard の値。入力は全部作り物。
表と道具のコードが読む鍵のずれは、読む時の読み口（tests/test_values_reader.py）が照らす。値の表への AI の書き込みを
どの道具・書き方でも道具の後に照らすのは tests/test_values_table_after_tool.py。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "guard"
GUARD = PLUGIN / "scripts" / "guard.py"


@pytest.fixture
def env(tmp_path):
    """試験ごとに一時の箱・台帳の置き場・repo の根を分ける（実の印を汚さない）。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    (tmp_path / "scratch").mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(proj), "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(tmp_path / "scratch")})
    return e


def hook(env, event, payload):
    p = subprocess.run([sys.executable, str(GUARD), event], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = p.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else {}


def denied(env, payload):
    return hook(env, "pre", payload).get("permissionDecision") == "deny"


import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("values_keys", PLUGIN / "scripts" / "values_keys.py")
VK = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(VK)

今の表 = {
    "_readme": "注は通す",
    "common": {"glossary": {"作り物の語": "意味"}, "save_dir": "/tmp/x"},
    "dev-flow": {"preimpl-cleanup": {"record": "PR 本文", "ledger": "1 行ずつ"}, "codex": {"clients": {"作り物": {"paths": []}}}},
    "docs-kit": {"qa-html": {"customer": {"何でも": 1}}, "pdf-read": {"engine_source": "作り物"}},
    "guard": {"context_limit": 1000, "_readme": "注"},
    "作り物の repo の頭": {"何でも": "repo が自分で持つ所は見ない"},
}


def test_values_keys_今の鍵だけの表は通る():
    assert VK.unknown(今の表) == []


@pytest.mark.parametrize("path", [
    ("dev-flow", "preimpl-cleanup", "cleanup_followup"),    # 畳んだ鍵（PR #36）
    ("dev-flow", "register-rule", "agents_table"),          # 畳んだ鍵（v0.3.0）
    ("common", "rules"),                                    # 畳んだ鍵（PR #43）
    ("dev-flow", "verify", "code_done_rule"),               # 畳んだ鍵（PR #43）
    ("dev-flow", "畳んだ作り物の skill"),
    ("guard", "作り物の書き違い"),
    ("common", "作り物の鍵"),
    ("checker", "作り物"),
])
def test_values_keys_土台が読まない鍵を名指しする(path):
    table = json.loads(json.dumps(今の表))
    node = table
    for k in path[:-1]:
        node = node.setdefault(k, {})
    node[path[-1]] = "古い値"
    assert VK.unknown(table) == [".".join(path)]


def test_values_keys_知っている鍵の正本は_SKILL_の表で_表の無い_skill_の鍵は知らない():
    keys, frames, heads, missing = VK.known_keys()
    assert missing == [] and {"common", "dev-flow", "docs-kit", "guard"} <= heads
    assert ("dev-flow", "preimpl-cleanup", "ledger") in keys and ("common", "glossary") in keys
    assert ("docs-kit", "qa-html", "customer", "*") in keys and ("docs-kit", "pdf-read", "engine_module") in keys
    assert not any(k[:3] == ("dev-flow", "preimpl-cleanup", "cleanup_followup") for k in keys)


def test_values_keys_値の表を読む_SKILL_は全部_表を持つ():
    """表に載せずに文の中だけで鍵を読む skill を足すと、その鍵が知らない鍵に見える＝表を持たせる。"""
    lacking = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "plugins").glob("*/skills/*/SKILL.md"))
               if "config/skill-values.json" in p.read_text(encoding="utf-8") and p.parent.parent.parent.name != "guard"
               and not VK.SECTION.search(p.read_text(encoding="utf-8"))]
    assert lacking == []


def _vk_write(env, content, tool="Write", **extra):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(proj),
            "tool_input": {"file_path": str(proj / "config" / "skill-values.json"), "content": content, **extra}}


def test_values_keys_AI_が知らない鍵を書くと止める(env):
    bad = dict(今の表, **{"dev-flow": {"preimpl-cleanup": {"cleanup_followup": "x"}}})
    out = hook(env, "pre", _vk_write(env, json.dumps(bad, ensure_ascii=False)))
    assert out.get("permissionDecision") == "deny"
    assert "dev-flow.preimpl-cleanup.cleanup_followup" in out["permissionDecisionReason"]
    assert not denied(env, _vk_write(env, json.dumps(今の表, ensure_ascii=False)))


def test_values_keys_知らない鍵を残したままの編集は止め_減らす編集は通す(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    old = {"guard": {"context_limit": 1, "古い鍵 1": 1, "古い鍵 2": 2}}
    (proj / "config" / "skill-values.json").write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    keep = _vk_write(env, None, tool="Edit", old_string='"context_limit": 1', new_string='"context_limit": 2')
    keep["tool_input"].pop("content")
    assert denied(env, keep)
    drop = _vk_write(env, None, tool="Edit", old_string='"古い鍵 1": 1,', new_string="")
    drop["tool_input"].pop("content")
    assert not denied(env, drop)


def test_values_keys_値の表の外と_JSON_でない書き込み(env):
    other = _vk_write(env, "{}")
    other["tool_input"]["file_path"] = str(Path(env["CLAUDE_PROJECT_DIR"]) / "config" / "他の表.json")
    other["tool_input"]["content"] = json.dumps({"dev-flow": {"x": 1}})
    assert not denied(env, other)
    assert denied(env, _vk_write(env, "{ 壊れた"))


def test_values_keys_起動の時に知らない鍵を知らせる(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    (proj / "config" / "skill-values.json").write_text(
        json.dumps({"dev-flow": {"register-rule": {"roster": "古い"}}}), encoding="utf-8")
    ctx = hook(env, "start", {"hook_event_name": "SessionStart", "cwd": str(proj)}).get("additionalContext", "")
    assert "dev-flow.register-rule.roster" in ctx
    (proj / "config" / "skill-values.json").write_text(json.dumps(今の表, ensure_ascii=False), encoding="utf-8")
    assert "土台が読まない鍵" not in hook(env, "start", {"hook_event_name": "SessionStart", "cwd": str(proj)}).get("additionalContext", "")


def test_values_keys_入れた_plugin_の形でも隣の_plugin_の表を読む(tmp_path):
    import shutil
    market = tmp_path / "cache" / "市場"
    for name in VK.FOUNDATION:
        src = ROOT / "plugins" / name
        if src.is_dir():
            shutil.copytree(src, market / name / "abc123", ignore=shutil.ignore_patterns("__pycache__"))
    keys, frames, heads, missing = VK.known_keys(str(market / "guard" / "abc123"))
    assert missing == [] and ("dev-flow", "preimpl-cleanup", "ledger") in keys


def test_values_keys_手で回す口は知らない鍵で_exit_1(tmp_path):
    t = tmp_path / "skill-values.json"
    t.write_text(json.dumps({"dev-flow": {"preimpl-cleanup": {"cleanup_followup": "x"}}}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "values_keys.py"), str(t)], capture_output=True, text=True)
    assert r.returncode == 1 and "cleanup_followup" in r.stdout
    t.write_text(json.dumps(今の表, ensure_ascii=False), encoding="utf-8")
    assert subprocess.run([sys.executable, str(PLUGIN / "scripts" / "values_keys.py"), str(t)]).returncode == 0
