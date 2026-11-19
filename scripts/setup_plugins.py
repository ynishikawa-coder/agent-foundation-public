#!/usr/bin/env python3
"""土台の plugin を全部入れる入口（使う側の環境の setup script が、土台の目録を足した後にこの 1 本を呼ぶ）。

使う側は plugin の名を写して持たない。入れる物は、この file と同じ checkout の配りの器
（`.claude-plugin/marketplace.json`）を直に読む。土台が plugin を足せば、次に立つ窓から黙って入る。

やる事:
  0. `claude plugin marketplace update <目録>` で目録の写し（この checkout）を main の先端へ進め、配りの器を読み直す。
     作り置きの容器では前の setup の目録の写しが残り、setup script の `marketplace add` は在る目録を足し直さない＝古いまま。
  1. 配りの器の plugin を全部 `claude plugin install <名>@<目録> --scope user` し、`claude plugin update` で追いつかせる。
  2. 入った commit（installed_plugins.json の gitCommitSha）を目録の写しの先端の commit と照らし、違う plugin は
     uninstall → install で入れ直す（入っているかでなく「どの commit か」で決める）。目録の写しが git でない
     （手元の dir から足した試し）時は照らせない＝印に書いて知らせは出さない（kaku.py の「比べられない」と同じ）。
  3. `claude plugin list --json` で、全部が user scope で enabled かを照らす。
  4. 入っていない・入れ直しても古い物があれば、窓が起動時に必ず読む `~/.claude/CLAUDE.md` に名指しの知らせを 1 行書く（全部揃えば消す）。
  5. この入口で入れた印を `~/.claude/af-foundation/setup.json` に書く（plugin core の起動の hook が、印の無い窓＝
     古い形の setup script で立った窓を名指しする）。

使い方（setup script の形は docs/核の届け方.md）: python3 <目録の checkout>/scripts/setup_plugins.py
  CLAUDE_BIN で claude の場所を差し替えられる（既定 claude）。
exit: 0=全部入って先端に揃った / 1=入っていない・古いままの物がある（知らせは書いた）/ 2=配りの器が読めない（知らせは書いた）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".claude-plugin" / "marketplace.json"
MARK = "<!-- af-plugin-missing -->"
STATE = "setup.json"  # plugin core の kaku.py が読む印の file 名（~/.claude/af-foundation/ の下）
ROOT_CAUSE = "直し: 入らない plugin を 1 つずつ入れ直すだけで済ませず、入らない形になった原因を細目 §3「まず構造を疑う」で探して直す"


def home() -> Path:
    return Path(os.environ.get("HOME") or "~").expanduser() / ".claude"


def catalog(manifest: Path = MANIFEST) -> tuple[str, list[str]]:
    """配りの器の (目録の名, plugin の名の並び)。読めない・空なら ValueError（黙って 0 本で進まない）。"""
    try:
        m = json.loads(manifest.read_text(encoding="utf-8"))
        name = m["name"]
        names = [p["name"] for p in m["plugins"]]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f"配りの器 {manifest} が読めない（{e}）") from e
    if not (isinstance(name, str) and name and names and all(isinstance(n, str) and n for n in names)):
        raise ValueError(f"配りの器 {manifest} に目録の名か plugin が無い")
    return name, names


def claude(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run([os.environ.get("CLAUDE_BIN") or "claude", *args], capture_output=True, text=True,
                              timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None


def enabled() -> set[str]:
    r = claude("plugin", "list", "--json")
    try:
        rows = json.loads(r.stdout) if r and r.returncode == 0 else []
    except ValueError:
        rows = []
    return {x.get("id") for x in rows if isinstance(x, dict) and x.get("scope") == "user" and x.get("enabled")}


def head_commit(root: Path = ROOT) -> str | None:
    """目録の写しの先端の commit。git でない・読めなければ None（照らせない）。"""
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and len(sha) == 40 else None


def installed_commits() -> dict[str, str]:
    """<plugin>@<目録> → user scope で入った commit（Claude Code の台帳 installed_plugins.json）。読めなければ空。"""
    base = Path(os.environ["CLAUDE_CONFIG_DIR"]) if os.environ.get("CLAUDE_CONFIG_DIR") else home()
    try:
        raw = json.loads((base / "plugins" / "installed_plugins.json").read_text(encoding="utf-8")).get("plugins") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    out = {}
    for k, recs in raw.items():
        for rec in recs if isinstance(recs, list) else []:
            if isinstance(rec, dict) and rec.get("scope", "user") == "user":
                out[k] = str(rec.get("gitCommitSha") or "")
    return out


def stale(names: list[str], market: str, head: str | None) -> list[str]:
    """入った commit が目録の写しの先端と違う plugin（入っていない物は数えない＝enabled の照らしが拾う）。"""
    if not head:
        return []
    got = installed_commits()
    return [n for n in names if f"{n}@{market}" in got and got[f"{n}@{market}"] != head]


def notice(text: str | None) -> None:
    """~/.claude/CLAUDE.md の知らせの行を替える（text が None なら消すだけ）。"""
    path = home() / "CLAUDE.md"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        old = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
        keep = [line for line in old if not line.startswith(MARK)]
        if text:
            if keep and not keep[-1].endswith("\n"):
                keep[-1] += "\n"
            keep.append(f"{MARK} {text}\n")
        path.write_text("".join(keep), encoding="utf-8")
    except OSError as e:
        print(f"✗ {path} に知らせを書けない: {e}", file=sys.stderr)


def save_state(state: dict) -> None:
    try:
        d = home() / "af-foundation"
        d.mkdir(parents=True, exist_ok=True)
        (d / STATE).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError as e:  # 印が無いと起動の hook が「古い形の setup script」と取り違えるので、書けなかった事を残す
        print(f"✗ 入れた印を書けない（起動の時に古い形と取り違えられる）: {e}", file=sys.stderr)


def main() -> int:
    try:
        market, names = catalog()
    except ValueError as e:
        notice(f"土台の plugin を入れられなかった: {e}。核と守りの hook がこの窓で効いていない。最初にオーナーへ知らせる。")
        print(f"✗ {e} {ROOT_CAUSE}")
        return 2
    claude("plugin", "marketplace", "update", market)  # 作り置きの容器に残った古い目録の写しを main の先端へ進める
    try:
        market, names = catalog()  # 進んだ写しの配りの器を読み直す（土台が足した plugin も入る）
    except ValueError as e:
        notice(f"土台の plugin を入れられなかった: {e}。核と守りの hook がこの窓で効いていない。最初にオーナーへ知らせる。")
        print(f"✗ {e} {ROOT_CAUSE}")
        return 2
    head = head_commit()
    for n in names:
        claude("plugin", "install", f"{n}@{market}", "--scope", "user")
        claude("plugin", "update", f"{n}@{market}")  # 前の setup で入った古い物を main の先端へ追いつかせる
    for n in stale(names, market, head):  # update が動かなくても、入った commit が先端と違えば入れ直す
        claude("plugin", "uninstall", f"{n}@{market}", "--scope", "user")
        claude("plugin", "install", f"{n}@{market}", "--scope", "user")
    old = stale(names, market, head)
    have = enabled()
    lack = [n for n in names if f"{n}@{market}" not in have]
    says = []
    if lack:
        says.append(f"土台の plugin が入っていない: {' '.join(lack)}（目録 {market}）。その plugin の決まりと守りの hook が"
                    "この窓で効いていない。")
    if old:
        says.append(f"土台の plugin が入れ直しても目録の先端（{head[:12]}）に揃わない: {' '.join(old)}（目録 {market}）。"
                    "その plugin は古い版の決まりと守りの hook で動く。")
    notice(" ".join(says) + "最初にオーナーへ知らせる。" if says else None)
    save_state({"entry": "scripts/setup_plugins.py", "market": market, "plugins": names, "missing": lack, "stale": old,
                "commit": head, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    bad = lack + [n for n in old if n not in lack]
    if not head:
        print("⚠ 目録の写しが git でない＝入った commit を照らせない（手元の dir から足した試し）")
    print(("✗ 入っていないか古い: " + " ".join(bad) + " " + ROOT_CAUSE) if bad else f"✅ 土台の plugin {len(names)} 本が入った")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
