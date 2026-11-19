"""守りが字の並びでなく 1 つの読み手で照らす約束（原因の台帳: 土台の守りが字の並びで照らし言い換えると通る）。

注入の試験: 台帳の行に挙がった「言い換えると通った形」を 1 つずつ入れ、今は拒む（止める・赤・拾う）ことを見る。
あわせて、前から通していた正しい形は通すことを見る（止める範囲を黙って広げない）。
"""
import importlib.util
import random
import re
import string
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
sys.path.insert(0, str(ROOT / "plugins" / "session-watch" / "scripts"))

import cmd_read  # noqa: E402
import irreversible  # noqa: E402
import paid_upstream  # noqa: E402
import qa_page  # noqa: E402
import session_watch  # noqa: E402
import spec_gate  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pr_shape = _load("pr_shape_m", ROOT / "scripts" / "pr_shape.py")
kaku = _load("kaku_m", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
pguard = _load("pguard_m", ROOT / "public-guard" / "guard.py")
handcopied = _load("handcopied_m", ROOT / "tests" / "test_no_handcopied_lists.py")

GATE = "check_spec" + "_doc.py"       # この file を書く窓の守りに当たらないよう字を割る（守りは割った字も読む）
LOCK = "--lo" + "ck"


# ── 読み手（cmd_read）──
@pytest.mark.parametrize("cmd, want", [
    ('python3 "check_spec"\'_doc.py\' x', ["python3", GATE, "x"]),
    ("G=%s; python3 $G d" % GATE, ["python3", GATE, "d"]),
    ("sudo -u x env A=1 dropdb foo > /tmp/o 2>&1", ["dropdb", "foo"]),
    ("timeout 5 nohup python3 x.py", ["python3", "x.py"]),
])
def test_読み手は字を割る形と包みを解いた語にする(cmd, want):
    assert want in cmd_read.read(cmd).argvs()


def test_読み手は_bash_c_と_eval_と_展開の中も段にし読めない所に印を付ける():
    r = cmd_read.read('bash -c "dropdb a" && eval "dropdb b" && echo $(dropdb c)')
    assert ["dropdb", "a"] in r.argvs() and ["dropdb", "b"] in r.argvs() and ["dropdb", "c"] in r.argvs()
    assert r.opaque


def test_読み手は_heredoc_の中身を命令にしない():
    assert cmd_read.read("cat <<EOF > f\ndropdb x\nEOF\necho hi").argvs() == [["cat"], ["echo", "hi"]]


# ── spec_gate（台帳 f393a9d8f785）──
@pytest.mark.parametrize("cmd", [
    "python3 %s d %s" % (GATE, LOCK),
    "python3 \"check_spec\"'_doc.py' d --loc",                   # 引用符で字を割る・略した印
    "python3 %s d --l" % GATE,
    "G=%s; python3 $G d %s" % (GATE, LOCK),                       # 変数に置く
    'bash -c "python3 %s d %s"' % (GATE, LOCK),                    # bash -c に包む
    "python3 $(echo %s) d %s" % (GATE, LOCK),                      # 走らせる file が読めない
    "python3 %s d $(echo %s)" % (GATE, LOCK),                      # 印が読めない
    "uv run python %s d %s=1" % (GATE, LOCK),
    "python3 -c 'import check_spec_doc; check_spec_doc.main([\"d\", \"%s\"])'" % LOCK,
])
def test_spec_gate_は言い換えた直の封を止める(cmd):
    assert spec_gate.hit(cmd), cmd


@pytest.mark.parametrize("cmd", [
    "python3 %s d" % GATE, "python3 %s d --verify-receipt" % GATE, "python3 %s d --stamp" % GATE,
    "python3 seal.py d", "echo $(date) && python3 tool.py --local", "grep -n lock %s" % GATE,
])
def test_spec_gate_は_lock_の無い呼び出しと別の命令を通す(cmd):
    assert not spec_gate.hit(cmd), cmd


# ── irreversible（台帳 e0b1b5b8f5d8）──
@pytest.mark.parametrize("name, ti", [
    ("mcp__x__notion-delete-pages", {}),
    ("mcp__x__notion-delete-databases", {}),
    ("mcp__drive__trash_file", {}),
    ("mcp__github__delete_file", {}),
    ("mcp__x__purgeEverything", {}),
    ("mcp__x__frobnicate", {}),                                    # 知らない動詞は既定で止める
    ("Artifact", {"action": "delete", "url": "u"}),
])
def test_irreversible_は並べていない削除の道具と知らない動詞を止める(name, ti):
    assert irreversible.tool_verbs(name, ti), name


@pytest.mark.parametrize("name, ti", [
    ("mcp__x__notion-fetch", {}), ("mcp__github__get_file_contents", {}), ("mcp__x__notion-update-page", {}),
    ("mcp__claude-code-remote__send_message", {}), ("Artifact", {"action": "publish"}), ("Read", {}),
])
def test_irreversible_は読む道具と戻せる書き込みを通す(name, ti):
    assert not irreversible.tool_verbs(name, ti), name


@pytest.mark.parametrize("cmd", [
    "dropdb prod", "sudo -u postgres dropdb prod", 'bash -c "dropdb prod"', "gh repo delete o/r --yes",
    "kubectl delete ns x", "aws s3 rm s3://b --recursive", "find . -name '*.db' -delete", "shred -u f",
    "$CMD prod",
])
def test_irreversible_は読み手の語で戻せない命令を拾う(cmd, tmp_path):
    assert irreversible.bash_verbs(cmd, str(tmp_path)), cmd


@pytest.mark.parametrize("cmd", ["ls -la", "git status", "git branch -a", "gh release create v9", "echo $(date)"])
def test_irreversible_は戻せる命令を拾わない(cmd, tmp_path):
    assert not irreversible.bash_verbs(cmd, str(tmp_path)), cmd


# ── qa_page（台帳 e36a4ee66ed4）──
SEND = "<script>fetch('/a', {method: 'POST', body: x})</script>"


@pytest.mark.parametrize("body", [
    "<select name=a><option>1</option></select>" + SEND,
    "<input type=checkbox name=a>" + SEND,
    "<div role=radio aria-checked=false>A</div>" + SEND,
    "<textarea name=a></textarea>" + SEND,
    "<div contenteditable>書く</div>" + SEND,
    "<script>const i=document.createElement('input');i.type='radio'</script>" + SEND,
    "<script>box.innerHTML = '<label><input type=\"radio\" name=q></label>'</script>" + SEND,
    "<input type=radio name=a><script>const m='POST';fetch('/a', {method: m, body: x})</script>",
    "<input type=radio name=a><script>fetch('/a', opts)</script>",
    "<input type=radio name=a><script>navigator.sendBeacon('/a', x)</script>",
    "<input type=radio name=a><script>parent.postMessage(x, '*')</script>",
])
def test_qa_page_は_radio_の字でなく入れる部品と出す口の類で問いのページと見る(body):
    assert qa_page.why_question_page("p.html", body), body


@pytest.mark.parametrize("body", [
    "<input type=radio name=a>",                                                   # 出す口が無い
    "<select><option>週</option></select><script>fetch('data.json').then(r=>r.json())</script>",  # 読むだけ
    "<input type=hidden name=a><script>fetch('/a', {method:'POST'})</script>",      # 入れる部品でない
])
def test_qa_page_は出す口の無い部品と読むだけのページを問いのページと見ない(body):
    assert not qa_page.why_question_page("p.html", body), body


# ── 手の窓の 4 欄（台帳 e36d33523d11）──
@pytest.mark.parametrize("text", [
    "①目的: ②手順: ③済んだ目印: ④済んだ後:",
    "目的・手順・済んだ目印・済んだ後 を書いた",
    "## 目的\n鍵を入れる\n## 手順\n貼る\n## 済んだ目印\n〔…〕\n## 済んだ後\n返す",
])
def test_手の窓の_4_欄は語が在るだけでは通らない(text):
    assert session_watch.hand_lack(text), text


@pytest.mark.parametrize("text", [
    "①目的: 作り物 ②手順: 貼る ③済んだ目印: 出る ④済んだ後: 返す",
    "## 目的\n鍵を入れる\n## 手順\n```\n貼る\n```\n## 済んだ目印\n画面に出る\n## 済んだ後\n頼んだ窓へ返す",
])
def test_手の窓の_4_欄は中身の在る形を通す(text):
    assert session_watch.hand_lack(text) == [], text


# ── pr_shape（台帳 d0ac1663147f）──
def test_pr_shape_は_class_の中に字下げした試験と代入で作る試験も数える():
    before = "def test_a():\n    pass\n"
    assert pr_shape.count_tests(before + "class TestX:\n    def test_b(self):\n        pass\n") == 2
    assert pr_shape.count_tests(before + "test_c = make()\n") == 2
    assert pr_shape.count_tests(before + "def helper():\n    pass\n") == 1


# ── 手で写した数（台帳 f7e306c03608）──
@pytest.mark.parametrize("text", ["守りの hook が 6 つ。", "見張りは六つ", "守り ６ 本", "3 つの見張り", "hook（guard の 6 つ）"])
def test_見張りの数は書き方を変えても拾う(text):
    assert handcopied.COUNT.search(handcopied.flat(text)), text


@pytest.mark.parametrize("text", ["入口は 1 本", "守りの hook は skill に書く", "3 つの段"])
def test_見張りの数でない数は拾わない(text):
    assert not handcopied.COUNT.search(handcopied.flat(text)), text


# ── 古い形（台帳 f32e0bc73587）──
ROWS = {r["id"]: r for r in kaku.olds_table()}


@pytest.mark.parametrize("rid, text", [
    ("tasu-mado-heading", "## 他の窓に回す"),
    ("tasu-mado-heading", "## ほかの窓へまわす"),
    ("tasu-mado-heading", "## 他の窓へ回す"),
    ("plugin-name-copy", 'claude plugin install "core@agent-"foundation --scope user'),
    ("plugin-name-copy", "claude plugin install core@agent-\\\nfoundation"),
])
def test_古い形は言い換えと字を割る形も拾う(rid, text):
    assert kaku.olds_hit(ROWS[rid], text), text


@pytest.mark.parametrize("rid, text", [
    ("tasu-mado-heading", "## 残り（原因の台帳の行）"),
    ("tasu-mado-heading", "前は他の窓へ回すと書いていたが台帳にした"),
])
def test_古い形は今の欄と地の文を拾わない(rid, text):
    assert not kaku.olds_hit(ROWS[rid], text), text


# ── 鍵の形（台帳 ea5b8d2c3b21）──
def _rnd(seed, n):
    r = random.Random(seed)
    return "".join(r.choice(string.ascii_letters + string.digits) for _ in range(n))


@pytest.mark.parametrize("prefix", ["sk-proj-", "glpat-", "pk_test_", "xai-"])
def test_表に無い会社の鍵も一般の形で拾う(prefix):
    hits = 0
    for seed in range(50):
        hits += bool(pguard.secret_labels(prefix + _rnd(seed, 40)))
    assert hits >= 48, (prefix, hits)


@pytest.mark.parametrize("text", ["session_011P2AMFXTerbArGMcP5CKRK", "test_SomeLongFunctionName2xx",
                                  "use_HTTPServerConfig2Default", "claude/20261119-mojinarabi-mamori"])
def test_窓の_id_と名前は鍵と見ない(text):
    assert not pguard.secret_labels(text), text


# ── 有料の上流（台帳 f0bde909a94d）──
@pytest.mark.parametrize("body", [
    "import anthropic\nc = anthropic.Anthropic()\n",                         # 環境から鍵を読む SDK
    "k = os.environ['ANTHROPIC_' + 'API_KEY']\n",                            # 組み立てた名
    "k = os.environ['XAI_API_KEY']\n",                                       # 表に無い会社
    "import OpenAI from 'openai';\n",
])
def test_有料の上流は類で拾う(body):
    assert paid_upstream.paid_hits(body, {}), body


def test_有料の上流は偽物の試験を拾わない():
    assert not paid_upstream.paid_hits("def test_a(fake_client):\n    assert fake_client.reply() == 'x'\n", {})


# ── pr_text が呼ぶ公開の検査（台帳 e2434a87f0d5）──
def test_pr_text_は出す先の作業の木の公開の検査を読まない(tmp_path, monkeypatch):
    pr_text = _load("pr_text_m", ROOT / "plugins" / "guard" / "scripts" / "pr_text.py")
    old = tmp_path / "古い枝" / "public-guard"
    old.mkdir(parents=True)
    (old / "guard.py").write_text("raise SystemExit(2)\n", encoding="utf-8")
    monkeypatch.delenv("AF_PUBLIC_GUARD", raising=False)
    found = pr_text.find_public_guard(str(tmp_path / "古い枝"))
    assert found and Path(found).resolve() == (ROOT / "public-guard" / "guard.py").resolve()
