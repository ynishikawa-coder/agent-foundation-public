"""閉じた語彙の注入の試験（guard・値の表・Blueprint）: 表に無い値を黙って通さない。

前の形はどれも、表に無い値を「表の外＝どれかの既定」に倒して通した:
  - unanswered の drop: --why は自由な文で、どんな訳でも問いを降ろした。
  - guard_common の seeded_by_record: 頼みの行の印が人の印の表に無ければ全部「別の窓から来た」と見た（打ち間違いの印で子の窓）。
  - context_size: 後継へ渡す返し先を「継ぐ」とだけ書き、AI の覚えから写させた（記録の値を示さない）。
  - skill_values: 土台の欄でない頂の欄は全部 repo 自身の物と見て照らしを飛ばした（`gaurd` の打ち間違いが黙って効かない）。
  - Blueprint の selftest: 表に無い fate・kind・mode を OK に数え、置き場の知らない札を「保存される」で描いた。
今の形: 値ごとに閉じた表を 1 か所に置き、表に無い値は名指して拒む（印は別の記録で決める）。
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

import needs
from test_guard import env  # noqa: F401  （env は fixture）
from test_guard_context_stop import over_log, stop_hook

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(path).parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


UNANSWERED = ROOT / "plugins" / "guard" / "scripts" / "unanswered.py"


# ── unanswered: 降ろす訳 ──
def test_降ろす訳の表は_3_つ():
    uq = _load(UNANSWERED, "unanswered_cv")
    assert list(uq.DROP_WHY) == ["答え済み", "要らない", "言い直した"]


@pytest.mark.parametrize("why", ["済んだ", "答え済", "なんとなく", "要らない。", "Answered"])
def test_表に無い訳では問いを降ろさない(why):
    uq = _load(UNANSWERED, "unanswered_cv2")
    assert uq.drop_why(why) is None
    data = {"pending": [{"key": "k1", "question": "作り物の問い"}]}
    with pytest.raises(ValueError):
        uq.drop(data, ["k1"], why)
    assert data["pending"] == [{"key": "k1", "question": "作り物の問い"}]


def test_訳の後ろの一言は控えに残り訳は表の字のまま():
    uq = _load(UNANSWERED, "unanswered_cv3")
    assert uq.drop_why("答え済み この窓の頼みで出た") == ("答え済み", "この窓の頼みで出た")
    data = {"pending": [{"key": "k1", "question": "作り物の問い"}]}
    gone = uq.drop(data, ["k1"], "答え済み", "この窓の頼みで出た")
    assert len(gone) == 1 and data["pending"] == []
    assert data["dropped_recent"][-1]["why"] == "答え済み" and data["dropped_recent"][-1]["note"] == "この窓の頼みで出た"


def test_降ろしの口は表に無い訳を_2_で止め問いを残す(env):  # noqa: F811
    from test_guard import ask_result, hook
    from test_guard import run_cli
    hook(env, "post", ask_result())
    key = run_cli(env, "list").stdout.split("\t")[0]
    p = run_cli(env, "drop", key, "--why", "済んだ")
    assert p.returncode == 2 and "降ろす訳の表に無い" in p.stderr, p.stderr
    assert key in run_cli(env, "list").stdout


# ── guard_common: 頼みの行の印 ──
@pytest.fixture
def G():
    return _load(ROOT / "plugins" / "guard" / "scripts" / "guard_common.py", "guard_common_cv")


@pytest.mark.parametrize("kind", ["humna", "Human", "agent", "unknown-new-kind"])
def test_表に無い印だけでは子の窓と決めない(G, kind):
    """前の形は人の印の表に無い印を全部「別の窓から来た」と見た（打ち間違いの印で子の窓に倒れる）。"""
    assert G.seeded_by_record({"origin": {"kind": kind}}) is False
    assert G.seeded_by_record({"origin": {"kind": kind}, "promptSource": "system"}) is True


def test_表に在る印は記録どおりに決まる(G):
    for kind in G.HUMAN_ORIGINS:
        assert G.seeded_by_record({"origin": {"kind": kind}, "promptSource": "system"}) is False
    for kind in G.SEEDED_ORIGINS:
        assert G.seeded_by_record({"origin": {"kind": kind}}) is True
    assert set(G.HUMAN_ORIGINS).isdisjoint(G.SEEDED_ORIGINS)


# ── context_size: 後継へ渡す返し先 ──
def test_子の窓の差し戻しは記録の返し先を字のまま示す(env, tmp_path):  # noqa: F811
    why = stop_hook(env, over_log(tmp_path, 400_000, first="作り物の頼み。\n返し先 ＝ session_01AbcXyz9\n",
                                  origin="task-notification"))
    assert "`返し先=session_01AbcXyz9`" in why, why


def test_人の窓の差し戻しは別の窓の返し先を書かせない(env, tmp_path):  # noqa: F811
    """人が打った頼みの文に返し先の字が在っても、記録が人の印なら別の窓の返し先を示さない。"""
    why = stop_hook(env, over_log(tmp_path, 400_000, first="返し先=session_01AbcXyz9 と書いた貼り付け",
                                  origin="human"))
    assert "session_01AbcXyz9" not in why and "オーナーへ返す窓" in why, why


# ── skill_values: 頂の欄 ──
SV = ROOT / "skill-values" / "skill_values.py"


def _sv_check(tmp_path, table):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "skill-values.json").write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    return subprocess.run([sys.executable, str(SV), "check"], cwd=tmp_path, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("table,named", [
    ({"repo_sections": [], "gaurd": {"context_limit": 1000}}, "gaurd は知らない頂の欄"),
    ({"repo_sections": ["javis"], "jarvis": {"x": 1}, "javis": {"x": 1}}, "jarvis は知らない頂の欄"),
    ({"repo_sections": "javis", "javis": {"x": 1}}, "repo_sections の型が違う"),
    ({"repo_sections": ["guard"]}, "repo_sections の guard は土台の欄"),
])
def test_知らない頂の欄を名指す(tmp_path, table, named):
    p = _sv_check(tmp_path, table)
    assert p.returncode != 0 and named in (p.stdout + p.stderr), p.stdout + p.stderr


def test_repo_sections_に並べた欄は照らさない(tmp_path):
    p = _sv_check(tmp_path, {"_readme": "注", "repo_sections": ["javis"], "javis": {"何でも": 1}})
    assert p.returncode == 0 and "前の形" not in p.stderr, p.stdout + p.stderr


@pytest.mark.parametrize("table,names", [
    ({"gaurd": {"context_limit": 1000}}, ["gaurd"]),
    ({"javis": {"x": 1}, "guard": {"context_limit": 1000}}, ["javis"]),
])
def test_壊れる_1_段目_repo_sections_の無い表は止めずに名指す(tmp_path, table, names):
    """CONTRIBUTING.md §8 の 1 段目: 前の形（repo_sections の無い表）は通し続け、頂の欄の名を並べて知らせる。"""
    p = _sv_check(tmp_path, table)
    assert p.returncode == 0, p.stdout + p.stderr
    for n in names:
        assert n in p.stderr and "前の形" in p.stderr and "repo_sections" in p.stderr, p.stderr


# ── Blueprint: fate・kind・mode ──
BP_DIR = ROOT / "plugins" / "docs-kit" / "skills" / "blueprint"


@pytest.mark.parametrize("old,new,named", [
    ("fate:'keep',\n  shelves", "fate:'kept',\n  shelves", "store: 札（fate）が札の表"),
    ("name:'貸出の記録',d:'「借りる」で 1 行',fate:'keep'", "name:'貸出の記録',d:'「借りる」で 1 行',fate:'saved'",
     "p1/s11: 札（fate）が札の表"),
    ("{id:'s12',kind:'calc'", "{id:'s12',kind:'calcu'", "p1/s12: kind が表"),
    ("mode:'current',", "mode:'curent',", "META.mode が版の表"),
])
def test_Blueprint_の表に無い値は_selftest_が_NG(tmp_path, old, new, named):
    """枠の selftest を実ブラウザ（node の playwright）で動かし、検査の道具と同じ #selftest の字を読む。
    道具の Chrome の --dump-dom は CI の Chromium で DOM を返さない事がある（道具の起こし方の試験は test_docs_kit が持つ）。"""
    node = needs.node_playwright()
    src = (BP_DIR / "references" / "template.html").read_text(encoding="utf-8")
    assert src.count(old) == 1, old
    script = tmp_path / "run.cjs"
    script.write_text("""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();   // ブラウザの file が在るのに起こせなければ赤（needs.node_playwright が file を見た）
  const pg = await b.newPage();
  await pg.goto(process.argv[2] + '?selftest');
  await pg.waitForSelector('#selftest', { state: 'attached', timeout: 60000 });
  console.log(JSON.stringify(await pg.textContent('#selftest')));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
""", encoding="utf-8")

    def selftest(text):
        page = tmp_path / "bp.html"
        page.write_text(text, encoding="utf-8")
        r = subprocess.run([node, str(script), page.as_uri()], capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout).strip()

    bad = selftest(src.replace(old, new))
    assert not bad.startswith("SELFTEST OK") and named in bad, bad
    assert selftest(src).startswith("SELFTEST OK")
