"""人や他の窓へ渡る道具の入力を出る前に照らす守り（guard の outbound）と、問いのページ・有料の上流の見張りの見る口の外
（Artifact の files・Bash の書き込み）が、止めるべき入力で止まり、通すべき入力で通るか。入力は全部作り物。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_guard import (PLUGIN, ROOT, STATE_PAGE, bash, denied, deny_reason, env, publish, without_check)  # noqa: F401  （env は fixture）


# ── outbound（人や他の窓へ渡る道具の入力: 鍵・番号だけの頼み・窓の題と手の窓の 4 欄）──
# 鍵の形は字をつないで作る（この file 自身が公開の検査に当たらないため）。値は作り物。
FAKE_KEYS = {
    "GitHub のトークン": "gh" + "p_" + "A1b2C3d4" * 5,
    "Anthropic の鍵": "sk-" + "ant-" + "x" * 30,
    "AWS の鍵 ID": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "Slack のトークン": "xo" + "xb-" + "1234567890-abc",
}
SEND = "mcp__claude-code-remote__send_message"
CREATE = "mcp__claude-code-remote__create_session"
SET_TITLE = "mcp__claude-code-remote__set_session_title"


def tool(name, **ti):
    return {"tool_name": name, "session_id": "s1", "cwd": "", "tool_input": ti}


@pytest.mark.parametrize("label", sorted(FAKE_KEYS))
@pytest.mark.parametrize("payload", [
    lambda k: tool(SEND, session_id="session_x", message="作り物の鍵はこれ: %s を使って" % k),
    lambda k: tool("SendMessage", to="worker", message="鍵 %s" % k),
    lambda k: tool(CREATE, title="🤖 作り物の作業", prompt="この鍵で入って %s" % k),
    lambda k: tool("mcp__github__create_pull_request", title="作り物", body="手順\n\n```\nTOKEN=%s\n```" % k),
    lambda k: tool("mcp__notion__notion-update-page", page_id="x", content_updates=[{"old_str": "a", "new_str": k}]),
])
def test_outbound_外へ渡す道具の入力に鍵の形があれば出す前に止め鍵の字は返さない(env, label, payload):
    key = FAKE_KEYS[label]
    why = deny_reason(env, payload(key))
    assert "鍵・認証情報の形" in why and label in why
    assert key not in why                       # 止めた文にも鍵を出さない


def test_outbound_Artifact_で出す_file_と_files_の中の鍵も止める(env, tmp_path):
    key = FAKE_KEYS["GitHub のトークン"]
    (tmp_path / "r.html").write_text("<p>報告</p><!-- %s -->" % key, encoding="utf-8")
    (tmp_path / "ok.html").write_text("<p>報告</p>", encoding="utf-8")
    (tmp_path / "d.json").write_text(json.dumps({"k": key}), encoding="utf-8")
    assert "鍵・認証情報の形" in deny_reason(env, publish("r.html", cwd=str(tmp_path)))
    assert "鍵・認証情報の形" in deny_reason(env, publish("ok.html", cwd=str(tmp_path), files={"data/d.json": "d.json"}))
    assert not denied(env, publish("ok.html", cwd=str(tmp_path)))


@pytest.mark.parametrize("payload", [
    tool(SEND, session_id="session_x", message="PR #31 の CHANGELOG の衝突は main を merge して直した。先端 1a21016e8983。"),
    tool("mcp__github__create_pull_request", title="作り物", body="鍵は環境の秘密に入れた（値は書かない）。sk-ant- で始まる形を止める。\n整地: 不要（試験の作り物の本文）"),
    tool("mcp__notion__notion-fetch", id="https://example.invalid/page"),
    tool("Bash", command="echo " + FAKE_KEYS["GitHub のトークン"]),     # 外へ渡す道具でない（返事・Bash は別の守り）
])
def test_outbound_鍵の無い入力と外へ渡さない道具は通す(env, payload):
    assert not denied(env, payload)


def test_outbound_作り物の見本は値の表で外せ_鍵の正本が無ければ止まる(env, tmp_path):
    key = FAKE_KEYS["AWS の鍵 ID"]
    p = tool(SEND, session_id="session_x", message="見本の鍵 %s の形" % key)
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    (proj / "config" / "skill-values.json").write_text(
        json.dumps({"guard": {"outbound_secret_allow": ["^" + key + "$"]}}), encoding="utf-8")
    assert not denied(env, p)
    gone = dict(env, AF_PUBLIC_GUARD=str(tmp_path / "無い.py"))
    assert "照らせない" in deny_reason(gone, tool(SEND, session_id="session_x", message="ふつうの文"))


@pytest.mark.parametrize("msg", [
    "#3 やって",
    "E02 の件、お願いします。",
    "了解しました。\nQ202611-67 の対応を進めて",
    "PR #31 merge して",
    "#616 と #617 も",
])
@pytest.mark.parametrize("name", [SEND, "SendMessage", CREATE])
def test_outbound_番号だけで中身の名の無い頼みは送る前に止める(env, msg, name):
    p = tool(name, message=msg, prompt=msg, title="🤖 作り物の作業")
    why = deny_reason(env, p)
    assert "番号だけで中身の名の無い文" in why and "直し方" in why


@pytest.mark.parametrize("msg", [
    "#3（請求書の送り先を顧客ごとに変える直し）を進めて",
    "PR #31 の CHANGELOG の衝突を直して",
    "E02・E03 の件（請求書の宛先の誤り）を直して",
    "session_011P2AMEYhnqWec1SQkBtQxp へ返す",
    "2026-11-19 に合流した。v0.4.15 で入った。",
    "請求書の送り先を顧客ごとに変える直しを進めて",
    "https://github.com/example/repo/pull/3 を見て",
])
def test_outbound_番号に名や中身が添えてあれば通す(env, msg):
    assert not denied(env, tool(SEND, session_id="session_x", message=msg))


def test_outbound_番号だけの頼みは値の表で外せる(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    (proj / "config" / "skill-values.json").write_text(
        json.dumps({"guard": {"number_request_exempt": ["^#3 やって$"]}}), encoding="utf-8")
    assert not denied(env, tool(SEND, message="#3 やって"))
    assert denied(env, tool(SEND, message="E02 の件"))


@pytest.mark.parametrize("payload, want", [
    (tool(SET_TITLE, session_id="s", title="作り物の作業"), "種類"),
    (tool(SET_TITLE, session_id="s", title="⏳🤖 作り物の作業"), "種類"),
    (tool(SET_TITLE, session_id="s", title="🤖❓"), "作業名が無い"),
    (tool(SET_TITLE, session_id="s", title="🙋✅ 作り物の相談"), "✅ は付けない"),
    (tool(CREATE, title="🤖 手: 作り物の設定", prompt="目的 手順 済んだ目印 済んだ後"), "手の窓の題は"),
    (tool(CREATE, title="🙋⏳ 手:", prompt="目的 手順 済んだ目印 済んだ後"), "何を頼むかが無い"),
    (tool(CREATE, title="🙋⏳ 手: 作り物の設定", prompt="目的: 作り物の鍵を入れる\n手順: 画面で貼る"), "済んだ目印・済んだ後"),
])
def test_outbound_題の形と手の窓の4欄が崩れていれば出す前に止める(env, payload, want):
    why = deny_reason(env, payload)
    assert "決まりの形でない" in why and want in why


@pytest.mark.parametrize("payload", [
    tool(SET_TITLE, session_id="s", title="🤖 書く: 作り物の作業"),
    tool(SET_TITLE, session_id="s", title="🙋❓ 作り物の相談"),
    tool(SET_TITLE, session_id="s", title="🤖✅ 作り物の作業"),
    tool(CREATE, title="🤖⏳ 作り物のレビュー", prompt="作り物の PR を見る"),
    tool(CREATE, prompt="題の無い窓立て"),
    tool(CREATE, title="🙋⏳ 手: 作り物の設定",
         prompt="①目的: 作り物 ②手順: 貼る ③済んだ目印: 出る ④済んだ後: 返す"),
])
def test_outbound_決まりの形の題と4欄の揃った手の窓は通す(env, payload):
    assert not denied(env, payload)


def test_outbound_題の形の見分けは_session_watch_の正本を直に呼ぶ(env, tmp_path):
    """正本の title_shape を外すと照らさなくなる＝写しを持っていない。"""
    fake = tmp_path / "session_watch.py"
    fake.write_text("import re\nHAND_TITLE=re.compile('^手')\nHAND_PARTS=()\n"
                    "def title_shape(t): return ['作り物の正本が止めた']\n"
                    "def split_title(t): return (None, None, t)\n", encoding="utf-8")
    why = deny_reason(dict(env, AF_SESSION_WATCH=str(fake)), tool(SET_TITLE, session_id="s", title="🤖 作り物"))
    assert "作り物の正本が止めた" in why


def _commit_all(repo):
    g = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                                  check=True, capture_output=True, text=True).stdout.strip()
    if not (repo / ".git").exists():
        g("init", "-q")
    g("add", "-A")
    g("commit", "-qm", "版")
    return g("rev-parse", "HEAD")


def test_outbound_正本の在り処は_repo_の形と入れた_plugin_の形の両方で見つかる(tmp_path):
    sys.path.insert(0, str(PLUGIN / "scripts"))
    try:
        import guard_common as G
    finally:
        sys.path.pop(0)
    assert G.foundation_file(os.path.join("public-guard", "guard.py")) == str(ROOT / "public-guard" / "guard.py")
    assert G.sibling_plugin_file("session-watch", os.path.join("scripts", "session_watch.py")) == \
        str(ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py")
    plugins = tmp_path / "plugins"
    pg = plugins / "marketplaces" / "market" / "public-guard" / "guard.py"
    pg.parent.mkdir(parents=True)
    pg.write_text("#", encoding="utf-8")
    ver = _commit_all(pg.parent.parent)[:12]  # 入った版＝cache の dir の名（市場の取り出しの HEAD と同じ版）
    guard_root = plugins / "cache" / "market" / "guard" / ver
    guard_root.mkdir(parents=True)
    sw = plugins / "cache" / "market" / "session-watch" / ver / "scripts" / "session_watch.py"
    sw.parent.mkdir(parents=True)
    sw.write_text("#", encoding="utf-8")
    assert G.foundation_file(os.path.join("public-guard", "guard.py"), str(guard_root)) == str(pg)
    assert G.sibling_plugin_file("session-watch", os.path.join("scripts", "session_watch.py"), str(guard_root)) == str(sw)


# ── 見る口の外: Artifact の files の問いのページ・Bash で試験へ書く有料の上流 ──
def test_qa_page_files_で足した問いのページも見る(env, tmp_path):
    (tmp_path / "index.html").write_text("<p>表紙</p>", encoding="utf-8")
    (tmp_path / "kakunin.html").write_text(STATE_PAGE, encoding="utf-8")
    env = without_check(env, tmp_path / "入れた", ver="v1")             # 同じ版の docs-kit が無い＝検査が見つからない
    for files in ({"q.html": "kakunin.html"}, {"q.html": {"from": "kakunin.html"}}, [{"path": "kakunin.html"}]):
        assert "緑を確かめられない" in deny_reason(env, publish("index.html", cwd=str(tmp_path), files=files)), files
    assert "緑を確かめられない" not in deny_reason(env, publish("index.html", cwd=str(tmp_path),
                                                                files={"a.html": {"artifact": "https://example.invalid/a", "path": "a.html"}}))
    assert not denied(env, publish("index.html", cwd=str(tmp_path), files={"a.html": None}))


@pytest.mark.parametrize("cmd", [
    "cat > tests/test_llm.py <<'EOF'\nimport os\nKEY = os.environ['" + "OPENAI" + "_API_KEY']\nEOF",
    "echo 'URL = \"https://api." + "anthropic.com/v1\"' >> tests/conftest.py",
    "printf 'x' | tee -a e2e/run.spec.ts && echo " + "GEMINI" + "_API_KEY",
    "sed -i 's/FAKE/" + "ANTHROPIC" + "_API_KEY/' tests/test_a.py",
])
def test_paid_upstream_Bash_で試験へ書く有料の上流も止める(env, cmd):
    assert "有料の上流" in deny_reason(env, bash(cmd))


@pytest.mark.parametrize("cmd", [
    "grep -rn " + "OPENAI" + "_API_KEY tests/",
    "cat > src/client.py <<'EOF'\nKEY = '" + "OPENAI" + "_API_KEY'\nEOF",
    "cat > tests/test_llm.py <<'EOF'\n# PAID_UPSTREAM_GUARD\nKEY = '" + "OPENAI" + "_API_KEY'\nEOF",
    "pytest tests/ 2>&1 > /tmp/out.txt && echo " + "OPENAI" + "_API_KEY",
])
def test_paid_upstream_Bash_の読みと試験の外への書き込みと関所つきは通す(env, cmd):
    assert not denied(env, bash(cmd))


def test_outbound_他の見分けが壊れても鍵は止まり_鍵の見分けが壊れたら止まる(env, tmp_path):
    key = FAKE_KEYS["GitHub のトークン"]
    p = tool(CREATE, title="🤖 作り物の作業", prompt="この鍵で入って %s" % key)
    old = tmp_path / "session_watch.py"              # 題の形の見分けが無い古い版の正本
    old.write_text("import re\n", encoding="utf-8")
    assert "鍵・認証情報の形" in deny_reason(dict(env, AF_SESSION_WATCH=str(old)), p)
    broke = tmp_path / "broke.py"                     # 読むと壊れる正本
    broke.write_text("raise RuntimeError('作り物の故障')\n", encoding="utf-8")
    assert "鍵・認証情報の形" in deny_reason(dict(env, AF_SESSION_WATCH=str(broke)), p)
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    table = proj / "config" / "skill-values.json"
    table.write_text(json.dumps({"guard": {"number_request_exempt": ["(崩れた"]}}), encoding="utf-8")
    assert "鍵・認証情報の形" in deny_reason(env, p)     # number が壊れても鍵は止まる
    table.write_text(json.dumps({"guard": {"outbound_secret_allow": ["(崩れた"]}}), encoding="utf-8")
    assert "照らせない" in deny_reason(env, p)          # 外す形が壊れたら、鍵を外さず止める
