"""値の表（各 repo の config/skill-values.json）に、土台の規律の写しを置く鍵が無いかを見る。

防ぐ故障: 土台に在る規律（核・細目・skill の本文）を、使う側の値の表の鍵（例 `common.rules.root_fix`・
`common.rules.no_confirm`）に「repo の正本」として写させると、土台の文が変わっても古い写しが勝ち、
誰も照らさない。値の表には本当に repo ごとに違う値（置き場・命令・会社の語・色など）だけを置く。

見る所:
- 各 SKILL.md の「repo ごとの値」の表の行が、既定に土台の正本（plugins/core の文書）の節を挙げる＝規律の写し → 赤。
- 使う所が「…の正本」で既定が本文の規律（無しでない）＝表の値が本文の規律に勝つ写しの入れ物 → 赤。
- 本文が正本（skill-values/schema.json）に無い common の鍵（畳んだ `common.rules`・知らない名の入れ物）を読ませる → 赤。
注入の試験: 畳んだ行・文を正本の写しに戻すと赤になるのを確かめる。
"""
import io
import json
import re
import sys
import tokenize
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill-values"))
import skill_values as SV  # noqa: E402  鍵の一覧と型の正本（schema.json）を読む 1 本の口

SKILL_FILES = sorted((ROOT / "plugins").glob("*/skills/*/SKILL.md"))
CORE = ROOT / "plugins" / "core"


def flat(text):
    """照らす前の寄せ: NFKC（全角→半角）と空白を詰める。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


# ── 土台の規律の正本を指すか: 字「核 §」を探さず、正本の文書（plugins/core/*.md）の名と、その文書の節（見出しの番号・名）を
#    正本から直に読んで照らす（「細目の §3」「核の 3 節」「細目の直すは根治」も同じ類）。──
def canon_sections():
    """{正本の文書の名: その節の番号と名の集合}。"""
    out = {}
    for p in sorted(CORE.glob("*.md")):
        marks = set()
        for m in re.finditer(r"^##\s*(\d+)\.\s*(.+)$", p.read_text(encoding="utf-8"), flags=re.M):
            marks.update({m.group(1), flat(m.group(2))})
        out[p.stem] = marks
    return out


def canon_ref(cell):
    """既定の欄が土台の正本の節を指すか（文書の名の後、句の切れ目の前に § か節か、その文書の節の番号・名が来る）。"""
    t = flat(cell)
    for name, marks in canon_sections().items():
        for m in re.finditer(re.escape(name), t):
            near = re.split(r"[。|]", t[m.end():m.end() + 12])[0]
            if "§" in near or "節" in near or any(k and k in near for k in marks):
                return True
    return False


# ── 会社の規律の写しの入れ物: 字 common.rules を探さず、common の欄の鍵を鍵の一覧の正本（schema.json）で照らす。
#    在る鍵（sections.common.keys）だけを通し、畳んだ鍵（retired）・知らない鍵（common.policy・common.kitei 等）は拒む。──
COMMON_REF = re.compile(r"(?<![A-Za-z0-9_.])common\.([A-Za-z_][A-Za-z0-9_]*)")


def bad_common(text):
    """本文の字が指す common の鍵のうち、正本に在る鍵でない物の並び。"""
    live = SV.keys_of("common") or {}
    retired = SV.schema().get("retired") or {}
    out = []
    # 寄せ: NFKC（全角の英字・点を半角へ）と、点の前後の空白を詰める（日本語の字は \w なので空白を全部詰めると境が消える）
    for m in COMMON_REF.finditer(re.sub(r"\s*\.\s*", ".", unicodedata.normalize("NFKC", text))):
        key = m.group(1)
        if key not in live or "common." + key in retired:
            out.append("common." + key)
    return out


def bad_common_table(data):
    """JSON の中の common の欄（{"common": {...}}）を値の表の照らしの口で読み、効かない鍵の並び。"""
    out = []
    if isinstance(data, dict):
        if isinstance(data.get("common"), dict):
            out += SV.check_section({"common": data["common"]}, "common")[0]
        for v in data.values():
            out += bad_common_table(v)
    elif isinstance(data, list):
        for v in data:
            out += bad_common_table(v)
    return out


def file_text(p):
    """照らす字: Python は字の値と注（tokenize）だけ（`common.rstrip` のような名の読みを鍵と取り違えない）。"""
    text = p.read_text(encoding="utf-8", errors="ignore")
    if p.suffix != ".py":
        return text
    toks = tokenize.generate_tokens(io.StringIO(text).readline)
    return "\n".join(tk.string for tk in toks if tk.type in (tokenize.STRING, tokenize.COMMENT))


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
        if canon_ref(default):
            out.append(f"表の鍵 {key} の既定が土台の正本（{default}）＝規律の写しを表に置かせている")
        elif use.endswith("正本") and not default.startswith("無し"):
            # 本文が既定の規律を持つのに、表の値を「正本」として本文に勝たせる＝写しの入れ物
            out.append(f"表の鍵 {key} が本文の規律（{default}）に勝つ正本を表に置かせている")
    for i, line in enumerate(text.splitlines(), 1):
        for key in bad_common(line):
            out.append(f"{i} 行目が正本に無い common の鍵 {key}（会社の規律の写しの入れ物）を読ませる: {line.strip()[:80]}")
    return out


def test_SKILL_の値の表に土台の規律の写しが無い():
    assert SKILL_FILES
    bad = {}
    for p in SKILL_FILES:
        found = problems(p.read_text(encoding="utf-8"))
        if found:
            bad[str(p.relative_to(ROOT))] = found
    assert not bad, f"値の表に土台の規律の写しを置かせている（土台の正本を直に読む形にする）: {bad}"


def test_雛形も正本に無い_common_の鍵を指さない():
    # 鍵の一覧（plugins/*/lib/schema.json＝skill-values/ の正本への symlink）は畳んだ鍵として名指しする所なので外す
    #（使う側の表に残れば「畳んだ鍵」と名指しされる＝tests/test_skill_values.py）。
    bad = {}
    for p in sorted((ROOT / "plugins").rglob("*")):
        if "lib" in p.relative_to(ROOT / "plugins").parts:
            continue
        if p.is_file() and p.suffix in (".md", ".py", ".mjs", ".json", ".html"):
            found = bad_common(file_text(p))
            if p.suffix == ".json":
                found += bad_common_table(json.loads(p.read_text(encoding="utf-8")))
            if found:
                bad[str(p.relative_to(ROOT))] = found
    assert not bad, f"正本（schema.json）に無い common の鍵を指す: {bad}"


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
