"""guard の答えの戻り: 選択肢の画面に答えが返った時、行き先（決定の記録・決まり・原因の台帳の行）を知らせるか（A9 の注入の試験）。"""
import json

from test_guard import ask_result, env, hook  # noqa: F401  （env は fixture）


def test_答えが返れば行き先を知らせ答えが無ければ知らせない(env):
    """答えを台帳から降ろすだけで行き先（細目 §8「決めた事」）を言わない古い形に戻すと赤（A9 の注入）。"""
    note = hook(env, "post", ask_result(answered=True)).get("additionalContext", "")
    assert "<answer-return>" in note and "細目 §8「決めた事」" in note
    assert "作り物の置き場を A と B のどちらにしますか" in note
    assert "<answer-return>" not in hook(env, "post", ask_result(sid="s9")).get("additionalContext", "")


def test_答えの知らせに値の表の書き方が載る(env, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "config").mkdir()
    (repo / "config" / "skill-values.json").write_text(
        json.dumps({"guard": {"answer_record": "作り物の記録の口に書く"}}, ensure_ascii=False), encoding="utf-8")
    data = dict(ask_result(answered=True), cwd=str(repo))
    assert "この repo の書き方: 作り物の記録の口に書く" in hook(env, "post", data).get("additionalContext", "")
