"""レビューの関所・先端に判定 1 つ・別の PR へ・並走の宣言の決まりを、字の有無でなく置き場（CONTRIBUTING の「2. レビュー」の節・
review-pr の太字の欄・振る舞いの既定の「並走」の欄）と、道具（review_gate.py・pr_overlap.py）の在る所・動きで照らす。

意図: 決まりが決めた節・欄に在り、名指す道具が在って動く事を守り、言い回しは縛らない。
課題: 試験が文を丸ごと file の全体から `in` で探していたので、別の節や注記・コードの囲いへ移しても緑、言い回しを直すと赤だった。
  pr_overlap.py は道具の中の文字（help の文）を照らし、`--files` を受けるかを見ていなかった。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、道具の動きでなく字を写していた。
"""
import re
import subprocess
import sys
from pathlib import Path

from md_yomi import 地の行, 欄, 節

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "plugins" / "checker" / "scripts" / "review_gate.py"
GATE_REL = GATE.relative_to(ROOT).as_posix()                       # CONTRIBUTING から呼ぶ形
GATE_PLUGIN = "${CLAUDE_PLUGIN_ROOT}/" + GATE.relative_to(ROOT / "plugins" / "checker").as_posix()  # skill から呼ぶ形
OVERLAP = ROOT / "scripts" / "pr_overlap.py"
SEC = "2. レビュー"


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def 並走の外れ(furumai: str) -> list[str]:
    body = 欄(furumai, "並走")
    if body is None:
        return ["振る舞いの既定に「並走」の欄が 1 つでない"]
    return [f"「並走」の欄に無い: {w}" for w in ("触る file", "宣言", "列に") if w not in body]


def レビューの節の外れ(contributing: str) -> list[str]:
    s = 節(contributing, SEC)
    if s is None:
        return [f"CONTRIBUTING に「{SEC}」の節が 1 つでない"]
    out = []
    gate = 欄(s, "レビューを頼むのは関所を通ってから。")
    if gate is None:
        out.append("「2. レビュー」に関所の欄が 1 つでない")
    else:
        out += [f"関所の欄に無い: {w}" for w in (f"`python3 {GATE_REL} --repo <owner/name> --pr <番号>`", "「まだ」") if w not in gate]
    add = 欄(s, "レビューが始まった後に、依頼に無い話を同じ PR へ足さない。")
    if add is None:
        out.append("「2. レビュー」に足さない話の欄が 1 つでない")
    elif "「別の PR へ」" not in add or "原因の台帳" not in add:
        out.append("足さない話の欄に「別の PR へ」・原因の台帳が無い")
    if "1 つの先端に判定は 1 つ" not in "\n".join(地の行(s)):
        out.append("「2. レビュー」に「1 つの先端に判定は 1 つ」が無い")
    return out


def review_pr_の外れ(skill: str) -> list[str]:
    out = []
    gate = 欄(skill, "関所を通ってから見る")
    if gate is None:
        out.append("review-pr に「関所を通ってから見る」の欄が 1 つでない")
    else:
        need = [f'"{GATE_PLUGIN}" --repo <owner/name> --pr <番号>', "exit 0 の時だけ見る", "exit 1・2", "コメントを残さず", "`まだ <PR>"]
        out += [f"関所の欄に無い: {w}" for w in need if w not in gate]
    if 欄(skill, "1 つの先端に判定は 1 つ") is None:
        out.append("review-pr に「1 つの先端に判定は 1 つ」の欄が 1 つでない")
    late = 欄(skill, "前回から足された話は見ない")
    if late is None:
        out.append("review-pr に「前回から足された話は見ない」の欄が 1 つでない")
    elif "`別の PR へ <PR> <枝>@<SHA12> 話=" not in late:
        out.append("足された話の欄に返す 1 行の形が無い")
    return out


def test_道具が在り_overlap_は_files_を受けて並走の欄を名指す():
    assert GATE.is_file()
    res = subprocess.run([sys.executable, "-B", str(OVERLAP), "--help"], capture_output=True, text=True)
    assert res.returncode == 0 and "--files" in res.stdout
    names = re.findall(r"振る舞いの既定「([^」]+)」", _read("scripts/pr_overlap.py"))
    assert names and all(欄(_read("plugins/core/振る舞い.md"), n) is not None for n in names), names


def test_注入_並走の宣言を注記や別の欄へ移すと赤_言い回しを変えても緑():
    t = _read("plugins/core/振る舞い.md")
    assert 並走の外れ(t) == []
    s = "触る file を先に宣言し、同じ file を取る窓は列に。"
    assert any("触る file" in x for x in 並走の外れ(t.replace(s, "", 1) + f"\n<!-- {s} -->\n"))
    assert any("列に" in x for x in 並走の外れ(t.replace(s, "", 1).replace("- **範囲** —", f"- **範囲** — {s}", 1)))
    assert 並走の外れ(t.replace(s, "同じ file を取る窓は列にし、触る file は先に宣言する。", 1)) == []


def test_注入_レビューの節の文を別の節_注記へ移すと赤_道具の名が変わると赤():
    c = _read("CONTRIBUTING.md")
    assert レビューの節の外れ(c) == []
    line = next(l for l in c.splitlines() if l.startswith("- **レビューが始まった後に"))
    moved = c.replace(line + "\n", "", 1).replace("## 4. 置かない物\n", "## 4. 置かない物\n\n" + line + "\n", 1)
    assert "別の PR へ" in moved and レビューの節の外れ(moved)
    assert レビューの節の外れ(c.replace(line, f"<!-- {line} -->", 1))
    assert レビューの節の外れ(c.replace("1 つの先端に判定は 1 つ", "<!-- 1 つの先端に判定は 1 つ -->", 1))
    assert レビューの節の外れ(c.replace(GATE_REL, "scripts/review_gate.py", 1))   # 道具の置き場とずれた文書
    assert レビューの節の外れ(c.replace("判定に入らず「まだ」とだけ返す", "判定に入らず「まだ」と返すだけにする", 1)) == []


def test_注入_review_pr_の欄を注記や囲いへ移すと赤():
    k = _read("plugins/checker/skills/review-pr/SKILL.md")
    assert review_pr_の外れ(k) == []
    for head in ("- **1 つの先端に判定は 1 つ**", "- **前回から足された話は見ない**", "- **関所を通ってから見る**"):
        line = next(l for l in k.splitlines() if l.startswith(head))
        assert review_pr_の外れ(k.replace(line, f"<!-- {line} -->", 1)), head
        assert review_pr_の外れ(k.replace(line, f"```\n{line}\n```", 1)), head
    assert review_pr_の外れ(k.replace("コメントを残さず", "コメントは残して", 1))
