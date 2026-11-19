#!/usr/bin/env python3
"""使う側の repo の文に、土台の決まりの写し（そのままの写しも言い換えた写しも）が無いかを拾う。

なぜ在るか: 使う側の写しの試験は、土台の文をそのまま写した物だけを拾い、言い換えた写しは拾えなかった
（言い換えた規律の写しが残っても緑）。写しは土台の文が変わっても古いまま勝つので、言い換えでも拾う。
照らし方: 文ごとに、記号と空白を除いた字の 2 字の並びの重なり（Dice の係数）を土台の全部の文と比べ、
  THRESHOLD 以上の組を写しとみなす。そのままの写しは 1.0、語順や語尾を変えた言い換えは 0.6〜0.8 ほど、
  関係の無い文は 0.1 ほど。MIN_CHARS より短い文は 1 つでは照らさず（短い決まり文句の取り違えを避ける）、
  短い文が続く所はつないで MIN_CHARS 以上にして照らす（1 つの写しを短い文に割って下限をすり抜けさせない）。
土台の文: 同じ plugin の 核.md・振る舞い.md・細目.md と、並ぶ plugin の skills/*/SKILL.md
  （repo の形 plugins/<名>/ と、入れた写しの形 cache/<市場>/<名>/<版>/ のどちらでも探す）。--foundation で dir を渡せば
  その下の .md を全部使う。土台の文が 1 つも読めない時は照らさずに止める（黙って緑にしない）。

  python3 copies.py <照らす file>... [--foundation DIR] [--threshold 0.5]
exit: 0=写し無し／1=写しが在る（組を 1 行ずつ出す）／2=土台の文が読めない・照らす file が読めない。
残る穴（正直に書く）: 字を大きく替えた言い換え（同じ意味を別の語で書く）は字の並びが重ならず拾えない
  （意味の同じさを決める構造の正本が無い＝語の言い換えの表を足して塞がない。写しの関所は別の目のレビュー）。
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
SPLIT_MAX = 4   # 短い文をつなぐのは続く 5 つまで
_STRIP = re.compile(r"[\s`*_>#|・、。，．,.:：;；()（）「」『』\[\]{}<>—\-–/\\!！?？=＝+〔〕【】]+")
_SPLIT = re.compile(r"(?<=[。！？])|\n")
ROOT_CAUSE = ("直し: 写しの文を言い換えて逃がさず、土台の正本を指す 1 行（どの file のどの節か）に替える。"
              "写しが要る形になった原因は細目 §3「まず構造を疑う」で探す")


def pieces(text: str):
    """(行番号, 文) の並び（短い文も含む）。表の行・箇条の頭・見出しの印は除いて文として切る。"""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#+|>)\s*", "", line)
        for part in _SPLIT.split(line):
            if _STRIP.sub("", part):
                out.append((no, part.strip()))
    return out


def sentences(text: str):
    """照らす単位の (行番号, 文)。MIN_CHARS 以上の文と、MIN_CHARS に満たない文が続く所はつないだ物
    （1 つの文を短い文に割って閾値と長さの下限をすり抜けさせない）。"""
    ps = pieces(text)
    short = [len(_STRIP.sub("", t)) < MIN_CHARS for _, t in ps]
    out = []
    for i, (no, t) in enumerate(ps):
        if not short[i]:
            out.append((no, t))
            continue
        joined, j = t, i
        while len(_STRIP.sub("", joined)) < MIN_CHARS and j + 1 < len(ps) and short[j + 1] and j - i < SPLIT_MAX:
            j += 1
            joined += ps[j][1]
        if j > i and len(_STRIP.sub("", joined)) >= MIN_CHARS:
            out.append((no, joined))
    return out


def grams(s: str) -> Counter:
    s = _STRIP.sub("", s)
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def foundation_files(base: Path | None) -> list[Path]:
    if base is not None:
        return sorted(p for p in base.rglob("*.md") if p.is_file())
    own = [PLUGIN / n for n in ("核.md", "振る舞い.md", "細目.md")]
    skills = set(PLUGIN.parent.glob("*/skills/*/SKILL.md")) | set(PLUGIN.parent.parent.glob("*/*/skills/*/SKILL.md"))
    return [p for p in own if p.is_file()] + sorted(skills)


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


def scan(targets: list[Path], rows, inv, threshold: float = THRESHOLD):
    hits = []
    for t in targets:
        for no, s in sentences(t.read_text(encoding="utf-8")):
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
    seen, out = set(), []
    for h in sorted(hits, key=lambda h: -h[3]):        # 割った文をつないだ窓が重なっても、土台の 1 文に 1 件
        if (h[0], h[4], h[5]) not in seen:
            seen.add((h[0], h[4], h[5]))
            out.append(h)
    return sorted(out, key=lambda h: (str(h[0]), h[1]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--foundation", type=Path)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    a = ap.parse_args(argv)
    try:
        rows, inv = index(foundation_files(a.foundation))
        if not rows:
            print("copies: 照らせない — 土台の文が 1 つも読めない（--foundation で土台の dir を渡す）")
            return 2
        hits = scan(a.files, rows, inv, a.threshold)
    except (OSError, UnicodeDecodeError) as e:
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
