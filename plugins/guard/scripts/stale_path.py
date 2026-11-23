"""stale_path（古い版の skill の本文・path を読んだ時の知らせ）: PostToolUse で知らせるだけ（止めない）。

意図: 窓の途中で土台が先端の版へ入れ直されても、AI が先端の版の skill の本文・雛形に従う。
課題: Claude Code は skill の一覧と ${CLAUDE_PLUGIN_ROOT} を窓が立った時の版の dir で持ち続け、窓の途中で入れ直しても
  替えない。script は入口で先端の版へ乗り換える（lib/af_place.py の run_newest）が、AI が読む skill の本文・雛形・
  参照の file は古い版のまま読まれ、合流した直しが効かなかった。
形: 道具を使った後に、
  - Skill を呼んだ: その skill の窓が立った時の版の SKILL.md と、入った台帳の今読まれる行の版の SKILL.md が違えば、
    先端の版の path を名指して「こちらを Read して従う」と知らせる（先端の版に skill が無ければ、畳まれたと知らせる）。
  - 道具の入力に入った plugin の置き場の path（…/plugins/cache/<目録>/<plugin>/<版>/…）が在り、その版が台帳の今読まれる
    行の版でなければ、先端の版の同じ path を名指す。
  どの版が今読まれるかの決め方の正本は目録の clone の plugins/core/scripts/hook_run.py の newest_dir（写さない）。
  止めない（古い版を読む手を止めるのは新しい「止める」決まり＝オーナーの同意が要る）。何か壊れたら黙って通す。
"""
import json
import os
import re

import guard_common as G

HOOKS = {"post": "notice"}

STARTED_ENV = "AF_HOOK_STARTED_ROOT"   # hook_run が残す、窓が立った時の版の dir（無ければ CLAUDE_PLUGIN_ROOT）
_PATH = re.compile(r"(/[^\s\"'`<>|;&()]*?/plugins/cache/[^/\s\"'`]+/[^/\s\"'`]+/[^/\s\"'`]+)(/[^\s\"'`<>|;&()]*)?")
LIMIT = 5


def _hook_run(cache_root):
    """cache_root（…/plugins/cache/<目録>）に対応する目録の clone の hook_run の module か None。"""
    market = os.path.basename(cache_root)
    plugins = os.path.dirname(os.path.dirname(cache_root))
    path = os.path.join(plugins, "marketplaces", market, "plugins", "core", "scripts", "hook_run.py")
    if not os.path.isfile(path):
        return None
    try:
        return G.load_module("af_guard_hook_run", path)
    except Exception:  # noqa: BLE001
        return None


def _newer(ver_dir):
    """ver_dir（…/cache/<目録>/<plugin>/<版>）の (先端の版の dir, ver_dir) か None（同じ版・置き場の形でない・引けない）。"""
    cache_root = os.path.dirname(os.path.dirname(ver_dir))
    hr = _hook_run(cache_root)
    if hr is None:
        return None
    try:
        root, new_root = hr.newest_dir(os.path.join(ver_dir, "_"))  # 版の dir の中の path で引く
    except Exception:  # noqa: BLE001
        return None
    if root is None or new_root is None or str(new_root) == str(root):
        return None
    return str(new_root), str(root)


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def skill_line(data, env=None):
    """Skill を呼んだ時: 窓が読んだ本文の版が先端でなければ 1 文。"""
    env = os.environ if env is None else env
    if data.get("tool_name") != "Skill":
        return ""
    name = str((data.get("tool_input") or {}).get("skill") or "")
    if ":" not in name:
        return ""
    plugin, skill = name.split(":", 1)
    started = env.get(STARTED_ENV) or env.get("CLAUDE_PLUGIN_ROOT") or ""
    if not started:
        return ""
    ver = os.path.basename(os.path.normpath(started))
    market_dir = os.path.dirname(os.path.dirname(os.path.normpath(started)))
    rel = os.path.join("skills", skill, "SKILL.md")
    old = os.path.join(market_dir, plugin, ver, rel)
    if not os.path.isfile(old):
        return ""
    got = _newer(os.path.join(market_dir, plugin, ver))
    if not got:
        return ""
    new_root, root = got
    new = os.path.join(new_root, rel)
    if not os.path.isfile(new):
        return (f"[guard] skill {name} は窓が立った時の版（{os.path.basename(root)}）で読まれたが、入れ直した先端の版"
                f"（{os.path.basename(new_root)}）にこの skill が無い（畳まれた）。先端の版の {new_root} の skills/ と"
                " CHANGELOG を見て、今の道を選び直す（知らせるだけ・止めていない）。")
    if _read(new) == _read(old):
        return ""
    return (f"[guard] skill {name} の本文は窓が立った時の版（{os.path.basename(root)}）。土台は先端の版"
            f"（{os.path.basename(new_root)}）へ入れ直されていて本文が違う。{new} を Read して、そちらに従う"
            "（skill から呼ぶ script は自分で先端の版へ乗り換える。知らせるだけ・止めていない）。")


def path_lines(data):
    """道具の入力に先端でない版の置き場の path があれば、先端の版の同じ path を名指す文の並び。"""
    try:
        text = json.dumps(data.get("tool_input") or {}, ensure_ascii=False)
    except (TypeError, ValueError):
        return []
    out, seen = [], set()
    for m in _PATH.finditer(text):
        ver_dir, rest = m.group(1), (m.group(2) or "")
        if (ver_dir, rest) in seen:
            continue
        seen.add((ver_dir, rest))
        got = _newer(ver_dir)
        if not got:
            continue
        new_root, _ = got
        new = new_root + rest
        tail = "" if not rest or os.path.exists(new) else "（先端の版にこの file は無い＝畳まれたか名が変わった）"
        out.append(f"  {ver_dir}{rest} → {new}{tail}")
        if len(out) >= LIMIT:
            break
    if not out:
        return []
    return ["[guard] 先端でない版の土台の置き場を使った（窓が立った時の版の path。土台は先端の版へ入れ直されている）。"
            "続きは先端の版の path を使う（知らせるだけ・止めていない）:"] + out


def notice(data, vals):
    lines = [x for x in [skill_line(data)] if x] + path_lines(data)
    return "\n".join(lines)
