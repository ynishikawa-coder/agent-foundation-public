"""土台の在り処探しの 1 本の口（plugin の外の土台の file・隣の plugin の file を、入った plugin と同じ版で探して読む）。

土台の plugin は市場から入ると cache/<市場>/<plugin>/<版> に置かれ、repo の根の物（public-guard/guard.py など）は
plugin の中に無い。正本を写さず直に読むために、どの plugin もここ 1 か所で探す（各 plugin の lib/ へは symlink で届く）。
plugin_root は呼ぶ plugin の根（repo の形では plugins/<plugin>・入れた形では cache/<市場>/<plugin>/<版>）。
"""
from __future__ import annotations

import os
import re
import tempfile


# foundation_file が "" を返した訳と直し方（呼ぶ側が止める文に添える。見つかった時は ""）。
MISS = ""


def _miss(why):
    global MISS
    MISS = why
    return ""


def miss_note():
    """直前の foundation_file が "" を返した訳（止める文の後ろに添える形）。無ければ ""。"""
    return f"（訳: {MISS}）" if MISS else ""


def _commit_at(clone, ver):
    return (_clone_git(clone, "rev-parse", "--verify", "-q", f"{ver}^{{commit}}") or b"").decode().strip()


def _installed_sha(plugins_dir, plugin_root, ver):
    """plugin の台帳（<plugins>/installed_plugins.json）で plugin_root に入った版の full sha（ver で始まる 40 桁）か ""。"""
    import json
    try:
        with open(os.path.join(plugins_dir, "installed_plugins.json"), encoding="utf-8") as f:
            rows = json.load(f).get("plugins") or {}
    except (OSError, ValueError, AttributeError):
        return ""
    want = os.path.realpath(plugin_root)
    for entries in rows.values() if isinstance(rows, dict) else ():
        for row in entries if isinstance(entries, list) else ():
            if not isinstance(row, dict) or os.path.realpath(str(row.get("installPath") or "")) != want:
                continue
            sha = str(row.get("gitCommitSha") or "")
            if re.fullmatch(r"[0-9a-f]{40}", sha) and sha.startswith(ver):
                return sha
    return ""


def _clone_git(clone, *args, timeout=10):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", clone, *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def foundation_file(rel, plugin_root):
    """土台の repo の根からの file（plugin の外・例 public-guard/guard.py）の、入った plugin と同じ版の path か ""。
    repo の形: plugins/<plugin> の 2 つ上が repo の根。
    入れた plugin の形: <plugins>/cache/<市場>/<plugin>/<版> → <plugins>/marketplaces/<市場>/（市場の取り出し＝repo 全体）。
    市場の取り出しの今の checkout は入った plugin と同じ版の時だけ読む（clone が先へ進んだ・古い clone が残った時に
    違う版の決まりで照らさない）。版が違えば、その版の中身を clone の歴史から取り出して読む（取り出せなければ ""
    ＝呼ぶ側が止めて名指しする）。版は cache の dir の名（commit の頭）。"""
    global MISS
    MISS = ""
    here = plugin_root
    cand = os.path.join(os.path.dirname(os.path.dirname(here)), rel)
    if os.path.isfile(cand):
        return cand
    market = os.path.dirname(os.path.dirname(here))
    cache = os.path.dirname(market)
    clone = os.path.join(os.path.dirname(cache), "marketplaces", os.path.basename(market))
    ver = os.path.basename(here)
    if not os.path.isdir(clone) or not re.fullmatch(r"[0-9A-Za-z._-]{1,64}", ver or ""):
        return _miss(f"{rel} が plugin の外に無く、市場の取り出し {clone} も無い（または版の名 {ver!r} が読めない）。"
                     "土台の plugin を市場から入れ直す")
    head = (_clone_git(clone, "rev-parse", "HEAD") or b"").decode().strip()
    if not head:
        return _miss(f"市場の取り出し {clone} が git として読めない（入った版と同じか分からない）。土台の plugin を市場から入れ直す")
    at = _commit_at(clone, ver)
    if not at:
        # 市場の取り出しは浅い clone（Claude Code が先端の 1 つだけを取る）で、入った版が先端と違うと歴史に無い。
        # 入った版の full sha（plugin の台帳 installed_plugins.json）を出所から取り寄せて同じ版を読む（窓の側の手を要さない）
        full = _installed_sha(os.path.dirname(cache), here, ver)
        if full:
            _clone_git(clone, "fetch", "--quiet", "--depth=1", "origin", full, timeout=60)
            at = _commit_at(clone, ver)
    if not at:
        shallow = (_clone_git(clone, "rev-parse", "--is-shallow-repository") or b"").decode().strip() == "true"
        return _miss(f"入った版 {ver} が市場の取り出し {clone} の歴史に無い"
                     + ("（浅い clone で、出所から入った版を取り寄せられなかった）" if shallow else "")
                     + f"。直し: git -C {clone} fetch --unshallow をしてから回し直す（出所へ届かない時は土台の plugin を市場から入れ直す）")
    cand = os.path.join(clone, rel)
    if at == head:
        return cand if os.path.isfile(cand) else _miss(f"入った版 {ver} の土台に {rel} が無い")
    body = _clone_git(clone, "show", f"{at}:{rel.replace(os.sep, '/')}")
    if body is None:
        return _miss(f"入った版 {ver} の土台に {rel} が無い（市場の取り出し {clone} の歴史から取り出せない）")
    out = os.path.join(tempfile.gettempdir(), "af-foundation-at", ver, rel)
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = f"{out}.{os.getpid()}"
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, out)
    except OSError as e:
        return _miss(f"入った版 {ver} の {rel} を一時の置き場へ書けない（{e.__class__.__name__}）")
    return out


def load_module(name, path):
    """path の .py を名前 name で読み込む（正本を写さず直に呼ぶ）。読めなければ例外。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
