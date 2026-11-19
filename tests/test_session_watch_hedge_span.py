"""完了の言い切りの照らしが、言い切らない語と終わりの語が「、」をまたぐ形を素通りさせない試験。

見込みの判定（先の事か）だけを句で見て、2 つの語の重なりは文で見る。句で切った前の形は、
「た、」の誤った差し戻しを直す代わりに、下の 5 つの形を全部通していた。
"""
import pytest

from test_session_watch import sw
from test_session_watch_reply import owner_reply, stopped


@pytest.mark.parametrize("text", [
    "直った、と思います。",
    "ほぼ、終わった。",
    "たぶん、通った。",
    "テストは通った、はず。",
    "全部終わった、と思う。",
])
def test_読点をまたぐ言い切らない完了を差し戻す(tmp_path, text):
    assert sw.hedge_hits(text)
    assert "done" in stopped(tmp_path, owner_reply(text))


@pytest.mark.parametrize("text", [
    "書き直した、次の版はたぶん来週できる。",
    "たぶん、来週できる。",
])
def test_見込みの句の言い切らない語は差し戻さない(tmp_path, text):
    assert sw.hedge_hits(text) == []
    assert stopped(tmp_path, owner_reply(text)) == []
