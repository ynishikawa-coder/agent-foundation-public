"""子の窓かを、頼みの文に手で書いた親窓・返し先（写し）だけで決めず、頼みの行の記録（origin.kind が人でない）と照らす注入の試験。

前の形: 文だけで決め、オーナーが貼った引き継ぎの文でオーナー相手の窓が子の窓（文脈の知らせ・題の印）と見なされた。
"""
import json

import pytest

from test_guard import env, hook, post_tool, usage_log  # noqa: F401  env は fixture
from test_guard_context_stop import over_log, stop_hook
from test_session_watch import sw
from test_session_watch_reply import CLOUD


CHILD_TEXTS = ["あなたは書く窓です（親窓 session_ABC123 の子）。", "作り物を調べて（返し先=session_ABC123）。"]


@pytest.mark.parametrize("first", CHILD_TEXTS)
@pytest.mark.parametrize("origin", [None, "human", "person"])
def test_注入_人が引き継ぎの文を貼った窓は子の窓にしない(env, tmp_path, first, origin):
    """頼みの文の親窓・返し先は手で書いた写し。頼みの行の記録が人（または記録なし）なら子の窓と見ない
    （前の形: 文だけで決め、オーナーが貼った引き継ぎの文でオーナー相手の窓が子の窓の知らせになった）。"""
    tpath = usage_log(tmp_path, 400_000, first=first, origin=origin)
    ctx = hook(env, "post", post_tool(tpath))["additionalContext"]
    assert "引き継ぎを書いて止まって" not in ctx, ctx


def test_context_stop_注入_人が貼った引き継ぎの文では子の窓の直し方にしない(env, tmp_path):
    """頼みの行の記録が人なら、文に親窓が在ってもオーナー相手の窓の直し方（後継の窓を立てる）を返す。"""
    why = stop_hook(env, over_log(tmp_path, 400_000, first="あなたは書く窓です（親窓 session_ABC123 の子）。", origin="human"))
    assert why and "返し先の窓へ送り、止まる" not in why, why


def test_注入_別の窓を指す返し先は頼みの行の記録と合う時だけ数える():
    """手で書いた返し先（写し）だけでは子の窓にしない。記録が人・記録なしなら決めない。"""
    for text in ("作り物を調べて（返し先=session_Y）。", "あなたは書く窓です（親窓 session_X の子）。"):
        assert sw.kind_of(text) is None
        for origin, want in ((None, None), ({"kind": "human"}, None), ({"kind": "person"}, None),
                             ({"kind": "task-notification"}, sw.AI), ({"kind": "peer"}, sw.AI)):
            row = {"type": "user", "message": {"content": text}}
            if origin:
                row["origin"] = origin
            log = sw.Log([row])
            assert sw.kind_of(log.first_prompt, log.first_seeded) == want, (text, origin)
        row = {"type": "user", "message": {"content": text}, "promptSource": "system"}
        log = sw.Log([row])
        assert sw.kind_of(log.first_prompt, log.first_seeded) == sw.AI


@pytest.mark.parametrize("origin", [None, {"kind": "human"}])
def test_注入_人が貼った引き継ぎの文では子窓の知らせにしない(tmp_path, origin):
    """オーナーが引き継ぎの文を貼った窓（記録が人・記録なし）は、文に親窓が在っても子の窓の知らせにしない。"""
    log = tmp_path / "owner.jsonl"
    row = {"type": "user", "message": {"content": "作り物を見て（親窓 session_X の子）"}}
    if origin:
        row["origin"] = origin
    log.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    text = sw.remind({"prompt": row["message"]["content"], "transcript_path": str(log)}, CLOUD)
    assert text and "付け直す" not in text
    # 行がまだ無い最初の知らせ: 文だけで子の窓と言い切らず、サーバの記録（parent_session_id）で決めさせる
    first = sw.remind({"prompt": row["message"]["content"]}, CLOUD)
    assert first and sw.REMIND_CHILD not in first and "parent_session_id" in first, first
