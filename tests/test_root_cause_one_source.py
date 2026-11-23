"""止めた・赤の知らせに付ける根治の 1 文（「直し: …意図（…）とのずれから入り、…原因を細目 §3「まず構造を疑う」で探して直す」）が、
skill-values/root_cause.py の 1 本の口から出て、道具ごとの写しに戻らないかを見る。

意図: 根治の 1 文の形を 1 か所で持ち、形を直す時に 1 か所だけ直せば全部の道具の知らせが揃う。
課題: 同じ形の文が道具ごとに 30 か所近く手で写され、形を変えるたびに写しの直し漏れと量の膨らみが出た。
原因: 文の形を持つ正本が無く、道具を足すたびに前の道具の文を真似て写した。
入力は全部作り物。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill-values"))
from root_cause import ENTRY, root_cause  # noqa: E402

# 写しの印: 文の形の真ん中（意図の括弧の後の決まった句）。
COPY = re.compile(r"とのずれから入")
SUFFIXES = {".py", ".sh", ".mjs", ".js"}

# まだ 1 本の口へ寄せていない所（持ち主は後の段の窓・PR の「残り」に在る）。寄せたら消す。ここに無い所に写しが出たら赤。
REMAINING = {
    "plugins/checker/scripts/pr_writer.py",
    "plugins/checker/scripts/review_gate.py",
    "plugins/dev-flow/skills/codex/codex_pack.py",
    "plugins/dev-flow/skills/spec-doc/seal.py",
    "plugins/docs-kit/skills/theory-mock/scripts/check_theory_mock.py",
    "plugins/docs-kit/skills/big-picture/scripts/big_picture.py",
    "plugins/docs-kit/skills/make-deck/scripts/render_prompt.py",
    "plugins/docs-kit/skills/make-deck/scripts/finish_deck.py",
    "plugins/docs-kit/skills/qa-html/check.mjs",
    "plugins/docs-kit/skills/blueprint/scripts/check_blueprint.py",
    "plugins/core/scripts/copies.py",
    "plugins/core/scripts/kaku.py",
    "plugins/core/scripts/refs.py",
    "scripts/checks/conftest_teeth.sh",
    "scripts/checks/public_guard.sh",
    "scripts/check_all.sh",
    "public-guard/guard.py",
    "public-guard/patrol.py",
}


def copies(text):
    """文の形を手で写した行（1 本の口の外）を返す。"""
    return [l.strip()[:100] for l in text.splitlines() if COPY.search(l)]


def offenders():
    out = {}
    for base in ("plugins", "scripts", "skill-values", "public-guard"):
        for f in (ROOT / base).rglob("*"):
            if f.suffix not in SUFFIXES or not f.is_file() or f.is_symlink():
                continue
            rel = str(f.relative_to(ROOT))
            if rel == "skill-values/root_cause.py":
                continue
            if b := copies(f.read_text(encoding="utf-8")):
                out[rel] = b
    return out


def test_根治の1文は1本の口の外に写されない():
    bad = {k: v for k, v in offenders().items() if k not in REMAINING}
    assert not bad, "根治の 1 文を写さず skill-values/root_cause.py の root_cause() を呼ぶ: %s" % bad


def test_注入_写した1文が戻ると拒む():
    restored = 'ROOT_CAUSE = "直し: 出し直すだけで済ませず、意図（守る物）とのずれから入り、その形が出た原因を細目 §3「まず構造を疑う」で探して直す"'
    assert copies(restored)
    assert not copies('ROOT_CAUSE = root_cause("守る物")')


def test_寄せた道具は口を呼ぶ():
    for rel in ("plugins/guard/scripts/guard.py", "plugins/guard/scripts/unanswered.py", "plugins/guard/scripts/values_keys.py",
                "plugins/session-watch/scripts/session_watch.py", "skill-values/skill_values.py",
                "scripts/plugin_smoke.py", "scripts/pr_overlap.py", "scripts/pr_shape.py", "scripts/conflict_markers.py",
                "scripts/setup_plugins.py", "scripts/call_flows.py", "scripts/changelog.py", "scripts/ruleset_apply.py"):
        assert "root_cause(" in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_各_plugin_の_lib_の口は正本への_symlink():
    for p in ("guard", "session-watch", "dev-flow", "docs-kit"):
        f = ROOT / "plugins" / p / "lib" / "root_cause.py"
        assert f.is_symlink() and f.resolve() == (ROOT / "skill-values" / "root_cause.py").resolve(), p


def test_口の文は意図から入り入口を指す():
    s = root_cause("守る物", cause="崩れた", shortcut="出し直す")
    assert s.startswith("直し: 出し直すだけで済ませず、意図（守る物）とのずれから入り、崩れた原因を")
    assert s.endswith(ENTRY + "で探して直す")
    assert s.find("意図") < s.find("原因")
