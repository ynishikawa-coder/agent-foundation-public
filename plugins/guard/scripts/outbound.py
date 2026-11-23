"""PreToolUse — 人や他の窓へ渡る道具の入力を、出る前に照らす。崩れていれば AI の呼び出しだけを止めて書き直させる。

意図: 秘密を出さない（核 §1）を、外へ渡す前に照らす
（オーナー同意 2026-11-19: 文で知らせるだけで、AI が読み飛ばすとそのままオーナーに届く所は、AI だけ止めて書き直させてよい）。
止まるのは AI の呼び出しだけ。人の操作は何も止めない。
課題: 鍵が他の窓・PR・Notion へ渡った。
原因: これらの決まりは文で知らせるだけで、AI が読み飛ばすと照らす物が無かった。

照らす物（見分けはどれも正本を直に呼ぶ＝写さない）:
  secret  … MCP の道具（名が mcp__ で始まる物）・Artifact・SendMessage の入力の全部の字と、Artifact で出す file の中身に、
            鍵・トークンの形がある。形の正本は公開の検査（public-guard/guard.py の SECRET_PATTERNS）。
            見つからない時は止める（照らせない物は外へ出さない）。在り処は AF_PUBLIC_GUARD → 土台の repo の根 → 市場の取り出し。
            大きすぎる（MAX_READ 超）・開けない file は「照らした」扱いにせず、出した後（PostToolUse の notice）に名と訳を知らせる
            （止めに変えるかはオーナーの同意待ち）。
誤って止めた時: 値の表 config/skill-values.json の "guard" の outbound_secret_allow（当たった字の塊の全体に当てる正規表現・各行 ^…$・
作り物の見本だけ）で外す。値の表は PR とレビューを通る＝窓の一存では外れない。
"""
from __future__ import annotations

import os
import re

import guard_common as G

HOOKS = {"pre": "check", "post": "notice"}

SEND_TOOLS = ("SendMessage",)
MAX_READ = 2_000_000          # Artifact で出す file を照らす上限（バイト）
MAX_STRINGS = 2000


# ── 正本の在り処 ──
def _public_guard():
    path = os.environ.get("AF_PUBLIC_GUARD") or G.foundation_file(os.path.join("public-guard", "guard.py"))
    if not path or not os.path.isfile(path):
        raise RuntimeError("見つからない" + G.miss_note())
    return G.load_module("af_public_guard", path)


# ── secret ──
def _strings(v, where="", out=None):
    """入力の中の字を (場所, 字) で全部。"""
    out = [] if out is None else out
    if len(out) >= MAX_STRINGS:
        return out
    if isinstance(v, str):
        out.append((where or "入力", v))
    elif isinstance(v, dict):
        for k, x in v.items():
            _strings(x, "%s.%s" % (where, k) if where else str(k), out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _strings(x, "%s[%d]" % (where, i), out)
    return out


def _artifact_files(ti, data):
    """Artifact の publish で出る手元の file（file_path・file_paths・files の元）。"""
    paths = []
    fp = ti.get("file_path")
    if isinstance(fp, str):
        paths.append(_resolve(fp, data))
    for p in ti.get("file_paths") or []:
        if isinstance(p, str):
            paths.append(_resolve(p, data))
    files = ti.get("files")
    root = ti.get("root") if isinstance(ti.get("root"), str) else ""
    items = []
    if isinstance(files, dict):
        for src in files.values():
            if isinstance(src, str):
                items.append(src)
            elif isinstance(src, dict) and isinstance(src.get("from"), str):
                items.append(src["from"])          # {artifact, path} は別の Artifact の物＝ここでは読めない
    elif isinstance(files, list):
        items = [f.get("path") for f in files if isinstance(f, dict) and isinstance(f.get("path"), str)]
    for src in items:
        if root and not os.path.isabs(os.path.expanduser(src)):
            src = os.path.join(root, src)
        paths.append(_resolve(src, data))
    return paths


def _resolve(path, data):
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        base = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        path = os.path.join(base, path)
    return path


def _unreadable(path):
    """Artifact で出す file を照らせない訳（照らせれば ""）。大きすぎる・開けない物を「照らした」扱いにしない。"""
    try:
        size = os.path.getsize(path)
        if size > MAX_READ:
            return "大きすぎる（%d バイト・照らす上限 %d バイト）" % (size, MAX_READ)
        with open(path, "rb"):
            pass
    except OSError as e:
        return "開けない（%s）" % (e.strerror or e.__class__.__name__)
    return ""


def unread_files(data):
    """[(path, 訳)]。Artifact の publish で出す file のうち、鍵の形を照らせない物。"""
    ti = data.get("tool_input")
    if str(data.get("tool_name") or "") != "Artifact" or not isinstance(ti, dict):
        return []
    return [(p, why) for p, why in ((p, _unreadable(p)) for p in _artifact_files(ti, data)) if why]


def secret_hits(data, vals, pg, unread=None):
    """[(場所, 札)]。当たった字そのものは返さない（止めた文にも鍵を出さない）。
    照らせなかった file は黙って飛ばさず、unread（渡されれば）に (path, 訳) で積む。"""
    ti = data.get("tool_input")
    texts = _strings(ti)
    if str(data.get("tool_name") or "") == "Artifact" and isinstance(ti, dict):
        for path in _artifact_files(ti, data):
            why = _unreadable(path)
            if not why:
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        texts.append(("file %s" % path, f.read()))
                    continue
                except OSError as e:
                    why = "開けない（%s）" % (e.strerror or e.__class__.__name__)
            if unread is not None:
                unread.append((path, why))
    if G.SV.bad_pattern_rows(vals.get("outbound_secret_allow") or []):
        raise re.error("outbound_secret_allow に読めない形")   # 外す形が壊れたら鍵を外さず照らせないと止める
    allow = G.patterns(vals, "outbound_secret_allow")
    hits = []
    for where, text in texts:
        for label, pat in pg.SECRET_PATTERNS.items():
            for m in re.finditer(pat, text):
                if G.SV.hit(allow, m.group(0)) is not None:
                    continue
                if (where, label) not in hits:
                    hits.append((where, label))
                break
    return hits


def check_secret(data, vals):
    name = str(data.get("tool_name") or "")
    if not (name.startswith("mcp__") or name in ("Artifact",) + SEND_TOOLS):
        return ""
    try:
        pg = _public_guard()
    except Exception as e:      # noqa: BLE001
        pg, err = None, str(e)
    else:
        err = ""
    if pg is None:
        return ("[guard] 外へ渡す道具の入力の鍵を照らせないので、出す前に止めた（照らせない物は外へ出さない）。\n"
                "  鍵の形の正本 public-guard/guard.py が見つからない／読めない%s。\n"
                "  直し方: 土台の plugin を市場（marketplace）から入れ直す。手元の置き場が違う時は環境変数 AF_PUBLIC_GUARD に"
                " guard.py の path を入れる。" % ((": " + err) if err else ""))
    unread = []
    hits = secret_hits(data, vals, pg, unread)
    if not hits:
        return ""
    lines = ["[guard] 外へ渡す道具（%s）の入力に鍵・認証情報の形があるので、出す前に止めた（核 §1・オーナー同意 2026-11-19・"
             "人の操作は止めていない）。" % name]
    lines += ["- %s に %s の形" % (w, label) for w, label in hits[:8]]
    lines.append("直し方: 鍵の値を文から抜き、「<鍵の名> は環境の秘密に入れた」のように名だけで書いて出し直す。鍵が要る相手には"
                 "値を渡さず、環境の秘密（request_credential）で渡す。Artifact の file に入っていれば file から抜く。")
    lines += unread_lines(unread)
    lines.append("誤って止めた時（作り物の見本の字が形に当たった等）: 値の表の guard.outbound_secret_allow に、その字に当てる"
                 "正規表現を足す（PR とレビューを通す）。鍵の型は skill-values/schema.json の guard.outbound_secret_allow。")
    return "\n".join(lines)



def unread_lines(unread):
    if not unread:
        return []
    out = ["- 照らせなかった file（鍵が無いと確かめていない）:"]
    out += ["  - %s — %s" % (p, why) for p, why in unread[:8]]
    if len(unread) > 8:
        out.append("  - （ほか %d 件）" % (len(unread) - 8))
    return out


def notice(data, vals):
    """PostToolUse: Artifact で出した file に、鍵の形を照らせなかった物があれば名と訳を知らせる（止めない＝止めに変えるかは
    オーナーの同意を待つ）。照らせなかった file を「照らした」扱いで黙って通さない。"""
    unread = unread_files(data)
    if not unread:
        return ""
    lines = ["[guard] Artifact で出した file のうち、鍵・認証情報の形を照らせなかった物がある（知らせるだけ・止めていない。"
             "照らせた物だけを照らした）:"]
    lines += unread_lines(unread)[1:]
    lines.append("直し方: その file に鍵が無いかを自分で確かめる（大きすぎる物は分けるか小さくして出し直す・開けない物は path と"
                 "権限を直して出し直す）。鍵が入っていれば file から抜き、出した Artifact を出し直す。")
    return "\n".join(lines)


def check(data, vals):
    """止めるなら理由、通すなら ""。照らせない時は止める（照らせない物は外へ出さない）。"""
    outs = []
    try:
        outs.append(check_secret(data, vals))
    except Exception as e:      # noqa: BLE001
        outs.append("[guard] 外へ渡す道具の入力の鍵を照らせないので、出す前に止めた（照らせない物は外へ出さない）: %s\n"
                    "  直し方: 値の表の guard.outbound_secret_allow の正規表現が崩れていないか見る。土台の plugin を市場から"
                    "入れ直す。" % type(e).__name__)
    return "\n\n".join(o for o in outs if o)
