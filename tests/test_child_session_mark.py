"""窓の環境の CLAUDE_CODE_CHILD_SESSION を子の窓の見分けに使わない注入の試験（台帳: 印の意味を子の窓で 1 を見ただけで決めた）。

前の形: guard_common.seeded_by_record は頼みの行がまだ無い時に CLAUDE_CODE_CHILD_SESSION を「別の窓が create_session で
立てた窓の印」と読み、最初の知らせ（session-watch の remind_title）が子の窓と決めて親の題の付け直しを知らせた。
正本で確かめた意味: 公式の文書 code.claude.com/docs/en/env-vars は「Claude Code が Bash・PowerShell・Monitor の道具・hook・
status line で起動する子プロセスに 1 を付ける」と書く。実物でも、別の窓が立てた窓の claude の本体と、その親の環境の
管理のプロセスには付いておらず、Bash の中にだけ 1 が在った＝窓ごとの記録でなく、どの窓でも hook の中では 1。
今の形: 環境の印を読まない。行が無い時は文だけで子の窓と決めず（人の窓の側）、文が別の窓を指す時だけサーバの記録
（get_session の parent_session_id）を AI に読ませる。印が無い・偽の値・どんな値でも、知らせは同じになる。
"""
from pathlib import Path

import pytest

from test_session_watch import CLOUD, sw

ROOT = Path(__file__).resolve().parent.parent
MARK = "CLAUDE_CODE_CHILD_SESSION"
TO_WINDOW = "作り物を見て（返し先=session_X）"
HUMAN_PASTE = "引き継ぎ: 作り物を見て（親窓 session_X の子）"
VALUES = [None, "", "0", "1", "true", "yes", "偽の値", " 1 "]


def empty_log(tmp_path):
    log = tmp_path / "empty.jsonl"
    log.write_text("", encoding="utf-8")
    return str(log)


def env_with(v):
    e = dict(CLOUD)
    if v is not None:
        e[MARK] = v
    return e


@pytest.mark.parametrize("prompt", [TO_WINDOW, HUMAN_PASTE, "作り物を見て", "作り物を見て（返し先=オーナー）"])
def test_注入_印の値をどう変えても最初の知らせは変わらない(tmp_path, prompt):
    """印が無い・偽の値・1 のどれでも同じ知らせ＝印に頼った見分けが入れない。"""
    outs = {sw.remind({"prompt": prompt, "transcript_path": empty_log(tmp_path)}, env_with(v)) for v in VALUES}
    assert len(outs) == 1, outs


@pytest.mark.parametrize("v", VALUES)
def test_注入_人が貼った文は印が1でも子の窓と言い切らない(tmp_path, v):
    """人が立てた窓に引き継ぎの文を貼った時、印が 1 でも親の題の付け直しを言い切らず、サーバの記録で決めさせる。"""
    text = sw.remind({"prompt": HUMAN_PASTE, "transcript_path": empty_log(tmp_path)}, env_with(v))
    assert text and "parent_session_id" in text and "🙋" in text, text
    assert sw.REMIND_CHILD not in text, text


def test_注入_文が窓を指さなければ印が1でも子の窓の知らせを出さない(tmp_path):
    text = sw.remind({"prompt": "作り物を見て", "transcript_path": empty_log(tmp_path)}, env_with("1"))
    assert text and "parent_session_id" not in text and sw.REMIND_CHILD not in text, text


def test_注入_行が無い時の記録は印によらず人の窓の側():
    G = sw.neighbor("guard_common")
    assert G is not None
    assert G.seeded_by_record(None) is False


def test_注入_見分けの道具が環境の印を読まない():
    """hook・Bash の中ではどの窓でも 1 の印を、見分けの道具（guard・session-watch）が読み直さない。"""
    for rel in ("plugins/guard/scripts/guard_common.py", "plugins/session-watch/scripts/session_watch.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
        assert ('"%s"' % MARK) not in code and ("'%s'" % MARK) not in code, rel
