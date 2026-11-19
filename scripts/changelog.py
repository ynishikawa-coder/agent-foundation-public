#!/usr/bin/env python3
"""変更の記録（CHANGELOG.d/ の断片）を照らす・束ねて見せる。

決まりの正本は CHANGELOG.d/README.md。PR ごとに自分の file を 1 つ足すだけにし、
全部の PR が同じ所（CHANGELOG.md の先頭）へ行を足して互いに衝突する形を無くす。

  python3 scripts/changelog.py check   # 形を照らす（赤なら 1 で終わる）
  python3 scripts/changelog.py         # 全部を新しい物が上で見せる（git の履歴で並べる）
  python3 scripts/changelog.py adopt <古い形の CHANGELOG.md> <断片の file>
      # 古い形で書いた記録の行のうち、CHANGELOG.d/ のどこにも無い物を、断片の file の頭へ移す
      # （断片の形の前に枝を切った PR が main を取り込む時の移し方・CHANGELOG.d/README.md）
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR_NAME = "CHANGELOG.d"
# 断片へ移す前の記録（そのまま移した経緯・札の形を照らさない）。
OLD_FILE = "00000000-断片へ移す前.txt"
# 移す前の記録は動かさない（頭へ足せば、同じ所へ追記する形がこの file へ移るだけ）。中身の印で止める。
OLD_SHA256 = "93e5dda7492211d6997bb3046b0bd8659069845e88da658d149b85fb6430eaff"
NAME_RE = re.compile(r"^\d{8}-[0-9A-Za-z][0-9A-Za-z._-]*\.txt$")
README = ROOT / DIR_NAME / "README.md"


def load_cards(path=README):
    """札の並び。正本は CHANGELOG.d/README.md の「札は `…`・`…` のどれか」の行（ここに写さない）。読めなければ例外。"""
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.search(r"札は(.+?)のどれか", ln)
        cards = re.findall(r"`([^`]+)`", m.group(1)) if m else []
        if cards:
            return tuple(cards)
    raise ValueError("札の並びが読めない: %s" % path)


CARDS = load_cards()
LINE_RE = re.compile(r"^- (%s)(（[^）\n]+）)?: \S" % "|".join(map(re.escape, CARDS)))
JST = timezone(timedelta(hours=9))
# CHANGELOG.md の中身はこれだけ（記録を書く所は CHANGELOG.d/）。見出しや地の文でも足せば赤。
MAIN_TEXT = """# 変更の記録

記録は 1 PR に 1 つの file で `CHANGELOG.d/` に置く。この file には記録の行を書かない（書くと検査が赤）。書き方は `CHANGELOG.d/README.md`。

全部を新しい物が上で読む: `python3 scripts/changelog.py`（main に入った順に並べる）。断片へ移す前の記録（v0.4.1 から）は `CHANGELOG.d/00000000-断片へ移す前.txt` にそのまま在る。

v0.1.1 までの版は移す前の private の repo で出した（この repo には印を打たない・記録もここに持たない）。v0.2.0 の「足した」は、v0.1.1 の後・移す前に入った物。
"""


def check(root: Path = ROOT) -> list[str]:
    """形の誤りを全部返す（空なら緑）。"""
    errs: list[str] = []
    main = root / "CHANGELOG.md"
    if not main.is_file():
        errs.append("CHANGELOG.md が無い")
    else:
        text = main.read_text(encoding="utf-8")
        if text != MAIN_TEXT:
            fixed = set(MAIN_TEXT.splitlines())
            extra = [n for n, l in enumerate(text.splitlines(), 1) if l.strip() and l not in fixed]
            where = ",".join(map(str, extra)) or "消した行"
            errs.append(f"CHANGELOG.md:{where}: CHANGELOG.md は決まった文だけ（記録は書かない）。"
                        f"記録は自分の枝の {DIR_NAME}/<日付>-<話題>.txt へ移す（{DIR_NAME}/README.md・"
                        f"移す命令は scripts/changelog.py adopt）。この文を変えるなら scripts/changelog.py の MAIN_TEXT と一緒に")
    d = root / DIR_NAME
    if not d.is_dir():
        errs.append(f"{DIR_NAME}/ が無い")
        return errs
    if not (d / OLD_FILE).is_file():
        errs.append(f"{DIR_NAME}/{OLD_FILE} が無い（移す前の記録を消さない）")
    elif hashlib.sha256((d / OLD_FILE).read_bytes()).hexdigest() != OLD_SHA256:
        errs.append(f"{DIR_NAME}/{OLD_FILE}: 移す前の記録は動かさない（足す・直すと、全部の PR が同じ所へ追記する形に戻る）。"
                    f"記録は自分の枝の {DIR_NAME}/<日付>-<話題>.txt へ書く")
    for p in sorted(d.iterdir()):
        if p.name == "README.md":
            continue
        if p.is_dir() or (p.name != OLD_FILE and not NAME_RE.match(p.name)):
            errs.append(f"{DIR_NAME}/{p.name}: 名は <YYYYMMDD>-<話題>.txt（枝 claude/<日付>-<話題> と同じ・英数と . _ -）")
            continue
        text = p.read_text(encoding="utf-8")
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            errs.append(f"{DIR_NAME}/{p.name}: 中身が無い")
        if p.name == OLD_FILE:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip() and not LINE_RE.match(line):
                errs.append(f"{DIR_NAME}/{p.name}:{n}: 行は" + "".join(f"「- {c}: …」" for c in CARDS) + "の形"
                            "（札の後に（…）を添えてよい）。1 項は 1 行")
    return errs


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def entries(root: Path = ROOT) -> list[tuple[str, str, str]]:
    """(名, 入った時, 中身) を新しい物が上で返す。入った時は、その file を足した最初の commit の時刻。
    まだ commit されていない断片は一番上。履歴が浅い（shallow）時は並べられないので止まる。"""
    if _git(root, "rev-parse", "--is-shallow-repository").strip() == "true":
        raise SystemExit("履歴が浅いので並べられない: git fetch --unshallow をしてから回す")
    rows = []
    for p in sorted((root / DIR_NAME).glob("*.txt")):
        out = _git(root, "log", "--diff-filter=A", "--format=%ct", "--", str(p.relative_to(root))).split()
        ts = int(out[-1]) if out else None
        when = (datetime.fromtimestamp(ts, JST).strftime("%Y-%m-%d %H:%M 日本時間") if ts else "まだ入っていない")
        key = ts if ts is not None else float("inf")
        rows.append((key, p.name, when, p.read_text(encoding="utf-8").strip()))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    return [(name, when, body) for _, name, when, body in rows]


def adopt(source_text: str, target: Path, root: Path = ROOT) -> list[str]:
    """source_text（古い形の CHANGELOG.md）の記録の行で、CHANGELOG.d/ のどこにも無い物を target の頭へ足す。
    足した行を返す。行の並び（新しい物が上）はそのまま。"""
    have: set[str] = set()
    for p in (root / DIR_NAME).glob("*.txt"):
        have.update(l.rstrip() for l in p.read_text(encoding="utf-8").splitlines())
    new = [l.rstrip() for l in source_text.splitlines()
           if l.startswith("- ") and l.rstrip() not in have]
    if new:
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text("\n".join(new) + "\n" + old, encoding="utf-8")
    return new


USAGE = ("使い方: changelog.py ／ changelog.py check ／ changelog.py adopt <古い形の CHANGELOG.md|-> <断片の file>")


def main(argv: list[str]) -> int:
    # 知らない口・数の違う引数は既定で止める（一覧の表示へ落として成功で返すと、頼んだ移し・検査をしていないのに緑になる）
    args = argv[1:]
    ok = (args == [] or args == ["check"] or (len(args) == 3 and args[0] == "adopt"
                                              and not any(a.startswith("--") for a in args[1:])))
    if not ok:
        print(USAGE, file=sys.stderr)
        return 2
    if argv[1:2] == ["adopt"] and len(argv) == 4:
        src = sys.stdin.read() if argv[2] == "-" else Path(argv[2]).read_text(encoding="utf-8")
        moved = adopt(src, Path(argv[3]))
        print(f"changelog: {len(moved)} 行を {argv[3]} へ移した")
        return 0
    if argv[1:2] == ["check"]:
        errs = check()
        for e in errs:
            print(e)
        print("changelog: 赤 直し: 赤の行を 1 つずつ潰さず、細目 §3「まず構造を疑う」で原因から直す" if errs else "changelog: 緑")
        return 1 if errs else 0
    for name, when, body in entries():
        print(f"## {name.removesuffix('.txt')}（{when}）\n\n{body}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
