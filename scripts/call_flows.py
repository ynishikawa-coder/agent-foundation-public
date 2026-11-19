#!/usr/bin/env python3
"""部品（plugin）どうしの呼び出しの流れを、コードと手順の文から機械で拾い、全体の絵に全部在るかを照らす。

なぜ在るか: 全体の絵を写す・描く時に、ある plugin の script・skill の手順が別の plugin の道具を呼ぶ流れを、
人の目で 2 回続けて拾い漏らした（合意した絵に無い流れが実物に在り、合流の前の照らしで red）。
流れは目で探さず、ここで拾った一覧を正にする。

  python3 scripts/call_flows.py list  [--repo DIR]            # 流れを 1 行ずつ「呼ぶ側 → 呼ばれる側  証拠」で出す
  python3 scripts/call_flows.py check <絵.json> [--repo DIR]  # 拾った流れが全部、絵の仕組みの構成（arch）の矢印に在るか

拾う物（道具＝plugins/<名>/ の下の .py .mjs .js .sh の file）:
  - 別の plugin の道具の file 名（その名の file が plugin の外にも在る時は path ごと書いた物だけ）
  - 別の plugin の道具の path（plugins/<名>/…/<道具の file 名>）
  拾わない物: skill の名を文で挙げるだけの物・文書（.md）の path（道具を呼ぶ流れでない）。
絵との対応: 絵の箱のうち tab が arch で、題の頭（「（」の前）が plugin の名と同じ箱をその plugin の箱とみる。
  箱が無い plugin・2 つ在る plugin は照らせない＝赤（黙って通さない）。矢印の向きは 呼ぶ側 → 呼ばれる側。
exit: list は 0。check は 0=全部在る／1=絵に無い流れが在る／2=照らせない（絵が読めない・箱が無い・重なる）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL_SUFFIX = (".py", ".mjs", ".js", ".sh")
TEXT_SUFFIX = (".py", ".mjs", ".js", ".sh", ".md", ".json", ".html", ".txt")
ROOT_CAUSE = ("直し: 絵に無い流れを 1 本ずつ足して済ませず、流れが絵から漏れた原因を細目 §3「まず構造を疑う」で探して直す"
              "（絵は合意の版＝足すならオーナーに差を見せて決めてもらう）")


def tracked(repo: Path) -> list[str]:
    r = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files"], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError(f"git の一覧が取れない: {r.stderr.strip()}")
    return [ln for ln in r.stdout.splitlines() if ln]


def flows(repo: Path) -> dict[tuple[str, str], list[str]]:
    """{(呼ぶ側, 呼ばれる側): [証拠 "path:行 字"]}。"""
    files = tracked(repo)
    plugins = sorted({f.split("/")[1] for f in files if f.startswith("plugins/") and f.count("/") >= 2
                      and (repo / "plugins" / f.split("/")[1] / ".claude-plugin" / "plugin.json").is_file()})
    owner: dict[str, set[str]] = defaultdict(set)      # 道具の file 名 → 持つ plugin
    outside: set[str] = set()                          # plugin の外にも同じ名の file が在る名
    for f in files:
        name = f.rsplit("/", 1)[-1]
        parts = f.split("/")
        if parts[0] == "plugins" and len(parts) >= 3 and parts[1] in plugins and f.endswith(TOOL_SUFFIX):
            owner[name].add(parts[1])
        elif not (parts[0] == "plugins"):
            outside.add(name)
    pats = []
    for name, ys in owner.items():
        for y in ys:
            path_pat = re.compile(r"plugins/%s/(?:[^\s'\"`)]*/)?%s(?![\w.])" % (re.escape(y), re.escape(name)))
            bare = None if (name in outside or len(ys) > 1) else re.compile(r"(?<![\w./-])%s(?![\w])" % re.escape(name))
            pats.append((y, name, path_pat, bare))
    out: dict[tuple[str, str], list[str]] = defaultdict(list)
    for f in files:
        parts = f.split("/")
        if parts[0] != "plugins" or len(parts) < 3 or parts[1] not in plugins or not f.endswith(TEXT_SUFFIX):
            continue
        x = parts[1]
        try:
            lines = (repo / f).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for no, ln in enumerate(lines, 1):
            for y, name, path_pat, bare in pats:
                if y == x:
                    continue
                if path_pat.search(ln) or (bare and bare.search(ln)):
                    out[(x, y)].append(f"{f}:{no} {name}")
    return dict(out)


def plugin_boxes(pic: dict, names) -> tuple[dict[str, str], list[str]]:
    boxes = [b for b in pic.get("boxes") or [] if isinstance(b, dict) and b.get("tab") == "arch"]
    found: dict[str, list[str]] = defaultdict(list)
    for b in boxes:
        head = str(b.get("t") or "").split("（", 1)[0].strip()
        if head in names:
            found[head].append(str(b.get("id")))
    errs = [f"plugin {n} の箱が絵の仕組みの構成（arch）に無い" for n in names if not found.get(n)]
    errs += [f"plugin {n} の箱が 2 つ以上在る（{'・'.join(ids)}）" for n, ids in found.items() if len(ids) > 1]
    return {n: ids[0] for n, ids in found.items() if len(ids) == 1}, errs


def check(pic_path: Path, repo: Path) -> int:
    try:
        pic = json.loads(pic_path.read_text(encoding="utf-8"))
        if not isinstance(pic, dict):
            raise ValueError("絵が JSON の object でない")
        got = flows(repo)
    except (OSError, ValueError) as e:
        print(f"call_flows: 照らせない — {e}")
        return 2
    names = sorted({n for pair in got for n in pair})
    box, errs = plugin_boxes(pic, names)
    if errs:
        for e in errs:
            print(f"✗ {e}")
        print("call_flows: 照らせない（plugin の箱と流れを結べない）")
        return 2
    arrows = {(a.get("from"), a.get("to")) for a in pic.get("arrows") or [] if isinstance(a, dict)}
    missing = [(x, y, ev) for (x, y), ev in sorted(got.items()) if (box[x], box[y]) not in arrows]
    for x, y, ev in missing:
        print(f"✗ 絵に無い流れ: {x} → {y}（{box[x]} → {box[y]}）証拠: {ev[0]}" + (f" ほか {len(ev) - 1}" if len(ev) > 1 else ""))
    if missing:
        print(f"call_flows: 赤 絵に無い流れ {len(missing)} 本")
        print(ROOT_CAUSE)
        return 1
    print(f"call_flows: 緑 流れ {len(got)} 本が全部絵に在る")
    return 0



def _strict_args():
    """印の読み方の正本（土台の shared/strict_args.py）。"""
    import importlib.util
    from pathlib import Path as _P
    lib = _P(__file__).resolve().parent.parent / "shared" / "strict_args.py"
    spec = importlib.util.spec_from_file_location("af_strict_args", lib)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main(argv=None) -> int:
    ap = _strict_args().ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--repo", type=Path, default=ROOT)
    ck = sub.add_parser("check")
    ck.add_argument("picture", type=Path)
    ck.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for (x, y), ev in sorted(flows(a.repo).items()):
            print(f"{x} → {y}  {ev[0]}" + (f" ほか {len(ev) - 1}" if len(ev) > 1 else ""))
        return 0
    return check(a.picture, a.repo)


if __name__ == "__main__":
    sys.exit(main())
