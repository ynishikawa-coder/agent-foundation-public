#!/usr/bin/env python3
"""使う側の repo の文に、土台の決まりの写し（そのままの写しも言い換えた写しも）が無いかを拾う。

意図: 使う側に残った土台の規律の写しを、言い換えでも拾う（写しは土台の文が変わっても古いまま勝つ）。
課題: 言い換えた規律の写しが残っても緑だった。
原因: 使う側の写しの試験は、土台の文をそのまま写した物だけを拾っていた。
照らし方: 文ごとに、記号と空白を除いた字の 2 字の並びの重なり（Dice の係数）を土台の全部の文と比べ、
  THRESHOLD 以上の組を写しとみなす。そのままの写しは 1.0、語順や語尾を変えた言い換えは 0.6〜0.8 ほど、
  関係の無い文は 0.1 ほど。MIN_CHARS より短い文は照らさない（短い決まり文句の取り違えを避ける）。
  正本を指す字（file の path・`…` のコード・skill の名 `plugin:skill`）は字の並びから除く（_POINTER）。写しの直し方は
  「正本を指す 1 行に替える」なので、指す字が重なっただけの行を写しと呼ぶと、直した行がまた赤になる。指す字を除いて
  MIN_CHARS に足りない行（指すだけの行）は照らさない。
土台の文: 同じ plugin の 核.md・振る舞い.md・細目/ の節ごとの file と、並ぶ plugin の skills/*/SKILL.md
  （repo の形 plugins/<名>/ は並ぶ plugin、入れた写しの形 cache/<市場>/<名>/<版>/ は入った版の dir だけ＝plugin_dirs）。--foundation で dir を渡せば
  その下の .md を全部使う。土台の文が 1 つも読めない時は照らさずに止める（黙って緑にしない）。

  python3 copies.py <照らす file>... [--foundation DIR] [--threshold 0.5]
exit: 0=写し無し／1=写しが在る（組を 1 行ずつ出す）／2=土台の文が読めない・照らす file が読めない。
残る穴（正直に書く）: 字を大きく替えた言い換え（同じ意味を別の語で書く）は字の並びが重ならず拾えない。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
THRESHOLD = 0.5
MIN_CHARS = 20
_STRIP = re.compile(r"[\s`*_>#|・、。，．,.:：;；()（）「」『』\[\]{}<>—\-–/\\!！?？=＝+〔〕【】]+")
_SPLIT = re.compile(r"(?<=[。！？])|\n")
_POINTER = re.compile(r"`[\x20-\x7e]*`"                              # 英数字だけのコード・path（日本語の文を `…` で囲んでも除かない）
                      r"|[\w.~-]*(?:/[\w.~-]+)+/?"                    # dir を含む path（.github/x.md・plugins/core/）
                      r"|[\w~-]+\.(?:md|py|json|sh|ya?ml|mjs|js|txt|toml)\b"  # 名だけの file（CONTRIBUTING.md）
                      r"|\b[a-z][\w-]*:[a-z][\w-]*\b", re.A)              # skill の名（dev-flow:verify）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from root_cause import root_cause  # noqa: E402  根治の 1 文の 1 本の口＝lib/root_cause.py の root_cause（正本へ戻る symlink）
ROOT_CAUSE = (root_cause("正本が 1 つで使う側は指すだけ", cause="写しが要る形になった", shortcut="写しの文を言い換えて逃がす")
              + "。写しは土台の正本を指す 1 行（どの file のどの節か。節は番号でなく名で指し、refs.py check で照らす）に替える")


def body(s: str) -> str:
    """照らす字: 正本を指す字と記号・空白を除いた残り。"""
    return _STRIP.sub("", _POINTER.sub(" ", s))


def sentences(text: str):
    """(行番号, 文) の並び。表の行・箇条の頭・見出しの印は除いて文として切る。"""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", line)
        for part in _SPLIT.split(line):
            if len(body(part)) >= MIN_CHARS:
                out.append((no, part.strip()))
    return out


def grams(s: str) -> Counter:
    s = body(s)
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def plugin_dirs() -> list[Path]:
    """土台の文を読む plugin の dir（入った版だけ）。
    repo の形（plugins/<名>/）: 並ぶ plugin の dir。入れた形（cache/<市場>/<名>/<版>/）: 入った台帳の、土台の目録の
    plugin ごとに今読まれる行（kaku.current_row）の installPath だけ。cache に残る前の版の dir は読まない
    （もう土台に無い言い回しの写しまで赤にしない）。台帳が無い・行が無ければ core と同じ版の dir だけ（在るのに読めない台帳は main が「照らせない」と名指す）。"""
    if (PLUGIN.parent.parent / ".claude-plugin").is_dir():
        return sorted(d for d in PLUGIN.parent.iterdir() if d.is_dir())
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kaku
    dirs = [Path(str(r["installPath"])) for r in (kaku.current_row(rows) for rows in kaku.user_rows().values()) if r]
    if dirs:
        return sorted(set(dirs) | {PLUGIN})
    return sorted(d / PLUGIN.name for d in PLUGIN.parent.parent.iterdir() if (d / PLUGIN.name).is_dir())


def foundation_files(base: Path | None) -> list[Path]:
    if base is not None:
        return sorted(p for p in base.rglob("*.md") if p.is_file())
    own = [PLUGIN / n for n in ("核.md", "振る舞い.md")]
    # 自分の版の核・振る舞い・細目は必ず在る物: 欠けを黙って除くと、その文の写しを拾わずに緑になる
    lack = [str(p) for p in own if not p.is_file()] + ([] if (PLUGIN / "細目").is_dir() else [str(PLUGIN / "細目")])
    if lack:
        raise OSError(f"土台の文が欠けている（照らす元に無い）: {' '.join(lack)}")
    own += sorted((PLUGIN / "細目").glob("*.md"))   # 細目は節ごとの file
    skills = {p for d in plugin_dirs() for p in d.glob("skills/*/SKILL.md")}
    return own + sorted(skills)


def index(files: list[Path]):
    rows, inv = [], defaultdict(set)
    for f in files:
        for no, s in sentences(f.read_text(encoding="utf-8")):
            g = grams(s)
            k = len(rows)
            rows.append((f, no, s, g, sum(g.values())))
            for b in g:
                inv[b].add(k)
    return rows, inv


def own_text(text: str) -> str:
    """照らす file の自分の文（出所を示して引いた所を除く）。写しは自分の文として決まりを書き直した物で、引用は出所を示した引き。
    読み方（コードの囲み・> の引用・「」『』“” の引用）の正本は kaku.md_own（写さない）。注記の中は AI が読む文なので照らし、
    地の文の `…` の中も照らす（決まりの文を `…` で囲むだけで迂回させない）。"""
    return _kaku().md_own(text, notes=True, spans=True)


def _kaku():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kaku
    return kaku


def scan(targets: list[Path], rows, inv, threshold: float = THRESHOLD):
    hits = []
    for t in targets:
        for no, s in sentences(own_text(t.read_text(encoding="utf-8"))):
            g = grams(s)
            n = sum(g.values())
            cand = Counter()
            for b in g:
                for k in inv.get(b, ()):
                    cand[k] += 1
            best = None
            for k, _ in cand.most_common(20):
                f, fno, fs, fg, fn = rows[k]
                score = 2 * sum((g & fg).values()) / (n + fn)
                if score >= threshold and (best is None or score > best[0]):
                    best = (score, f, fno, fs)
            if best:
                hits.append((t, no, s, *best))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--foundation", type=Path)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kaku
    try:
        rows, inv = index(foundation_files(a.foundation))
        if not rows:
            print("copies: 照らせない — 土台の文が 1 つも読めない（--foundation で土台の dir を渡す）")
            return 2
        hits = scan(a.files, rows, inv, a.threshold)
    except (OSError, UnicodeDecodeError, kaku.Unreadable) as e:  # 入った台帳が読めない時も名指す
        print(f"copies: 照らせない — {e}")
        return 2
    for t, no, s, score, f, fno, fs in hits:
        where = "/".join(f.parts[-4:]) if f.name == "SKILL.md" else f.name
        print(f"✗ {t}:{no} が土台の {where}:{fno} の写し（重なり {score:.2f}）: {s[:60]}")
    if hits:
        print(f"copies: 赤 写し {len(hits)} 件")
        print(ROOT_CAUSE)
        return 1
    print(f"copies: 緑（土台の文 {len(rows)} と照らした）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
