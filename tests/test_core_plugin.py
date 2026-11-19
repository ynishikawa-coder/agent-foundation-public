"""plugin core の試験: 核の差し込み（写しの枠が在れば差し込まない）と、量の上限の照らし。"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "core"
TOOL = PLUGIN / "scripts" / "kaku.py"

spec = importlib.util.spec_from_file_location("kaku", TOOL)
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)
LIMITS = kaku.LIMITS


def size(text: str) -> int:
    return len(text.encode("utf-8"))


def run(*args, project=None):
    env = dict(os.environ)
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True,
                          timeout=30, env=env)


def test_核と振る舞いと細目と_hook_が_plugin_の中に在る():
    assert all((PLUGIN / n).is_file() for n in ["核.md", "振る舞い.md", "細目.md"])
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    cmd = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/kaku.py" in cmd and cmd.endswith(" inject")


def test_写しの枠が無い_repo_には核と細目の在り処を差し込む(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# 固有の決まり\n", encoding="utf-8")
    r = run("inject", project=tmp_path)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    ctx = out["additionalContext"]
    assert ctx.startswith((PLUGIN / "核.md").read_text(encoding="utf-8").rstrip("\n"))
    assert (PLUGIN / "振る舞い.md").read_text(encoding="utf-8").rstrip("\n") in ctx, "振る舞いの既定が毎回差し込まれない"
    assert str(PLUGIN / "細目.md") in ctx
    assert "形に迷った時" not in ctx, "細目の案内が「形の細目」と分からない言葉に戻った"


def test_CLAUDE_md_が無い_repo_にも差し込む(tmp_path):
    r = run("inject", project=tmp_path)
    assert r.returncode == 0 and "additionalContext" in r.stdout


def test_写しの枠が在る_repo_には差し込まない(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("<!-- AF-CORE:BEGIN 写し -->\n核\n<!-- AF-CORE:END -->\n固有\n",
                                         encoding="utf-8")
    r = run("inject", project=tmp_path)
    assert r.returncode == 0 and r.stdout == ""


def test_上限の数は_1_か所で_核より各社固有が小さい():
    assert set(LIMITS) == {"核", "振る舞い", "各社固有"}
    assert LIMITS["各社固有"] < LIMITS["核"] and LIMITS["振る舞い"] < LIMITS["核"]


def test_今の核と_この_repo_の_CLAUDE_md_は上限の内():
    r = run("check", "--claude", ROOT / "CLAUDE.md")
    assert r.returncode == 0, r.stdout


def test_各社固有が上限を越えると赤で_上限ちょうどは緑(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("決" * (LIMITS["各社固有"] // 3), encoding="utf-8")
    assert size(claude.read_text(encoding="utf-8")) <= LIMITS["各社固有"]
    assert run("check", "--claude", claude).returncode == 0
    claude.write_text("決" * (LIMITS["各社固有"] // 3 + 1), encoding="utf-8")
    r = run("check", "--claude", claude)
    assert r.returncode == 1 and "各社固有" in r.stdout


def test_写しの枠が在れば枠の外だけを各社固有として測る(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    big = "核" * (LIMITS["各社固有"] // 3 + 10)
    claude.write_text(f"<!-- AF-CORE:BEGIN x -->\n{big}\n<!-- AF-CORE:END -->\n固有\n", encoding="utf-8")
    assert run("check", "--claude", claude).returncode == 0


def test_核が上限を越えると赤(monkeypatch, tmp_path, capsys):
    fat = tmp_path / "核.md"
    fat.write_text("足" * (LIMITS["核"] // 3 + 1), encoding="utf-8")
    monkeypatch.setattr(kaku, "KAKU", fat)
    assert kaku.check(None) == 1
    assert "核" in capsys.readouterr().out


def _節(text, n):
    a = text.index(f"## {n}. ")
    b = text.find("\n## ", a + 1)
    return text[a:] if b < 0 else text[a:b]


def test_核の根治は問題_原因_解決_未来の_4_段で_未来は試験の段でない():
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s3 = _節(kaku_text, 3)
    assert "問題→原因→解決→未来" in s3
    assert "仕組み・設計）が悪い前提" in s3 and "別の目の助手" in s3
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    assert "同じ問題と同じ原因の他の問題が起きない状態" in s3d, "細目 §3 の未来が直した後の姿でない"
    for word in ["**問題**", "**原因**", "**同じ原因の他の問題**", "**解決**", "**未来**",
                 "無理・無駄・重複", "聞かせ方", "混じって", "試験を足す段ではない"]:
        assert word in s3d, f"細目 §3 に無い: {word}"


def test_MGkm_は根治の_4_段の呼び名で説明の頼みにも_4_段で答える():
    assert "問題→原因→解決→未来（MGkm）" in _節((PLUGIN / "核.md").read_text(encoding="utf-8"), 3), "核 §3 に MGkm が無い"
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    assert "**呼び名 MGkm**" in s3d, "細目 §3 に MGkm の呼び名が無い"
    line = next(l for l in s3d.splitlines() if "呼び名 MGkm" in l)
    for word in ["問題 Mondai", "原因 Genin", "解決 Kaiketsu", "未来 Mirai"]:
        assert word in line, f"MGkm の行に無い: {word}"
    line = next(l for l in (PLUGIN / "振る舞い.md").read_text(encoding="utf-8").splitlines() if "**MGkm**" in l)
    for word in ["説明", "4 段の見出しで答える"]:
        assert word in line, f"振る舞いの既定の MGkm の行に無い: {word}"


def test_問いは選ぶ問いと開いた問いに分け_分からないを置き_言葉を混ぜない():
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s4 = _節(kaku_text, 4)
    for word in ["選択肢の画面", "「分からない」も置く", "開いた問い", "AI の読み", "「分からない」には問いを作り直す"]:
        assert word in s4, f"核 §4 に無い: {word}"
    assert "例え話にせず" in _節(kaku_text, 2)
    s4d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 4)
    for word in ["どの問いにも「分からない」の選択肢", "AI の今の読み", "選ぶ問いと開いた問い", "問いの言葉", "開発用語", "業界の専門用語", "決まりの言葉", "オーナーの言葉", "例え話に替えず"]:
        assert word in s4d, f"細目 §4 に無い: {word}"


def test_古い根治と聞き方の言い回しが土台に残らない():
    olds = ["根治の 4 つの問い", "①構造の原因", "いつも選択肢の画面", "返事の中で平文の問いを出さない",
            "専門用語は日常の言葉にする", "専門の語は日常の言葉に言い換え", "名前・数字など選べない答えも候補を選択肢に置き"]
    hits = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in {".git", "tests"} or p.name == "CHANGELOG.md":
            continue                       # 試験の中の古い語の一覧と、変更の記録の経緯は除く
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".html"}:
            text = p.read_text(encoding="utf-8")
            hits += [f"{rel}: {o}" for o in olds if o in text]
    assert not hits, hits


def test_一言の返事は札と締めを省き_窓の役に決まった一覧を置かない():
    """同じ原因（決まりが 1 つの形に押し込める）の残り: 短い返事に 3 行を足さない・役の名を 5 つに閉じない。古い形を戻すと赤。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    assert "一言で済む返事は札と締めを省く" in _節(kaku_text, 5)
    s5d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 5)
    assert "**一言で済む返事**" in s5d and "札を付けたら締めも付ける" in s5d
    olds = ["の 5 つだけ。他の名を足さない", "親・書く・レビュー・調べ・手 の 5 つ", "社内で確かめてから答える", "問いの形（3 つだけ）", "決まった 4 文"]
    hits = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in {".git", "tests"} or p.name == "CHANGELOG.md":
            continue
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".html"}:
            text = p.read_text(encoding="utf-8")
            hits += [f"{rel}: {o}" for o in olds if o in text]
    assert not hits, hits


def test_核の根治は誤りが入れない形と注入の試験を持つ():
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s3 = _節(kaku_text, 3)
    for word in ["誤りが入れない形", "1 つの正本", "写さない", "既定で止める", "証明", "人の関所", "わざと入れて"]:
        assert word in s3, f"核 §3 に無い: {word}"
    assert "申告でなく記録" in _節(kaku_text, 7)
    saimoku = (PLUGIN / "細目.md").read_text(encoding="utf-8")
    s3d = _節(saimoku, 3)
    for word in ["写す工程を無くす", "誤った物が入れない", "正しい道だけが外へ出す", "防げない物は名指しで人の関所へ", "注入の試験", "古い道は残さず"]:
        assert word in s3d, f"細目 §3 に無い: {word}"
    assert "記録で確かめる" in _節(saimoku, 7)


def test_挙げた原因は全部台帳に行き先つきで持ち_全部済むまで終わったと言わない():
    """原因が 5 つ挙がって 1 つしか直らない形を戻すと赤（1 つ選ぶ・一番手前から取る・どれを今回直すか）。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s3 = _節(kaku_text, 3)
    for word in ["原因の台帳", "1 行ずつ", "直す窓／直した／直さない", "オーナーが決めた理由"]:
        assert word in s3, f"核 §3 に無い: {word}"
    s7 = _節(kaku_text, 7)
    assert "「直した」か「直さない」になるまで終わったと言わない" in s7 and "直す窓の行が残れば一部" in s7
    s4 = _節(kaku_text, 4)
    assert "1 つ選ばせる問いを出さない" in s4 and "挙がった物は全部やり" in s4
    saimoku = (PLUGIN / "細目.md").read_text(encoding="utf-8")
    assert "**原因の台帳**" in _節(saimoku, 3) and "**選ばせない**" in _節(saimoku, 4) and "**根治の終わり**" in _節(saimoku, 7)
    assert "1 本の列にせず" in (PLUGIN / "振る舞い.md").read_text(encoding="utf-8"), "引き継ぎの残りが番号の列に戻った"
    olds = ["どれを今回直す", "一番手前の未決から取る", "どれから進めますか」と聞"]
    hits = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in {".git", "tests"} or p.name == "CHANGELOG.md":
            continue
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".html"}:
            text = p.read_text(encoding="utf-8")
            hits += [f"{rel}: {o}" for o in olds if o in text]
    assert not hits, hits


def test_main_へは製品もオーナーに聞かずに入れ_絵と差がある時だけ止める():
    """「本番への出荷は聞く」を核に戻すと赤（Notion の決定と窓が読む核が食い違う形）。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    assert "本番への出荷" not in _節(kaku_text, 4), "核 §4 に「本番への出荷は聞く」が戻った"
    s7 = _節(kaku_text, 7)
    for word in ["（製品も）オーナーに聞かずに入れる", "レビュー green", "試験が緑で衝突なし", "全体の絵", "差がある・照らせない時は止めて聞く", "先に絵を描き"]:
        assert word in s7, f"核 §7 に無い: {word}"
    s7d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 7)
    assert "**main へ入れる**" in s7d and "**③の段が土台に入るまで**" in s7d
    assert "核 §7 の「照らせない時」" in s7d, "照らす段が無い間の一言が核から読めない形に戻った"
    assert "核 §7 と細目 §7 の「main へ入れる」" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_ミスが出たらまず構造を疑い_単発と言うのは絵の上で示せた時だけ():
    """根治の入口を「直す・作る時」だけに戻す・単発で片付ける道を戻す・規律を 2 度目まで足し続ける形を戻すと赤。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s3 = _節(kaku_text, 3)
    first = s3.split("\n- ", 1)[1]
    assert first.startswith("ミスが出た時（画面の見た目を除く）と直す・作る時の既定は根治"), "根治の入口が直す・作る時だけに戻った"
    for word in ["まず構造（上位の前提", "単発の誤りと言うのは全体の絵の上で構造に原因が無いと示せた時だけ",
                 "守り（確かめ・決まり）を足さず"]:
        assert word in s3, f"核 §3 に無い: {word}"
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    assert "**まず構造を疑う**" in s3d
    for word in ["作業の途中・レビュー・検査・引き継ぎ", "画面の見た目の崩れだけは除く", "示した所（絵のどこを見たか）を書く",
                 "根に届いていない合図で、原因の段へ戻る"]:
        assert word in s3d, f"細目 §3 の「まず構造を疑う」に無い: {word}"
    rr = (ROOT / "plugins" / "dev-flow" / "skills" / "register-rule" / "SKILL.md").read_text(encoding="utf-8")
    assert "細目 §3「まず構造を疑う」" in rr, "register-rule が規律を足す前に原因の段へ戻さない"
    assert "細目 §3「まず構造を疑う」" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"), "red を単発の手直しで済ませる形に戻った"
    olds = ["同じ種類の失敗が 2 度なら", "原因は仕組み・設計が悪い前提で探し"]
    hits = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in {".git", "tests"} or p.name == "CHANGELOG.md":
            continue
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".html"}:
            text = p.read_text(encoding="utf-8")
            hits += [f"{rel}: {o}" for o in olds if o in text]
    assert not hits, hits


def test_核から細目へ移した物が細目に在る():
    """量を空けるために核から移した物が、どこにも無くならない。"""
    saimoku = (PLUGIN / "細目.md").read_text(encoding="utf-8")
    assert "「ほぼ終わった」と書かない" in _節(saimoku, 7)
    s8 = _節(saimoku, 8)
    assert "Javis は Notion と Drive" in s8 and "**またぐ連絡**" in s8


# ---- 振る舞いの既定（AI の癖と逆を求める物）は核と一緒に毎回差し込む ----

FURUMAI_WORDS = {  # 既定の要の語: 振る舞い.md だけに在り、細目に戻らない（2 か所に書かない）
    "並走": ["着手と言われたら確認させずに進め", "5 分を超える作業は窓・助手を並べて同時に進める",
             "読むだけの調べは助手", "書く仕事と互いに待たない長い仕事は窓"],
    "後継": ["1 本の列にせず"],
    "範囲": ["止まる条件は狭く", "黙って縮めない"],
    "聞かない": ["自分の枝への push の前に聞かない", "依頼文の出来を人に見てもらわない"],
    "引く": ["決定の記録と問いの表を問いと同じ言葉で引く"],
    "人の手": ["まず Claude in Chrome に貼る文"],
    "正本": ["「無い」「止まった」と言い切る前に正本を読む"],
    "ぼかさない": ["「たぶん」「概ね」と書かず", "前→後"],
    "逃げ場": ["「できれば」「間に合わなければ後で」と書かない"],
    "呼び出し": ["2 回で打ち方を変えるか止める"],
    "一覧": ["削らない・選ばない"],
    "MGkm": ["「MGkm して」と言ったら"],
}


def test_振る舞いの既定は全部_振る舞い_md_に在り細目に戻らない():
    furumai = (PLUGIN / "振る舞い.md").read_text(encoding="utf-8")
    saimoku = (PLUGIN / "細目.md").read_text(encoding="utf-8")
    missing = [w for ws in FURUMAI_WORDS.values() for w in ws if w not in furumai]
    assert not missing, f"振る舞いの既定に無い: {missing}"
    olds = ["自分の枝への push の前", "「無い」「止まった」と言い切る前", "間に合わなければ後で", "2 回で打ち方を変える",
            "「たぶん」「概ね」", "削らない・選ばない", "5 分を超え", "③は 1 本の列", "説明・振り返りの頼みでもこの 4 段",
            "広く任された物として進め", "依頼文の出来を人に求めない"]
    back = [o for o in olds if o in saimoku]
    assert not back, f"振る舞いの既定が細目にも書かれた（2 か所）: {back}"


def test_振る舞いの正本が無いと_check_は赤で_inject_は欠けを名指しする(monkeypatch, tmp_path, capsys):
    gone = tmp_path / "振る舞い.md"            # わざと消す
    monkeypatch.setattr(kaku, "FURUMAI", gone)
    assert kaku.check(None) == 2
    assert "振る舞い.md が読めない" in capsys.readouterr().out
    ctx = kaku.inject_text()
    assert "振る舞いの既定" in ctx and "差し込まれていない" in ctx and str(gone) in ctx


def test_振る舞いが上限を越えると赤で_上限ちょうどは緑(monkeypatch, tmp_path, capsys):
    f = tmp_path / "振る舞い.md"
    monkeypatch.setattr(kaku, "FURUMAI", f)
    f.write_text("既" * (LIMITS["振る舞い"] // 3), encoding="utf-8")
    assert kaku.check(None) == 0
    f.write_text("既" * (LIMITS["振る舞い"] // 3 + 1), encoding="utf-8")
    assert kaku.check(None) == 1
    assert "振る舞いの既定" in capsys.readouterr().out


def test_inject_は振る舞いを核の後に毎回入れる(monkeypatch, tmp_path):
    f = tmp_path / "振る舞い.md"
    f.write_text("# 既定\n- 印の既定\n", encoding="utf-8")
    monkeypatch.setattr(kaku, "FURUMAI", f)
    ctx = kaku.inject_text()
    assert ctx.index("# 振る舞いの核") < ctx.index("- 印の既定")
