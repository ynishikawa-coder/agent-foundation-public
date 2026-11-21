"""「読み切れた」と見なす命令の読み方が bash とずれる所と、前の main より止める・当てる場面が変わる所を、わざと入れて
今の扱いを示す（レビューの red の 4 回目）。
- | && || |& の後の改行（空行・注釈も）は bash が越えて同じ命令を続ける＝動く側（前の main でも止まっていた形）。
- 引用の外の \\ と改行・\\r は bash と shlex で読みがずれる＝読み切れない形として字全体で見る。
- path 付きの道具の名（./grep・~/bin/echo）は同じ名の別の実行ファイルかもしれない＝動く側（/bin・/usr/bin の物だけ字を挙げる側）。
- 字を挙げるだけの並びは打った字（引用と \\ で逃がした字を空にした形）で当てる＝`DROP\\ TABLE` を前の main より多く止めない。
- 動く並びは打った字のまま当てる＝値の表の引用符を含む行が前の main と同じく当たる。
入力は全部作り物（名は字を割って書く）。"""
import json

import pytest

from test_guard import ask_result, bash, denied, env, hook  # noqa: F401  （env は fixture）
from test_guard_uses_form import GATE, LOCK, SQL

RUN = "python3 型/%s 設計書 %s" % (GATE, LOCK)
PSQL = "psql -c \"%s\"" % SQL

SPLIT = [
    "echo '{x}' |\nsh",
    "echo '{x}' |# c\nsh",
    "echo '{x}' |&\nsh",
    "echo '{x}' |\n\nsh",
    "git commit -m '{x}' |\nsh",
    "echo '{x}' \\\n| sh",
    "echo '{x}' &&\nsh -c '{x}'",
    "echo ok ||\n\n{x}",
    "echo '{x}'\r| sh",
    "./grep -c '{x}'",
    "/tmp/x/echo -c '{x}'",
    "~/bin/cat -c '{x}'",
    "echo '{x}' | ./grep",
    "bin/git log --grep='{x}'",
]


@pytest.mark.parametrize("form", SPLIT)
def test_spec_gate_bash_と区切りがずれる形と_path_付きの道具は止まる(env, form):
    cmd = form.replace("{x}", RUN)
    assert denied(env, bash(cmd)), cmd


@pytest.mark.parametrize("form", SPLIT)
def test_irreversible_bash_と区切りがずれる形と_path_付きの道具は離席中止まる(env, form):
    hook(env, "post", ask_result())
    cmd = form.replace("{x}", PSQL)
    assert denied(env, bash(cmd)), cmd


@pytest.mark.parametrize("cmd", [
    "echo '%s は止まる'\n/bin/echo ok" % RUN,
    "/usr/bin/grep -rn '%s' plugins" % LOCK,
    "git commit -m '%s を止める' &&\n  git push -u origin claude/x" % RUN,
])
def test_spec_gate_決まった置き場の道具と続きの行の字を挙げるだけの形は今も通す(env, cmd):
    assert not denied(env, bash(cmd)), cmd


@pytest.mark.parametrize("cmd", [
    "git commit -m DROP\\ TABLE",
    "echo DROP\\ TABLE",
    "grep -rn DROP\\ TABLE .",
    "git commit -m TRUNCATE\\ TABLE",
])
def test_irreversible_字を挙げるだけの並びの逃がした空白は前の_main_より止めない(env, cmd):
    hook(env, "post", ask_result())
    assert not denied(env, bash(cmd)), cmd


def test_irreversible_値の表の引用符を含む行は動く並びに前の_main_と同じく当たる(env, tmp_path):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"irreversible_bash_extra": [
        {"pattern": r'kubectl\s+delete\s+ns\s+"prod"', "why": "本番の名前空間の削除"},
        {"pattern": r"my-db\s+--wipe\s+'all'", "why": "DB の破棄"}]}}), encoding="utf-8")
    env["SKILL_VALUES"] = str(table)
    hook(env, "post", ask_result())
    assert denied(env, bash('kubectl delete ns "prod"'))
    assert denied(env, bash("my-db --wipe 'all'"))
    assert not denied(env, bash('git commit -m \'kubectl delete ns "prod" を止める\''))
