"""字の並びで照らしていた試験を、正本から照らす物を読み・字を寄せて照らす形に替えた注入の試験（台帳の行ごとに 1 つ以上）。

どれも、行の「起きた問題」の形（言い換え・全角・空白の差・別の名の入れ物）を作り物で入れ、照らしが拒むことを見る。
"""
import subprocess

import pytest

import test_checker_eye_and_cards as EYE
import test_guard_hooks_decl as HK
import test_no_handcopied_lists as NH
import test_skill_shohon as SH
import test_skill_values_no_rule_copy as RC

ROOT = NH.ROOT


# ── 行 ede4be7d5f3a: 入口の一覧を変数の名・空白の差で戻しても拒む（ast で読む）──
@pytest.mark.parametrize("inject", [
    'HOOK_TABLE = [("irreversible","check")]\n',
    "WATCH = {'pre': [( 'irreversible' , 'check' )]}\n",
    'NAMES = "irreversible.check outbound.check".split()\n',
    "import irreversible\n",
    "from outbound import check as _o\n",
])
def test_H7_入口に一覧を戻すと拒む(inject):
    src = (HK.SCRIPTS / "guard.py").read_text(encoding="utf-8")
    assert HK.entry_copies(src.replace("EVENTS = {", inject + "EVENTS = {", 1), HK.watcher_names())


# ── どの行も: 照らす相手（正本から読む要素）が空のまま緑にしない ──
def test_H7_正本から読む要素が空でない():
    assert len(SH.wrong_form_canon()[1]) == 4 and len(SH.decider_canon()) == 2
    assert {"原因の台帳", "決定の記録"} <= SH.canon_records()
    assert RC.canon_sections()["核"] and RC.canon_sections()["細目"]


# ── 行 cd196bc6dc07: 古い 1 文の語順・言い回しを変えても拒む ──
@pytest.mark.parametrize("line", [
    "- 書いた窓と別の目を立てる時は読むだけの助手（Agent）にこの skill を読ませる。",
    "- 読むだけの助手を立てれば、書いた窓とは別の目になる。",
    "- 別の目は、書いた窓が立てた助手でもよい。",
])
def test_H7_助手を別の目と言う文は語順を変えても拒む(line):
    text = EYE.SKILL.read_text(encoding="utf-8")
    assert EYE.eye_problems(text + "\n" + line + "\n")


def test_H7_description_から打ち消しを外すと拒む():
    text = EYE.SKILL.read_text(encoding="utf-8")
    assert EYE.eye_problems(text.replace("書いた窓が立てた助手は別の目にならない", "書いた窓が立てた助手も使える", 1))


# ── 行 fd113c8d4b1c / c9a7b1a1a291: 正本の要素を言い換えて並べた写し・表の頭を変えた写しを拒む ──
def _step1():
    text = SH.read(SH.REGISTER)
    return text[text.index("## Step 1"):text.index("## Step 2")]


def test_H7_誤りが入れない形を言い換えて並べると拒む():
    s = _step1().replace("「誤りが入れない形」）", "「誤りが入れない形」）— 写しの段を無くす／入口で誤りを拒む／正道だけを外へ出す／名指しで人の関所へ回す", 1)
    assert SH.copies(s)


@pytest.mark.parametrize("head", ["| 足す物 | 誰が決める |", "| 足す物 | 決める人 |", "| 種類 | 入れる人 |"])
def test_H7_分け方の表は頭を変えても拒む(head):
    table = (head + "\n|---|---|\n| 畳む・直す・言い換え・止めずに知らせるだけの物 | AI が入れてよい |\n"
             "| 新しく「止める」物・核の原則の変更 | オーナーの同意を取る |\n\n")
    s = _step1().replace("- 安全の常設の守り", table + "- 安全の常設の守り", 1)
    assert SH.copies(s)


def test_H7_昔の_Step_1_は写しと見る():
    old = subprocess.run(["git", "show", "9406c94^:plugins/dev-flow/skills/register-rule/SKILL.md"],
                         cwd=ROOT, capture_output=True, text=True)
    if old.returncode != 0:
        pytest.skip("git の歴史が浅い")
    s = old.stdout[old.stdout.index("## Step 1"):old.stdout.index("## Step 2")]
    assert len(SH.copies(s)) == 2


# ── 行 f81f01697855 / dbd73e17fc99: 記録の行き先を言い換えて他の所に置かせると拒む ──
@pytest.mark.parametrize("cell", [
    "各社の原因の台帳。返事に 1 行書く",
    "各社の置き場。プルリクの本文に書く",
    "各社の決定の記録と、プルリクの本文",
    "返事に 1 行書く",
    "無し（各社の原因の台帳）。プルリクの説明に残す",
])
def test_H7_記録の行き先を言い換えても拒む(cell):
    assert not SH.record_default_ok(cell)
    assert not SH.record_dest_ok(cell + "＝核 §8")


def test_H7_記録の行き先の正しい形は通す():
    assert SH.record_dest_ok("各社の原因の台帳の行にする＝細目 §3・核 §8。返事の中だけに置かない")
    assert SH.record_default_ok("各社の CLAUDE.md が名指す決定の記録。名指しが無ければ PR 本文で代わりにせず聞く")


# ── 行 fa23b0312aab: common の入れ物の名を変えても拒む（鍵の一覧の正本 schema.json で照らす）──
@pytest.mark.parametrize("line", [
    "会社の規律は表の `common.policy`。", "会社の規律は表の `common.kitei.no_confirm`。",
    "会社の規律は表の common.rules。", "会社の規律は表の ｃｏｍｍｏｎ．ｒｕｌｅｓ。", "会社の規律は表の common . rules。",
])
def test_H7_正本に無い_common_の鍵は拒む(line):
    text = RC.MINDMAP.read_text(encoding="utf-8") + "\n" + line + "\n"
    assert RC.problems(text)


def test_H7_在る_common_の鍵と名の読みは通す():
    assert RC.bad_common("`common.glossary`・`common.save_dir_avoid`・guard_common.foundation_file") == []
    assert RC.bad_common_table({"common": {"policy": {}}}) and RC.bad_common_table({"common": {"glossary": {}}}) == []


# ── 行 ee82d88c1c27: 正本の節を指す書き方を変えても写しと見る ──
@pytest.mark.parametrize("default", ["細目の §3", "核の 3 節", "細目の「直すは根治」", "核 ３ 項", "核の細目 §7"])
def test_H7_正本の節を言い換えて指す既定も写しと見る(default):
    text = RC._insert_row(RC.PREIMPL.read_text(encoding="utf-8"), f"| `root_fix` | 根治の定義 | {default} |")
    assert RC.problems(text)


def test_H7_skill_の中の節を指す既定は写しと見ない():
    assert not RC.canon_ref("下の §戻り の 7 欄") and not RC.canon_ref("無し（下の §往き の芯だけ）")


# ── 行 ffdda08ccb4e / d2e9b8a99c90 / ece6a88bbe7b: PR の型の欄を全角・別の名・別の区切りで戻しても拒む ──
@pytest.mark.parametrize("field", ["触る path：<x>", "触る path: <x>", "触った path: <x>", "変えた file: <x>", "path＝<x>"])
def test_H7_PR_の型の頭に手で写す欄を足すと拒む(field):
    t = NH.template()
    c = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert NH.head_problems(t.replace("検査:", field + "\n検査:", 1), c)


@pytest.mark.parametrize("form", [
    "- 台帳の行 <行の id の末尾 12 字> 行き先＝直す窓",
    "- <行の題> — 回す先: 直す窓 <窓の URL>",
    "- 台帳の行 <行の id> 直す窓",
    "- <行の題> 行き先: 直す窓 <窓の URL>",
])
def test_H7_残りの_1_行に行き先を写させると拒む(form):
    t = NH.template()
    assert NH.rest_problems(t.replace("- 台帳の行 <行の id の末尾 12 字>", form, 1))


@pytest.mark.parametrize("src", ["PR 本文の `触る path：` と依頼の触ってよい path", "PR 本文の `変えた file:` と依頼の path"])
def test_H7_レビューが本文の欄から_path_を取ると拒む(src):
    assert NH.review_path_problems(f"| 2 宣言した path | {src} | その外を変えた |")
