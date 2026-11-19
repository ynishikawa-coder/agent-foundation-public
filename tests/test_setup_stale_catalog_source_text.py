"""setup script の塊（docs/核の届け方.md）の外す行に、出所を文字列の包含で見る前の形（json.dumps）が戻っていないか（字の照らし）。

動きの照らし（外すか）は tests/test_setup_stale_catalog_source.py。字の照らしを動きの試験の中で先に当てると、
文書を戻した時に動きの試験が全部ここで止まり、動きの歯が効いているかが読めないので file を分ける。
"""
from test_setup_stale_catalog_source import decide_text


def test_字_出所を文字列の包含で見る形が戻っていない():
    assert "json.dumps" not in decide_text(), "出所を文字列の包含で見る形が戻った"
