"""残りの受け皿は原因の台帳 1 つ（細目 §3）を、「後へ回す」言葉の側から照らす。

古い受け皿の名を並べる照らしでは、新しい名の受け皿を足しても緑のままになる（PR #36 のレビュー）。
決まりの文書のどの行も、後へ回す言葉を使うなら決まった言い回しで原因の台帳を指す。指さない行は理由つきの外の表に在る物だけ。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# 残りの受け皿の名は古い言い回しを並べても尽きない（新しい名を足せばすり抜ける）。そこで「後へ回す」言葉の方で照らす:
# 決まりの文書のどの行も、後へ回す言葉を使うなら原因の台帳を指す。指さない行は下の表に理由つきで載せた物だけ（知らない行は赤）。
後へ回す言葉 = re.compile(r"後で|あとで|後ほど|のちほど|追って|後回し|後日|次回|今度|持ち越|保留|DEFER|TODO|[Ff]ollow-?up|backlog|後の便|次の便|別の PR で|宿題|箱へ|箱に")
# 台帳を「指す」形だけ通す（「原因の台帳とは別の置き場」のように字だけ在る行は通さない・PR #59 のレビュー）
# 台帳を指すのは決まった肯定の言い回しだけ（字が在るだけ・打ち消しの語を並べて外す形にしない＝決まった言い回しの外は赤）。
# 言い回しの直後に続ける字も決めておく（「…の行にする必要は無い」「…の行にするのは任意」「…の行にしません」は赤）。
# 次の句で打ち消す文（「…の行にして、載せなくてよい」）は字の形で見分けられない＝review-pr の点 12 が読む（残る穴）。
台帳を指す言い回し = re.compile(r"原因の台帳(の行(にする|にして|になる|に入れる|へ|を足す|として|（)|に行を入れ(る|て)|の 1 行| 1 つ)(?=[。、）・：:\s（＝*]|から|$)")


def 台帳を指す(ln):
    return bool(台帳を指す言い回し.search(ln))
後へ回す言葉の外 = {   # (path, その行を見分ける語): 理由 — 残りの受け皿ではない
    ("plugins/dev-flow/skills/public-repo/SKILL.md", "新しい repo へ持ち越さない"): "歴史を新しい repo へ写さない話（仕事の残りではない）",
    ("plugins/dev-flow/skills/public-repo/SKILL.md", "歴史ごと公開してよいか"): "同上",
    ("plugins/dev-flow/skills/codex/SKILL.md", "ACCEPT/MODIFY/REJECT/DEFER"): "Codex 側の報告の札の名（行き先は同じ skill の §戻り が台帳と書く）",
    ("plugins/core/細目/05-返事の形.md", "AI がこの後やること＝"): "後で起こす手の名",
    ("plugins/core/振る舞い.md", "**計画に逃げ場を書かない**"): "「後で」の逃げ場を書かない決まりそのもの",
}


def _後へ回す行(root):
    """原因の台帳を指さず、外の表にも無い「後へ回す」行の並び。
    used_texts を通さない: 注入の試験が作り物の root を渡し、引用・囲みの中の「後で」も決まりとして読むため字のまま見る。"""
    out = []
    files = [*root.glob("plugins/**/*.md"), *root.glob("docs/**/*.md"), *root.glob(".github/**/*.md"),
             *(root / n for n in ("CONTRIBUTING.md", "README.md", "CLAUDE.md"))]
    for p in sorted(f for f in files if f.is_file()):
        rel = p.relative_to(root).as_posix()
        for ln in p.read_text(encoding="utf-8").splitlines():
            if 後へ回す言葉.search(ln) and not 台帳を指す(ln) \
                    and not any(r == rel and key in ln for r, key in 後へ回す言葉の外):
                out.append(f"{rel}: {ln[:80]}")
    return out


def test_後へ回す言葉を使う決まりは全部原因の台帳を指す():
    """新しい名の受け皿（「後で 🍀箱へ」など）を足すと、古い言い回しの一覧に無くても赤。"""
    assert _後へ回す行(ROOT) == []
    for r, key in 後へ回す言葉の外:           # 外の表の行が消えたら表からも消す（古い外を残さない）
        assert any(key in ln for ln in (ROOT / r).read_text(encoding="utf-8").splitlines()), f"外の表の行が無い: {r}: {key}"


@pytest.mark.parametrize("line", [
    "- 片付かなかった物は後で 🍀箱 に置く。",
    "- DEFER の物は返しの欄に残す。",
    "- 今回入らなかった物は別の PR で拾う。",
    "- 気づきは follow-up の札で次の窓へ。",
    "- 片付かない物は後ほど拾う。",
    "- 残りは後で 🌱棚 に置く（原因の台帳とは別の置き場）。",
    "- 気づきは後で拾い、原因の台帳に載せない。",
    "- DEFER の物は原因の台帳へは書かない。",
    "- 保留の物は原因の台帳で管理しない。",
    "- 後で拾う物は原因の台帳の行にしません。",
    "- 保留は原因の台帳の行にする必要は無い。",
    "- 後で拾う物は原因の台帳の行にするのは任意。",
    "- 持ち越す物を原因の台帳の行にするのは禁止。",
    "- 後で直す物は原因の台帳に書く。",
])
def test_新しい名の受け皿を足すと赤(tmp_path, line):
    for rel in ["plugins/x/skills/y/SKILL.md"]:
        (tmp_path / rel).parent.mkdir(parents=True)
        (tmp_path / rel).write_text("# 作り物\n" + line + "\n", encoding="utf-8")
    assert _後へ回す行(tmp_path) == [f"plugins/x/skills/y/SKILL.md: {line}"]
    (tmp_path / "plugins/x/skills/y/SKILL.md").write_text(line.replace("。", "（原因の台帳の行にする）。"), encoding="utf-8")
    assert _後へ回す行(tmp_path) == []

