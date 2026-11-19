"""guard の跡の見分け（prior_ask・context_size）: 跡は道具の名と入力の欄で見て、頼みの境は頼みの印で切り、
引く先の無い repo の窓を止めず、値の表の壊れた形は黙って通さず名指すか（注入の試験・入力は全部作り物）。"""
import importlib.util
import itertools
import json
import shutil
import subprocess
import sys

import pytest

from test_guard import GUARD, ROOT, ask_pre, deny_reason, env, hook, q, write_log  # noqa: F401  （env は fixture）
from test_guard_context_stop import over_log, stop_hook

SCRIPTS = ROOT / "plugins" / "guard" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
import guard_common as G  # noqa: E402

LOOKUP_TOOL = "mcp__fake__lookup_records"


_IDS = itertools.count(1)


def use(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_fake%d" % next(_IDS),
                                                          "name": name, "input": inp}]}}


def result(tid, out="作り物の結果", err=False):
    return {"type": "user", "toolUseResult": {"stdout": out},
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": out, "is_error": err}]}}


def call(name, inp, out="作り物の結果", err=False):
    """道具の呼び出しと、同じ tool_use_id の返りの 2 行。"""
    u = use(name, inp)
    return [u, result(u["message"]["content"][0]["id"], out, err)]


def owner(text, uuid, pid=None):
    row = {"type": "user", "uuid": uuid, "message": {"content": text}}
    if pid:
        row["promptId"] = pid
    return row


def ask_with(tpath, sid="s1"):
    p = ask_pre(q("会議を回数で別に数えますか", header="会議の数え方"))
    p.update({"transcript_path": tpath, "session_id": sid})
    return p


def values(env, tmp_path, table):
    path = tmp_path / "values.json"
    path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    env["SKILL_VALUES"] = str(path)


def lookup(env, tmp_path, specs):
    values(env, tmp_path, {"guard": {"ask_prior_lookup": specs}})


def log(tmp_path, *rows, name="t.jsonl"):
    flat = [r for row in rows for r in (row if isinstance(row, list) else [row])]
    return write_log(tmp_path / name, [owner("作り物の頼み", "u1", "p1"), *flat])


# ── 1. 跡は道具の名と入力の欄で見る（入力にその字を含むだけの呼び出しを跡に数えない）──
FAKE_TRACES = [
    ("Bash の命令に道具の名の字を書いただけ", call("Bash", {"command": "echo %s" % LOOKUP_TOOL})),
    ("Grep で問いの表の字を探しただけ", call("Grep", {"pattern": "問いの表", "path": "/x/作り物のコード"})),
]


NEW_FORMS = [{"tool": LOOKUP_TOOL}, {"tool": "Grep", "input": {"path": "問いの表"}}]


@pytest.mark.parametrize("name,row", FAKE_TRACES, ids=[c[0] for c in FAKE_TRACES])
def test_引いた跡は入力にその字を含むだけの呼び出しで数えない(env, tmp_path, name, row):
    lookup(env, tmp_path, NEW_FORMS)
    why = deny_reason(env, ask_with(log(tmp_path, row)))
    assert "引いた跡が会話ログに無い" in why, why


def test_引いた跡は道具の名と挙げた入力の欄が当たれば数える(env, tmp_path):
    lookup(env, tmp_path, NEW_FORMS)
    assert deny_reason(env, ask_with(log(tmp_path, call("Grep", {"pattern": "会議", "path": "/x/問いの表.md"})))) == ""
    assert deny_reason(env, ask_with(log(tmp_path, call(LOOKUP_TOOL, {"q": "会議"}), name="b.jsonl"))) == ""


def test_引き継ぎの跡は命令の字に送る道具の名を含むだけでは数えない(env, tmp_path):
    tpath = over_log(tmp_path, 300_000, use("Bash", {"command": "grep -rn send_message create_session plugins/"}))
    assert "まだ引き継いでいない" in stop_hook(env, tpath)


def test_組み込みの窓へ送る道具は引き継ぎの跡に数える(env, tmp_path):
    tpath = over_log(tmp_path, 300_000, use("SendMessage", {"to": "作り物の窓", "message": "作り物の引き継ぎ"}))
    assert stop_hook(env, tpath) == ""


# ── 2. 頼みの境は頼みの印で切る（hook の差し戻しの行は新しい頼みでない）──
FEEDBACK = "Stop hook feedback:\n[guard] 作り物の差し戻し"
SAME_REQUEST = [
    ("差し戻しが同じ頼みの印の user 行で残る版", owner(FEEDBACK, "u2", "p1")),
    ("差し戻しが頼みの印の無い user 行で残る版", owner(FEEDBACK, "u2")),
]


@pytest.mark.parametrize("name,row", SAME_REQUEST, ids=[c[0] for c in SAME_REQUEST])
def test_hookの差し戻しの行は頼みの境に数えない(env, tmp_path, name, row):
    lookup(env, tmp_path, [{"tool": LOOKUP_TOOL}])
    tpath = log(tmp_path, call(LOOKUP_TOOL, {"q": "会議"}), row)
    assert deny_reason(env, ask_with(tpath)) == ""


def test_頼みの印が替わった人の行は新しい頼みとして引き直させる(env, tmp_path):
    lookup(env, tmp_path, [{"tool": LOOKUP_TOOL}])
    tpath = log(tmp_path, call(LOOKUP_TOOL, {"q": "会議"}), owner("次の作り物の頼み", "u2", "p2"))
    assert "引いた跡が会話ログに無い" in deny_reason(env, ask_with(tpath))


def test_session_watchの頼みの境もhookの差し戻しの行を数えない():
    spec = importlib.util.spec_from_file_location("sw_trace", ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py")
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    for _, row in SAME_REQUEST:
        assert not G.is_owner_row(row) and not sw.is_owner_text(row)
    assert G.is_owner_row(owner("作り物の頼み", "u1")) and sw.is_owner_text(owner("作り物の頼み", "u1"))


# ── 3. 引く先の無い repo の窓を止めない（起動の時に照らせていない事を知らせる）──
def test_引く先の無いrepoでは画面を止めず起動の時に知らせる(env, tmp_path):
    tpath = log(tmp_path)
    assert deny_reason(env, ask_with(tpath)) == "" and deny_reason(env, ask_with(tpath, sid="s2")) == ""
    assert hook(env, "start", {"session_id": "s1"}) == {}, "値の表そのものが無い repo には知らせない"
    values(env, tmp_path, {"guard": {"context_limit": 300000}})
    assert deny_reason(env, ask_with(tpath, sid="s3")) == ""
    note = hook(env, "start", {"session_id": "s1"}).get("additionalContext", "")
    assert "照らしていない" in note and "guard.ask_prior_lookup" in note, note


def test_確認ページの前の答えを引く命令を引く先に使う(env, tmp_path):
    values(env, tmp_path, {"docs-kit": {"qa-html": {"prior_check_cmd": "python3 tools/作り物の引く道具.py"}}})
    tpath = log(tmp_path, call("Read", {"file_path": "/x/a"}))
    assert deny_reason(env, ask_with(tpath)) and deny_reason(env, ask_with(tpath)), "引く先が在れば上限まで止める"
    for i, cmd in enumerate(["python3 tools/作り物の引く道具.py < q.json", "node /x/qa-html/check.mjs p.html --run-prior"]):
        tpath = log(tmp_path, call("Bash", {"command": cmd}, out=MARKED), name="r%d.jsonl" % i)
        assert deny_reason(env, ask_with(tpath)) == ""
    assert hook(env, "start", {"session_id": "s1"}).get("additionalContext", "").find("照らしていない") < 0


# 引く命令の字を含むだけで走らせていない Bash（注入: 字で見ると全部跡に数えていた）
NOT_RUN = [
    ("echo の引数", 'echo "python3 tools/作り物の引く道具.py"'),
    ("echo の引数（check.mjs）", 'echo "node /x/qa-html/check.mjs p.html --run-prior"'),
    ("grep で探す字", 'grep -rn "check.mjs --run-prior" .'),
    ("grep で探す字（命令）", "grep -rn 'python3 tools/作り物の引く道具.py' docs/"),
    ("# の注", "# node /x/qa-html/check.mjs p.html --run-prior"),
    ("行の後ろの # の注", "ls  # python3 tools/作り物の引く道具.py"),
    ("command -v は走らせない", "command -v python3 tools/作り物の引く道具.py"),
    ("別の道具の引数に命令の字", "git commit -m 'node check.mjs p --run-prior'"),
    ("頭の違う道具", "python3 tools/別の道具.py"),
    ("check.mjs を --run-prior 無しで", "node /x/qa-html/check.mjs p.html"),
]


@pytest.mark.parametrize("name,cmd", NOT_RUN, ids=[c[0] for c in NOT_RUN])
def test_引く命令の字を含むだけのBashは走らせた跡に数えない(env, tmp_path, name, cmd):
    values(env, tmp_path, {"docs-kit": {"qa-html": {"prior_check_cmd": "python3 tools/作り物の引く道具.py"}}})
    why = deny_reason(env, ask_with(log(tmp_path, call("Bash", {"command": cmd}))))
    assert "引いた跡が会話ログに無い" in why, (cmd, why)


MARKED = "🟢 緑  作り物.html（問い 2）\nprior-check: 2 件"     # check.mjs --run-prior が引き終えた時の返り

RAN = [
    ("前置きの環境変数と入力の向け替え", "A=1 python3 tools/作り物の引く道具.py < q.json"),
    ("ヒアドキュメントで問いを渡す", "python3 tools/作り物の引く道具.py <<'EOF'\n{\"questions\": []}\nEOF"),
    ("前の cd と &&", "cd /x && python3 tools/作り物の引く道具.py"),
    ("node に旗を付けて check.mjs", "node --no-warnings /x/qa-html/check.mjs p.html --run-prior"),
    ("前の cd と改行の 2 行目", "cd /x\nnode /x/check.mjs p.html --run-prior"),
]


@pytest.mark.parametrize("name,cmd", RAN, ids=[c[0] for c in RAN])
def test_引く命令を走らせたBashは跡に数える(env, tmp_path, name, cmd):
    values(env, tmp_path, {"docs-kit": {"qa-html": {"prior_check_cmd": "python3 tools/作り物の引く道具.py"}}})
    assert deny_reason(env, ask_with(log(tmp_path, call("Bash", {"command": cmd}, out=MARKED)))) == "", cmd


# ── 4. 値の表の壊れた形は黙って通さず名指す ──
def test_引く先の壊れた形は数えずに止めて名指す(env, tmp_path):
    lookup(env, tmp_path, ["(", LOOKUP_TOOL])
    why = deny_reason(env, ask_with(log(tmp_path)))
    assert "壊れた形" in why and '"("' in why, why
    lookup(env, tmp_path, ["("])
    assert "壊れた形" in deny_reason(env, ask_with(log(tmp_path), sid="s2")), "全部壊れていても通さない"



# input の偽の値（注入: 黙って名だけの形に広がり、全部の Bash を跡に数えていた）
FALSY_INPUT = [("並び", []), ("null", None), ("空の字", ""), ("空の {}", {}), ("0", 0), ("空の欄の名", {"": "x"}),
               ("空の正規表現", {"command": ""})]


@pytest.mark.parametrize("name,inp", FALSY_INPUT, ids=[c[0] for c in FALSY_INPUT])
def test_跡の形のinputの偽の値は名だけの形に広げず名指す(env, tmp_path, name, inp):
    with pytest.raises(ValueError):
        G.trace_matcher({"tool": "Bash", "input": inp})
    lookup(env, tmp_path, [{"tool": "Bash", "input": inp}])
    why = deny_reason(env, ask_with(log(tmp_path, call("Bash", {"command": "ls"}))))
    assert "引いた跡が会話ログに無い" in why and "壊れた形" in why, why
    note = hook(env, "start", {"session_id": "s1"}).get("additionalContext", "")
    assert "guard.ask_prior_lookup: 跡の形として読めない" in note, note


# ── 5. 壊れる 1 段目: 文字列の古い形は今までどおり読み、起動の時に古い形と名指す ──
def test_文字列の古い形は今までどおり字に当てて読み起動の時に名指す(env, tmp_path):
    lookup(env, tmp_path, ['"q": "会議"', "create_session\\b"])
    assert deny_reason(env, ask_with(log(tmp_path, call(LOOKUP_TOOL, {"q": "会議"})))) == "", "入力の JSON に当てる古い形"
    assert deny_reason(env, ask_with(log(tmp_path, call("mcp__x__create_session", {}), name="b.jsonl"))) == "", \
        "名の一部に当てていた古い形の意味を変えない"
    note = hook(env, "start", {"session_id": "s1"}).get("additionalContext", "")
    assert "guard.ask_prior_lookup: 古い形の跡" in note and "2 段目" in note, note


def test_古い形の一覧が値の表の文字列の跡の形を見つけ新しい形は見つけない():
    rows = {r["id"]: r for r in json.loads((ROOT / "plugins" / "core" / "古い形.json").read_text(encoding="utf-8"))["olds"]}
    rx = __import__("re").compile(rows["guard-trace-string"]["pattern"])
    olds = ['{"guard": {"ask_prior_lookup": ["mcp__x__search"]}}',
            '{"guard": {"context_handoff": [{"tool": "SendMessage"}, "create_session\\\\b"]}}']
    news = ['{"guard": {"context_handoff": [{"tool": "W", "input": {"file_path": "h"}}, {"tool": "S"}], "ask_prior_lookup": []}}']
    assert all(rx.search(t) for t in olds) and not any(rx.search(t) for t in news)
    assert all(isinstance(s, dict) for s in G.DEFAULTS["context_handoff"]), "土台の既定は新しい形"


def test_引き継ぎの跡の壊れた形は数えずに差し戻して名指す(env, tmp_path):
    values(env, tmp_path, {"guard": {"context_handoff": ["("]}})
    why = stop_hook(env, over_log(tmp_path, 300_000, use("mcp__x__send_message", {"message": "作り物"})))
    assert "壊れた形" in why and '"("' in why, why


def test_起動の時に値の表の読めない値を名指す(env, tmp_path):
    values(env, tmp_path, {"guard": {"ask_prior_lookup": [{"tool": "("}], "context_handoff": "作り物",
                                     "ask_prior_exempt": ["["]}})
    note = hook(env, "start", {"session_id": "s1"}).get("additionalContext", "")
    for want in ("guard.ask_prior_lookup", "guard.context_handoff の型が違う", "guard.ask_prior_exempt: 正規表現として読めない"):
        assert want in note, (want, note)
    values(env, tmp_path, {"guard": {"irreversible_bash_extra": [{"pattern": "(", "why": "作り物"}]}})
    assert "guard.irreversible_bash_extra" in hook(env, "start", {"session_id": "s1"}).get("additionalContext", "")


def test_外す形の壊れた正規表現1本で見張りごと黙って通らない(env, tmp_path):
    values(env, tmp_path, {"guard": {"ask_prior_lookup": [{"tool": LOOKUP_TOOL}], "ask_prior_exempt": ["[", "終わりましたか"]}})
    assert "引いた跡が会話ログに無い" in deny_reason(env, ask_with(log(tmp_path)))


# pr_ruler_trace は pr_text が guard_common.tool_matchers（PR #77 の口）で読む跡の形＝この分けの外
NOT_REGEX = {"unattended_env", "paid_markers_extra", "ask_topic_stopwords_extra", "pr_ruler_trace"}


def test_値の表の並びの鍵は全部壊れの名指しの分けに載る():
    lists = {k for k, v in G.DEFAULTS.items() if isinstance(v, list)}
    kinds = [set(G.REGEX_LIST_KEYS), set(G.MATCHER_KEYS), set(G.PATTERN_DICT_KEYS)]
    assert lists - NOT_REGEX == set().union(*kinds)
    assert sum(len(k) for k in kinds) == len(set().union(*kinds)), "1 つの鍵は 1 つの分けだけ"


def test_既定の引き継ぎの跡の形は全部読める():
    ok, bad = G.trace_matchers(G.DEFAULTS, "context_handoff")
    assert not bad and len(ok) == len(G.DEFAULTS["context_handoff"])


# ── 6. 「走った」を頼んだ字で決めず、走った証（同じ tool_use_id の返り・引く道具が出す行）で見る ──
CMD = "python3 tools/作り物の引く道具.py"
RUN = "node /x/qa-html/check.mjs p.html --run-prior"
DENIED = "Permission to use Bash with command %s has been denied." % CMD
BLOCKED = "PreToolUse:Bash hook error: [作り物の hook] 止めた"


def prior_values(env, tmp_path):
    values(env, tmp_path, {"docs-kit": {"qa-html": {"prior_check_cmd": CMD}}})


# 注入: どれも引く命令を走らせていない（か、走った証が返りに無い）のに、f0b43ab は跡に数えて画面を通していた
NOT_COUNTED = [
    ("ヒアドキュメントの本文に命令", [call("Bash", {"command": "cat > notes.md <<'EOF'\n%s\nEOF" % CMD}, out="")],
     None),
    ("ヒアドキュメントの本文に check.mjs", [call("Bash", {"command": "cat > a.md <<EOF\n%s\nEOF" % RUN}, out="")], None),
    ("false && の後", [call("Bash", {"command": "false && " + CMD}, out="Exit code 1", err=True)], "&&"),
    ("exit の後", [call("Bash", {"command": "exit 0; " + CMD}, out="")], "命令 1 つだけの形でない"),
    ("改行で書いた if false の枝", [call("Bash", {"command": "if false\nthen\n%s\nfi" % CMD}, out="")],
     "命令 1 つだけの形でない"),
    ("while false の中", [call("Bash", {"command": "while false\ndo\n%s\ndone" % CMD}, out="")], "命令 1 つだけの形でない"),
    ("呼ばない関数の本体", [call("Bash", {"command": "f() {\n%s\n}" % CMD}, out="")], "function_def"),
    ("$(…) の中", [call("Bash", {"command": "x=$(%s)" % RUN}, out="")], "$(…)"),
    ("`…` の中", [call("Bash", {"command": "x=`%s`" % CMD}, out="")], None),
    ("shell への管", [call("Bash", {"command": "echo '%s' | bash" % CMD}, out=MARKED)], None),
    ("権限で拒まれた", [call("Bash", {"command": CMD}, out=DENIED, err=True)], "拒まれた"),
    ("hook に止められた check.mjs", [call("Bash", {"command": RUN}, out=BLOCKED, err=True)], "拒まれた"),
    ("誤りで終わった命令", [call("Bash", {"command": CMD}, out="Exit code 1\nTraceback 作り物", err=True)], "Exit code 1"),
    ("返りの無い呼び出し", [use("Bash", {"command": CMD})], "無い"),
    ("出力の無い命令", [call("Bash", {"command": CMD}, out="(Bash completed with no output)")], "出力が空"),
    ("出力を file へ向け替え", [call("Bash", {"command": CMD + " > out.json"}, out="(Bash completed with no output)")],
     "出力の向け替え"),
    ("引き終えた行の無い check.mjs", [call("Bash", {"command": RUN}, out="--run-prior: 値の表に無い")], "prior-check"),
    ("落ちた check.mjs", [call("Bash", {"command": RUN}, out="Exit code 2\n読めない", err=True)], "prior-check"),
    ("返りの tool_use_id が違う", [use("Bash", {"command": RUN}), result("toolu_別の呼び出し", MARKED)], "無い"),
]


@pytest.mark.parametrize("name,rows,named", NOT_COUNTED, ids=[c[0] for c in NOT_COUNTED])
def test_走った証の無い呼び出しは引いた跡に数えず理由を名指す(env, tmp_path, name, rows, named):
    prior_values(env, tmp_path)
    why = deny_reason(env, ask_with(log(tmp_path, *rows)))
    assert "引いた跡が会話ログに無い" in why, (name, why)
    if named:
        assert "跡に数えなかった呼び出し" in why and named in why, (name, why)


COUNTED = [
    ("check.mjs が引き終えた行を返した", [call("Bash", {"command": RUN}, out=MARKED)]),
    ("ページが赤で 0 でない数で終わっても引き終えた行が在る",
     [call("Bash", {"command": RUN}, out="Exit code 1\n🔴 赤\nprior-check: 2 件", err=True)]),
    ("前の cd と && の後の値の表の命令", [call("Bash", {"command": "cd /x && " + CMD})]),
    ("値の表の命令が出力を返した", [call("Bash", {"command": CMD + " < q.json"}, out='{"checked": {"q1": "x"}}')]),
    ("拒まれた後に走らせ直した", [call("Bash", {"command": CMD}, out=DENIED, err=True), call("Bash", {"command": CMD})]),
]


@pytest.mark.parametrize("name,rows", COUNTED, ids=[c[0] for c in COUNTED])
def test_走った証の在る呼び出しは引いた跡に数える(env, tmp_path, name, rows):
    prior_values(env, tmp_path)
    assert deny_reason(env, ask_with(log(tmp_path, *rows))) == "", name


def test_値の表の引く先の跡も拒まれた呼び出しは数えない(env, tmp_path):
    lookup(env, tmp_path, [{"tool": LOOKUP_TOOL}])
    for i, out in enumerate(["ユーザーが拒んだ", "作り物の誤り"]):
        tpath = log(tmp_path, call(LOOKUP_TOOL, {"q": "会議"}, out, True), name="d%d.jsonl" % i)
        why = deny_reason(env, ask_with(tpath, sid="d%d" % i))
        assert "引いた跡が会話ログに無い" in why and "拒まれた" in why, why


def test_値の表の命令が読み切れない形なら名指してcheck_mjsだけを数える(env, tmp_path):
    values(env, tmp_path, {"docs-kit": {"qa-html": {"prior_check_cmd": "cd tools && " + CMD}}})
    why = deny_reason(env, ask_with(log(tmp_path, call("Bash", {"command": "cd tools && " + CMD}))))
    assert "引いた跡が会話ログに無い" in why and "prior_check_cmd が素の命令 1 つでない" in why, why
    assert deny_reason(env, ask_with(log(tmp_path, call("Bash", {"command": RUN}, out=MARKED), name="b.jsonl"))) == ""


NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="node が無い")
def test_check_mjs_の本物の返りを跡に数え落ちた回は数えない(env, tmp_path):
    from test_docs_kit import CHECK, filled_template, prior_cmd, write_values
    page = tmp_path / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    for i, (cmd, counted) in enumerate([(prior_cmd(tmp_path), True), ("false", False)]):
        env["SKILL_VALUES"] = str(write_values(tmp_path, {"prior_check_cmd": cmd}))
        res = subprocess.run([NODE, str(CHECK), str(page), "--run-prior"], capture_output=True, text=True, cwd=tmp_path)
        out = (res.stdout + res.stderr).strip()
        if res.returncode:
            out = "Exit code %d\n%s" % (res.returncode, out)
        run = "node %s %s --run-prior" % (CHECK, page)
        tpath = log(tmp_path, call("Bash", {"command": run}, out=out, err=res.returncode != 0), name="n%d.jsonl" % i)
        why = deny_reason(env, ask_with(tpath, sid="n%d" % i))
        assert (why == "") is counted, (cmd, out, why)


# ── 7. 走った証は呼び出し全体の返りでなく、命令 1 つの返り（PR #82 の 3 回目の red の所見 1）──
# 注入: どれも引く命令が引き終えた証にならないのに、b713f7d は跡に数えて画面を通していた
MOVED = "Command was moved to the background (ID: b1). Output is being written to a file; it was not interrupted."
BG = "Command running in background with ID: b2"
LOOKED = '{"checked": {"q1": "作り物"}}'


def bare(tid, out, **extra):
    """is_error の欄を作り物の値にした（か欄の無い）返り。"""
    return {"type": "user", "toolUseResult": {"stdout": out},
            "message": {"content": [dict({"type": "tool_result", "tool_use_id": tid, "content": out}, **extra)]}}


def call_bare(inp, out, **extra):
    u = use("Bash", inp)
    return [u, bare(u["message"]["content"][0]["id"], out, **extra)]


def dup_results(cmd, *outs):
    u = use("Bash", {"command": cmd})
    return [u] + [result(u["message"]["content"][0]["id"], o) for o in outs]


WHOLE_CALL = [
    ("命令の後に ; echo", [call("Bash", {"command": CMD + "; echo x"}, out="Traceback 作り物\nx")], ";"),
    ("命令の後に | head -1", [call("Bash", {"command": CMD + " | head -1"}, out="Traceback 作り物")], "|"),
    ("命令を & で背に回して echo", [call("Bash", {"command": CMD + " & echo started"}, out="started")], "&"),
    ("命令の後ろに & だけ", [call("Bash", {"command": CMD + " &"}, out="[1] 4242")], "&"),
    ("命令に --help", [call("Bash", {"command": CMD + " --help"}, out="usage: 作り物")], "引数が値の表の命令と違う"),
    ("命令の後に || true", [call("Bash", {"command": CMD + " || true"}, out=LOOKED)], "||"),
    ("命令の後に && echo", [call("Bash", {"command": CMD + " && echo ok"}, out="ok")], "&&"),
    ("stderr を stdout へ", [call("Bash", {"command": CMD + " 2>&1"}, out=LOOKED)], "出力の向け替え"),
    ("bash -c の中", [call("Bash", {"command": "bash -lc 'cd /x; %s'" % CMD}, out=LOOKED)], "bash -c"),
    ("bash -c の中の向け替え", [call("Bash", {"command": "bash -c '%s > out.json'" % CMD}, out="(no output)")],
     "bash -c"),
    ("sudo・env・time の前置き", [call("Bash", {"command": "sudo -u a env B=2 time " + CMD}, out=LOOKED)], "前置き"),
    ("管の後ろの命令", [call("Bash", {"command": "cat q.json | " + CMD}, out=LOOKED)], "|"),
    ("Bash が背景に回した返り", [call("Bash", {"command": CMD}, out=MOVED)], "背景"),
    ("run_in_background の呼び出し", [call("Bash", {"command": CMD, "run_in_background": True}, out=BG)], "背景"),
    ("run_in_background で返りの字は普通", [call("Bash", {"command": CMD, "run_in_background": True}, out=LOOKED)],
     "背景"),
    ("is_error の欄が無い返り", [call_bare({"command": CMD}, LOOKED)], "is_error の欄が無い"),
    ("is_error が字の true の拒まれた返り", [call_bare({"command": CMD}, DENIED, is_error="true")], "真偽でない"),
    ("is_error が字の false", [call_bare({"command": CMD}, LOOKED, is_error="false")], "真偽でない"),
    ("check.mjs の後に echo で印の字", [call("Bash", {"command": RUN + "; echo 'prior-check: 1 件'"},
                                          out="--run-prior: 値の表に無い\nprior-check: 1 件")], ";"),
    ("check.mjs の後に cat で下書き", [call("Bash", {"command": RUN + "; cat draft.md"},
                                         out="--run-prior: 値の表に無い\nprior-check: 3 件")], ";"),
    ("check.mjs の印が最後の行でない", [call("Bash", {"command": RUN}, out="prior-check: 2 件\n🔴 その後の行")],
     "最後の行"),
    ("check.mjs の | tail", [call("Bash", {"command": RUN + " 2>&1 | tail -3"}, out=MARKED)], "|"),
    ("check.mjs を背景に回した返り", [call("Bash", {"command": RUN}, out=MOVED + "\nprior-check: 2 件")], "背景"),
    ("check.mjs の返りに is_error の欄が無い", [call_bare({"command": RUN}, MARKED)], "is_error の欄が無い"),
    ("同じ id の返りが 2 つ", [dup_results(RUN, "x", MARKED)], "2 つ以上"),
]


@pytest.mark.parametrize("name,rows,named", WHOLE_CALL, ids=[c[0] for c in WHOLE_CALL])
def test_呼び出し全体の返りを命令1つの走った証に数えない(env, tmp_path, name, rows, named):
    prior_values(env, tmp_path)
    why = deny_reason(env, ask_with(log(tmp_path, *rows)))
    assert "引いた跡が会話ログに無い" in why, (name, why)
    assert "跡に数えなかった呼び出し" in why and named in why, (name, why)


def test_値の表の引く先の跡もBashは命令1つと在る印で見る(env, tmp_path):
    lookup(env, tmp_path, [{"tool": "Bash", "input": {"command": "作り物の表を引く"}}])
    bad = [("; echo", call("Bash", {"command": "作り物の表を引く q; echo x"}, out="x")),
           ("背景", call("Bash", {"command": "作り物の表を引く q"}, out=MOVED)),
           ("欄が無い", call_bare({"command": "作り物の表を引く q"}, LOOKED)),
           ("Exit code", call("Bash", {"command": "作り物の表を引く q"}, out="Exit code 1\n落ちた", err=True))]
    for i, (name, rows) in enumerate(bad):
        why = deny_reason(env, ask_with(log(tmp_path, rows, name="L%d.jsonl" % i), sid="L%d" % i))
        assert "引いた跡が会話ログに無い" in why, (name, why)
    assert deny_reason(env, ask_with(log(tmp_path, call("Bash", {"command": "作り物の表を引く q"}), name="ok.jsonl"),
                                     sid="Lok")) == ""


def test_ran_of_は在る印だけで走ったと言う():
    import prior_ask as PA
    u = use("Bash", {"command": CMD})
    blk = u["message"]["content"][0]
    tid = blk["id"]
    assert PA.ran_of([u, result(tid, LOOKED)], blk) == (True, LOOKED, "")
    assert PA.ran_of([u, result(tid, "Exit code 3\nx", True)], blk) == (True, "Exit code 3\nx", "Exit code 3")
    for rows in ([u], [u, bare(tid, LOOKED)], [u, bare(tid, LOOKED, is_error="true")], [u, result(tid, MOVED)],
                 [u, result(tid, DENIED, True)], [u, result(tid, "a"), result(tid, "b")]):
        ran, _, why = PA.ran_of(rows, blk)
        assert not ran and why, rows
    m = use(LOOKUP_TOOL, {"q": "会議"})
    mblk = m["message"]["content"][0]
    assert PA.ran_of([m, bare(mblk["id"], LOOKED)], mblk)[0], "Bash の外の道具は欄の無い返りを誤りでないと読む"
    assert not PA.ran_of([m, result(mblk["id"], "作り物の誤り", True)], mblk)[0]
