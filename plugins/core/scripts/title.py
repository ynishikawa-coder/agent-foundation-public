#!/usr/bin/env python3
"""窓の題の知らせ（plugin core・UserPromptSubmit の hook・止めない）。

意図: 人が立てた窓も AI が立てた窓も、一覧で題を見れば種類と状態が分かる（細目 §4「窓の題」）。
課題: 2026-11-23 に窓の見張り（plugin session-watch）を畳んだ後、人が立てた窓の題に印が付かなくなった。
原因: 題の決まりを細目（窓が自分で読みに行く文）にだけ置き、毎回の頼みで AI に知らせる口が無くなった。
  AI が立てる窓は立てる時に題を渡す決まりが別に在るので付き続け、人が立てた窓だけが抜けた。
形: クラウドの窓（題の道具 set_session_title を持つ窓）で、頼みが来た時に会話の記録を読み、
  - まだ題を付けていない → 種類と状態の印を付けるよう知らせる
  - 前の返事の 1 行目の札（✅／❓／💤／🛑）と、最後に付けた題の状態が食い違う → 付け替えるよう知らせる
  どちらでもなければ何も出さない。知らせるだけで止めない。読めない・壊れた時は何も出さない（窓を止めない）。
表の正本は細目 §4「窓の題」（ここは知らせる時に要る印だけを持つ）。秘密は読まない（読むのは会話の記録だけ）。
"""
from __future__ import annotations

import json
import os
import re
import sys

TOOL = "set_session_title"
HUMAN, HAND, AI = "🙋", "✋", "🤖"
KINDS = (HUMAN, HAND, AI)
STATES = ("❓", "💤", "🛑", "✅")
VS16 = "️"
# 返事の 1 行目の札（核 §5）。札の絵と題の状態の絵は同じ。
CARD = re.compile(r"^[#>*\s]*(✅ ?終わった|❓ ?答えて|💤 ?待ち|🛑 ?止まった)(?=$|[\s。、:：（(])")

FORM = ("形は `<種類><状態> <作業名>`。種類は 🙋（オーナーと話す窓）・✋（オーナーの操作を頼む手の窓）・"
        "🤖（AI が立てて AI に返す窓）。状態は 無し（動いている）・❓（オーナーの答え待ち）・💤（ほかの窓・CI 待ち）・"
        "🛑（止まった）・✅（終わった）で、✋ には ✅ だけ付ける。返事の 1 行目の札を変えたら、同じ返事の中で題の状態も"
        "同じ絵へ付け替える。後継が引き取っただけなら ✅ にせず、作業名に「｜引き継ぎ済み」を残す（細目 §4「窓の題」）。")
UNTITLED = ("[core] この窓ではまだ `mcp__claude-code-remote__set_session_title` に成功した記録がない（立てた時に付いた題は"
            "会話の記録に出ないので、ここからは見えない）。この返事の中で `get_session` を session_id を省いて読み、今の題に"
            "印が無ければ付け、在っても同じ題で 1 回 `set_session_title` を呼ぶ（成功が記録に残ると、この知らせは止まる。"
            "`parent_session_id` が無ければ人が立てた窓＝🙋、在れば別の窓が立てた窓＝🤖）。" + FORM)
MISMATCH = ("[core] 前の返事の札は「%s」なのに、最後に付けた題は「%s」で状態が合っていない。この返事の終わりに、"
            "返事の札と同じ状態へ `mcp__claude-code-remote__set_session_title` で題を付け替える。" + FORM)


def split(title: str):
    """題を (種類, 状態) に分ける。種類が無ければ (None, None)。状態が無ければ ''（動いている）。"""
    t = str(title or "").strip()
    for k in KINDS:
        if t.startswith(k):
            rest = t[len(k):].lstrip(VS16)
            for s in STATES:
                if rest.startswith(s):
                    return k, s
            return k, ""
    return None, None


def rows(path: str):
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def blocks(row: dict) -> list:
    c = (row.get("message") or {}).get("content")
    return c if isinstance(c, list) else ([{"type": "text", "text": c}] if isinstance(c, str) else [])


def read(path: str):
    """(最後に付けた題, 前の返事の 1 行目の札の絵)。無ければ None。
    前の返事＝本文を書いた最後のターンの、最後の道具より後ろの本文（途中の実況は返事に数えない）。"""
    title, last, cur = None, [], []
    pending = {}
    for row in rows(path):
        kind = row.get("type")
        if kind == "user" and not row.get("isMeta"):
            bs = [b for b in blocks(row) if isinstance(b, dict)]
            for b in bs:
                if b.get("type") != "tool_result":
                    continue
                name = pending.pop(b.get("tool_use_id"), None)
                if name is not None and not b.get("is_error"):
                    title = name
            if bs and not any(b.get("type") == "tool_result" for b in bs):
                last, cur = (cur or last), []   # 人の頼みでターンが替わる
        elif kind == "assistant":
            for b in blocks(row):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    cur = []
                    if str(b.get("name", "")).endswith(TOOL) and b.get("id"):
                        name = (b.get("input") or {}).get("title")
                        if isinstance(name, str) and name.strip():
                            pending[b["id"]] = name
                elif b.get("type") == "text" and b.get("text"):
                    cur.append(b["text"])
    text = "\n".join(cur or last)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    m = CARD.match(first)
    return title, (m.group(1)[0] if m else None)


def note(data: dict, env=None) -> str | None:
    env = os.environ if env is None else env
    if str(env.get("CLAUDE_CODE_REMOTE", "")).strip().lower() != "true":
        return None   # 題の道具はクラウドの窓だけ
    path = data.get("transcript_path")
    title, card = read(path) if path and os.path.isfile(path) else (None, None)
    kind, state = split(title)
    if kind is None:
        return UNTITLED
    if kind == HAND or card is None:
        return None   # 手の窓の状態は 無し・✅ だけ・札の無い一言の返事は照らさない
    if card != state:
        return MISMATCH % (card, title)
    return None


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        text = note(data)
    except Exception:
        return 0   # 壊れても窓を止めない
    if text:
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
