#!/usr/bin/env python3
"""土台の plugin を全部入れる入口（使う側の環境の setup script が、土台の目録を足した後にこの 1 本を呼ぶ）。

使う側は plugin の名を写して持たない。入れる物は、この file と同じ checkout の配りの器
（`.claude-plugin/marketplace.json`）を直に読む。土台が plugin を足せば、次に立つ窓から黙って入る。

やる事:
  1. 配りの器の plugin を全部 `claude plugin install <名>@<目録> --scope user` し、`claude plugin update` で追いつかせる。
  2. `claude plugin list --json` で、全部が user scope で enabled かを照らす。
  3. 入っていない物があれば、窓が起動時に必ず読む `~/.claude/CLAUDE.md` に名指しの知らせを 1 行書く（全部入れば消す）。
  4. この入口で入れた印を `~/.claude/af-foundation/setup.json` に書く（plugin core の起動の hook が、印の無い窓＝
     古い形の setup script で立った窓を名指しする）。

使い方（setup script の形は docs/核の届け方.md）: python3 <目録の checkout>/scripts/setup_plugins.py
  CLAUDE_BIN で claude の場所を差し替えられる（既定 claude）。
exit: 0=全部入った / 1=入っていない物がある（知らせは書いた）/ 2=配りの器が読めない（知らせは書いた）
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
        print(f"✗ {e}")
        return 2
    for n in names:
        claude("plugin", "install", f"{n}@{market}", "--scope", "user")
        claude("plugin", "update", f"{n}@{market}")  # 前の setup で入った古い物を main の先端へ追いつかせる
    have = enabled()
    lack = [n for n in names if f"{n}@{market}" not in have]
    if lack:
        notice(f"土台の plugin が入っていない: {' '.join(lack)}（目録 {market}）。その plugin の決まりと守りの hook が"
               "この窓で効いていない。最初にオーナーへ知らせる。")
    else:
        notice(None)
    save_state({"entry": "scripts/setup_plugins.py", "market": market, "plugins": names, "missing": lack,
                "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    print(("✗ 入っていない: " + " ".join(lack)) if lack else f"✅ 土台の plugin {len(names)} 本が入った")
    return 1 if lack else 0


if __name__ == "__main__":
    sys.exit(main())
