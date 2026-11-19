#!/usr/bin/env python3
"""核を窓の起動時に差し込む口と、常に読まれる量の上限を照らす口（plugin core の道具はこの 1 本）。

使い方:
  python3 kaku.py inject              SessionStart の hook が呼ぶ。核（同じ plugin の 核.md）と振る舞いの既定
                                      （振る舞い.md）を窓の文脈へ毎回差し込み、形の細目（細目.md）の在り処を知らせる。開いた repo の根の CLAUDE.md に
                                      写しの枠（AF-CORE:BEGIN）がまだ在る時は、核が二重に入らないよう差し込まない。
                                      あわせて、窓の最初の 1 回だけ、入った土台が main の先端と同じかを見て窓ごとに覚える（古ければ知らせる）。
  python3 kaku.py fresh               UserPromptSubmit の hook が呼ぶ。起動の後に main の先端の plugin が変わったら、
                                      この窓を新しい窓へ引き継いで閉じるよう AI に知らせる（人の作業は止めない）。
  python3 kaku.py check [--claude P]  核と振る舞いの既定が在り、上限の内かを照らす。--claude を渡すと、その CLAUDE.md（写しの枠が在れば
                                      枠の外だけ）が各社固有の上限の内かも照らす。
  python3 kaku.py grow --base REF     増やさない物（guarded() の一覧＝毎回差し込む物と形の細目）が git の REF の時より
                                      増えていないかを照らす。足すなら同じ変更で同じだけ畳む（上限の内で足し続けて満杯にしない）。
exit: inject と fresh は何が起きても 0（窓の起動も人の作業も止めない）。check・grow は 0=緑 / 1=越えた・増えた / 2=読めない。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
KAKU = PLUGIN / "核.md"
FURUMAI = PLUGIN / "振る舞い.md"
SAIMOKU = PLUGIN / "細目.md"
FRAME_BEGIN = "<!-- AF-CORE:BEGIN"
FRAME_END = "<!-- AF-CORE:END -->"
# 越えた時の最後の行（中身は細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: 文を移して量を合わせるだけで済ませず、決まりが増えた原因を細目 §3「まず構造を疑う」で探して畳む"
# 常に読まれる量の上限（バイト・UTF-8）。数はここの 1 か所だけに置く。
LIMITS = {"核": 4800, "振る舞い": 2400, "各社固有": 3000}
MARKET = "agent-foundation"
# 土台の振る舞いを運ぶ path。ここが変わった時だけ「古い土台」と見る（文書・試験・CI だけの変更では窓を替えない）。
CARRIERS = ("plugins", ".claude-plugin")
FRESH_INTERVAL = 900  # 起動の後に main の先端を見に行く間（秒）。毎回の問いごとに外へ出ない。


# 読めない時の類（無い・権限・UTF-8 でない中身）を 1 か所で受ける。どの読みもこれで受け、欠けを名指しする。
UNREADABLE = (OSError, UnicodeDecodeError)


def size(text: str) -> int:
    return len(text.encode("utf-8"))


def has_frame(claude_md: Path) -> bool:
    try:
        return FRAME_BEGIN in claude_md.read_text(encoding="utf-8")
    except UNREADABLE:
        return False


def outside_frame(text: str) -> str:
    """写しの枠が在れば枠の外だけを返す（移る間の repo の各社固有を測るため）。"""
    if FRAME_BEGIN not in text or FRAME_END not in text:
        return text
    head, rest = text.split(FRAME_BEGIN, 1)
    return head + rest.split(FRAME_END, 1)[1]


def injected() -> tuple[Path, ...]:
    """毎回差し込む物の一覧（差し込む inject と増え方を照らす grow が同じこの 1 つを読む）。頭の核は欠けたら差し込まない。"""
    return (KAKU, FURUMAI)


def guarded() -> tuple[Path, ...]:
    """増やさない物の一覧＝毎回差し込む物と、核から押し出した物の行き先の細目（細目だけ照らさないと押し出した物がそこで膨らむ）。"""
    return (*injected(), SAIMOKU)


def inject_text() -> str:
    head, *rest = injected()
    parts = [head.read_text(encoding="utf-8").rstrip("\n")]
    for path in rest:
        try:
            parts.append(path.read_text(encoding="utf-8").rstrip("\n"))
        except UNREADABLE as e:
            # 欠けたまま黙って核だけにしない: 窓の起動は止めず、欠けた事を文脈に名指しで出す
            print(f"plugin core: {path.name} が読めない（{e}）", file=sys.stderr)
            parts.append(f"（毎回差し込む {path} が読めず、差し込まれていない。最初にオーナーへ知らせる）")
    return ("\n\n".join(parts) + "\n\n"
            + "（この核と振る舞いの既定は土台の plugin core が起動時に差し込んだ。"
            + f"返事・問い・手の窓などの形の細目は {SAIMOKU} の同じ番号の節。その形を書く時に Read する）\n")


# ── 土台の新しさ（入っている物と main の先端を比べる） ──

def _home() -> Path:
    return Path(os.environ.get("HOME") or "~").expanduser() / ".claude"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _git(loc: str, *args: str, timeout: int = 20) -> str | None:
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=off", "-C", loc, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def installed_sha() -> str | None:
    """この窓に入った plugin core の commit（入れた時に Claude Code が書く台帳から）。"""
    table = _read_json(_home() / "plugins" / "installed_plugins.json") or {}
    rows = (table.get("plugins") or {}).get(f"core@{MARKET}") or []
    for row in rows:
        if Path(row.get("installPath") or "/nonexistent").resolve() == PLUGIN:
            return row.get("gitCommitSha")
    return rows[0].get("gitCommitSha") if len(rows) == 1 else None


def freshness() -> dict | None:
    """{installed, main, plugins}（plugins が空でなければ古い）。比べられない時は None。

    GitHub から入れた時だけ見る（手元の dir から入れた試し・CI は main の先端と比べる物が無い）。
    main の先端は、入れた時の marketplace の clone へ main だけを取って来て比べる（鍵は要らない・public）。"""
    m = (_read_json(_home() / "plugins" / "known_marketplaces.json") or {}).get(MARKET) or {}
    loc = m.get("installLocation")
    if (m.get("source") or {}).get("source") != "github" or not loc:
        return None
    have = installed_sha()
    if not have or _git(loc, "fetch", "--quiet", "--depth=1", "origin", "main") is None:
        return None
    tip = _git(loc, "rev-parse", "FETCH_HEAD")
    if not tip:
        return None
    if tip == have:
        return {"installed": have, "main": tip, "plugins": []}
    names = _git(loc, "diff", "--name-only", have, tip, "--", *CARRIERS)
    if names is None:      # 入った commit が clone に無い＝比べられないが先端とは違う。古いと見る（既定で知らせる側）
        plugins = ["（どれか分からない）"]
    else:
        plugins = sorted({n.split("/")[1] if n.startswith("plugins/") and n.count("/") >= 2 else n.split("/")[0]
                          for n in names.splitlines() if n})
    return {"installed": have, "main": tip, "plugins": plugins}


def _state_path(session: str) -> Path:
    safe = "".join(c for c in session if c.isalnum() or c in "-_") or "unknown"
    return _home() / "af-foundation" / f"{safe}.json"


def _save_state(session: str, state: dict) -> None:
    try:
        path = _state_path(session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _hook_input() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _short(f: dict) -> str:
    return f"入った土台 {f['installed'][:12]}・main の先端 {f['main'][:12]}・変わった plugin: {'・'.join(f['plugins'])}"


def stale_at_start_text(f: dict) -> str:
    return ("## 土台が古いまま立った窓 — setup script を直してから引き継いで閉じる\n"
            f"この窓は main の先端より古い土台で立った（{_short(f)}）。setup script が版（tag）を指している・入れ損ねている"
            "ので、直さずに立て直しても同じ物が入る。この返事では頼みに手を付けず次をする（人の作業は新しい窓で止まらず続く・🙋 の窓も同じ）:\n"
            "1. 環境の setup script を土台の docs/核の届け方.md の形（main の先端を入れる）に直す: "
            "claude-code-remote の get_environment → update_environment（直せる環境の時）。\n"
            "2. 直せた時は、手の中の変更を push し、create_session で同じ repo・同じ環境に新しい窓を立てて引き継ぎ文"
            "（元の頼み・済んだ事・枝と PR・未決・次の 1 手・窓の題と「古い土台の窓からの引き継ぎ」の 1 行）を渡し、"
            "人と親の窓へ新しい窓の URL を返し、archive_session で自分の窓を閉じる。\n"
            "3. 直せない時（他のアカウントの環境・道具が無い・この窓自身が「古い土台の窓からの引き継ぎ」で立った）は引き継がず、"
            "UTC の環境なら連絡板の issue で setup script の直しを頼み、オーナーへ「核と守りが古い形で動いている」と 1 行知らせてから頼みを続ける。\n")


def handover_text(f: dict) -> str:
    return ("## 土台が新しくなった — この窓を引き継いで閉じる\n"
            f"この窓が立った後に、土台の main の先端で窓の振る舞いが変わった（{_short(f)}）。"
            "この窓は古い核と守りで動いているので、この返事では頼みに手を付けず次をする（人の作業は新しい窓で止まらず続く・🙋 の窓も同じ）:\n"
            "1. 手の中の変更を枝へ commit・push する。\n"
            "2. claude-code-remote の create_session で、同じ repo・同じ環境に新しい窓を立てる。prompt は引き継ぎ文: "
            "元の頼み（オーナーの原文）・ここまでに済んだ事・枝と PR・未決の問い・次の 1 手・窓の題と、「古い土台の窓からの引き継ぎ」の 1 行。\n"
            "3. 人へ 1 行で新しい窓の URL を返す。親の窓がある時は親へも send_message で URL を知らせる。\n"
            "4. archive_session で自分の窓を閉じる。\n"
            "窓を立てる道具が無い時（手元の CLI 等）は、人へ「土台が新しくなった・新しい窓で続けてほしい」と 1 行知らせてから頼みを続ける。\n")


def inject() -> int:
    data = _hook_input()
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    parts = []
    if not has_frame(project / "CLAUDE.md"):  # 写しの枠が在る repo は CLAUDE.md が核を持つ＝差し込まない（二重を避ける）
        try:
            parts.append(inject_text())
        except UNREADABLE as e:
            print(f"plugin core: 核.md が読めない（{e}）＝核は差し込まれていない", file=sys.stderr)
    session = data.get("session_id")
    state = _read_json(_state_path(session)) if session else None
    if isinstance(state, dict):
        # 同じ窓の 2 回目（文脈の圧縮・/clear・resume）: 起動の時の記録を書き直さない（途中で古くなった窓を
        # 「起動の時から古い」と取り違えて引き継ぎを消さない）。外へも見に行かない。
        f = state.get("start") if state.get("stale_at_start") else None
    else:
        try:
            f = freshness()
        except Exception:  # noqa: BLE001  新しさの見張りが壊れても核の差し込みは止めない
            f = None
        if session:
            _save_state(session, {"checked": time.time(), "stale_at_start": bool(f and f["plugins"]),
                                  "comparable": f is not None, "start": f})
    if f and f["plugins"]:
        parts.append(stale_at_start_text(f))
    if parts:
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(parts)}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


def fresh() -> int:
    """起動の後に土台が新しくなったかを見る。新しくなっていれば、引き継いで閉じる手順を AI に知らせる。

    起動の時から古かった窓（setup script が古い物を入れた）はここでは扱わない（inject の知らせが setup script を直してから引き継がせる）。"""
    data = _hook_input()
    session = data.get("session_id")
    if not session:
        return 0
    path = _state_path(session)
    state = _read_json(path)
    if not isinstance(state, dict) or state.get("stale_at_start") or not state.get("comparable"):
        return 0
    f = state.get("seen")
    if not f:
        interval = float(os.environ.get("AF_FRESH_INTERVAL") or FRESH_INTERVAL)
        if time.time() - float(state.get("checked") or 0) < interval:
            return 0
        try:
            got = freshness()
        except Exception:  # noqa: BLE001
            got = None
        state["checked"] = time.time()
        if got and got["plugins"]:
            state["seen"] = f = got
        _save_state(session, state)
    if f:  # 一度見つけたら、引き継ぐまで問いのたびに知らせる（外へは出ない）
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": handover_text(f)}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


def check(claude: Path | None) -> int:
    bad = []
    try:
        n = size(KAKU.read_text(encoding="utf-8"))
    except UNREADABLE as e:
        print(f"✗ 核.md が読めない: {e}")
        return 2
    if n > LIMITS["核"]:
        bad.append(f"核（{KAKU.name}）が上限を越えた: {n} > {LIMITS['核']} バイト（細目へ移す）")
    try:
        f = size(FURUMAI.read_text(encoding="utf-8"))
    except UNREADABLE as e:
        print(f"✗ 振る舞い.md が読めない: {e}")
        return 2
    if f > LIMITS["振る舞い"]:
        bad.append(f"振る舞いの既定（{FURUMAI.name}）が上限を越えた: {f} > {LIMITS['振る舞い']} バイト（癖と逆を求めない物を細目へ移す）")
    if claude is not None:
        try:
            m = size(outside_frame(claude.read_text(encoding="utf-8")))
        except UNREADABLE as e:
            print(f"✗ {claude} が読めない: {e}")
            return 2
        if m > LIMITS["各社固有"]:
            bad.append(f"各社固有（{claude}）が上限を越えた: {m} > {LIMITS['各社固有']} バイト（その repo の文書へ移す）")
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(ROOT_CAUSE)
        return 1
    print("✅ 量の上限 緑")
    return 0


# 増やさない物（guarded＝毎回差し込む物と細目）。足す時は同じ変更で同じだけ畳む（上限の内でも純増は赤）。
GROW_FIX = "直し: 足すなら同じ変更で同じだけ畳む（重複を細目・skill の正本へ寄せる）。量を合わせるだけで済ませず、細目 §3「まず構造を疑う」で増えた原因から畳む"


def base_text(ref: str, path: Path) -> str:
    """git の ref の時の中身。読めない（ref が無い・その時に file が無い）時は OSError で止める。"""
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path.parent, capture_output=True, text=True)
    if top.returncode != 0:
        raise OSError(f"git の外: {top.stderr.strip()}")
    rel = path.resolve().relative_to(Path(top.stdout.strip()).resolve()).as_posix()
    r = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=path.parent, capture_output=True)
    if r.returncode != 0:
        raise OSError(f"{ref}:{rel} が読めない: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout.decode("utf-8")


def grow(ref: str) -> int:
    bad = []
    for path in guarded():
        try:
            now = size(path.read_text(encoding="utf-8"))
            before = size(base_text(ref, path))
        except UNREADABLE as e:
            # 比べる元が無い時に黙って緑にしない（既定で止める）
            print(f"✗ {path.name} の増え方を照らせない: {e}")
            return 2
        if now > before:
            bad.append(f"{path.name} が {ref} より増えた: {before} → {now} バイト（+{now - before}）")
        else:
            print(f"・{path.name}: {before} → {now} バイト")
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(GROW_FIX)
        return 1
    print("✅ 毎回差し込む物と細目は増えていない")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="核の差し込みと量の上限の照らし")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inject", help="SessionStart の hook から呼ぶ")
    sub.add_parser("fresh", help="UserPromptSubmit の hook から呼ぶ")
    c = sub.add_parser("check", help="量の上限を照らす")
    c.add_argument("--claude", type=Path, help="照らす repo の根の CLAUDE.md")
    g = sub.add_parser("grow", help="毎回差し込む物と細目が REF より増えていないかを照らす")
    g.add_argument("--base", required=True, help="比べる元の git の ref（例: main との分かれ目）")
    a = ap.parse_args(argv)
    if a.cmd == "inject":
        return inject()
    if a.cmd == "grow":
        return grow(a.base)
    if a.cmd == "fresh":
        return fresh()
    return check(a.claude)


if __name__ == "__main__":
    sys.exit(main())
