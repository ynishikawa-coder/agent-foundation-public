"""値の表の字・正規表現を、型の正本（skill-values/schema.json の against・match）が言う相手の全体か一部に当てるか（注入の試験）。

どれも「前の誤り（相手の一部に当てる・相手を広く取る・字か正規表現かが割れる）」を入れた時に赤になる形で書く:
相手の一部に当てる読み方へ戻すと、全体に当てる鍵の試験が当たってしまい赤になる。
"""
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
sys.path.insert(0, str(ROOT / "skill-values"))

import skill_values as SV  # noqa: E402
import guard_common as G  # noqa: E402
import ask_shape  # noqa: E402
import context_size  # noqa: E402
import irreversible  # noqa: E402
import outbound  # noqa: E402
import paid_upstream  # noqa: E402
import pick_one  # noqa: E402
import prior_ask  # noqa: E402
import qa_page  # noqa: E402

sys.path.insert(0, str(ROOT / "plugins" / "dev-flow" / "skills" / "codex"))
import codex_pack  # noqa: E402


def specs_all():
    out = []
    for plugin, sec in SV.schema()["sections"].items():
        if "keys" in sec:
            out += [((plugin, None, k), s) for k, s in SV.keys_of(plugin).items()]
        for skill in (sec.get("skills") or {}):
            out += [((plugin, skill, k), s) for k, s in (SV.keys_of(plugin, skill) or {}).items()]
    return out


# 字・正規表現・glob を読む鍵（道具が値を re・in・fnmatch で当てる物）。足したらここにも足す＝型の正本に当て方が無い鍵を拾う。
MATCHED_KEYS = {
    ("guard", None, k) for k in (
        "paid_markers_extra", "irreversible_bash_extra", "irreversible_tools_extra", "qa_page_exempt",
        "ask_inner_terms_extra", "ask_term_allow", "ask_shape_exempt", "ask_pick_one_exempt", "ask_rec_notice_exempt",
        "outbound_secret_allow", "number_request_exempt", "context_handoff", "ask_prior_lookup", "ask_prior_exempt",
        "pr_cleanup_exempt_repos", "pr_words_exempt_repos", "public_repos_extra")
} | {("session-watch", "watch-log", "reply_exempt"), ("dev-flow", "codex", "self_allow"),
     ("dev-flow", "codex", "entropy_allow"), ("dev-flow", "spec-doc", "decision_match_allow")}


def test_字や正規表現を読む鍵は型の正本に当てる相手と当て方を持つ():
    specs = dict(specs_all())
    for at in MATCHED_KEYS:
        s = specs[at]
        if s["type"] in ("repo_names", "globs", "words"):
            continue
        assert s.get("match") in ("whole", "part") and s.get("against"), at
    # 型 patterns は全部 against と match を持つ（当て方の書かれていない patterns を足すと赤）
    for at, s in specs.items():
        if s["type"] == "patterns":
            assert s.get("match") in ("whole", "part") and s.get("against"), at


def test_全体に当てる鍵の既定は全部_錨で始まり終わる():
    for at, s in specs_all():
        if s["type"] == "patterns" and s.get("match") == "whole":
            assert not SV.old_pattern_rows(s, s.get("default") or []), at


def test_全体の行は相手の全体だけに当たり_前の形の行は名指される():
    spec = SV.key_spec("guard", None, "irreversible_tools_extra")
    rows = SV.compile_patterns(spec, ["^mcp__s__delete_item$"])
    assert SV.hit(rows, "mcp__s__delete_item") is not None
    assert SV.hit(rows, "mcp__s__undelete_item") is None        # 一部に当てる読み方へ戻すと赤
    # ^…$ の行でも | で分けた形は、一部に当てると片側の錨が外れる（全体に当てる＝fullmatch でだけ当たらない）
    alt = SV.compile_patterns(spec, ["^mcp__s__delete_item|mcp__s__purge$"])
    assert SV.hit(alt, "mcp__s__delete_item") is not None
    assert SV.hit(alt, "mcp__s__delete_item_undo") is None
    probs = SV.check({"guard": {"irreversible_tools_extra": ["delete"]}})
    assert any("前の形" in p and "delete" in p and "道具の名" in p for p in probs), probs


def test_字の鍵に正規表現のつもりの行を書くと名指される():
    probs = SV.check({"guard": {"paid_markers_extra": ["api.paid\\b"]}})
    assert any("paid_markers_extra" in p and "正規表現でない" in p for p in probs), probs
    assert SV.words_in(["api.example-paid.com"], "curl https://api.example-paid.com/x") == ["api.example-paid.com"]


def test_有料の印の字は字のまま当たる():
    vals = {"paid_markers_extra": ["api.example-paid.com"]}
    data = {"tool_name": "Write", "tool_input": {"file_path": "/r/tests/test_x.py",
                                                 "content": "URL = 'https://api.example-paid.com/v1'"}}
    assert paid_upstream.check(data, vals)
    assert not paid_upstream.check(data, {"paid_markers_extra": ["api.other-paid.com"]})


def _use(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def _log(tmp_path, *rows, name="l.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in
                           [{"type": "user", "uuid": "u1", "message": {"content": "作り物の頼み"}}, *rows]), encoding="utf-8")
    return str(p)


@pytest.mark.parametrize("row, want", [
    (_use("Grep", {"pattern": "会議", "path": "/x/問いの表.md"}), True),
    (_use("Bash", {"command": "echo Grep 問いの表"}), False),               # 道具の名でなく入力の中の語
    (_use("Write", {"file_path": "/x/a.md", "content": "Grep で問いの表を引く"}), False),
])
def test_聞く前に引いた跡は道具の名から全体に当てる(tmp_path, row, want):
    pats = G.patterns({"ask_prior_lookup": ["^Grep \\{.*問いの表.*\\}$"]}, "ask_prior_lookup")
    assert prior_ask.scan(_log(tmp_path, row), pats)[1] is want


@pytest.mark.parametrize("row, want", [
    (_use("mcp__claude-code-remote__create_session", {"prompt": "続き"}), True),
    (_use("mcp__claude-code-remote__send_message", {"message": "引き継ぎ"}), True),
    (_use("Write", {"file_path": "/x/handoff.md", "content": "続き"}), True),
    (_use("Bash", {"command": "grep -rn send_message ."}), False),
    (_use("Grep", {"pattern": "create_session"}), False),
    (_use("Read", {"file_path": "/x/handoff.md"}), False),                  # 読んだだけは引き継ぎでない
])
def test_引き継ぎの跡は既定の形が道具の名から全体に当たる(tmp_path, row, want):
    over = {"type": "assistant", "message": {"content": [], "usage": {"input_tokens": 10}}}
    pats = G.patterns(G.DEFAULTS, "context_handoff")
    assert context_size.handoff_state(_log(tmp_path, over, row), 5, pats) == (True, want)


def _repo(tmp_path, parent="work"):
    r = tmp_path / parent / "repo"
    (r / ".git").mkdir(parents=True)
    return r


def test_問いのページの外す形は_repo_の根からの_path_の全体に当てる(tmp_path):
    r = _repo(tmp_path, parent="docs")                       # repo の上の dir の名（docs）に当たらない
    pats = G.patterns({"qa_page_exempt": ["^quiz/[^/]+\\.html$", "^docs/.*$"]}, "qa_page_exempt")
    for rel, want in (("quiz/a.html", True), ("quizzes-old/a.html", False), ("app/a.html", False)):
        f = r / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
        assert (SV.hit(pats, qa_page.repo_rel(str(f)), str(f)) is not None) is want, rel


def test_戻せない道具の足しは道具の名の全体に当てる():
    vals = {"irreversible_tools_extra": [{"pattern": "^mcp__s__delete_item$", "why": "作り物の削除"}]}
    assert irreversible.match("mcp__s__delete_item", {}, "", vals) == "作り物の削除"
    assert irreversible.match("mcp__s__undelete_item", {}, "", vals) == ""
    assert irreversible.match("TaskDelete", {}, "", vals) == ""
    # 1 段目: 前の形の行（錨なし）は前の読み方で止め続ける（止める側を黙って狭めない）
    assert irreversible.match("mcp__s__undelete_item", {}, "", {"irreversible_tools_extra": ["delete"]})


def test_鍵の外す形は当たった塊の全体に当てる():
    pg = types.SimpleNamespace(SECRET_PATTERNS={"作り物の鍵": r"ghp_[A-Za-z0-9]{36}"})
    real = "ghp_" + "EXAMPLE" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o"   # 塊の全体（36 字）
    data = {"tool_name": "mcp__x__send", "tool_input": {"text": real}}
    assert outbound.secret_hits(data, {"outbound_secret_allow": ["^ghp_EXAMPLE.*EXAMPLE$"]}, pg)
    assert outbound.secret_hits(data, {"outbound_secret_allow": ["^EXAMPLE$"]}, pg)       # 一部に当てると通ってしまう
    assert not outbound.secret_hits(data, {"outbound_secret_allow": ["^" + real + "$"]}, pg)


def test_中の言葉の外す字は見つけた塊の全体に当てる():
    text = "部屋は ABC123-4 です"
    assert ("番号", "ABC123-4") in ask_shape.inner_terms(text, {})
    assert ("番号", "ABC123-4") in ask_shape.inner_terms(text, {"ask_term_allow": ["^ABC$"]})
    assert ("番号", "ABC123-4") not in ask_shape.inner_terms(text, {"ask_term_allow": ["^ABC123-4$"]})


def test_一部に当てる鍵は問いの文の一部に当たる():
    q = {"question": "作り物の試しの順はどれを進めますか", "options": [{"label": "a"}, {"label": "b"}]}
    assert pick_one.classify(q, {}) == "work"
    assert pick_one.classify(q, {"ask_pick_one_exempt": ["作り物の試し"]}) == ""


@pytest.mark.parametrize("pat, path, want", [
    ("tools/*", "tools/a.py", True),
    ("tools/*", "tools/sub/deep/x.py", False),                 # * が / をまたぐ読み方へ戻すと赤
    ("tools/**", "tools/sub/deep/x.py", True),
    ("tools/**/x.py", "tools/x.py", True),
    ("tools/?.py", "tools/a/b.py", False),
])
def test_glob_は_path_の全体に当て星は斜線をまたがない(pat, path, want):
    assert SV.glob_match(pat, path) is want
    assert codex_pack.match_any(path, [pat]) is want


def test_顧客の物は前の読み方でも見落とさない():
    assert codex_pack.client_hit("clients/a/deep/x.py", ["clients/a/*"])
    assert not codex_pack.match_any("clients/a/deep/x.py", ["clients/a/*"])


def test_値の表の照らしが前の形と読めない行を名指し_鍵は落とさない():
    table = {"guard": {"ask_prior_lookup": ["\\bGrep\\b.*問いの表", "^Grep \\{.*\\}$", "("]}}
    probs = SV.check(table)
    assert any("前の形" in p for p in probs) and any("読めない" in p for p in probs), probs
    sec, _ = SV.check_section(table, "guard")[0], None
    assert "ask_prior_lookup" not in SV.check_section(table, "guard")[1]


def test_値の表の口を通さず値を当てる道具が無い():
    """guard の scripts が値の表の正規表現の鍵を、口（patterns・patterns_of・words_in）を通さず re で直に当てない。"""
    keys = [k for (p, s, k), sp in specs_all() if p == "guard" and sp["type"] in ("patterns", "words")]
    for f in sorted((ROOT / "plugins" / "guard" / "scripts").glob("*.py")):
        for no, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for k in keys:
                if '"%s"' % k in ln and ".get(" in ln and not any(
                        x in ln for x in ("bad_pattern_rows", "words_in", "_patterns(vals, k", "list(vals.get")):
                    pytest.fail("%s:%d が値の表の %s を口を通さず読む: %s" % (f.name, no, k, ln.strip()))


def test_型_patterns_の字でない行の形も鍵を読む道具が全部受ける(tmp_path, monkeypatch):
    """型 patterns は {"pattern": 字} の行を許す。手で読む道具がその行を黙って捨てると赤（session-watch の reply_exempt）。"""
    sys.path.insert(0, str(ROOT / "plugins" / "session-watch" / "scripts"))
    import session_watch as sw
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"session-watch": {"watch-log": {"reply_exempt": [{"pattern": "^> "}]}}}), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(table))
    assert sw.reply_exempt({})[0] == ["^> "]
    assert not SV.check(json.loads(table.read_text()))
