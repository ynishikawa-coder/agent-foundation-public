"""根治は意図→課題→原因→解決→未来の 5 段（呼び名 MGK）。

なぜ在るか: 4 段（問題→原因→解決→未来）では、本来の意図が「問題」の付け足しに埋もれて意図そのものを疑う段が無く、
「問題」の語が評価を含むので原因が問題の段に紛れ込んだ（オーナー決定 2026-11-22）。意図を独り立ちさせ、
課題は意図とのずれだけを書いて「なぜ」を原因へ送る。決まりの文はそのまま照らす（消すと赤）。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core"


def _節(text, n):
    a = text.index(f"## {n}. ")
    b = text.find("\n## ", a + 1)
    return text[a:] if b < 0 else text[a:b]


SAIMOKU_3 = [
    "- **根治の 5 段（意図→課題→原因→解決→未来）**",
    "  - **呼び名 MGK** — 根治の 5 段をまとめた呼び名（大文字・小文字は問わない）。",
    "言われた時の答え方は振る舞いの既定。",
    "  - **意図** — その仕組み・作業が本来何のために在るか（誰の・何を・どうしたいか）。",
    "事象より先に書き、意図そのものが誤っていないかもここで疑う。",
    "  - **課題** — 意図と起きた事象のずれ。",
    "起きた事実（何が・どこで・誰が何に困ったか）と、意図に照らして何がどれだけずれたかを書き、「なぜ」は書かない（原因の段へ送る）。",
    "渡された 1 件の症状を課題の幅にしない。",
    "  - **未来** — 直した後の姿。",
    "意図が果たされ、同じ課題と同じ原因の他の問題が起きない状態で、何が無くなり何が変わるか（作業する者の手順・オーナーの手・決まりの量）を書く。",
    "試験を足す段ではない。",
    "言えない時は解決がまだ足りていない。",
]


def test_細目の根治の段は意図と課題を持ち_課題はなぜを原因へ送る():
    s3 = _節((CORE / "細目.md").read_text(encoding="utf-8"), 3)
    missing = [s for s in SAIMOKU_3 if s not in s3]
    assert not missing, f"細目 §3 の根治の 5 段に無い文: {missing}"


def test_核の根治は_5_段で呼び名は_MGK():
    s3 = _節((CORE / "核.md").read_text(encoding="utf-8"), 3)
    assert "の既定は根治＝意図→課題→原因→解決→未来（MGK）。" in s3


def test_MGK_して_と言われたら_5_段の見出しで答える():
    furumai = (CORE / "振る舞い.md").read_text(encoding="utf-8")
    line = ("- **MGK** — オーナーが「MGK して」と言ったら、直す時に限らず説明・振り返りでも、"
            "意図・課題・原因・解決・未来の 5 段の見出しで答える（別の形に置き換えない）。")
    assert line in furumai.splitlines()


def test_古い_4_段と呼び名_MGkm_が決まりと道具に残らない():
    olds = ["問題→原因→解決→未来", "MGkm", "根治の 4 段", "## 1. 問題"]
    hits = []
    for p in list((ROOT / "plugins").rglob("*")) + [ROOT / ".github" / "pull_request_template.md"]:
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".sh"}:
            text = p.read_text(encoding="utf-8", errors="ignore")
            hits += [f"{p.relative_to(ROOT)}: {o}" for o in olds if o in text]
    assert not hits, hits
