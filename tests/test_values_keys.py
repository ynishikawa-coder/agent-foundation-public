"""値の表（使う側の repo の config/skill-values.json）に土台が読まない鍵を、守り values_keys が名指し・止めるかを見る。

知っている鍵の正本は値の表の 1 本の口（skill-values/ の skill_values.py と schema.json）。道具のコードが読む鍵とのずれも照らす。入力は全部作り物。
"""
import json
import os
import re
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
SECTION = re.compile(r"^## repo ごとの値[^\n]*\n(.*?)(?=^## |\Z)", re.M | re.S)


def _named(problems, path):
    """問題の文の並びが path（鍵の path）だけを名指すか。"""
    return len(problems) == 1 and problems[0].startswith(".".join(path) + " は")

今の表 = {
    "_readme": "注は通す",
    "common": {"glossary": {"作り物の語": "意味"}, "save_dir": "/tmp/x"},
    "dev-flow": {"preimpl-cleanup": {"record": "PR 本文", "ledger": "1 行ずつ"}, "codex": {"clients": {"作り物": {"paths": []}}}},
    "docs-kit": {"qa-html": {"customer": {"check_cmd": "作り物"}}, "pdf-read": {"engine_source": "作り物"}},
    "guard": {"context_limit": 1000, "_readme": "注"},
    "repo_sections": ["作り物の repo の頭"],
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
    assert _named(VK.unknown(table), path), VK.unknown(table)


def test_values_keys_知っている鍵の正本は値の表の_1_本の口で_自分で一覧を持たない():
    text = (PLUGIN / "scripts" / "values_keys.py").read_text(encoding="utf-8")
    assert "def known_keys" not in text and "SKILL.md" not in text.split('"""')[2] and "glob" not in text
    assert VK.SV.keys_of("dev-flow", "preimpl-cleanup").get("ledger") and "glossary" in VK.SV.keys_of("common")
    assert "dev-flow.preimpl-cleanup.cleanup_followup" in VK.SV.schema()["retired"]


def test_values_keys_値の表を読む_SKILL_は全部_表を持つ():
    """表に載せずに文の中だけで鍵を読む skill を足すと、その鍵が知らない鍵に見える＝表を持たせる。"""
    lacking = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "plugins").glob("*/skills/*/SKILL.md"))
               if "config/skill-values.json" in p.read_text(encoding="utf-8") and p.parent.parent.parent.name != "guard"
               and not SECTION.search(p.read_text(encoding="utf-8"))]
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


def test_values_keys_入れた_plugin_の形では隣の_plugin_に頼らず_lib_の正本で照らす(tmp_path):
    import shutil
    root = tmp_path / "cache" / "市場" / "guard" / "abc123"           # guard だけを入れた形（隣の plugin が無い・別の版も無い）
    shutil.copytree(PLUGIN, root, ignore=shutil.ignore_patterns("__pycache__"))
    assert not (root / "lib" / "schema.json").is_symlink()             # 入れる時に symlink は実体で写る
    t = tmp_path / "skill-values.json"
    t.write_text(json.dumps({"dev-flow": {"preimpl-cleanup": {"cleanup_followup": "x", "ledger": "y"}}}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(root / "scripts" / "values_keys.py"), str(t)], capture_output=True, text=True)
    assert r.returncode == 1 and "cleanup_followup は畳んだ鍵" in r.stdout and "ledger" not in r.stdout.split("直し方")[0]


def test_values_keys_手で回す口は知らない鍵で_exit_1(tmp_path):
    t = tmp_path / "skill-values.json"
    t.write_text(json.dumps({"dev-flow": {"preimpl-cleanup": {"cleanup_followup": "x"}}}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "values_keys.py"), str(t)], capture_output=True, text=True)
    assert r.returncode == 1 and "cleanup_followup" in r.stdout
    t.write_text(json.dumps(今の表, ensure_ascii=False), encoding="utf-8")
    assert subprocess.run([sys.executable, str(PLUGIN / "scripts" / "values_keys.py"), str(t)]).returncode == 0


# 道具のコードが読む鍵。表と読む側がずれると、読まれている鍵を知らない鍵と言い、値の表への書き込みを全部止める（PR #59 のレビュー）。
# 値の表を読む file は全部ここに載せる（載っていない file が値の表を読むと赤＝知らない読み口は既定で止める）。
# 鍵を読む形は字の形で並べた網で、並べない形（別名・分割代入・鍵の名を組み立てる形）は通る。表とコードがずれた時の本当の止めは values_keys 自身
# （コードが読む鍵を表が持たなければ、その鍵を書いた値の表への AI の書き込みが止まり、止めた文が土台の表に行を足す道を示す）。
_読む口 = {   # path: その file が読む値の表の枠
    "plugins/docs-kit/skills/qa-html/check.mjs": ("docs-kit", "qa-html"),
    "plugins/dev-flow/skills/codex/codex_pack.py": ("dev-flow", "codex"),
    "plugins/dev-flow/skills/spec-doc/seal.py": ("dev-flow", "spec-doc"),
    "plugins/docs-kit/skills/make-deck/scripts/finish_deck.py": ("docs-kit", "make-deck"),
    "plugins/docs-kit/skills/make-deck/scripts/render_prompt.py": ("docs-kit", "make-deck"),
    "plugins/session-watch/scripts/session_watch.py": ("session-watch", "watch-log"),
    **{f"plugins/guard/scripts/{p.name}": ("guard",) for p in (ROOT / "plugins/guard/scripts").glob("*.py")},
}
_読まない口 = {   # 値の表に触れるが鍵を読まない file: 理由
    **{f"plugins/{p}/lib/skill_values.py": "読む口の本体（土台の skill-values/ への symlink・鍵は呼ぶ側が渡す）"
       for p in ("dev-flow", "docs-kit", "guard")},
}
_値の表に触れる = re.compile(r"skill-values|skill_values|SKILL_VALUES|guard_common|\bvals\b")
_鍵を読む形 = [
    re.compile(r"\b(?:values|vals|company)\s*(?:\.get\(\s*|\[\s*)[\"']([A-Za-z_]+)[\"']"),
    re.compile(r"\bcompany\??\.([A-Za-z_]+)"),
    re.compile(r"skill_values\.get\((?:\*mk|\"docs-kit\", \"make-deck\"),\s*\"([A-Za-z_]+)\""),
]


def _コードが読む鍵(rel, text):
    return {k for pat in _鍵を読む形 for k in pat.findall(text)}


def test_values_keys_値の表を読む_file_は全部読む口に載る():
    out = subprocess.run(["git", "ls-files", "plugins"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    touch = [r for r in out if r.endswith((".py", ".mjs", ".js", ".sh")) and _値の表に触れる.search((ROOT / r).read_text(encoding="utf-8"))]
    assert "plugins/dev-flow/skills/spec-doc/seal.py" in touch, "拾い方が壊れた"
    unknown = [r for r in touch if r not in _読む口 and r not in _読まない口]
    assert not unknown, f"値の表を読むのに読む口に載っていない file（載せて鍵を照らす）: {unknown}"
    assert not [r for r in [*_読む口, *_読まない口] if not (ROOT / r).is_file()], "読む口の表に古い行"


def test_values_keys_道具のコードが読む鍵は全部_SKILL_の表に在る():
    """check.mjs の company.later_lead のように、表に載せずにコードだけが読む鍵があると赤。"""
    missing = []
    for rel, head in _読む口.items():
        for k in sorted(_コードが読む鍵(rel, (ROOT / rel).read_text(encoding="utf-8"))):
            table = {head[0]: {k: 1}} if len(head) == 1 else {head[0]: {head[1]: {k: 1}}}
            if [p for p in VK.unknown(table) if "知らない鍵" in p or "畳んだ鍵" in p]:
                missing.append(f"{rel}: {k}")
    assert not missing, missing


@pytest.mark.parametrize("rel, code", [
    ("plugins/dev-flow/skills/spec-doc/seal.py", 'x = values.get("zz_new_key")'),
    ("plugins/guard/scripts/context_size.py", 'x = vals.get("zz_ctx")'),
    ("plugins/docs-kit/skills/qa-html/check.mjs", 'const x = company["zz_lead"];'),
    ("plugins/docs-kit/skills/qa-html/check.mjs", "const x = company?.zz_lead;"),
])
def test_values_keys_表に無い鍵をコードが読み始めると赤(rel, code):
    """注入の試験: 読む口のどの形で表に無い鍵を読み足しても名指す。"""
    text = (ROOT / rel).read_text(encoding="utf-8") + "\n" + code + "\n"
    head = _読む口[rel]
    got = [k for k in _コードが読む鍵(rel, text) if k.startswith("zz_")]
    assert got and VK.unknown({head[0]: {got[0]: 1}} if len(head) == 1 else {head[0]: {head[1]: {got[0]: 1}}})


def test_values_keys_表から鍵の行を消すと読む口の試験が赤(monkeypatch):
    """注入の試験: 鍵の一覧（schema.json）から qa-html の later_lead を消すと、上の試験が名指す。"""
    import copy
    sch = copy.deepcopy(VK.SV.schema())
    sch["sections"]["docs-kit"]["skills"]["qa-html"]["keys"].pop("later_lead")
    monkeypatch.setattr(VK.SV, "_SCHEMA", sch)
    with pytest.raises(AssertionError, match="later_lead"):
        test_values_keys_道具のコードが読む鍵は全部_SKILL_の表に在る()
