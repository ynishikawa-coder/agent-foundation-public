"""原因の台帳（字の並びで照らす類）の H2 の受け持ちの注入の試験: 外へ出す道具・問いのページ・引いた跡・引き継ぎの跡・
子の窓の見分け・値の表の探し方を、字の並びでなく 1 つの読み手と構造で読むか。入力は全部作り物。"""
import base64
import json
import os
import sys
from pathlib import Path

import pytest

from test_guard import PLUGIN, ROOT, deny_reason, denied, env, publish, without_check, write_log  # noqa: F401
from test_guard_context_stop import over_log, stop_hook, use

sys.path.insert(0, str(PLUGIN / "scripts"))
import guard_common as G  # noqa: E402
import context_size  # noqa: E402
import prior_ask  # noqa: E402
import qa_page  # noqa: E402
sys.path.pop(0)


def tool(name, **ti):
    return {"tool_name": name, "session_id": "s1", "cwd": "", "tool_input": ti}


NOTION_SEND = "mcp__notion__notion-send-message-to-session"
NOTION_SPAWN = "mcp__notion__notion-spawn-session"
SLACK_POST = "mcp__slack__slack_post_message"
DRIVE_CREATE = "mcp__drive__create_file"
NOTION_PAGES = "mcp__notion__notion-create-pages"

# 部品と出す口を持つ問いのページ（型の印なし）
QA_HTML = ("<!doctype html><html><body><p>週の起算日はどれですか</p>"
           "<label><input type=radio name=q value=a>日曜</label><label><input type=radio name=q value=b>月曜</label>"
           "<script>navigator.sendBeacon('/a', x)</script></body></html>")


# ── 行 …81e5: 子の窓かを決まった言い回しでなく、自分でない窓の id が在るかで読む ──
@pytest.mark.parametrize("text", [
    "返事は session_ABC123xyz へ",
    "戻し先: session_ABC123xyz",
    "終わったら session_01ABCdef9 に送って",
    "あなたは書く窓です（親窓 session_ABC123 の子）。",
])
def test_rui82_H2_子の窓は言い回しでなく別の窓の_id_で読む(text):
    assert G.is_child_prompt(text, own="zzz999")


@pytest.mark.parametrize("text", [
    "作り物の頼み",
    "この窓（session_ABC123xyz）で続ける",          # 自分の id
    "この窓（ｓｅｓｓｉｏｎ＿ABC123xyz）で続ける",      # 全角で書いた自分の id（NFKC で寄せる）
])
def test_rui82_H2_自分の_id_は子の窓と見ない(text, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_REMOTE_SESSION_ID", "cse_ABC123xyz")
    assert not G.is_child_prompt(text)


def test_rui82_H2_子の窓の見分けは_session_watch_の_kind_of_を直に呼ぶ(tmp_path, monkeypatch):
    fake = tmp_path / "session_watch.py"
    fake.write_text("AI='🤖'\ndef own_id(env=None): return ''\ndef kind_of(t, own=None): return AI\n", encoding="utf-8")
    monkeypatch.setenv("AF_SESSION_WATCH", str(fake))
    assert G.is_child_prompt("作り物の頼み")          # 正本の答えに従う＝写しを持たない


def test_rui82_H2_返し先の言い回しを替えても子の窓の締めの直し方になる(env, tmp_path):
    why = stop_hook(env, over_log(tmp_path, 400_000, first="終わったら返事は session_ABC123xyz へ。"))
    assert "返し先の窓へ送り、止まる" in why, why


# ── 行 …810b: 引き継ぎの跡を字でなく、道具が実際に渡した物で数える ──
def test_rui82_H2_echo_で道具の名を書いた_Bash_は引き継ぎに数えない(env, tmp_path):
    t = over_log(tmp_path, 400_000, use("Bash", {"command": "echo send_message create_session 引き継ぎ"}))
    assert "まだ引き継いでいない" in stop_hook(env, t)


@pytest.mark.parametrize("row", [
    use("Write", {"file_path": "/x/申し送り.md",
                  "content": "## 済んだ事\nA\n## 残り\nB\n## 次の一手\nC\n## 返し先\nオーナー"}),
    use(NOTION_SEND, {"session": "x", "message": "続きをお願いします。済んだ事と残りは下に。"}),
    use(NOTION_SPAWN, {"prompt": "後継の窓として、引き継ぎの続きを進めて"}),
])
def test_rui82_H2_申し送りの_file_と別の名の窓立てを引き継ぎに数える(env, tmp_path, row):
    assert stop_hook(env, over_log(tmp_path, 400_000, row)) == ""


def test_rui82_H2_4_欄の無い_md_を書いただけは引き継ぎに数えない():
    assert not context_size.is_handoff({"name": "Write", "input": {"file_path": "/x/申し送り.md", "content": "メモ"}}, [])


# ── 行 …8148: 引いた跡を入力の JSON の字でなく、道具が実際に読んだ物で数える ──
PAT = ["決定の記録"]


@pytest.mark.parametrize("block", [
    {"name": "Bash", "input": {"command": "echo 決定の記録 を引いた"}},
    {"name": "Bash", "input": {"command": "printf '%s' 決定の記録"}},
    {"name": NOTION_PAGES, "input": {"pages": [{"content": "決定の記録 を書く"}]}},
    {"name": "Write", "input": {"file_path": "/x/決定の記録.md", "content": "x"}},
])
def test_rui82_H2_名を書いただけと作る道具の入力は引いた跡に数えない(block):
    assert not any(prior_ask.re.search(p, s) for s in prior_ask.read_sigs(block) for p in PAT)


@pytest.mark.parametrize("block", [
    {"name": "Bash", "input": {"command": "cat docs/決定の記録.md"}},
    {"name": "Read", "input": {"file_path": "/x/決定の記録.md"}},
    {"name": "mcp__notion__notion-search", "input": {"query": "決定の記録"}},
])
def test_rui82_H2_読む道具と読む段は引いた跡に数える(block):
    assert any(prior_ask.re.search(p, s) for s in prior_ask.read_sigs(block) for p in PAT)


# ── 行 …8140: 問いのページを拡張子と鍵の名でなく中身で読む ──
@pytest.mark.parametrize("name, body", [
    ("q.json", json.dumps({"items": [{"text": "週の起算日はどれですか", "answers": ["日曜", "月曜"]}]}, ensure_ascii=False)),
    ("q.data", json.dumps([{"ask": "締め日はいつですか？", "picks": [{"v": "a", "t": "末日"}, {"v": "b", "t": "20日"}]}],
                          ensure_ascii=False)),
    ("q.xhtml", QA_HTML),
    ("q.svg", QA_HTML),
    ("q", QA_HTML),
])
def test_rui82_H2_拡張子と鍵の名を替えても問いのページと見て止める(env, tmp_path, name, body):
    (tmp_path / name).write_text(body, encoding="utf-8")
    assert "緑を確かめられない" in deny_reason(without_check(env, tmp_path), publish(tmp_path / name))


@pytest.mark.parametrize("body", [
    json.dumps({"title": "売上", "series": [{"name": "a", "v": 1}, {"name": "b", "v": 2}]}),   # 問いの文の無い並び
    json.dumps({"rows": [{"name": "x", "tags": ["a", "b"]}]}),
])
def test_rui82_H2_問いの文の無い_JSON_は問いのページと見ない(body):
    assert not qa_page.why_question_page("d.json", body)


# ── 行 …814f: 問いのページを照らす出口を Artifact に限らない ──
@pytest.mark.parametrize("payload", [
    tool(DRIVE_CREATE, title="確認", mimeType="text/html", content=QA_HTML),
    tool(DRIVE_CREATE, title="確認", content=base64.b64encode(QA_HTML.encode()).decode()),
    tool(NOTION_PAGES, pages=[{"properties": {"title": "確認"}, "content": QA_HTML}]),
])
def test_rui82_H2_Drive_と_Notion_で出す問いのページも検査に掛ける(env, tmp_path, payload):
    assert "緑を確かめられない" in deny_reason(without_check(env, tmp_path), payload)


def test_rui82_H2_Drive_へ手元の問いのページを上げても検査に掛ける(env, tmp_path):
    (tmp_path / "k.html").write_text(QA_HTML, encoding="utf-8")
    p = tool(DRIVE_CREATE, title="確認", file_path=str(tmp_path / "k.html"))
    assert "緑を確かめられない" in deny_reason(without_check(env, tmp_path), p)


def test_rui82_H2_読む道具と問いでない中身は検査に掛けない(env, tmp_path):
    e = without_check(env, tmp_path)
    assert not denied(e, tool("mcp__notion__notion-fetch", id="x", note=QA_HTML))
    assert not denied(e, tool(NOTION_PAGES, pages=[{"content": "# 議事録\n- 決まった事"}]))


# ── 親の足し (2): 字を割って組む部品・button を選択肢にするページ ──
@pytest.mark.parametrize("body", [
    "<script>box.innerHTML = '<inp' + 'ut type=radio name=q>'; navigator.sendBeacon('/a', x)</script>",
    "<script>const t='radio'; box.innerHTML = '<input type=' + t; sendPrompt(x)</script>",
    "<button onclick=\"pick('a')\">日曜</button><button>月曜</button><script>sendPrompt(ans)</script>",
    "<div role=button>日曜</div><script>navigator.sendBeacon('/a', x)</script>",
])
def test_rui82_H2_出す口が在り部品が読めない形のページは問いのページと見る(body):
    assert qa_page.why_question_page("p.html", body), body


# ── 行 …8158・…8104: 窓立て・送る道具を名の末尾でなく動詞の類と窓の語で読む ──
@pytest.mark.parametrize("payload", [
    tool(NOTION_SPAWN, title="作り物の作業", prompt="作り物の頼み"),
    tool("mcp__other__start_agent_session", title="⏳🤖 作り物", prompt="作り物の頼み"),
])
def test_rui82_H2_別の窓立ての道具の崩れた題も止める(env, payload):
    assert "決まりの形でない" in deny_reason(env, payload)


@pytest.mark.parametrize("payload", [
    tool(NOTION_SEND, session="x", message="#3 やって"),
    tool(NOTION_SPAWN, prompt="E02 の件、お願いします。"),
    tool(SLACK_POST, channel="C1", text="#3 やって"),
])
def test_rui82_H2_別の送る道具と窓立てでも番号だけの頼みを止める(env, payload):
    assert "番号だけで中身の名の無い文" in deny_reason(env, payload)


def test_rui82_H2_送らない道具の番号は見ない(env):
    assert not denied(env, tool("mcp__github__add_issue_comment", body="#3 やって"))
    assert not denied(env, tool(NOTION_PAGES, pages=[{"content": "## E02"}]))


# ── 行 …81bc: 番号の横の頼みの語の列挙でなく、番号の外の内容の語の数と添えた説明で読む ──
@pytest.mark.parametrize("msg", ["#3", "#3 を実装して", "E02 の改修", "#12 の改善をお願い", "PR #31 rebase して"])
def test_rui82_H2_列挙に無い頼みの語でも番号だけなら止める(env, msg):
    assert "番号だけで中身の名の無い文" in deny_reason(env, tool("SendMessage", to="w", message=msg))


@pytest.mark.parametrize("msg", ["#3 の請求書の送り先を変えて", "#3（送り先の直し）を実装して", "E02: 宛先の誤りを直す"])
def test_rui82_H2_番号に物の名と中身か説明を添えれば通す(env, msg):
    assert not denied(env, tool("SendMessage", to="w", message=msg))


# ── 親の足し (1): 古い題の正本へ黙って倒れない ──
def test_rui82_H2_hand_lack_の無い古い正本では題を照らせないと止める(env, tmp_path):
    old = tmp_path / "session_watch.py"
    old.write_text("import re\nHAND_TITLE=re.compile('^手')\nHAND_PARTS=('目的',)\n"
                   "def title_shape(t): return []\ndef split_title(t): return (None, None, t)\n", encoding="utf-8")
    p = tool("mcp__claude-code-remote__create_session", title="🙋⏳ 手: 作り物", prompt="目的")
    assert "形を照らせない" in deny_reason(dict(env, AF_SESSION_WATCH=str(old)), p)


# ── 行 …81d3: 値の表の探し方は skill_values.find の 1 本（#48 で既に）──
def test_rui82_H2_guard_の値の表は上の_dir_へ遡って探す_1_本の口(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "config").mkdir()
    (repo / "config" / "skill-values.json").write_text(json.dumps({"guard": {"context_stop_max": 7}}), encoding="utf-8")
    sub = repo / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.delenv("SKILL_VALUES", raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(sub))
    monkeypatch.chdir(tmp_path)
    assert G.values()["context_stop_max"] == 7
    src = (PLUGIN / "scripts" / "guard_common.py").read_text(encoding="utf-8")
    assert "skill-values.json\")" not in src and "os.walk" not in src and "SV.find(" in src
