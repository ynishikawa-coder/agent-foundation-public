#!/usr/bin/env python3
"""窓の文脈に土台が入れる量を数える（起動で入る量・毎ターン付く文・skill ごとの量・同じ文の写し）。

  python3 scripts/measure_load.py            人が読む表
  python3 scripts/measure_load.py --json     機械が読む形（前→後を比べる時は 2 つの版で回して並べる）

意図: 土台が窓の文脈に入れる量（＝トークン）を減らす仕事で、前→後を同じ物差しで数え、PR に数字で書けるようにする。
課題: 起動だけで約 9〜10 万トークン使い、どこが何字かを窓ごとに手で数えていた（数え方が揃わず、減ったかを記録で言えない）。
原因: 量の上限と数えは kaku.py の LIMITS・grow が核・振る舞い・細目だけを見て、skill の説明文・skill の本文・毎ターンの
知らせは誰も数えていなかった。

数える物（字数＝len(str)。バイトは UTF-8）:
  起動     skill の説明文（全 plugin の SKILL.md の頭の description。窓の一覧に毎回載る）と、核の差し込み（kaku.inject_text）。
  毎ターン 題の無いクラウドの窓に UserPromptSubmit の hook が付ける知らせ（session_watch の remind_title。人の窓・子の窓・
           頼みの文が別の窓を指す窓の 3 つ）と、Stop の知らせの頭と足（NOTE_HEAD・STOP_FOOT）。
  skill    skill ごとの説明文・本文（SKILL.md の頭の後）・同じ dir の他の文の file（.md・.py・.mjs・.json など）。
  写し     道具の中の、根治の 1 文（「まず構造を疑う」を含む行）の数。正本へ寄せると減る。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
TEXT_EXT = {".md", ".py", ".mjs", ".js", ".json", ".txt", ".html", ".css", ".yaml", ".yml", ".sh"}
COPY_MARK = "まず構造を疑う"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def split_front(text: str) -> tuple[str, str]:
    """SKILL.md を (頭の description, 本文) に分ける。頭が無ければ ("", 全文)。"""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return "", text
    import yaml
    head = yaml.safe_load(m.group(1)) or {}
    return str(head.get("description") or ""), text[m.end():]


def size(s: str) -> dict:
    return {"字": len(s), "バイト": len(s.encode("utf-8"))}


def skills(plugins: Path = PLUGINS) -> list[dict]:
    out = []
    for md in sorted(plugins.glob("*/skills/*/SKILL.md")):
        desc, body = split_front(md.read_text(encoding="utf-8"))
        extra = 0
        for f in sorted(md.parent.rglob("*")):
            if f.is_file() and f != md and f.suffix in TEXT_EXT:
                extra += len(f.read_text(encoding="utf-8", errors="ignore"))
        out.append({"skill": f"{md.parent.parent.parent.name}:{md.parent.name}",
                    "説明文": len(desc), "本文": len(body), "他の file": extra})
    return out


def every_turn(plugins: Path = PLUGINS) -> dict:
    sw = load("af_measure_session_watch", plugins / "session-watch" / "scripts" / "session_watch.py")
    empty = sw.Log([])
    texts = {
        "題の無い人の窓（remind_title）": sw.remind_title(empty, {"prompt": "x"}) or "",
        "題の無い子の窓（REMIND_CHILD）": sw.REMIND_CHILD,
        "頼みの文が別の窓を指す窓（REMIND_PARENT）": sw.REMIND_PARENT,
        "Stop の知らせの頭（NOTE_HEAD）": sw.NOTE_HEAD,
        "Stop の知らせの足（STOP_FOOT）": sw.STOP_FOOT,
    }
    return {k: size(v) for k, v in texts.items()}


def copies(root: Path = ROOT) -> dict:
    hits = {}
    for f in sorted([*(root / "plugins").rglob("*.py"), *(root / "scripts").glob("*.py")]):
        if f.resolve() == Path(__file__).resolve():
            continue
        n = sum(1 for line in f.read_text(encoding="utf-8", errors="ignore").splitlines() if COPY_MARK in line)
        if n:
            hits[str(f.relative_to(root))] = n
    return {"行": sum(hits.values()), "file": hits}


def measure(root: Path = ROOT) -> dict:
    plugins = root / "plugins"
    kaku = load("af_measure_kaku", plugins / "core" / "scripts" / "kaku.py")
    sk = skills(plugins)
    desc = sum(s["説明文"] for s in sk)
    inj = kaku.inject_text()
    return {
        "起動": {"skill の説明文": {"字": desc, "skill の数": len(sk)},
                 "核の差し込み": size(inj),
                 "計（字）": desc + len(inj)},
        "毎ターン": every_turn(plugins),
        "skill": sorted(sk, key=lambda s: -(s["本文"] + s["他の file"])),
        "写し": copies(root),
    }


def table(m: dict) -> str:
    st = m["起動"]
    lines = ["## 起動で入る量（字）",
             f"- skill の説明文: {st['skill の説明文']['字']}（{st['skill の説明文']['skill の数']} skill）",
             f"- 核の差し込み: {st['核の差し込み']['字']}",
             f"- 計: {st['計（字）']}",
             "", "## 毎ターン付く文（字）"]
    lines += [f"- {k}: {v['字']}" for k, v in m["毎ターン"].items()]
    lines += ["", "## skill ごとの量（字）", "", "| skill | 説明文 | 本文 | 他の file |", "|---|---:|---:|---:|"]
    lines += [f"| {s['skill']} | {s['説明文']} | {s['本文']} | {s['他の file']} |" for s in m["skill"]]
    lines += ["", f"## 根治の 1 文の写し: {m['写し']['行']} 行（{len(m['写し']['file'])} file）"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="機械が読む形で出す")
    ap.add_argument("--root", type=Path, default=ROOT, help="数える repo の根（別の版の checkout と比べる時）")
    a = ap.parse_args(argv)
    m = measure(a.root.resolve())
    print(json.dumps(m, ensure_ascii=False, indent=1) if a.json else table(m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
