#!/usr/bin/env python3
"""seal: 設計書の封（/spec-doc Step3）の入口。15 §6 の決定照合が済んでいなければ、gate を呼ばずに止める。

なぜ在るか: 決定照合（15 §6・型の外のオーナーの決定との照らし）は「結果で seal を止めない・§6 が空なら警告だけ」で、
AI が照合を飛ばしても、決定の記録と食い違う設計書が LOCK されて渡っていた（オーナー同意 2026-11-19: 文で知らせるだけの
決まりは AI だけ止めて書き直させてよい）。止まるのは封をしようとする AI だけ。人の操作は何も止めない。

見る物（15_*.md の §6 の節＝見出しに「§6」「6.」か「決定照合」を持つ節。次の同じか上の段の見出しまで）:
  - 節の行（表の行〔見出しの行と区切りを除く〕か、箇条の行）を 1 行ずつ見る。
  - 扱いは閉じた形だけを読む（推し量らない）: 欄（表は「扱い」の列・箇条は括弧の外の最後の区切り → ： の後）が
    `直した`／`覆す`／`覆す＝墓標へ`／`関係なし` のどれかちょうどで、後ろに置けるのは `（理由: …）` か `（根拠: …）` の
    1 つだけ。それ以外の字が付く（「直した（まだ未定）」「直したいが未定」）・理由の中に未定の語（未定・未照合・まだ・
    聞く・保留・TBD）が在る行は済みでない。表に「扱い」の列が無い表の行も済みでない。
  - 節の中の地の文（表・箇条・見出し・空行・<!-- --> の注・> の注のどれでもない行）は形の決まらない行として止める
    （照合の結果を地の文で書くと読めない＝黙って飛ばさない）。
  - 「未照合」の行: 値の表に照合の口（decision_match）が在る repo では止める（口があるのに照らしていない）。
    口が無い repo では通して知らせるだけ（照らしようが無い）。
  - 扱いの無い行（「ぶつかる」のまま・未定・空）は止める。15 が無い・§6 が無い・§6 に行が 1 つも無い時も止める。
止まらなければ、型の gate（<型>/check_spec_doc.py <設計書dir> --lock）を直に呼んで、その終わりの値をそのまま返す
（gate の中身は写さない）。型が無い repo では gate を呼べない＝LOCK しない（exit 3）。

値の表: config/skill-values.json の `dev-flow.spec-doc`（在る時だけ。探し方と鍵の一覧は plugin の lib/skill_values.py
  ＝土台の skill-values/ の正本。知らない鍵・畳んだ鍵・型の違う値は名指しして止める＝黙って既定で動かない）。
  template_dir（型の置き場）・decision_match（照合の口の行の並び。在れば「未照合」で止める）・
  decision_match_allow（誤って止まる行に当てる正規表現の並び。当たる行は済みとみなす。PR とレビューを通る）

exit: 0=照合が済み gate も緑／1=照合で止めた（gate を呼んでいない）か入力の不正／3=照合は済んだが型が無く LOCK しない／
      それ以外=gate の終わりの値。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
import skill_values  # noqa: E402  値の表の 1 本の口（plugin の lib/＝土台の skill-values/ への symlink）

UNMATCHED = "未照合"
_HEAD = re.compile(r"^(#{1,6})\s*(.*?)\s*#*\s*$")
_SEC6 = re.compile(r"(?:§\s*6(?!\d)|^6[.．](?!\d)|決定照合)")
_TABLE = re.compile(r"^\s*\|")
_TABLE_SEP = re.compile(r"^\s*\|[\s:\-|]+\|?\s*$")
# 扱いの閉じた形: 語ちょうど（覆すだけ ＝墓標へ を付けてよい）＋ 理由か根拠の括弧 1 つまで。ほかの字が付けば済みでない。
_DONE = re.compile(r"^(?:直した|覆す(?:＝墓標へ)?|関係なし)(?:[（(](?:理由|根拠)\s*[:：]\s*([^（）()]+)[）)])?$")
# 理由の中にこれが在れば、照合の中身が済んでいない印（「直した（理由: まだ未定）」）。
_PENDING = re.compile(r"未定|未照合|まだ|聞く|保留|TBD|TODO", re.I)
_SEP = re.compile(r"→|->|:|：")
_PAREN = re.compile(r"（[^（）]*）|\([^()]*\)")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
# 節の中で照合の行として読まない行（空行・見出し・注）。これ以外の地の文は形の決まらない行。
_NOTE = re.compile(r"^\s*(?:$|#|>|<!--.*-->\s*$)")


class Abort(Exception):
    pass


def repo_root(start: Path) -> Path | None:
    res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                         capture_output=True, text=True)
    return Path(res.stdout.strip()) if res.returncode == 0 else None


def load_values(root: Path | None, path: str | None) -> dict:
    try:
        return skill_values.section("dev-flow", "spec-doc", explicit=path, starts=[str(root or Path.cwd())])
    except skill_values.ValuesError as e:
        raise Abort(str(e))


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def section6(text: str) -> list[tuple[int, str]] | None:
    """§6 の節の中の行を (行番号, 行) で返す。節が無ければ None。当たる見出しが 2 つ以上なら止める。"""
    lines = text.splitlines()
    heads = [(i, len(m.group(1)), m.group(2)) for i, ln in enumerate(lines)
             if (m := _HEAD.match(ln))]
    hits = [h for h in heads if _SEC6.search(h[2])]
    if len(hits) > 1:
        names = "、".join(f"{i + 1} 行目「{t}」" for i, _, t in hits)
        raise Abort(f"§6（決定照合）に当たる見出しが 2 つ以上ある（{names}）＝どれを照らすか決まらない。"
                    "§6 の見出しを 1 つにし、ほかの見出しから「§6」「6.」「決定照合」を外す")
    if not hits:
        return None
    start, level, _ = hits[0]
    end = next((i for i, lv, _ in heads if i > start and lv <= level), len(lines))
    return [(j + 1, lines[j]) for j in range(start + 1, end)]


def _after_last_sep(body: str) -> str:
    """括弧の外の最後の区切り（→ -> : ：）の後ろ。括弧の中の区切り（「（理由: …）」）は見ない。"""
    masked = _PAREN.sub(lambda m: "＿" * len(m.group(0)), body)
    cut = 0
    for m in _SEP.finditer(masked):
        cut = m.end()
    return body[cut:].strip()


def rows_of(body: list[tuple[int, str]]) -> tuple[list[tuple[int, str, str]], list[tuple[int, str]]]:
    """節の行を (行番号, 行の字, 扱いを見る字) の並びと、形の決まらない地の文の (行番号, 行) の並びにする。
    表の見出しの行と区切りは除く。「扱い」の列が無い表の行は扱いを見る字を空にする（済みでない）。"""
    out, loose, header, col = [], [], None, None
    for no, ln in body:
        if _TABLE.match(ln):
            if _TABLE_SEP.match(ln):
                continue
            cells = _cells(ln)
            if header is None:
                header = cells
                col = next((k for k, c in enumerate(cells) if "扱い" in c), None)
                continue
            look = cells[col] if col is not None and col < len(cells) else ""
            out.append((no, ln.strip(), look))
        else:
            header = col = None
            if _ITEM.match(ln):
                item = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", ln)
                out.append((no, ln.strip(), _after_last_sep(item)))
            elif not _NOTE.match(ln):
                loose.append((no, ln.strip()))
    return out, loose


def settled(look: str) -> bool:
    """扱いが閉じた形で、理由に未定の印が無い時だけ True。"""
    m = _DONE.match(look.strip())
    return bool(m) and not (m.group(1) and _PENDING.search(m.group(1)))


def check_match(spec_dir: Path, values: dict) -> tuple[list[str], list[str]]:
    """決定照合を照らす。(止める訳, 知らせる事) を返す。"""
    files = sorted(spec_dir.glob("15_*.md"))
    if not files:
        return [f"15 の台帳（15_*.md）が {spec_dir} に無い＝照合の結果を置く所が無い"], []
    if len(files) > 1:
        return [f"15 の台帳が 2 つ以上ある（{', '.join(f.name for f in files)}）＝どれが正本か決まらない"], []
    f = files[0]
    body = section6(f.read_text(encoding="utf-8"))
    if body is None:
        return [f"{f.name} に §6（決定照合）の節が無い"], []
    rows, loose = rows_of(body)
    early = [f"{f.name}:{no} 形の決まらない行（表・箇条でない地の文は照合の結果として読めない）: "
             f"{ln if len(ln) <= 80 else ln[:79] + '…'}" for no, ln in loose]
    if not rows:
        return early + [f"{f.name} の §6 に行が 1 つも無い＝照合していない"], []
    allow = values.get("decision_match_allow", [])
    if not isinstance(allow, list) or not all(isinstance(p, str) and p for p in allow):
        raise Abort("値の表の decision_match_allow は空でない字（正規表現）の並びで書く")
    try:
        allow_re = [re.compile(p) for p in allow]
    except re.error as e:
        raise Abort(f"値の表の decision_match_allow に読めない正規表現（{e}）")
    has_port = bool(values.get("decision_match"))
    stops, notes = list(early), []
    for no, ln, look in rows:
        short = ln if len(ln) <= 80 else ln[:79] + "…"
        if any(r.search(ln) for r in allow_re):
            notes.append(f"{f.name}:{no} 値の表 decision_match_allow で外した: {short}")
            continue
        if UNMATCHED in look or UNMATCHED in ln:
            if has_port:
                stops.append(f"{f.name}:{no} 未照合のまま（この repo には照合の口 decision_match が在る）: {short}")
            else:
                notes.append(f"{f.name}:{no} 未照合（照合の口が値の表に無い repo）: {short}")
            continue
        if not settled(look):
            stops.append(f"{f.name}:{no} 扱いが無い（直した／覆す／関係なし のどれかちょうど＋（理由: …）でない・"
                         f"理由に未定の印が在る）: {short}")
    return stops, notes


FIX = """直し方:
  - 扱いの無い行は、決定の記録と照らして 直した（設計書を決定に合わせた）／覆す（旧決定を墓標へ回す）／関係なし のどれかを
    ちょうど書く。添えるなら （理由: …） の 1 つだけ。地の文の行は表か箇条の行に書き直す。
    決められない食い違いはオーナーに聞く（封をしてから聞かない）。
  - 未照合の行は、照合の口（値の表 decision_match）を回して結果を写す。口に届かない時は届くまで封をしない。
  - §6 が無い・空の時は、照合の口を回して「ぶつかる」「Claude が読む」を 1 行ずつ写す。
誤って止まった時（扱いを書いたのに読めない形など）: 15 §6 の行を「扱い」の列か 直した／覆す／関係なし の語で書き直す。
  同じ形で何度も誤るなら、repo の値の表 dev-flow.spec-doc.decision_match_allow（行に当てる正規表現）に足す PR を出す。
直しは行を 1 つずつ埋めて出し直すだけで済ませず、照合が抜けた原因（照合の口を回す段を飛ばした等）を細目 §3「まず構造を疑う」で探して直す。"""



def _strict_args():
    """印の読み方の正本（plugin の lib/strict_args.py＝土台の shared/ への symlink）。"""
    import importlib.util
    from pathlib import Path as _P
    lib = _P(__file__).resolve().parents[2] / "lib" / "strict_args.py"
    spec = importlib.util.spec_from_file_location("af_strict_args", lib)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main(argv=None) -> int:
    ap = _strict_args().ArgumentParser(description="設計書の封の入口（決定照合を照らしてから gate --lock を呼ぶ）")
    ap.add_argument("spec_dir", help="設計書の dir")
    ap.add_argument("--values", help="値の表の path（既定は今の repo の根の config/skill-values.json）")
    ap.add_argument("--match-only", action="store_true", help="決定照合だけを照らす（gate を呼ばない）")
    a = ap.parse_args(argv)
    try:
        spec = Path(a.spec_dir)
        if not spec.is_dir():
            raise Abort(f"設計書の dir が無い: {spec}")
        root = repo_root(Path.cwd())
        values = load_values(root, a.values)
        stops, notes = check_match(spec, values)
        for n in notes:
            print(f"  知らせ: {n}")
        if stops:
            print("seal: 止めた — 15 §6 の決定照合が済んでいない（gate を呼ばない＝LOCK しない）", file=sys.stderr)
            for s in stops:
                print(f"  - {s}", file=sys.stderr)
            print(FIX, file=sys.stderr)
            return 1
        print("seal: 決定照合 緑")
        if a.match_only:
            return 0
        tdir = values.get("template_dir")
        base = Path(tdir).expanduser() if tdir else None
        if base is not None and not base.is_absolute() and root is not None:
            base = root / base   # 型の置き場は repo の根からの相対で書いてよい
        gate = base / "check_spec_doc.py" if base is not None else None
        if gate is None or not gate.is_file():
            why = "値の表に template_dir が無い" if not tdir else f"gate が無い: {gate}"
            print(f"seal: 型が無い（{why}）＝gate 未通過（型なし）。LOCK しない・状態は Draft のまま")
            return 3
        return subprocess.run([sys.executable, str(gate), str(spec), "--lock"]).returncode
    except Abort as e:
        print(f"seal: 中止 — {e}", file=sys.stderr)
        print("直し: 値や入力を差し替えて出し直すだけで済ませず、崩れた原因を細目 §3「まず構造を疑う」で探して直す", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
