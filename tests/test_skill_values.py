"""値の表（config/skill-values.json）の読み方が 1 本（skill-values/）で、知らない鍵・畳んだ鍵・型の違う値を黙って捨てないかを見る。

注入の試験: 写しを戻す（道具が自分で表を探す・読み口の写しを置く）・畳んだ鍵を置く・知らない鍵を置く・型を違える、を
わざと入れると赤（道具は止まり、guard は起動の時に名指しする）。入力は全部作り物。
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
SOURCE = ROOT / "skill-values"
PLUGINS = ROOT / "plugins"
SCHEMA = json.loads((SOURCE / "schema.json").read_text(encoding="utf-8"))
SV = SOURCE / "skill_values.py"
GUARD = PLUGINS / "guard" / "scripts" / "guard.py"
CHECK = PLUGINS / "docs-kit" / "skills" / "qa-html" / "check.mjs"
CODEX = PLUGINS / "dev-flow" / "skills" / "codex" / "codex_pack.py"
RENDER = PLUGINS / "docs-kit" / "skills" / "make-deck" / "scripts" / "render_prompt.py"
GOOD_PAGE = ROOT / "tests" / "docs_kit" / "good.json"

needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node が無い（qa-html の検査は node で動く）")


def clean_env(**extra):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    e.update(extra)
    return e


def make_repo(tmp_path, table):
    r = tmp_path / "repo"
    (r / "config").mkdir(parents=True)
    (r / "sub" / "deep").mkdir(parents=True)
    (r / "tools").mkdir()
    (r / "tools" / "calc.py").write_text("X = 1\n", encoding="utf-8")
    (r / "config" / "skill-values.json").write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    return r


def sv(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, str(SV), *args], cwd=cwd, env=env or clean_env(),
                          capture_output=True, text=True)


# ── 正本は 1 つ: 各 plugin の lib/ は symlink・道具は自分で表を探さない ──
USERS = ("docs-kit", "dev-flow", "guard")   # 値の表を道具が読む plugin


@pytest.mark.parametrize("plugin", USERS)
@pytest.mark.parametrize("name", ["skill_values.py", "schema.json"])
def test_plugin_の読み口は正本への_symlink(plugin, name):
    p = PLUGINS / plugin / "lib" / name
    assert p.is_symlink(), f"{p.relative_to(ROOT)} が写し（正本 skill-values/{name} への symlink にする）"
    assert p.resolve() == (SOURCE / name).resolve()


LITERAL = re.compile(r"""["']skill-values\.json["']""")


def code_files():
    for p in PLUGINS.rglob("*"):
        if p.suffix in (".py", ".mjs", ".js") and p.is_file() and "lib" not in p.relative_to(PLUGINS).parts:
            yield p


def test_道具は表を自分で探さない_読み口の写しも置かない():
    bad = [str(p.relative_to(ROOT)) for p in code_files()
           if p.name == "skill_values.py" or LITERAL.search(p.read_text(encoding="utf-8"))]
    assert bad == [], f"値の表を自分で探す・読む写し（lib/skill_values.py を使う）: {bad}"


def test_写しを戻すと照らしが赤になる(tmp_path):
    """注入: make-deck に前の読み口の写しを戻す・道具に表の path を書く → 上の照らしが拾う。"""
    copy = tmp_path / "skill_values.py"
    copy.write_text('REL_PATH = os.path.join("config", "skill-values.json")\n', encoding="utf-8")
    assert copy.name == "skill_values.py" and LITERAL.search(copy.read_text(encoding="utf-8"))


def test_鍵の一覧の型は決まった物だけ():
    def walk(where, keys):
        for k, raw in keys.items():
            spec = {"type": raw} if isinstance(raw, str) else raw
            assert spec["type"] in ("str", "int", "bool", "list", "dict", "text", "any"), f"{where}.{k}"
            if "keys" in spec:
                walk(f"{where}.{k}", spec["keys"])
    for plugin, sec in SCHEMA["sections"].items():
        walk(plugin, sec.get("keys", {}))
        for skill, sk in sec.get("skills", {}).items():
            walk(f"{plugin}.{skill}", sk.get("keys", {}))
            assert (PLUGINS / plugin / "skills" / skill / "SKILL.md").is_file(), f"{plugin}.{skill} の skill が無い"


def test_鍵の一覧に全部の_plugin_と_skill_がある():
    for d in PLUGINS.iterdir():
        if (d / ".claude-plugin" / "plugin.json").is_file():
            assert d.name in SCHEMA["sections"], f"plugin {d.name} の欄が鍵の一覧に無い"
            if "keys" in SCHEMA["sections"][d.name]:
                continue   # 欄の直下に鍵を持つ plugin（guard）
            for s in (d / "skills").glob("*/SKILL.md") if (d / "skills").is_dir() else []:
                assert s.parent.name in SCHEMA["sections"][d.name].get("skills", {}), f"{d.name}.{s.parent.name} が無い"


# ── SKILL.md の鍵の表と鍵の一覧が食い違わない ──
def table_keys(text):
    m = re.search(r"^## (?:repo ごとの値|値の表).*?(?=^## )", text, re.S | re.M)
    out = set()
    for line in (m.group(0) if m else "").splitlines():
        if line.startswith("| `"):
            out |= set(re.findall(r"`([A-Za-z0-9_.\-*]+)`", line.split("|")[1]))
    return out


def skill_specs():
    for plugin, sec in SCHEMA["sections"].items():
        for skill, sk in sec.get("skills", {}).items():
            yield plugin, skill, sk.get("keys", {})


@pytest.mark.parametrize("plugin,skill,keys", list(skill_specs()), ids=lambda x: x if isinstance(x, str) else "")
def test_SKILL_md_の鍵は鍵の一覧と同じ(plugin, skill, keys):
    text = (PLUGINS / plugin / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    for tok in table_keys(text):
        parts = tok.rstrip(".*").split(".")
        if parts[0] == "common":
            assert parts[1] in SCHEMA["sections"]["common"]["keys"], f"{plugin}.{skill}: {tok} が鍵の一覧に無い"
            continue
        if parts[:2] == [plugin, skill]:
            parts = parts[2:]
        assert parts[0] in keys, f"{plugin}.{skill}: SKILL.md の鍵 {tok} が鍵の一覧（skill-values/schema.json）に無い"
    for k in keys:
        assert re.search(r"`(?:[\w.\-]+\.)?%s(?:\.\*)?`" % re.escape(k), text), \
            f"{plugin}.{skill}: 鍵の一覧の {k} を SKILL.md が書いていない"


def test_guard_の鍵は_guard_rules_の例と同じ():
    text = (PLUGINS / "guard" / "skills" / "guard-rules" / "SKILL.md").read_text(encoding="utf-8")
    example = json.loads(re.search(r"```json\n(.*?)```", text, re.S).group(1))
    assert set(example["guard"]) == set(SCHEMA["sections"]["guard"]["keys"])


def test_common_の鍵はどれかの_SKILL_md_が使う():
    texts = "\n".join(p.read_text(encoding="utf-8") for p in PLUGINS.glob("*/skills/*/SKILL.md"))
    for k in SCHEMA["sections"]["common"]["keys"]:
        assert f"common.{k}" in texts, f"common.{k} を使う skill が無い"


# ── 照らし（1 本の口） ──
def test_表が無い_鍵が無い_空なら問題なし(tmp_path):
    r = make_repo(tmp_path, {"docs-kit": {"make-deck": {"accent": ""}, "qa-html": {"limits": ""}}, "guard": {"qa_page_exempt": ""},
                             "dev-flow": {"codex": {"self_allow": "", "pack_dir": []}}})   # 型の違う空も既定で動く
    res = sv("check", cwd=r / "sub")
    assert res.returncode == 0, res.stderr
    empty = tmp_path / "empty"
    empty.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=empty, check=True)
    assert sv("check", cwd=empty).returncode == 0


def test_repo_自身の欄と注は照らさない(tmp_path):
    r = make_repo(tmp_path, {"_readme": "注", "説明": "x", "gate": {"terms": []},
                             "javis": {"x": {"y": 1}}, "docs-kit": {"_readme": "注", "qa-html": {"_note": 1}}})
    assert sv("check", cwd=r).returncode == 0


@pytest.mark.parametrize("table,word", [
    ({"dev-flow": {"register-rule": {"agents_table": []}}}, "dev-flow.register-rule.agents_table は畳んだ鍵"),
    ({"dev-flow": {"codex": {"pack_dri": "x"}}}, "dev-flow.codex.pack_dri は知らない鍵"),
    ({"docs-kit": {"qa-htm": {}}}, "docs-kit.qa-htm は知らない skill の欄"),
    ({"guard": {"context_limit": "300000"}}, "guard.context_limit の型が違う"),
    ({"guard": {"context_limt": 1}}, "guard.context_limt は知らない鍵"),
    ({"docs-kit": {"qa-html": {"customer": {"check_cmmd": "x"}}}}, "docs-kit.qa-html.customer.check_cmmd は知らない鍵"),
    ({"common": {"save_dir": ["a"]}}, "common.save_dir の型が違う"),
    ({"common": {"rules": {"no_confirm": "x"}}}, "common.rules は畳んだ鍵"),          # 束 B（PR #43）で畳んだ写し
    ({"dev-flow": {"verify": {"code_done_rule": "x"}}}, "dev-flow.verify.code_done_rule は畳んだ鍵"),
    ({"dev-flow": {"codex": {"task_rule": "x"}}}, "dev-flow.codex.task_rule は畳んだ鍵"),          # 原因の台帳へ移した（#36）
    ({"dev-flow": {"preimpl-cleanup": {"cleanup_followup": "x"}}}, "dev-flow.preimpl-cleanup.cleanup_followup は畳んだ鍵"),
])
def test_知らない鍵_畳んだ鍵_型違いを名指しする(tmp_path, table, word):
    r = make_repo(tmp_path, table)
    res = sv("check", cwd=r / "sub" / "deep")
    assert res.returncode == 1 and word in res.stderr, res.stderr


def test_壊れた表は名指しする(tmp_path):
    r = make_repo(tmp_path, {})
    (r / "config" / "skill-values.json").write_text("{", encoding="utf-8")
    res = sv("section", "guard", cwd=r)
    assert res.returncode == 2 and "JSON として読めない" in res.stderr


def test_探し方は_values_と_SKILL_VALUES_と起点の順(tmp_path):
    r = make_repo(tmp_path, {"guard": {"context_limit": 5}})
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"guard": {"context_limit": 7}}), encoding="utf-8")
    get = lambda *a, **kw: sv("get", "guard", "context_limit", *a, **kw).stdout.strip()  # noqa: E731
    assert get(cwd=r / "sub") == "5"                                           # 今の dir から上へ（repo の根で止まる）
    assert get(cwd=tmp_path, env=clean_env(CLAUDE_PROJECT_DIR=str(r))) == "5"  # 窓の repo
    assert get(cwd=r, env=clean_env(SKILL_VALUES=str(other))) == "7"
    assert get("--values", str(other), cwd=r) == "7"
    missing = sv("get", "guard", "context_limit", "--values", str(tmp_path / "nai.json"), cwd=r)
    assert missing.returncode == 2 and "表の file が無い" in missing.stderr     # 渡した path が無いのを黙って既定にしない


# ── 4 つの道具が同じ表を同じ探し方で見つけ、同じ問題で止まる・知らせる ──
BAD_EVERYWHERE = {
    "guard": {"context_limt": 1},
    "dev-flow": {"codex": {"self_allow": ["tools/*"], "pack_dri": "x"}},
    "docs-kit": {"qa-html": {"limitz": {}}, "make-deck": {"acent": "#000000"}},
}


@needs_node
def test_qa_html_の検査は知らない鍵で赤(tmp_path):
    r = make_repo(tmp_path, BAD_EVERYWHERE)
    res = subprocess.run(["node", str(CHECK), str(GOOD_PAGE), "--json"], cwd=r / "sub", env=clean_env(),
                         capture_output=True, text=True)
    out = json.loads(res.stdout)
    assert res.returncode == 1 and any("docs-kit.qa-html.limitz は知らない鍵" in x for x in out["red"]), out["red"]


@needs_node
def test_qa_html_の検査は_limits_why_の知らない鍵でも赤(tmp_path):
    r = make_repo(tmp_path, {"docs-kit": {"qa-html": {"why": {"onse": "x"}, "limits": {"questions_per_page": "3"}}}})
    res = subprocess.run(["node", str(CHECK), str(GOOD_PAGE), "--json"], cwd=r, env=clean_env(),
                         capture_output=True, text=True)
    red = json.loads(res.stdout)["red"]
    assert any("docs-kit.qa-html.why.onse は知らない鍵" in x for x in red), red
    assert any("docs-kit.qa-html.limits.questions_per_page の型が違う" in x for x in red), red


@needs_node
def test_qa_html_の検査は正しい表なら緑(tmp_path):
    r = make_repo(tmp_path, {"docs-kit": {"qa-html": {"why": {"once": "この月だけの事を確かめます"}}}})
    res = subprocess.run(["node", str(CHECK), str(GOOD_PAGE)], cwd=r / "sub", env=clean_env(),
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


def test_codex_pack_は知らない鍵で中止(tmp_path):
    r = make_repo(tmp_path, BAD_EVERYWHERE)
    res = subprocess.run([sys.executable, str(CODEX), "--task", "t1", "--purpose", "p", "--scope", "s", "--done", "d",
                          "--file", "tools/calc.py", "--out-dir", str(tmp_path / "out"), "--today", "2026-11-11"],
                         cwd=r / "sub", env=clean_env(), capture_output=True, text=True)
    assert res.returncode == 1 and "dev-flow.codex.pack_dri は知らない鍵" in res.stderr, res.stderr
    assert not (tmp_path / "out").exists()


def test_make_deck_は知らない鍵で止まる(tmp_path):
    r = make_repo(tmp_path, BAD_EVERYWHERE)
    thin = tmp_path / "case.json"
    thin.write_text('{"対象": "x"}', encoding="utf-8")   # スロットが欠け、会社の既定の見本を引きに行く
    res = subprocess.run([sys.executable, str(RENDER), "render", "--values", str(thin)],
                         cwd=r / "sub", env=clean_env(), capture_output=True, text=True)
    assert res.returncode == 2 and "docs-kit.make-deck.acent は知らない鍵" in res.stderr, res.stderr


def guard_start(r, tmp_path):
    env = clean_env(CLAUDE_PROJECT_DIR=str(r), AF_GUARD_TMP=str(tmp_path / "t"), AF_GUARD_STATE=str(tmp_path / "s"))
    p = subprocess.run([sys.executable, str(GUARD), "start"], input=json.dumps({"session_id": "s1", "cwd": str(r)}),
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"] if p.stdout.strip() else ""


def test_guard_は起動の時に表全体を名指しで知らせる(tmp_path):
    r = make_repo(tmp_path, {**BAD_EVERYWHERE, "dev-flow": {"register-rule": {"roster": "x"}, **BAD_EVERYWHERE["dev-flow"]}})
    ctx = guard_start(r, tmp_path)
    for w in ("guard.context_limt は知らない鍵", "dev-flow.codex.pack_dri は知らない鍵",
              "docs-kit.make-deck.acent は知らない鍵", "dev-flow.register-rule.roster は畳んだ鍵"):
        assert w in ctx, ctx


def test_guard_は正しい表なら黙る(tmp_path):
    # 聞く前に引く先（ask_prior_lookup）が無い表は、照らしていない事を起動の時に知らせる（prior_ask）ので、引く先を持つ表で見る
    r = make_repo(tmp_path, {"guard": {"context_limit": 1000, "ask_prior_lookup": [{"tool": "mcp__x__search"}]}})
    assert guard_start(r, tmp_path) == ""


def test_guard_は問題の鍵だけ既定で動き守りを止めない(tmp_path, monkeypatch):
    r = make_repo(tmp_path, {"guard": {"context_limit": "多い", "ask_question_max_chars": 30, "nazo": 1}})
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(r))
    monkeypatch.delenv("SKILL_VALUES", raising=False)
    monkeypatch.setattr(sys, "dont_write_bytecode", True)   # plugin の置き場に __pycache__ を作らない
    sys.path.insert(0, str(GUARD.parent))
    try:
        import guard_common as G
        v = G.values({})
    finally:
        sys.path.remove(str(GUARD.parent))
    assert v["context_limit"] == SCHEMA["sections"]["guard"]["keys"]["context_limit"]["default"]
    assert v["ask_question_max_chars"] == 30
    assert "nazo" not in v
