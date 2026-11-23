"""核・細目・振る舞いの既定の要の語を、その語が決まりとして置かれた所（核の箇条・細目と振る舞いの欄・表の行・見出しの下）で照らす。

意図: 核と細目の要の語が、決まりとして置かれた所に在る間だけ試験が緑になる。
課題: test_core_plugin.py は要の語を節や file の字のどこかに在るかで照らし、注記の中・囲いの中・別の箇条・別の欄へ移っても緑だった。
      赤を返す所の入口（細目 §3「まず構造を疑う」）も file のどこかに在れば緑で、赤の文の隣に在るかを見なかった。
      増え方の照らしの入口はコードの字を照らし、回した時に何を比べるかを見なかった。
原因: 試験が文書を字の並びとして読み、置き場（箇条・欄・表の行・見出し）を読む共通の読み方（tests/md_yomi.py）を通らなかった。
解決: 照らしの関数をここに 1 つずつ置き（md_yomi で読む・道具は動かして見る）、test_core_plugin.py の試験はここを呼ぶ。
      注入の試験は、語を注記へ移す・別の欄へ移す・囲いに入れると赤、言い回しの外を変えても緑を見る。
"""
import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from md_yomi import 地の行, 箇条の子, 欄, 節, 見出し, 置き場, 表の行
from saimoku import 全文 as 細目の全文

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "core"
GUARD = ROOT / "plugins" / "guard" / "scripts"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kaku = _load("kaku_okiba", PLUGIN / "scripts" / "kaku.py")


def 核():
    return (PLUGIN / "核.md").read_text(encoding="utf-8")


def 振る舞い():
    return (PLUGIN / "振る舞い.md").read_text(encoding="utf-8")


# ── 読み方 ──

def 番号の節(text, n):
    """`## n. 名` の見出しの下（1 つでなければ None）。"""
    heads = [h for h in 見出し(text, 2) if h.startswith(f"{n}. ")]
    return 節(text, heads[0]) if len(heads) == 1 else None


def 核の箇条(text, n):
    """核 §n の上の段の箇条を出る順に返す（字下げの続きの行は同じ箇条に入れる）。注記・囲いの中は読まない。"""
    body = 番号の節(text, n)
    out = []
    for line in 地の行(body or ""):
        if line.startswith("- "):
            out.append(line[2:])
        elif out and line.startswith(" ") and line.strip():
            out[-1] += "\n" + line.strip()
    return out


# ── 照らし（崩れを文の列で返す。空なら緑）──

def 箇条の語(text, n, words, where="核"):
    """words が全部、核 §n の同じ 1 つの箇条に在るか。"""
    items = 核の箇条(text, n)
    if not items:
        return [f"{where} §{n} に箇条が無い"]
    best = max(items, key=lambda b: sum(w in b for w in words))
    return [f"{where} §{n} の同じ箇条に無い: {w}" for w in words if w not in best]


def 欄の語(text, name, words, where):
    """太字の名が name の欄がちょうど 1 つ在り、words が全部その欄の中に在るか。"""
    body = 欄(text or "", name)
    if body is None:
        return [f"{where} の欄「{name}」が 1 つでない"]
    return [f"{where} の欄「{name}」に無い: {w}" for w in words if w not in body]


def 細目の欄の語(n, name, words, saimoku=None):
    return 欄の語(番号の節(saimoku if saimoku is not None else 細目の全文(), n), name, words, f"細目 §{n}")


# 核の要の語: 同じ箇条に揃って在る物の組
核の語 = {
    2: [["例え話にせず"]],
    3: [["まず構造（上位の前提", "仕組み・設計）が悪い前提", "単発の誤りと言うのは構造に原因が無いと示せた時だけ（絵があれば絵の上で）",
         "守り（確かめ・決まり）を足さず", "別の目の助手", "原因の台帳", "全部", "行き先", "誤りが入れない形", "1 つの正本",
         "写さない", "既定で止める", "証明", "人の関所", "わざと入れて"]],
    4: [["並べて 1 つ選ばせる問いを出さない", "全部やり、分け方は AI が決める"],
        ["案と前提をチャットで先に見せ", "画面の問いは 1 文に", "選択肢の画面", "開いた問い", "AI の読み",
         "推奨の印は作り方の分かれ道だけ", "済んだかは AI が確かめてから", "答えを待つ間は答えに頼らない事を進める"]],
    5: [["一言で済む返事は札と締めを省く"]],
    7: [["申告でなく記録", "「直した」か「直さない」になるまで終わったと言わない", "直す窓の行が残れば一部"]],
}
根治の入口 = "ミスが出た時（画面の見た目を除く）と直す・作る時の既定は根治"


def 核の崩れ(text=None):
    text = 核() if text is None else text
    out = []
    for n, groups in 核の語.items():
        for words in groups:
            out += 箇条の語(text, n, words)
    first = 核の箇条(text, 3)[:1]
    if not first or not first[0].startswith(根治の入口):
        out.append("核 §3 の 1 つ目の箇条が根治の入口で始まらない")
    return out


# 細目の要の語: {節: {欄の名: [語]}}（[] は欄が 1 つ在ればよい）
細目の語 = {
    3: {"誤りが入れない形": ["写す工程を無くす", "誤った物が入れない", "正しい道だけが外へ出す", "防げない物は名指しで人の関所へ"],
        "根治の 5 段": ["注入の試験", "古い道は残さず"],
        "まず構造を疑う": ["作業の途中・レビュー・検査・引き継ぎ", "画面の見た目の崩れだけは除く",
                       "示した所を書く（合意した全体の絵があれば絵のどこを見たか、無ければ言葉で）", "根に届いていない合図で、原因の段へ戻る"],
        "原因の台帳": ["1 つ 1 行", "`直す窓`", "`直した`", "`直さない`", "オーナーが決めた理由"],
        "残りの受け皿は原因の台帳 1 つ": ["`台帳へ` の札", "DEFER", "一時しのぎ", "「一部」の残り", "どの窓も持たなかった論点", "選ばれなかった案",
                                "1 窓 1 枝 1 PR に入らなかった仕事", "合流の後の続き", "道具の都合", "正本は台帳"]},
    4: {"選ぶ問いと開いた問い": ["どの問いにも「分からない」の選択肢", "「分からない」が返った", "AI の今の読み"],
        "問いの言葉": ["開発用語", "業界の専門用語", "決まりの言葉", "オーナーの言葉", "例え話に替えず"],
        "見せてから聞く": ["1 文（前提も①へ）", "選択肢の説明へ"],
        "前提の出所": ["オーナーの言葉／記録の事実／AI の読み", "「ずれ」と決め込まない", "「なぜこの形か」を問う"],
        "推奨の印": ["済んだかの確認には付けない"],
        "答えを待つ間": ["推奨で先に進めない"],
        "手の窓": ["「終わった」「うまくいかない」「分からない」・推奨の印は付けない"],
        "選ばせない": []},
    5: {"一言で済む返事": ["札を付けたら締めも付ける"]},
    7: {"書かない言い方": ["「ほぼ終わった」と書かない"], "記録で確かめる": [], "根治の終わり": [],
        "土台の直しの終わり": ["使う側の repo", "同じ仕事の中で直す", "洗い出しだけで終わらせない", "使う側の写しの残り",
                         "合流するまで「終わった」と言わない", "原因の台帳の行"]},
    8: {"置き場": ["Javis は Notion と Drive"], "またぐ連絡": []},
}
五段の語 = {"原因": ["無理・無駄・重複", "聞かせ方", "混じって"], "未来": ["意図が果たされ", "試験を足す段ではない"]}


def 細目の崩れ(saimoku=None, only=None):
    saimoku = 細目の全文() if saimoku is None else saimoku
    out = []
    for n, fields in 細目の語.items():
        if only and n not in only:
            continue
        for name, words in fields.items():
            out += 細目の欄の語(n, name, words, saimoku)
    if not only or 3 in only:
        dan = dict(箇条の子(番号の節(saimoku, 3) or "", "根治の 5 段") or [])
        out += [f"細目 §3 の{step}の段に無い: {w}" for step, ws in 五段の語.items() for w in ws if w not in dan.get(step, "")]
    return out


# 振る舞いの既定の要の語: {欄の名: [語]}（語は振る舞い.md のその欄だけに在り、細目に戻らない）
振る舞いの語 = {
    "並走": ["着手と言われたら確認させずに進め", "5 分を超える作業は窓・助手を並べて同時に進める",
           "読むだけの調べは助手", "書く仕事と互いに待たない長い仕事は窓"],
    "後継へ渡す残り": ["1 本の列にせず"],
    "範囲": ["止まる条件は狭く", "黙って縮めない"],
    "聞かない": ["自分の枝への push の前に聞かない", "依頼文の出来を人に見てもらわない"],
    "聞く前に引く": ["決定の記録と問いの表を問いと同じ言葉で引く"],
    "人の手": ["まず Claude in Chrome に貼る文"],
    "言い切る前に正本": ["「無い」「止まった」と言い切る前に正本を読む"],
    "ぼかさない": ["「たぶん」「概ね」「〜と思われます」と書かず", "前→後"],
    "計画に逃げ場を書かない": ["「できれば」「間に合わなければ後で」と書かない"],
    "崩れた呼び出し": ["2 回で打ち方を変えるか止める"],
    "同じ原因の他の問題": ["削らず選ばず全部を原因の台帳へ", "直す窓は行ごとでなく関係しない束ごとに並べる"],
    "MGK": ["「MGK して」と言ったら"],
}


def 振る舞いの崩れ(text=None):
    text = 振る舞い() if text is None else text
    return [p for name, words in 振る舞いの語.items() for p in 欄の語(text, name, words, "振る舞い.md")]


# ── 使う側の文書: 置かれた所で照らす ──

def 写しの残りの行(text):
    """design-mode の論点の表（頭の升が「項目」）で、1 つ目の升が「写しの残り」の行（升の列）。"""
    return [r for r in 表の行(text, "項目") if r and r[0] == "写しの残り"]


def 土台の直しの所の崩れ():
    out = []
    c = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    if 置き場(c, "土台の直しの終わり") != ["1. 枝と PR"]:
        out.append(f"CONTRIBUTING の「土台の直しの終わり」の置き場が 1. 枝と PR でない: {置き場(c, '土台の直しの終わり')}")
    dm = (ROOT / "plugins/dev-flow/skills/design-mode/SKILL.md").read_text(encoding="utf-8")
    rows = 写しの残りの行(dm)
    if len(rows) != 1 or "同じ仕事の中" not in " ".join(rows[0]):
        out.append("design-mode の表の写しの残りの行が同じ仕事の中で直さない")
    return out


def 理論モックの印の崩れ(text=None):
    text = (ROOT / "plugins/docs-kit/skills/theory-mock/SKILL.md").read_text(encoding="utf-8") if text is None else text
    body = 節(text, "作り方（skip 禁止）")
    lines = [l for l in 地の行(body or "") if l.startswith("4. ")]
    need = ["作り方の分かれ道（画面・データ・流れをどう作るか）だけを置き", "推奨を付けずにチャットで聞く"]
    if len(lines) != 1:
        return ["theory-mock の作り方の 4. の行が 1 つでない"]
    return [f"theory-mock の作り方の 4. に無い: {w}" for w in need if w not in lines[0]]


def 待つ間の知らせ():
    """unanswered.py の REMINDER を埋めて出る文（動かして見る）。"""
    sys.path.insert(0, str(GUARD))
    try:
        mod = _load("unanswered_okiba", GUARD / "unanswered.py")
    finally:
        sys.path.remove(str(GUARD))
    return mod.REMINDER.format(n=1, stems="「x」", ttl=mod.LEDGER_TTL_HOURS, ledger="L")


# ── 赤を返す所: 入口が赤の文と同じまとまりに在るか ──

入口 = re.compile(r"細目(?:\s*§\s*\d+)?「まず構造を疑う」")
ミスの文 = re.compile(r"赤|(?<![A-Za-z])(NG|red)(?![A-Za-z])|漏れ|抜け|落ち|拾われ|違反|止め|止まっ|失敗|exit 1|clean=False|不一致|出し直|直し[:：]|済ませず")


def 読む所(rel, text):
    """.md は地の行（注記・囲いの外）、ほかは kaku.own（注釈を除いたコード・文字列）。"""
    return "\n".join(地の行(text)) if rel.endswith(".md") else kaku.own(rel, text)


def まとまり(text):
    """空行・箇条の頭・見出しで切ったまとまりの列。"""
    out, cur = [], []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or re.match(r"^\s*([-*]|\d+\.)\s", ln) or s.startswith("#"):
            if cur:
                out.append("\n".join(cur))
            cur = [ln] if s else []
        else:
            cur.append(ln)
    if cur:
        out.append("\n".join(cur))
    return out


def 入口が赤の隣に在る(text, rel="x.md", with_word=ミスの文):
    return any(入口.search(u) and with_word.search(u) for u in まとまり(読む所(rel, text)))


def 見張りの文が入口を持つ(rel, text):
    """guard の見張り（頭に HOOKS を持つ file）は、止めた時の文に guard.py が ROOT_CAUSE を足す（guard.watchers）。
    その見張りは ROOT_CAUSE が入口を赤の文と同じまとまりで持てば足りる。"""
    if not rel.startswith("plugins/guard/scripts/") or not re.search(r"^HOOKS\s*=", text, re.M):
        return False
    sys.path.insert(0, str(GUARD))
    try:
        g = _load("guard_okiba", GUARD / "guard.py")
    finally:
        sys.path.remove(str(GUARD))
    return 入口が赤の隣に在る(g.ROOT_CAUSE, "x.md")


def 入口の崩れ(rel, text=None):
    text = (ROOT / rel).read_text(encoding="utf-8") if text is None else text
    if 入口が赤の隣に在る(text, rel) or 見張りの文が入口を持つ(rel, text):
        return []
    return [f"{rel}: 根治の入口が赤・止めの文と同じまとまりに無い"]


# ── 増え方の照らしの入口を作り物の python3・git で回す ──

def 増え方の入口を回す(tmp_path, merge_base, main_ok=True, has_parent=True):
    work = tmp_path / "repo"
    (work / "scripts" / "checks").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "checks" / "kaku_growth.sh", work / "scripts" / "checks" / "kaku_growth.sh")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "log"
    head = "c" * 40
    py = f"""#!/bin/sh
echo "python3 $*" >> {log}
case "$*" in *--print-main*) {'echo ' + 'b' * 40 if main_ok else 'exit 1'};; esac
exit 0
"""
    git = f"""#!/bin/sh
echo "git $*" >> {log}
case "$1" in
  merge-base) echo {merge_base};;
  rev-parse) case "$*" in *HEAD^1*) {'echo ' + 'd' * 40 if has_parent else 'exit 1'};; *) echo {head};; esac;;
esac
"""
    for name, body in (("python3", py), ("git", git)):
        p = bin_ / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"}
    r = subprocess.run(["bash", str(work / "scripts" / "checks" / "kaku_growth.sh")], env=env, capture_output=True, text=True)
    return r.returncode, (log.read_text() if log.exists() else "")


def ci_の_check_は全部の歴史を取る(ci=None):
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")) if ci is None else ci
    steps = ci["jobs"]["check"]["steps"]
    return any((s.get("with") or {}).get("fetch-depth") == 0 for s in steps)


# ── 注入の試験 ──

def test_注入_核の語を注記へ移すと赤_別の箇条へ移すと赤_言い回しの外を変えても緑():
    t = 核()
    assert 核の崩れ(t) == []
    assert 核の崩れ(t.replace("申告でなく記録", "<!-- 申告でなく記録 -->", 1))
    s4 = 番号の節(t, 4)
    moved = s4.replace("画面の問いは 1 文に", "", 1) + "\n- 画面の問いは 1 文に。\n"
    assert any("画面の問いは 1 文に" in p for p in 核の崩れ(t.replace(s4, moved, 1)))
    assert 核の崩れ(t.replace("返事・実況は日本語", "返事と実況は日本語", 1)) == []


def test_注入_核の根治の入口を後ろへ回すと赤():
    t = 核()
    first = 核の箇条(t, 3)[0].split("\n")[0]
    assert "根治の入口" in " ".join(核の崩れ(t.replace(first, "まず決まり。" + first, 1)))


def test_注入_細目の語を別の欄へ移すと赤_欄を囲いに入れると欄が無い_言い回しの外を変えても緑():
    s = 細目の全文()
    assert 細目の崩れ(s) == []
    body = 欄(番号の節(s, 7), "土台の直しの終わり")
    assert any("洗い出しだけで終わらせない" in p for p in 細目の崩れ(s.replace("洗い出しだけで終わらせない", "", 1) + "\n- **記録で確かめる** — 洗い出しだけで終わらせない\n", only=[7]))
    assert any("1 つでない" in p for p in 細目の崩れ(s.replace(body, "```\n" + body + "\n```", 1) if body else s, only=[7]))
    assert 細目の崩れ(s.replace("合流するまで「終わった」と言わない", "合流するまで「終わった」と言わない（言い換え）", 1), only=[7]) == []


def test_注入_振る舞いの語を別の欄へ移すと赤_注記にすると赤():
    f = 振る舞い()
    assert 振る舞いの崩れ(f) == []
    gone = f.replace("1 本の列にせず", "", 1).replace("**範囲** —", "**範囲** — 1 本の列にせず。", 1)
    assert any("1 本の列にせず" in p for p in 振る舞いの崩れ(gone))
    assert 振る舞いの崩れ(f.replace("2 回で打ち方を変えるか止める", "<!-- 2 回で打ち方を変えるか止める -->", 1))


def test_注入_赤を返す所の入口を注記へ移すと赤_赤の文から離すと赤():
    ok = "- 検査が赤なら細目 §3「まず構造を疑う」で原因を探す。\n"
    assert 入口が赤の隣に在る(ok)
    assert not 入口が赤の隣に在る("- 検査が赤なら直す。\n<!-- 細目 §3「まず構造を疑う」 -->\n")
    assert not 入口が赤の隣に在る("- 検査が赤なら直す。\n\n- 原因は細目 §3「まず構造を疑う」で探す。\n")
    assert 入口が赤の隣に在る('import sys\nMSG = "止めた: 細目 §3「まず構造を疑う」で探す"\n', "x.py")
    assert not 入口が赤の隣に在る('"""止めた: 細目 §3「まず構造を疑う」"""\nMSG = "止めた"\n', "x.py")


def test_注入_design_mode_の写しの残りの行を表の外へ出すと赤():
    dm = (ROOT / "plugins/dev-flow/skills/design-mode/SKILL.md").read_text(encoding="utf-8")
    assert len(写しの残りの行(dm)) == 1
    row = [l for l in dm.splitlines() if l.strip().startswith("| 写しの残り |")][0]
    assert 写しの残りの行(dm.replace(row, "<!--" + row + "-->", 1)) == []


def test_注入_理論モックの印の語を_4_の行から外すと赤():
    t = (ROOT / "plugins/docs-kit/skills/theory-mock/SKILL.md").read_text(encoding="utf-8")
    assert 理論モックの印の崩れ(t) == []
    assert 理論モックの印の崩れ(t.replace("推奨を付けずにチャットで聞く", "推奨を付けて聞く", 1))


def test_注入_増え方の入口は分かれ目と比べ_先端が_main_なら_1_つ前と比べ_main_が聞けなければ赤(tmp_path):
    rc, log = 増え方の入口を回す(tmp_path / "a", "a" * 40)
    assert rc == 0 and f"grow --base {'a' * 40}" in log and "--print-main" in log
    rc, log = 増え方の入口を回す(tmp_path / "b", "c" * 40)      # 分かれ目が先端そのもの
    assert rc == 0 and f"grow --base {'d' * 40}" in log
    rc, log = 増え方の入口を回す(tmp_path / "c", "c" * 40, has_parent=False)
    assert rc == 2 and "grow" not in log
    rc, log = 増え方の入口を回す(tmp_path / "d", "a" * 40, main_ok=False)
    assert rc == 2 and "grow" not in log


def test_注入_ci_の_check_が浅い_clone_なら赤():
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert ci_の_check_は全部の歴史を取る(ci)
    for s in ci["jobs"]["check"]["steps"]:
        if isinstance(s.get("with"), dict):
            s["with"].pop("fetch-depth", None)
    assert not ci_の_check_は全部の歴史を取る(ci)


@pytest.mark.parametrize("rel", ["plugins/guard/scripts/prior_ask.py", "plugins/guard/scripts/values_keys.py"])
def test_見張りは_guard_が足す文で入口を持つ(rel):
    assert 入口の崩れ(rel) == []
