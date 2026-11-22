"""返事の本文の言語の照らし（session-watch の Stop の hook の札 lang）。

意図: 返事も実況も日本語で書く（核 §2）を、文の決まりだけでなく仕組みで守る。
課題: 会話が自動で要約された後、窓が要約の英語に引きずられ、札と締めだけ日本語で本文が英語の返事を出しても、
      Stop の hook は 1 行目の札と締めの 2 行しか見ず知らせなかった。
原因: 返事の見張りが本文の言語を照らす所を持っていなかった。lang の札がそれを持つ。ここは誤りの類をわざと入れて拒む試験と、
      正しい返事（日本語の本文・コードの塊の多い日本語の返事・英語の識別子の多い日本語の返事）を知らせない試験を置く。
"""
import json

import pytest

from test_session_watch import rows, stop_env, sw
from test_session_watch_reply import owner_log, owner_reply, stopped

EN_BODY = (
    "I updated the Stop hook so that it now checks the language of the reply body.",
    "The tests pass and the pull request is ready for review by another session.",
)


def test_英語の本文で札と締めだけ日本語の返事を知らせる(tmp_path):
    assert "lang" in stopped(tmp_path, owner_reply(*EN_BODY))


def test_日本語の本文は知らせない(tmp_path):
    reply = owner_reply("Stop の hook に本文の言語の照らしを足した。", "根拠: 試験が緑（tests/test_session_watch_lang.py）。")
    assert "lang" not in stopped(tmp_path, reply)


def test_コードの塊が多い日本語の返事は知らせない(tmp_path):
    code = ["```python", "def check(reply):", "    return reply.body.language != 'ja'",
            "for line in open('transcript.jsonl'):", "    print(json.loads(line).get('message'))",
            "if __name__ == '__main__':", "    main(sys.argv[1:])", "```"]
    reply = owner_reply("照らしの中身はこの形にした。", *code,
                        "`git push -u origin claude/20261122-reply-lang` で上げた。https://example.com/docs/en/hooks を読んだ。")
    assert "lang" not in stopped(tmp_path, reply)


def test_英語の識別子と引用が多い日本語の返事は知らせない(tmp_path):
    reply = owner_reply("session_watch.py の STOP_CODES と STOP_HOW に lang を足し、watch-log の SKILL.md も同じ順に直した。",
                        "> The Stop hook now reports when the reply body is mostly written in English, outside code blocks.",
                        "上は PR に書いた英語の一文の引用。")
    assert "lang" not in stopped(tmp_path, reply)


def test_英語の実況も知らせる(tmp_path):
    """締めは日本語でも、このターンの途中の文（実況）が英語なら知らせる。"""
    rs = rows("owner_ok.jsonl") + [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Let me check the hook script first and then run the whole test suite again."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "true"}}]}},
        {"type": "user", "toolUseResult": {"stdout": ""}, "message": {"content": [{"type": "tool_result", "content": ""}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Now I will update the skill document so that both lists use the same order."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "true"}}]}},
    ]
    reply = owner_reply("照らしを足した。")
    assert "lang" in stopped(tmp_path, reply, rs)


def compacted(tmp_path):
    """要約（compact）の後の会話ログ: 要約の行は英語で、user の行に isCompactSummary の印が付く（実物の形）。"""
    return rows("owner_ok.jsonl") + [
        {"type": "system", "subtype": "compact_boundary"},
        {"type": "user", "isCompactSummary": True, "isVisibleInTranscriptOnly": True,
         "message": {"role": "user", "content": "This session is being continued from a previous conversation that ran out of "
                                                "context. The summary below covers the earlier portion of the conversation."}},
    ]


def test_要約の後の最初の英語の返事を知らせる(tmp_path):
    rs = compacted(tmp_path)
    reply = owner_reply(*EN_BODY)
    assert "lang" in stopped(tmp_path, reply, rs)
    # last_assistant_message が無い時（会話ログの締めの本文から読む）も同じに知らせる
    rs2 = rs + [{"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}}]
    data = {"hook_event_name": "Stop", "session_id": "s2", "transcript_path": owner_log(tmp_path, rs2), "stop_hook_active": False}
    reason = sw.stop(data, stop_env(tmp_path)) or ""
    assert "lang:" in reason


def test_要約の後の日本語の返事は知らせない(tmp_path):
    """英語の要約の行は人の行なので（番は切らない）、AI の文（実況・返事）に混ぜない。"""
    assert "lang" not in stopped(tmp_path, owner_reply("要約の後も日本語で続けた。"), compacted(tmp_path))


@pytest.mark.parametrize("short", ["OK", "Done.", "LGTM です。"])
def test_一言の英語は数えない(tmp_path, short):
    assert "lang" not in stopped(tmp_path, owner_reply(short))
