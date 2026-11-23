"""窓の題・手の窓・値の表の鍵・qa-html の在り処の照らしを、字の有無でなく置き場（節・欄・節の箇条）で照らす。

意図: 窓の種類の決め方・窓の題の種類と正本の指し・手の窓の題・repo の名に当てる鍵の説明・qa-html の dir の見つけ方が、
  決まった節・欄に在る事を守り、言い回しは縛らない。
課題: 試験が決まりの文を SKILL・細目の全体から `in` で探し、行の頭を写して `startswith` で拾っていたので、別の節・
  注記・囲いへ移しても緑、細目の文を少し直すと赤だった。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、名（種類の印・手の窓の印）も動く物（見張りの正本）から読まずに写していた。
"""
from md_yomi import 地の行, 欄, 節

種類の節 = "種類（1 文字目）"
値の表の節 = "値の表"
配り方の節 = "配り方（単一ソース）"
窓の中 = "- 窓の中:"


def 種類の決め方の外れ(skill: str, rule: str) -> list[str]:
    """title-mark の「種類」の節の地の行に、見張りの正本の決まりの文で始まる箇条が在るか。"""
    body = 節(skill, 種類の節)
    if body is None:
        return [f"title-mark に「{種類の節}」の節が 1 つでない"]
    return [] if any(l.startswith("- " + rule) for l in 地の行(body)) else ["種類の節に見張りの正本と同じ決め方の文が無い"]


def 窓の題の外れ(detail: str, table) -> list[str]:
    """細目の「窓の題」の欄が、見張りの表の種類を全部挙げ、正本の skill を指すか。"""
    f = 欄(detail, "窓の題")
    if f is None:
        return ["細目に「窓の題」の欄が 1 つでない"]
    bad = [f"窓の題の欄に種類 {k} が無い" for k in table if f"`{k}`" not in f]
    return bad + ([] if "session-watch:title-mark" in f else ["窓の題の欄が正本の skill を指さない"])


def 手の窓の外れ(detail: str, hand: str) -> list[str]:
    """細目の「手の窓」の欄が、題を種類（見張りの印）で書き、済んだ形も書き、古い作業名の印（手:）を持たないか。"""
    f = 欄(detail, "手の窓")
    if f is None:
        return ["細目に「手の窓」の欄が 1 つでない"]
    bad = [f"手の窓の欄に {x} が無い" for x in (f"`{hand} <何を>`", f"`{hand}✅`") if x not in f]
    return bad + (["手の窓の欄が古い作業名の印（手:）を持つ"] if "手: <何を>" in f else [])


def 値の表の行の外れ(md: str, keys) -> list[str]:
    """guard-rules の「値の表」の節の地の行の箇条に、鍵ごとに名の全体に当てる正規表現と書く行が在るか。"""
    body = 節(md, 値の表の節)
    if body is None:
        return [f"guard-rules に「{値の表の節}」の節が 1 つでない"]
    lines = [l for l in 地の行(body) if l.startswith("- `")]
    return [f"値の表の箇条に {k} を名の全体に当てると書く行が無い" for k in keys
            if not any(k in l and "名の全体に当てる正規表現" in l for l in lines)]


def 窓の中の行の外れ(skill: str) -> list[str]:
    """qa-html の「配り方」の節の地の行に「窓の中」の行が 1 つだけ在り、今読む 1 つ（installPath）を書くか。"""
    body = 節(skill, 配り方の節)
    if body is None:
        return [f"qa-html に「{配り方の節}」の節が 1 つでない"]
    lines = [l for l in 地の行(body) if l.strip().startswith(窓の中)]
    if len(lines) != 1:
        return [f"配り方の節に「窓の中」の行が 1 つでない（{len(lines)} 行）"]
    line = lines[0]
    bad = [] if "claude plugin list --json" in line and "installPath" in line else ["窓の中の行が今読む 1 つを書かない"]
    return bad + (["窓の中の行が台帳の最初の行を読む"] if "の `docs-kit@<市場>` の `installPath`（今入っている 1 つ）" in line else [])


# 注入の試験: 置き場から外す・注記へ隠す・古い形へ戻すと赤、言い回しを変えるだけなら緑。

def _hk():
    from test_hand_window_kind import DETAIL, SKILL, sw
    return SKILL.read_text(encoding="utf-8"), DETAIL.read_text(encoding="utf-8"), sw


def test_注入_種類の決め方を別の節_注記へ移すと赤_言い回しは緑():
    s, _, sw = _hk()
    assert 種類の決め方の外れ(s, sw.KIND_RULE) == []
    line = next(l for l in 節(s, 種類の節).splitlines() if l.startswith("- " + sw.KIND_RULE))
    # 種類の節から状態の節へ移す（全体には字が残る）
    moved = s.replace(line + "\n", "", 1).replace("| 状態 | 意味 |", line + "\n\n| 状態 | 意味 |", 1)
    assert sw.KIND_RULE in moved and 種類の決め方の外れ(moved, sw.KIND_RULE)
    # 注記の中へ
    assert 種類の決め方の外れ(s.replace(line, f"<!-- {line} -->", 1), sw.KIND_RULE)
    # 見張りの正本と文が違えば赤
    assert 種類の決め方の外れ(s, sw.KIND_RULE.replace("2 段", "二段"))
    # 決まりの文の後ろの言い回しを変えても緑
    assert 種類の決め方の外れ(s.replace("試験が一致を照らす", "試験が一致を確かめる", 1), sw.KIND_RULE) == []


def test_注入_窓の題の種類を別の欄_注記へ移すと赤_言い回しは緑():
    _, d, sw = _hk()
    assert 窓の題の外れ(d, sw.TITLE_TABLE) == []
    f = 欄(d, "窓の題")
    # 種類 ✋ を窓の題の欄から消し、手の窓の欄と注記に残す（全体には字が残る）
    gone = d.replace(f, f.replace(f"`{sw.HAND}`・", ""), 1) + f"\n<!-- `{sw.HAND}` -->\n"
    assert f"`{sw.HAND}`" in gone and any(sw.HAND in x for x in 窓の題の外れ(gone, sw.TITLE_TABLE))
    # 正本の skill を指さない
    assert any("正本" in x for x in 窓の題の外れ(d.replace(f, f.replace("session-watch:title-mark", "title-mark"), 1), sw.TITLE_TABLE))
    # 見張りの表に種類が増えれば細目が古いので赤
    assert 窓の題の外れ(d, {**sw.TITLE_TABLE, "🧪": ()})
    # 言い回しを変えても緑
    assert 窓の題の外れ(d.replace(f, f.replace("役は作業名に書く", "役は作業名へ書く"), 1), sw.TITLE_TABLE) == []


def test_注入_手の窓の題を別の欄へ移す_古い印へ戻すと赤_言い回しは緑():
    _, d, sw = _hk()
    assert 手の窓の外れ(d, sw.HAND) == []
    f = 欄(d, "手の窓")
    title = f"題 `{sw.HAND} <何を>` の窓を立てて頼む（済んだら `{sw.HAND}✅`）。"
    assert title in f
    # 手の窓の欄から消し、別の欄へ移す（全体には字が残る。移す先は作り物の欄＝細目の他の文に頼らない）
    moved = d.replace(title, "窓を立てて頼む。", 1) + f"\n- **作り物** — {title}\n"
    assert title in moved and 手の窓の外れ(moved, sw.HAND)
    # 古い作業名の印へ戻す
    assert any("手:" in x for x in 手の窓の外れ(d.replace(title, title + "題は `🙋⏳ 手: <何を>`。", 1), sw.HAND))
    # 言い回しを変えても印が在れば緑
    assert 手の窓の外れ(d.replace(title, f"題 `{sw.HAND} <何を>` の窓で頼む（済めば `{sw.HAND}✅`）。", 1), sw.HAND) == []


def _gr():
    from test_pr_text_exact_reads import REPO_KEYS, ROOT
    return (ROOT / "plugins" / "guard" / "skills" / "guard-rules" / "SKILL.md").read_text(encoding="utf-8"), REPO_KEYS


def test_注入_鍵の説明を射程の外_囲いへ移すと赤_言い回しは緑():
    md, keys = _gr()
    assert 値の表の行の外れ(md, keys) == []
    line = next(l for l in 節(md, 値の表の節).splitlines() if keys[0] in l and "名の全体に当てる正規表現" in l)
    # 値の表の節から射程の外の節へ移す（全体には字が残る）
    moved = md.replace(line + "\n", "", 1).replace("## 射程の外\n", "## 射程の外\n\n" + line + "\n", 1)
    assert line in moved and len(値の表の行の外れ(moved, keys)) == len(keys)
    # 値の表の節の中のコードの囲いへ
    fenced = md.replace(line, "```\n" + line + "\n```", 1)
    assert line in fenced and len(値の表の行の外れ(fenced, keys)) == len(keys)
    # 言い回しを変えても緑
    assert 値の表の行の外れ(md.replace(line, line.replace("の並び", "の列"), 1), keys) == []


def _qa():
    from test_stale_compare_f2 import ROOT
    return (ROOT / "plugins" / "docs-kit" / "skills" / "qa-html" / "SKILL.md").read_text(encoding="utf-8")


def test_注入_窓の中の行を別の節へ移す_古い形へ戻すと赤_注記は数えず_言い回しは緑():
    s = _qa()
    assert 窓の中の行の外れ(s) == []
    line = next(l for l in 節(s, 配り方の節).splitlines() if l.strip().startswith(窓の中))
    # 配り方の節から関連の節へ移す（全体には字が残る）
    moved = s.replace(line + "\n", "", 1).replace("## 関連\n", "## 関連\n\n" + line.strip() + "\n", 1)
    assert "claude plugin list --json" in moved and 窓の中の行の外れ(moved)
    # 台帳の最初の行を読む古い形の行を足す（2 行になる）・古い形に替える
    old = "  - 窓の中: `installed_plugins.json` の `docs-kit@<市場>` の `installPath`（今入っている 1 つ）"
    assert 窓の中の行の外れ(s.replace(line, line + "\n" + old, 1))
    assert any("台帳" in x for x in 窓の中の行の外れ(s.replace(line, line + " 前は" + old.strip()[len(窓の中):], 1)))
    # 古い形を注記に残すだけなら数えない
    assert 窓の中の行の外れ(s.replace(line, line + "\n<!--\n" + old + "\n-->", 1)) == []
    # 言い回しを変えても緑
    assert 窓の中の行の外れ(s.replace(line, line.replace("直に読まない", "そのまま読まない"), 1)) == []
