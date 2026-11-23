"""人や他の窓へ渡る道具の入力の鍵を出る前に照らす守り（guard の outbound）と、有料の上流の見張りの見る口の外
（Bash の書き込み）が、止めるべき入力で止まり、通すべき入力で通るか。入力は全部作り物。"""
import json
from pathlib import Path

import pytest

from test_guard import bash, denied, deny_reason, env  # noqa: F401  （env は fixture）


def publish(path, cwd="", **extra):
    return {"tool_name": "Artifact", "cwd": cwd, "tool_input": {"file_path": str(path), **extra}}


# ── outbound（人や他の窓へ渡る道具の入力の鍵）──
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


def test_outbound_ほかの値が崩れても鍵は止まり_鍵の外す形が壊れたら止まる(env):
    key = FAKE_KEYS["GitHub のトークン"]
    p = tool(CREATE, title="🤖 作り物の作業", prompt="この鍵で入って %s" % key)
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    table = proj / "config" / "skill-values.json"
    table.write_text(json.dumps({"guard": {"unknown_key": ["(崩れた"]}}), encoding="utf-8")
    assert "鍵・認証情報の形" in deny_reason(env, p)     # ほかの鍵が崩れても鍵は止まる
    table.write_text(json.dumps({"guard": {"outbound_secret_allow": ["(崩れた"]}}), encoding="utf-8")
    assert "照らせない" in deny_reason(env, p)          # 外す形が壊れたら、鍵を外さず止める
