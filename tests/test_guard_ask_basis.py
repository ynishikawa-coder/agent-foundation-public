"""オーナーに判断を頼む前に、チャットで具体例と判断を頼む理由を見せる（細目 §4「見せてから聞く」）。
guard の ask_shape の知らせ（部品 ask_basis）が、2 行の無い選択肢の画面を画面の後に知らせ、止めないか（誤りの例をわざと入れる試験）。"""
import pathlib
import re

import pytest

from test_guard import env, hook, q, write_log  # noqa: F401  （env は fixture）

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE = ROOT / "plugins" / "core"
EXAMPLE = "具体例: 作り物の検査の file「作り物.yml」が今は main で毎回走る。A を選ぶと止まり、B なら残る。"
REASON = "判断を頼む理由: 作り物の検査を残すかはオーナーだけが知る事情で決まる（オーナーだけの情報）。"
ASK = q("作り物の検査を残しますか", header="作り物の検査", labels=("残す", "止める", "分からない"))


def say(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def use(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def owner(text, uuid="u1"):
    return {"type": "user", "uuid": uuid, "message": {"content": text}}


def shown(env, tmp_path, *rows, ask=ASK, name="b.jsonl"):
    tpath = write_log(tmp_path / name, [owner("作り物の頼み"), *rows])
    payload = {"tool_name": "AskUserQuestion", "session_id": "s1", "transcript_path": tpath,
               "tool_input": {"questions": [ask]}, "tool_response": {"questions": [ask], "answers": {}}}
    out = hook(env, "post", payload)
    assert "permissionDecision" not in out, "知らせるだけで止めない"
    return mine(out)


def mine(out):
    """ほかの見張り（答えの無い問いの台帳など）の知らせを除いた、ask_basis の知らせだけ。"""
    return "\n\n".join(b for b in out.get("additionalContext", "").split("\n\n") if "見せてから聞く" in b)


BAD = [
    ("具体例も理由も無い", [say("名指しの検査が切れるので決めてください。")], ["具体例:", "判断を頼む理由:"]),
    ("具体例だけ", [say(EXAMPLE)], ["判断を頼む理由:"]),
    ("理由だけ", [say(REASON)], ["具体例:"]),
    ("2 行は前の頼みの中だけ", [say(EXAMPLE + "\n" + REASON), owner("次の作り物の頼み", "u2"), say("決めてください")],
     ["具体例:", "判断を頼む理由:"]),
    ("2 行は 1 つ前の画面の前だけ", [say(EXAMPLE + "\n" + REASON),
                              use("AskUserQuestion", {"questions": [q("作り物の色を変えますか")]}), say("続けて")],
     ["具体例:", "判断を頼む理由:"]),
    ("文の中ほどに語が在るだけ", [say("ここでは具体例: を省きます。判断を頼む理由: も同じです。")], ["具体例:", "判断を頼む理由:"]),
    ("中身の無い行", [say("具体例:\n判断を頼む理由:")], ["具体例:", "判断を頼む理由:"]),
]


@pytest.mark.parametrize("name,rows,lack", BAD, ids=[c[0] for c in BAD])
def test_ask_basis_具体例か理由が欠けた画面は画面の後に知らせる(env, tmp_path, name, rows, lack):
    txt = shown(env, tmp_path, *rows, use("AskUserQuestion", {"questions": [ASK]}))
    assert "見せてから聞く" in txt and "止めていない" in txt, txt
    for word in lack:
        assert "「%s」" % word in txt, (word, txt)
    for word in {"具体例:", "判断を頼む理由:"} - set(lack):
        assert "「%s」" % word not in txt.splitlines()[0], (word, txt)
    assert "AI が決めて進め" in txt


GOOD = [
    ("2 行が在る", [say("案はこう。\n" + EXAMPLE + "\n" + REASON)]),
    ("全角のコロンと箇条書き", [say("- 具体例： 作り物の file が消える\n- **判断を頼む理由**：戻せない")]),
    ("別々の文に分けて書いた", [say(EXAMPLE), use("Read", {"file_path": "/x/作り物"}), say(REASON)]),
]


@pytest.mark.parametrize("name,rows", GOOD, ids=[c[0] for c in GOOD])
def test_ask_basis_2行が画面の前に在れば黙る(env, tmp_path, name, rows):
    assert shown(env, tmp_path, *rows, use("AskUserQuestion", {"questions": [ASK]})) == ""


def test_ask_basis_今の画面がまだ会話ログに無くても最後の頼みより後の文を見る(env, tmp_path):
    assert shown(env, tmp_path, say(EXAMPLE + "\n" + REASON)) == ""
    assert "「具体例:」" in shown(env, tmp_path, say("決めてください"), name="c.jsonl")


def test_ask_basis_済んだかの確かめだけの画面と助手の中と画面の外は黙る(env, tmp_path):
    done = q("作り物の設定の保存は終わりましたか", header="手の確かめ", labels=("終わった", "うまくいかない", "分からない"))
    assert shown(env, tmp_path, say("手順はこう"), ask=done) == ""
    tpath = write_log(tmp_path / "m.jsonl", [owner("作り物の頼み"), say("手順はこう")])
    out = hook(env, "post", {"tool_name": "AskUserQuestion", "session_id": "s1", "transcript_path": tpath,
                             "tool_input": {"questions": [done, ASK]}})
    assert "「具体例:」" in mine(out), "判断を頼む問いが混ざれば照らす"
    d = tmp_path / "subagents"
    d.mkdir()
    tpath = write_log(d / "a.jsonl", [owner("作り物の頼み"), say("決めて")])
    out = hook(env, "post", {"tool_name": "AskUserQuestion", "session_id": "s1", "transcript_path": tpath,
                             "tool_input": {"questions": [ASK]}})
    assert mine(out) == ""
    out = hook(env, "post", {"tool_name": "Bash", "session_id": "s1", "transcript_path": tpath, "tool_input": {"command": "echo"}})
    assert mine(out) == ""


def _sec4(text):
    m = re.search(r"^## 4\..*?(?=^## \d|\Z)", text, re.S | re.M)
    return m.group(0)


def test_聞き方は判断を頼む前に具体例と頼む理由を見せ_理由が無ければAIが決める():
    """原因の台帳 420a40dc（2026-11-23）: 「名指しの検査が切れる」のような中の言葉だけで判断を頼み、オーナーが何を・なぜ
    決めるのか分からなかった。古い文に戻すと赤。"""
    kaku = _sec4((CORE / "核.md").read_text(encoding="utf-8"))
    assert "オーナーだけの情報・言葉の解釈" in kaku, "核 §4 の聞く線（判断を頼む理由の元）が無い"
    s4 = (CORE / "細目" / "04-聞き方.md").read_text(encoding="utf-8")
    for word in ["判断を頼む時は①に行の頭で `具体例:`", "この件で実際に起きる事＝物の本当の名・今の状態・選ぶと何が変わるか",
                 "`判断を頼む理由:`（「選ばせない」の聞く時のどれか）", "理由が書けなければ聞かず AI が決める",
                 "この件で何を指すかを `具体例:` の行に書く"]:
        assert word in s4, f"細目 §4 に無い: {word}"
    for old in ["「この件で何を指すか・選ぶと何が変わるか」を具体で 1 行添える", "窓を読んでいない人がチャットと画面だけで答えられる",
                "済んだかは、AI が確かめられる所（ファイル・設定・画面の結果）を先に確かめ", "その答えに頼らない仕事を進める"]:
        assert old not in s4, f"畳んだ文が残る: {old}"
    skill = (ROOT / "plugins" / "guard" / "skills" / "guard-rules" / "SKILL.md").read_text(encoding="utf-8")
    assert "| ask_shape の notice（推奨の印の知らせ・判断を頼む前の具体例と理由の知らせ＝部品 ask_basis） | PostToolUse |" in skill
