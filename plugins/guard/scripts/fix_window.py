"""PreToolUse — 直す窓を立てる呼び出し（create_session）に、オーナーの答えの引用が無い・会話ログに無い物を止める。

意図: 窓が働くのはオーナーと合意した目標の中だけ。目標の外で見つけた穴は、終わりの報告の後にオーナーへ聞き、
「直して」と答えた物にだけ直す窓を立てる（オーナー決定 2026-11-22・細目 §3 原因の台帳・§7 報告の書き方）。
課題: 合意した目標（作り替え 1 つ）を AI が「台帳の全部」へ広げ、聞かずに直す窓を 10 以上立てた。止めてと言われた後も
窓が残った。
原因: 「台帳の全部の行に行き先を付けるまで終わらない」「直さないは AI が決めない」が重なり、AI が聞かずに付けられる
行き先が「直す窓を立てる」だけだった。立てる時に、誰がそれを頼んだかを照らす物が無かった。

止める物: create_session の頼みの文か題に「直す窓」が在り、次のどちらか。
  - 頼みの文に `オーナーの答え: 「…」` の行が無い。
  - 引いた「…」（4 字以上）が、会話ログのオーナーの打った行か選択肢の画面の答えに、そのままの字で無い（空白は詰めて比べる）。
通す物: 直す窓でない窓（並走の窓・レビューの窓）・助手の中・会話ログが読めない（見張りの故障で窓を止めない）。
残る穴: 頼みの文に「直す窓」と書かずに立てれば抜けられる（語の形の推し量り）。オーナーが合意した目標の文を引けば、
目標の中の直す窓として通る（目標の中の行は合意そのものが答え）。
"""
from __future__ import annotations

import json
import os
import re

import guard_common as G

HOOKS = {"pre": "check"}
MARK = "直す窓"
QUOTE = re.compile(r"オーナーの答え\s*[:：]\s*「([^」]{4,})」")
ASK_TOOL = "AskUserQuestion"


def _squash(text):
    return re.sub(r"\s+", "", str(text or ""))


def owner_words(tpath):
    """オーナーの打った行と選択肢の画面の答えを、空白を詰めて 1 本の字にする。"""
    asks, out = set(), []
    for row in G.iter_rows(tpath):
        msg = row.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if G.is_owner_row(row) and not G.seeded_by_record(row):
            out.append(G.text_of(row))
            continue
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") == ASK_TOOL:
                asks.add(b.get("id"))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in asks:
                c = b.get("content")
                out.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
        tr = row.get("toolUseResult")
        if isinstance(tr, dict) and isinstance(tr.get("answers"), dict):
            out.extend(str(v) for v in tr["answers"].values())
    return _squash("\n".join(out))


HOW = ("直し方: 目標の外で見つけた穴なら、直す窓を立てずに終わりの報告の後に穴ごとに「何が穴か／放っておくと何が起きうるか／"
       "AI の案」を添えて「どうしますか」と聞く（細目 §7「報告の書き方」）。オーナーが「直して」と答えた穴、または合意した目標の"
       "中の行なら、頼みの文に `オーナーの答え: 「<オーナーの言葉をそのまま>」` の行を書いて立て直す（細目 §3 原因の台帳）。")


def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if not str(data.get("tool_name") or "").endswith("create_session"):
        return ""
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return ""
    prompt = str(ti.get("prompt") or "")
    if MARK not in prompt and MARK not in str(ti.get("title") or ""):
        return ""
    tpath = str(data.get("transcript_path") or "")
    if not tpath or not os.path.isfile(tpath) or "/subagents/" in tpath.replace(os.sep, "/"):
        return ""
    quotes = QUOTE.findall(prompt)
    head = "[guard] 直す窓を立てる頼みに、それを頼んだオーナーの答えが照らせないので止めた（窓はまだ立っていない）。"
    if not quotes:
        return "\n".join([head, "頼みの文に `オーナーの答え: 「…」` の行が無い。", HOW])
    try:
        words = owner_words(tpath)
    except Exception:          # noqa: BLE001  会話ログが読めない＝見張りの故障。窓を止めない
        return ""
    missing = [q for q in quotes if _squash(q) not in words]
    if not missing:
        return ""
    return "\n".join([head, "引いた答えが、この窓のオーナーの打った行・選択肢の画面の答えに、そのままの字で無い: %s"
                      % "／".join("「%s」" % q[:40] for q in missing[:3]), HOW])
