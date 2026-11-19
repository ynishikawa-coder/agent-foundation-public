"""PreToolUse — 問いのページ（確認ページ）を Artifact で出す前に、qa-html の検査（check.mjs）をかけ、赤なら止める。

なぜ在るか: 型（qa-html の template.html）と検査を通らない独自の確認ページが、前に答えた問い・調べれば分かる問い・
道具の都合をそのまま問いにした物をオーナーに出した。宛先がオーナーでも、ページで聞くなら同じ型と検査を当てる
（オーナー同意 2026-11-17）。

見る物: Artifact の publish（action が無いか "publish"・asset の上げは除く）で、file_path が .html か .json の時だけ。
問いのページの見分け（誤検知を少なくするため、どれか 1 つが要る）:
  HTML: ① 型の印（<body data-dest="send|copy|artifact">・CustomEvent('qa:submit')）
        ② 選ぶ問い（radio）と、答えを外へ出す仕組み（form・qa:submit・sendPrompt・window.claude の書く呼び出し・POST 等の fetch・clipboard への書き込み）の両方
           （読むだけの fetch や表示の切り替えの radio は数えない）
        ③ <script id="state"> などの JSON に、問いの並び（qs・questions）で、選択肢（options・choices）を持つ物
  JSON: 問いの並び（questions・qs）で、選択肢を持つ物（Artifact 型へ渡す問いのデータ）
検査が走らない（check.mjs が見つからない・node が無い・検査が壊れた）時も止める＝緑を確かめられない物は出さない。
  check.mjs の在り処: 環境変数 AF_QA_CHECK → 同じ repo の plugins/docs-kit → 入れた plugin の docs-kit（同じ版を先に）。
問いのページでないのに止まる時は、repo の値の表 guard.qa_page_exempt（file の path に当てる正規表現の並び）で外す
（値の表は PR とレビューを通るので、窓の中の一存では外れない）。
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess

PAGE_EXT = (".html", ".htm", ".json")
TIMEOUT = 30
RED_SHOWN = 12

QA_SUBMIT = r"CustomEvent\s*\(\s*[\"']qa:submit[\"']"
TYPE_MARK = re.compile(r"<body\b[^>]*\bdata-dest\s*=\s*[\"']?(?:send|copy|artifact)\b|" + QA_SUBMIT, re.I)
RADIO = re.compile(r"""type\s*[=:]\s*\\?["']?radio\b|["']radio["']""", re.I)
# 答えを外へ出す仕組みだけ（読むだけの fetch・window.claude の読み・表示の切り替えは数えない）
SENDER = re.compile(
    r"<form\b|" + QA_SUBMIT + r"|\bsendPrompt\s*\("
    r"|window\.claude\.(?:\w+\.)*(?:send|submit|ask|prompt|set|write|save|update|add|put|insert|append)\w*\s*\("
    r"|\bmethod\s*:\s*[\"'](?:POST|PUT|PATCH)[\"']|navigator\.clipboard\.write",
    re.I)
JSON_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.I | re.S)
Q_KEYS = ("questions", "qs")
OPT_KEYS = ("options", "choices", "opts")


def _has_question_list(data, depth=0):
    """問いの並び（questions・qs）で、選択肢を持つ問いが 1 つでもあるか。入れ子は 3 段まで見る。"""
    if depth > 3:
        return False
    if isinstance(data, dict):
        for k in Q_KEYS:
            qs = data.get(k)
            if isinstance(qs, list) and any(isinstance(q, dict) and any(isinstance(q.get(o), list) and q.get(o) for o in OPT_KEYS) for q in qs):
                return True
        return any(_has_question_list(v, depth + 1) for v in data.values() if isinstance(v, (dict, list)))
    if isinstance(data, list):
        return any(_has_question_list(v, depth + 1) for v in data if isinstance(v, (dict, list)))
    return False


def why_question_page(path, raw):
    """問いのページなら見分けた理由（1 行）、違えば ""。"""
    if path.lower().endswith(".json"):
        try:
            return "問いのデータ（questions／qs に選択肢）" if _has_question_list(json.loads(raw)) else ""
        except ValueError:
            return ""
    if TYPE_MARK.search(raw):
        return "確認ページの型の印（data-dest・CustomEvent('qa:submit')）"
    for attrs, body in JSON_SCRIPT.findall(raw):
        if "json" in attrs.lower() or re.search(r"\bid\s*=\s*[\"']?state\b", attrs, re.I):
            try:
                if _has_question_list(json.loads(body.strip())):
                    return "ページに埋めた問いのデータ（<script> の JSON に questions／qs と選択肢）"
            except ValueError:
                pass
    if RADIO.search(raw) and SENDER.search(raw):
        return "選ぶ問い（radio）と答えを外へ出す仕組みの両方"
    return ""


def find_check(guard_root=None):
    """check.mjs の path か ""。"""
    env = os.environ.get("AF_QA_CHECK") or ""
    if env:
        return env if os.path.isfile(env) else ""
    here = guard_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rel = os.path.join("skills", "qa-html", "check.mjs")
    # repo の形: plugins/guard と plugins/docs-kit が隣
    cand = os.path.join(os.path.dirname(here), "docs-kit", rel)
    if os.path.isfile(cand):
        return cand
    # 入れた plugin の形: cache/<市場>/guard/<版> と cache/<市場>/docs-kit/<版>。同じ版を先に、無ければ新しい物
    ver = os.path.basename(here)
    market = os.path.dirname(os.path.dirname(here))
    same = os.path.join(market, "docs-kit", ver, rel)
    if os.path.isfile(same):
        return same
    found = sorted(glob.glob(os.path.join(market, "docs-kit", "*", rel)), key=os.path.getmtime, reverse=True)
    return found[0] if found else ""


def _resolve(path, data):
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        base = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        path = os.path.join(base, path)
    return path


def reason(path, why, lines, chk=""):
    return (
        "問いのページ（確認ページ）が qa-html の検査を通っていないので、Artifact に出すのを止めました。\n"
        "  出そうとした file: {}\n"
        "  問いのページと見た訳: {}\n"
        "{}\n"
        "直し方（skill guard:guard-rules の qa_page・docs-kit:qa-html）:\n"
        "  ① まず聞く前に引く: 決定の記録と問いの表を同じ言葉で引き、答え済み・資料で決まる・道具の都合の問いは消す（細目 §4）\n"
        "  ② オーナーへの問いなら選択肢の画面（AskUserQuestion）で聞く。ページで出すなら qa-html の型（template.html）を写して作り直す\n"
        "  ③ node {} {} が緑の物だけを publish する（赤の行を 1 つずつ潰すかは、止めた文の最後の行の入口から決める）"
    ).format(path, why, "\n".join(lines), chk or "<qa-html の check.mjs>", path)


def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if str(data.get("tool_name") or "") != "Artifact":
        return ""
    ti = data.get("tool_input")
    if not isinstance(ti, dict) or ti.get("asset"):
        return ""
    if str(ti.get("action") or "publish") != "publish":
        return ""
    fp = ti.get("file_path")
    if not isinstance(fp, str) or not fp.lower().endswith(PAGE_EXT):
        return ""
    path = _resolve(fp, data)
    for pat in vals.get("qa_page_exempt") or []:
        if isinstance(pat, str) and pat and re.search(pat, path.replace(os.sep, "/")):
            return ""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return ""          # 読めない file は Artifact の道具の側が断る
    why = why_question_page(path, raw)
    if not why:
        return ""
    chk = find_check()
    node = shutil.which("node")
    if not chk:
        return reason(path, why, ["  検査（docs-kit の qa-html の check.mjs）が見つからず、緑を確かめられない。plugin docs-kit を入れる（または AF_QA_CHECK に path）"])
    if not node:
        return reason(path, why, ["  node が無く、検査（check.mjs）を走らせられない。node を入れる"], chk)
    try:
        p = subprocess.run([node, chk, path, "--json"], capture_output=True, text=True, timeout=TIMEOUT,
                           cwd=os.path.dirname(path))
    except (OSError, subprocess.SubprocessError) as e:
        return reason(path, why, ["  検査が走らなかった: %s" % e], chk)
    if p.returncode == 0:
        return ""
    try:
        res = json.loads(p.stdout)
        red = [str(r) for r in res.get("red") or []]
    except ValueError:
        red = []
    if p.returncode != 1 or not red:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-3:]
        return reason(path, why, ["  検査が壊れた（exit %d）: %s" % (p.returncode, " / ".join(tail))], chk)
    lines = ["  検査の赤 %d 件:" % len(red)]
    lines += ["    ✗ " + r for r in red[:RED_SHOWN]]
    if len(red) > RED_SHOWN:
        lines.append("    …ほか %d 件（全部は node %s %s で出る）" % (len(red) - RED_SHOWN, chk, path))
    return reason(path, why, lines, chk)
