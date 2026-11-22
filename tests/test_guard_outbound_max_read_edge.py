"""外へ渡す file を照らす上限（outbound.MAX_READ）の境目の下側: 上限ちょうどの file は照らせた物として名指さない。

上限の数は試験に写さず、正本の outbound.MAX_READ を直に読む（正本が変わっても試験が境目を見続ける）。
比べ方を `>` から `>=` に変える誤りが入ると、この試験が赤になる。
"""
from test_guard import env, hook  # noqa: F401  （env は fixture）
from test_guard_unreadable_named import notice, outbound, publish  # noqa: F401  （outbound は fixture）


def test_上限ちょうどの_file_は照らせた物として名指さない(env, tmp_path, outbound):
    (tmp_path / "ok.html").write_text("<p>報告</p>", encoding="utf-8")
    (tmp_path / "edge.json").write_text("x" * outbound.MAX_READ, encoding="utf-8")
    assert notice(env, publish(tmp_path, file_path="ok.html", files={"data/edge.json": "edge.json"})) == ""
