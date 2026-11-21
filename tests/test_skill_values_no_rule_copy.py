"""値の表（各 repo の config/skill-values.json）に、土台の規律の写しを置く鍵が無いかを見る。

防ぐ故障: 土台に在る規律（核・細目・skill の本文）を、使う側の値の表の鍵（例 `common.rules.root_fix`・
`common.rules.no_confirm`）に「repo の正本」として写させると、土台の文が変わっても古い写しが勝ち、
誰も照らさない。値の表には本当に repo ごとに違う値（置き場・命令・会社の語・色など）だけを置く。

見る所:
- 各 SKILL.md の「repo ごとの値」の表の行が、既定に核・細目を挙げる＝土台に正本が在る規律の写し → 赤。
- 使う所が「…の正本」で既定が本文の規律（無しでない）＝表の値が本文の規律に勝つ写しの入れ物 → 赤。
- 本文が `common.rules` を読ませる → 赤（会社の規律の写しの入れ物）。
注入の試験: 畳んだ行・文を正本の写しに戻すと赤になるのを確かめる。
"""
import re
from pathlib import Path
from uses import kaku

ROOT = Path(__file__).resolve().parent.parent
SKILL_FILES = sorted((ROOT / "plugins").glob("*/skills/*/SKILL.md"))
# 土台の規律の正本を指す字（既定の欄にこれが在れば、その鍵は土台の正本の写し）。
CANON_REF = re.compile(r"核(の細目)?\s*§|細目\s*§")
# 会社の規律の写しの入れ物。
RULE_BUCKET = re.compile(r"common\.rules\b")


def pointing(suffix, text):
    """file の中で指す形の所だけ: .py は注釈と docstring を除いたコード・.mjs は注釈を除いた字・.md と .html は注記
    <!-- --> を除いた字。.json は字のまま（値の表の鍵か値＝指す形）。注釈・注記の読み方の正本は kaku.code（写さない）。
    .md の `common.rules` は鍵の名を指す字なので、引用・囲みも外さない。禁じる・畳んだと説明する文かを語で分けない
    （語で分けると「写さない」を添えるだけで指しが通る）＝地の文で名を挙げれば赤。"""
    if suffix in (".md", ".html"):
        return kaku.note_code(text)
    return kaku.code("x" + suffix, text)


def value_rows(text):
    """「repo ごとの値」の節の表の行を (鍵の欄, 使う所, 既定) で返す。"""
    m = re.search(r"^## repo ごとの値[^\n]*\n(.*?)(?=^## )", text, flags=re.S | re.M)
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not line.lstrip().startswith("|"):
            continue
        if cells[0] in ("鍵",) or set(cells[0]) <= set("-: "):
            continue
        rows.append((cells[0], cells[1], cells[-1]))
    return rows


def problems(text):
    out = []
    for key, use, default in value_rows(text):
        if CANON_REF.search(default):
            out.append(f"表の鍵 {key} の既定が土台の正本（{default}）＝規律の写しを表に置かせている")
        elif use.endswith("正本") and not default.startswith("無し"):
            # 本文が既定の規律を持つのに、表の値を「正本」として本文に勝たせる＝写しの入れ物
            out.append(f"表の鍵 {key} が本文の規律（{default}）に勝つ正本を表に置かせている")
    for i, line in enumerate(text.splitlines(), 1):
        if RULE_BUCKET.search(line):
            out.append(f"{i} 行目が common.rules（会社の規律の写し）を読ませる: {line.strip()[:80]}")
    return out


def test_SKILL_の値の表に土台の規律の写しが無い():
    assert SKILL_FILES
    bad = {}
    for p in SKILL_FILES:
        found = problems(p.read_text(encoding="utf-8"))
        if found:
            bad[str(p.relative_to(ROOT))] = found
    assert not bad, f"値の表に土台の規律の写しを置かせている（土台の正本を直に読む形にする）: {bad}"


def test_雛形も_common_rules_を指さない():
    # 鍵の一覧（plugins/*/lib/schema.json＝skill-values/ の正本への symlink）は畳んだ鍵として名指しする所なので外す
    #（使う側の表に残れば「畳んだ鍵」と名指しされる＝tests/test_skill_values.py）。
    for p in sorted((ROOT / "plugins").rglob("*")):
        if "lib" in p.relative_to(ROOT / "plugins").parts:
            continue
        if p.is_file() and p.suffix in (".md", ".py", ".mjs", ".json", ".html"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert not RULE_BUCKET.search(pointing(p.suffix, text)), f"{p.relative_to(ROOT)} が common.rules を指す"


def test_値の表の節を読めている():
    # 照らす相手が空のまま緑にならないこと（節の見出しが変わったら赤）。
    n = sum(len(value_rows(p.read_text(encoding="utf-8"))) for p in SKILL_FILES)
    assert n >= 30, n


# ---- 注入の試験: 畳んだ写しを戻すと赤 ----

PREIMPL = ROOT / "plugins/dev-flow/skills/preimpl-cleanup/SKILL.md"
VERIFY = ROOT / "plugins/dev-flow/skills/verify/SKILL.md"
MINDMAP = ROOT / "plugins/docs-kit/skills/mindmap/SKILL.md"


def _insert_row(text, row):
    head = "|---|---|---|\n"
    i = text.index(head) + len(head)
    return text[:i] + row + "\n" + text[i:]


def test_注入_根治の定義の写しの鍵を戻すと赤():
    text = _insert_row(PREIMPL.read_text(encoding="utf-8"),
                       "| `common.rules.root_fix` | 根治の定義の repo の正本 | 核 §3・細目 §3 |")
    assert problems(text)


def test_注入_4_状態の定義の写しの鍵を戻すと赤():
    text = _insert_row(VERIFY.read_text(encoding="utf-8"),
                       "| `completion_states_doc` | 4 状態の定義表の正本 | 核の細目 §7 |")
    assert problems(text)


def test_注入_本文が会社の規律の写しを読ませると赤():
    text = MINDMAP.read_text(encoding="utf-8") + "\n会社の規律は表の `common.rules.no_confirm`。\n"
    assert problems(text)


def test_注入_本文の規律に勝つ正本の鍵を戻すと赤():
    text = _insert_row(VERIFY.read_text(encoding="utf-8"),
                       "| `code_done_rule` | コードの完了の決め方の正本 | PR の CI 緑＋別の窓のレビュー 1 回 |")
    assert problems(text)


def test_今の本文は緑():
    for p in (PREIMPL, VERIFY, MINDMAP):
        assert problems(p.read_text(encoding="utf-8")) == [], p
