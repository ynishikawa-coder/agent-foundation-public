"""オーナーに聞くのは合意した線（細目 §4 の 1 文が正本・§3 と §5 は写さず指す）の時だけで、AI が既定で進められる所の決まりが「オーナーに聞く」「人に聞く」に戻っていないか（注入の試験）。

意図: オーナーに届く問いは、オーナーにしか決められない事だけにし、AI は任された範囲を止まらずにやり切る。
課題: 守りや決まりが止めた所・既定の無い所が、AI が進められるのにオーナーへの問いになっていた（設計書の残す先・engine の置き場・
決定の記録の口・「直さない」の行ごとの問い・窓の分け方・AI が外せる止めの 🛑）。"""
import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAIMOKU = ROOT / "plugins" / "core" / "細目"

# 2026-11-22 にオーナーと合意した聞く線の項目。字の正本は細目 §4 の 1 文だけで、ここは項目が欠けていないかだけを照らす
AGREED = ("仕上がり", "要件", "顧客側", "計算の結果", "顧客に見える変更は出す前に確かめる", "AI が本当に迷う",
          "消すと出来る事が減る", "戻せない", "お金", "社外", "中の形を決めるのは聞かない")
_LINE = re.compile(r"オーナーに聞くのは、[^\n]*?聞かない。")
_COPY = re.compile(r"聞くのは[^。\n]*だけ")
_ASKW = re.compile(r"聞|問")


def copies(text):
    """§3・§5 に置かれた聞く線の写し（字の形でなく中身で拾う）: 問う・聞く文が合意の項目を 1 つでも持つか、「聞くのは…だけ」の形。"""
    return [s for s in re.split(r"[。\n]", text)
            if _COPY.search(s) or (_ASKW.search(s) and any(a in s for a in AGREED))]


# AI が既定で進める所＝既定の欄・既定の手順に「聞く」を戻さない（file → 照らす行の印）
DEFAULTS = {
    "plugins/dev-flow/skills/spec-doc/SKILL.md": ["| `save_place` |", "1. 配置先を決める", "型を正当に編集した後", "部分にする正当な理由"],
    "plugins/docs-kit/skills/pdf-read/SKILL.md": ["engine 置き場:", "| `engine_source` |", "| `engine_module` |"],
    "plugins/dev-flow/skills/register-rule/SKILL.md": ["| `decision_record` |"],
    "plugins/dev-flow/skills/codex/SKILL.md": ["§往き の**対称**"],
}
_ASK = re.compile(r"聞く|承認|コピーして貼る")


def _text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def asks_in_defaults(texts):
    """既定の行に戻った「聞く」を (file, 行の頭) で返す。"""
    hit = []
    for rel, marks in DEFAULTS.items():
        for line in texts[rel].splitlines():
            if any(m in line for m in marks) and _ASK.search(line):
                hit.append((rel, line[:40]))
    return hit


def ask_line(s04):
    """細目 §4 の聞く線の 1 文（無ければ空）。"""
    m = _LINE.search(s04)
    return m.group(0) if m else ""


def saimoku_ok(s03, s04, s05):
    """聞く線の正本が細目 §4 の 1 文だけで合意の項目を全部持ち、§3・§5 は写さず §4 を指すか。"""
    line = ask_line(s04)
    return (bool(line) and all(t in line for t in AGREED)
            and "（中の形だけの前提は AI が決める" in s04 and "1 つずつの物について「直さない」か" not in s04
            and "§4 の聞く線で決める" in s03 and not copies(s03) and not copies(s05)
            and "1 行ずつオーナーに聞く" not in s03
            and "AI が外せる止めは直して続ける（🛑 にしない）" in s05)


def _saimoku():
    return [Path(glob.glob(str(SAIMOKU / f"{n}-*.md"))[0]).read_text(encoding="utf-8") for n in ("03", "04", "05")]


def test_細目に聞く線が在る():
    assert saimoku_ok(*_saimoku())


def test_注入_線を戻すと赤():
    s03, s04, s05 = _saimoku()
    line = ask_line(s04)
    # §4 の線を古い狭い線に戻す・合意の項目を 1 つ落とす
    assert not saimoku_ok(s03, s04.replace(line, "オーナーに聞くのは、1 つずつの物について「直さない」か、だけ。出来る事を足す・中の形を決めるのは聞かない。"), s05)
    for t in AGREED:
        assert not saimoku_ok(s03, s04.replace(line, line.replace(t, "")), s05), t
    # §3・§5 に聞く線の短い写しを置く（正本が 2 つになる）
    copy = "「直さない」をオーナーに聞くのは仕上がり・顧客側に効く行だけ（AI の中の形・道具の行は直す）。"
    assert not saimoku_ok(s03.replace("「直さない」をオーナーに聞くかは §4 の聞く線で決める。", copy), s04, s05)
    assert not saimoku_ok(s03, s04, s05 + "\n- オーナーに聞くのは顧客側の時だけ。")
    assert not saimoku_ok(s03, s04.replace("（中の形だけの前提は AI が決める・", "（"), s05)
    assert not saimoku_ok(s03, s04, s05.replace("AI が外せる止めは直して続ける（🛑 にしない）。", ""))


def test_既定の行に聞くが無い():
    texts = {rel: _text(rel) for rel in DEFAULTS}
    assert not asks_in_defaults(texts), asks_in_defaults(texts)


def test_注入_既定の行に聞くを戻すと拾う():
    base = {rel: _text(rel) for rel in DEFAULTS}
    for rel, line, ins in [
        ("plugins/dev-flow/skills/spec-doc/SKILL.md", "| `save_place` |", "残す先はオーナーに聞く"),
        ("plugins/docs-kit/skills/pdf-read/SKILL.md", "| `engine_source` |", "無し＝人に聞く"),
        ("plugins/dev-flow/skills/register-rule/SKILL.md", "| `decision_record` |", "名指しが無ければ聞く"),
        ("plugins/dev-flow/skills/spec-doc/SKILL.md", "部分にする正当な理由", "理由＋owner 承認"),
        ("plugins/dev-flow/skills/codex/SKILL.md", "§往き の**対称**", "オーナーがコピーして貼る"),
    ]:
        texts = dict(base)
        texts[rel] = texts[rel].replace(line, line + ins, 1)
        assert asks_in_defaults(texts), (rel, ins)


def test_窓の分け方を問わせない():
    how = _text("plugins/guard/scripts/pick_one.py")
    assert "順と窓の分け方は AI が決めて進め、問わない" in how and "聞くならやり方を問う" not in how
    rules = _text("plugins/guard/skills/guard-rules/SKILL.md")
    assert "①順と窓の分け方は AI が決めて進める（問わない）" in rules and "聞くならやり方を問う" not in rules
