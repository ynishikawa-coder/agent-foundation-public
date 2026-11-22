"""土台の在り処探しの 1 本の口（plugin の外の土台の file・隣の plugin の file を、入った plugin と同じ版で探して読む）。

土台の plugin は市場から入ると cache/<市場>/<plugin>/<版> に置かれ、repo の根の物（public-guard/guard.py など）は
plugin の中に無い。正本を写さず直に読むために、どの plugin もここ 1 か所で探す（各 plugin の lib/ へは symlink で届く）。
plugin_root は呼ぶ plugin の根（repo の形では plugins/<plugin>・入れた形では cache/<市場>/<plugin>/<版>）。
"""
from __future__ import annotations

import os
import re
import tempfile


def sibling_plugin_file(plugin, rel, plugin_root):
    """隣の plugin の file の path か ""。正本を写さず直に読むための在り処探し。
    repo の形: plugins/<呼ぶ plugin> と plugins/<plugin> が隣。
    入れた plugin の形: cache/<市場>/<呼ぶ plugin>/<版> と cache/<市場>/<plugin>/<同じ版>。
    同じ版だけを見る（別の版へ降りない＝正本と呼ぶ plugin の版が食い違ったまま照らさない。見つからなければ "" で、
    呼ぶ側が止めて「同じ版で入れ直す」と名指しする）。"""
    here = plugin_root
    cand = os.path.join(os.path.dirname(here), plugin, rel)
    if os.path.isfile(cand):
        return cand
    ver = os.path.basename(here)
    market = os.path.dirname(os.path.dirname(here))
    same = os.path.join(market, plugin, ver, rel)
    return same if os.path.isfile(same) else ""


def _clone_git(clone, *args):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", clone, *args], capture_output=True, timeout=10)
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
    here = plugin_root
    cand = os.path.join(os.path.dirname(os.path.dirname(here)), rel)
    if os.path.isfile(cand):
        return cand
    market = os.path.dirname(os.path.dirname(here))
    cache = os.path.dirname(market)
    clone = os.path.join(os.path.dirname(cache), "marketplaces", os.path.basename(market))
    ver = os.path.basename(here)
    if not os.path.isdir(clone) or not re.fullmatch(r"[0-9A-Za-z._-]{1,64}", ver or ""):
        return ""
    head = (_clone_git(clone, "rev-parse", "HEAD") or b"").decode().strip()
    at = (_clone_git(clone, "rev-parse", "--verify", "-q", f"{ver}^{{commit}}") or b"").decode().strip()
    if not head or not at:
        return ""  # 入った版が clone の歴史に無い・clone が git でない＝同じ版か分からない
    cand = os.path.join(clone, rel)
    if at == head:
        return cand if os.path.isfile(cand) else ""
    body = _clone_git(clone, "show", f"{at}:{rel.replace(os.sep, '/')}")
    if body is None:
        return ""
    out = os.path.join(tempfile.gettempdir(), "af-foundation-at", ver, rel)
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = f"{out}.{os.getpid()}"
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, out)
    except OSError:
        return ""
    return out


def load_module(name, path):
    """path の .py を名前 name で読み込む（正本を写さず直に呼ぶ）。読めなければ例外。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
