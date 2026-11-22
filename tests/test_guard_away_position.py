"""guard の irreversible: 離席の間の戻せない操作の止めを、離席の印に記した会話ログの位置より後の人の行で解くか（注入の試験）。

意図: オーナーが席を外している間だけ戻せない操作を止め、戻ったら止めを解く。
課題: 戻った後に大きな出力が続くと止め続け、積まれた入力は戻りと数えず、子の窓の知らせの行で人がいないのに止めを解いていた。
  読めない離席の印を「印が無い＝在席」と読み、印を書けない時は黙っていた（原因の台帳の行）。
原因: 戻りを時刻と末尾 200KB で数え、人の行を origin の欠けで見分け、読めない印を無いと同じに扱っていた。
"""
import json

import pytest

from test_guard import (DROP, append, ask_result, away_log, bash, deny_reason, denied, env, hook,  # noqa: F401
                        human, write_log)


def test_戻った後に大きな出力が続いても戻りを数える(env, tmp_path):
    """末尾の 200KB だけを読む古い形では、人の行が大きな出力の後ろに埋もれて止め続けた。"""
    tpath = away_log(env, tmp_path)
    big = {"type": "user", "toolUseResult": {}, "message": {"content": "作" * 120_000}}
    append(tpath, human("戻りました"), big, big)
    assert not denied(env, bash(DROP, tpath=tpath))


def test_積まれた入力は時刻が印より前でも位置で戻りと数える(env, tmp_path):
    """入力が積まれた時刻（印より前）で書かれる行を、時刻で比べる古い形は戻りと数えなかった。"""
    tpath = away_log(env, tmp_path)
    append(tpath, human("積んでおいた頼み", ts="2000-01-01T00:00:00Z"))
    assert not denied(env, bash(DROP, tpath=tpath))


@pytest.mark.parametrize("row", [
    {"type": "user", "origin": {"kind": "task-notification"}, "promptSource": "system",
     "message": {"content": "<task-notification>作り物の子の窓が終わった</task-notification>"}},
    {"type": "user", "isCompactSummary": True, "message": {"content": "作り物の要約"}},
], ids=["子の窓の知らせ", "縮めた要約"])
def test_人のいない行では離席の止めを解かない(env, tmp_path, row):
    tpath = away_log(env, tmp_path)
    append(tpath, dict(row, timestamp="2999-01-01T00:00:00Z"))
    assert denied(env, bash(DROP, tpath=tpath))


def test_印より後の読めない行は止めたまま行の番号を出す(env, tmp_path):
    tpath = away_log(env, tmp_path)
    append(tpath, raw="{壊れた行\n")
    why = deny_reason(env, bash(DROP, tpath=tpath))
    assert "戻りを確かめられなかった訳" in why and "行の番号: 2" in why, why


def test_位置の無い古い印と別の会話ログでは戻りを数えない(env, tmp_path):
    away = tmp_path / "tmp" / "away"
    away.mkdir(parents=True)
    (away / "s1.json").write_text(json.dumps({"since": "2000-01-01T00:00:00Z", "questions": ["作り物"]}), encoding="utf-8")
    tpath = write_log(tmp_path / "o.jsonl", [human("戻りました", ts="2999-01-01T00:00:00Z")])
    assert "古い印" in deny_reason(env, bash(DROP, tpath=tpath))
    mine = away_log(env, tmp_path)
    other = write_log(tmp_path / "x.jsonl", [human("別の窓の頼み")])
    assert "違う" in deny_reason(env, bash(DROP, tpath=other))
    assert denied(env, bash(DROP, tpath=mine))
    write_log(tmp_path / "t.jsonl", [])                       # 縮んだ会話ログ
    assert "短い" in deny_reason(env, bash(DROP, tpath=mine))


@pytest.mark.parametrize("raw", ['{"since": "2000-01-01T00:00:00Z", "questi', "[1, 2]"], ids=["書きかけ", "dict でない"])
def test_読めない離席の印は閉じたと取り違えず止めたまま訳を出す(env, tmp_path, raw):
    """読めない印を「印が無い＝在席」と読む古い形は、人のいない間に戻せない操作を通した。"""
    away = tmp_path / "tmp" / "away"
    away.mkdir(parents=True)
    (away / "s1.json").write_text(raw, encoding="utf-8")
    tpath = write_log(tmp_path / "o.jsonl", [human("戻りました")])
    why = deny_reason(env, bash(DROP, tpath=tpath))
    assert "離席の印" in why and ("読めない" in why or "dict でない" in why), why


def test_離席の印を書けなければ黙らず知らせ_重ねて閉じた問いは控えを残す(env, tmp_path):
    tpath = away_log(env, tmp_path)
    second = ask_result(tpath=tpath)
    second["tool_response"]["questions"][0]["question"] = "作り物の次の問いですか"
    hook(env, "post", second)
    marker = json.loads((tmp_path / "tmp" / "away" / "s1.json").read_text(encoding="utf-8"))
    assert len(marker["questions"]) == 2, marker
    blocker = tmp_path / "tmp2"
    blocker.write_text("置き場を塞ぐ file", encoding="utf-8")
    env["AF_GUARD_TMP"] = str(blocker)                       # 印の置き場が file で塞がれ、書けない
    note = hook(env, "post", ask_result(sid="s9")).get("additionalContext", "")
    assert "離席の印" in note and "書けなかった" in note, note
