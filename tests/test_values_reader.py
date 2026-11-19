"""値の表を読む土台の道具は、1 つの読み口（guard の values_keys・G.Strict）を通し、表に無い鍵を読むと実行の時に止まるか（注入の試験）。

前の形は道具のコードの字の形を並べた網（`values.get("…")` など）で照らし、並べない形（別名・分割代入・鍵の名を組み立てる形）で
表に無い鍵を読んでも緑だった。今の形は読む時に照らす: 読み口が SKILL.md の「repo ごとの値」の表（guard は DEFAULTS）に
載った鍵だけを読ませる。ここでは、前の網を抜けた形でわざと表に無い鍵を読み、止まるのを見る。入力は全部作り物。
読み口を通らずに値の表を直に開く道具を足す形は構造で塞げない＝チェック役の点 10（review-pr）へ名指しで回す。
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fresh(monkeypatch):
    """読み口の module の控え（sys.modules["af_values_keys"]）を試験ごとに捨てる。"""
    monkeypatch.delitem(sys.modules, "af_values_keys", raising=False)
    yield


def _table(tmp_path, data):
    p = tmp_path / "skill-values.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


# ── guard（G.values） ──
def test_guard_の値は_DEFAULTS_に無い鍵を読むと止まる():
    G = load(PLUGINS / "guard/scripts/guard_common.py", "guard_common_t")
    vals = G.values({})
    assert vals.get("context_limit") == G.DEFAULTS["context_limit"]
    k = "zz_" + "ctx"                                  # 鍵の名を組み立てる形
    for read in (lambda v: v.get(k), lambda v: v[k], lambda v: k in v, lambda v: v.copy().get(k)):
        with pytest.raises(G.UnknownKey):
            read(vals)


def _copy_guard(tmp_path, extra):
    d = tmp_path / "guard" / "scripts"
    shutil.copytree(PLUGINS / "guard/scripts", d, ignore=shutil.ignore_patterns("__pycache__"))
    (d / "zz_reader.py").write_text(extra, encoding="utf-8")
    (d / "zz_deny.py").write_text('HOOKS = {"pre": "check"}\n\n\ndef check(data, vals):\n    return "作り物の止め"\n',
                                  encoding="utf-8")   # 他の見張りの止め（消えてはいけない）
    return d


def _pre(scripts, env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "GUARD_STRICT"))}
    env.update(env_extra)
    return subprocess.run([sys.executable, "-B", str(scripts / "guard.py"), "pre"], capture_output=True, text=True, env=env,
                          input=json.dumps({"tool_name": "Bash", "session_id": "s1", "tool_input": {"command": "echo 作り物"}}))


def test_表に無い鍵を読む見張りは試験で赤_窓の中では他の止めを消さない(tmp_path):
    """注入: 別名と分割代入で表に無い鍵を読む見張りを足す。試験の時は exit 3、窓の中では exit 0 で他の見張りの止めは残る。"""
    d = _copy_guard(tmp_path, 'HOOKS = {"pre": "check"}\n\n\ndef check(data, vals):\n'
                              '    v = vals\n    name = "zz_" + "new"\n    return v.get(name) or ""\n')
    strict = _pre(d, {"GUARD_STRICT_KEYS": "1", "AF_GUARD_TMP": str(tmp_path / "t")})
    assert strict.returncode == 3 and "zz_new" in strict.stderr
    live = _pre(d, {"AF_GUARD_TMP": str(tmp_path / "t")})
    assert live.returncode == 0 and "zz_new" in live.stderr
    out = json.loads(live.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "作り物の止め" in out["permissionDecisionReason"]
    ok = _copy_guard(tmp_path / "ok", 'HOOKS = {"pre": "check"}\n\n\ndef check(data, vals):\n'
                                      '    return "" if vals.get("context_limit") else "x"\n')
    r = _pre(ok, {"GUARD_STRICT_KEYS": "1", "AF_GUARD_TMP": str(tmp_path / "t")})
    assert r.returncode == 0 and "作り物の止め" in r.stdout


def test_試験の全体は表に無い鍵の読みを赤にする():
    assert os.environ.get("GUARD_STRICT_KEYS") == "1", "tests/conftest.py が GUARD_STRICT_KEYS を立てていない"


# ── dev-flow（codex_pack・seal） ──
@pytest.mark.parametrize("rel, name, frame, known", [
    ("dev-flow/skills/codex/codex_pack.py", "codex_pack_t", "codex", "pack_dir"),
    ("dev-flow/skills/spec-doc/seal.py", "seal_t", "spec-doc", "template_dir"),
])
def test_dev_flow_の道具は表に無い鍵を読むと止まる(tmp_path, fresh, rel, name, frame, known):
    mod = load(PLUGINS / rel, name)
    p = _table(tmp_path, {"dev-flow": {frame: {known: "作り物", "zz_new": 1}}})
    vals = mod.load_values(tmp_path, str(p))
    assert vals.get(known) == "作り物"
    VK = sys.modules["af_values_keys"]
    alias = vals                                       # 別名
    with pytest.raises(VK.G.UnknownKey):
        alias.get("zz_" + "new")                       # 鍵の名を組み立てる形
    with pytest.raises(VK.G.UnknownKey):
        _ = {"x": alias["zz_new"]}
    empty = mod.load_values(tmp_path / "無い", None) if frame == "codex" else mod.load_values(None, None)
    with pytest.raises(VK.G.UnknownKey):               # 値の表が無い repo でも同じ照らし（表の中身に依らない）
        empty.get("zz_new")


# ── docs-kit（make-deck の skill_values・qa-html の check.mjs） ──
def test_make_deck_の読み口は表に無い鍵を引くと止まる(tmp_path, fresh):
    SV = load(PLUGINS / "docs-kit/skills/make-deck/scripts/skill_values.py", "skill_values_t")
    table = {"docs-kit": {"make-deck": {"accent": "#123456", "zz_new": "x"}}}
    assert SV.get("docs-kit", "make-deck", "accent", table=table) == "#123456"
    mk = ("docs-kit", "make-deck")
    with pytest.raises(sys.modules["af_values_keys"].G.UnknownKey):
        SV.get(*mk, "zz_" + "new", default="", table=table)
    with pytest.raises(sys.modules["af_values_keys"].G.UnknownKey):
        SV.get(*mk, "zz_new", default="", table={})    # 値の表が空でも止まる


def node(code, cwd=ROOT, check_mjs=PLUGINS / "docs-kit/skills/qa-html/check.mjs"):
    if not shutil.which("node"):
        pytest.skip("node が無い（qa-html の検査は node で動く）")
    src = f"import {{ strictCompany }} from {json.dumps(check_mjs.as_uri())};\n{code}"
    return subprocess.run(["node", "--input-type=module", "-e", src], cwd=cwd, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("code", [
    "const c = strictCompany({}); const { zz_lead } = c;",                  # 分割代入
    "const c = strictCompany({}); const k = 'zz_' + 'lead'; c[k];",         # 鍵の名を組み立てる
    "const c = strictCompany({}); const d = c; d?.zz_lead;",                # 別名と ?.
    "const c = strictCompany({}); 'zz_lead' in c;",                         # 在るかを問う
])
def test_qa_html_の検査は表に無い鍵を読むと止まる(code):
    r = node(code)
    assert r.returncode != 0 and "zz_lead" in r.stderr, r.stderr


def test_qa_html_の検査は表に載った鍵と元の名を通す():
    r = node("const c = strictCompany({ later_lead: 'x' }); console.log(c.later_lead, c.limits ?? '-', String(c.toString === Object.prototype.toString), JSON.stringify({...c}));")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["x", "-", "true", '{"later_lead":"x"}']


# ── 表の行を消すと、読んでいる道具が止まる（表とコードのずれを読む所で出す） ──
def _copy_plugins(dst):
    for name in ("guard", "dev-flow", "docs-kit", "core", "checker", "session-watch"):
        shutil.copytree(PLUGINS / name, dst / name, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def _drop_row(md, key):
    t = md.read_text(encoding="utf-8")
    lines = [ln for ln in t.splitlines(keepends=True) if not ln.startswith(f"| `{key}`")]
    assert len(lines) < len(t.splitlines()), f"{key} の行が無い"
    md.write_text("".join(lines), encoding="utf-8")


def test_表から鍵の行を消すと_その鍵を読む道具が止まる(tmp_path, fresh):
    d = _copy_plugins(tmp_path / "plugins")
    _drop_row(d / "dev-flow/skills/codex/SKILL.md", "pack_dir")
    mod = load(d / "dev-flow/skills/codex/codex_pack.py", "codex_pack_drop")
    vals = mod.load_values(tmp_path, str(_table(tmp_path, {"dev-flow": {"codex": {"pack_dir": "x"}}})))
    with pytest.raises(sys.modules["af_values_keys"].G.UnknownKey):
        vals.get("pack_dir")
    _drop_row(d / "docs-kit/skills/qa-html/SKILL.md", "docs-kit.qa-html.later_lead")
    r = node("strictCompany({}).later_lead;", check_mjs=d / "docs-kit/skills/qa-html/check.mjs")
    assert r.returncode != 0 and "later_lead" in r.stderr
    r = node("strictCompany({}).later_lead;")                  # 元の表（行が在る）では通る
    assert r.returncode == 0, r.stderr


# ── 在り処: 入れた plugin の形でも隣の guard を読み、guard が無ければ止まる ──
def test_入れた_plugin_の形でも読み口を見つけ_無ければ止まる(tmp_path, fresh):
    market = tmp_path / "cache" / "市場"
    for name in ("guard", "dev-flow", "docs-kit"):
        shutil.copytree(PLUGINS / name, market / name / f"{name}-v1", ignore=shutil.ignore_patterns("__pycache__"))
    mod = load(market / "dev-flow/dev-flow-v1/skills/codex/codex_pack.py", "codex_pack_cache")
    assert Path(mod.values_reader().__file__).resolve() == (market / "guard/guard-v1/scripts/values_keys.py").resolve()
    r = node("console.log(String(strictCompany({later_lead: 'y'}).later_lead));",
             check_mjs=market / "docs-kit/docs-kit-v1/skills/qa-html/check.mjs")
    assert r.returncode == 0 and r.stdout.strip() == "y", r.stderr
    shutil.rmtree(market / "guard")
    sys.modules.pop("af_values_keys", None)
    with pytest.raises(mod.Abort, match="読み口"):
        mod.values_reader()
    r = node("strictCompany({});", check_mjs=market / "docs-kit/docs-kit-v1/skills/qa-html/check.mjs")
    assert r.returncode != 0 and "読み口" in r.stderr


def test_読み口は鍵の一覧を_JS_の道具へ渡す():
    r = subprocess.run([sys.executable, str(PLUGINS / "guard/scripts/values_keys.py"), "--keys", "docs-kit", "qa-html"],
                       capture_output=True, text=True, check=True)
    got = json.loads(r.stdout)
    assert "later_lead" in got["keys"] and "customer" in got["keys"] and got["any"] is False
