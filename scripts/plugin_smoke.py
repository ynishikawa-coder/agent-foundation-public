#!/usr/bin/env python3
"""土台の plugin を、使う側と同じ入れ方で入れて窓を起動し、届く物が全部届くかを見る（CI の job `plugin-smoke`）。

土台は版で止めず main の先端をそのまま配る。合流した物は次に立つ全部の窓へ届くので、合流の前にここで
「入れる → 起動する → 核が差し込まれる・守りの hook が止める・skill が読み込まれる」を、使う側と同じ道で確かめる。

  python3 scripts/plugin_smoke.py --source <marketplace の出所> [--expect-sha SHA] [--repo DIR]

  --source      `claude plugin marketplace add` に渡す物。CI は使う側と同じ `<owner>/<repo>#<枝>`（GitHub から取る）、
                試験は作り物の dir。
  --expect-sha  入った commit がこれでなければ赤（PR の先端を試したかの証明）。
  --repo        「届くべき物」の正本を読む checkout（既定はこの repo）。plugin は plugins/*/.claude-plugin/plugin.json、
                skill は plugins/*/skills/*/SKILL.md、核は plugins/core/核.md を直に読む（写した一覧を持たない）。

窓は鍵なしで立てる（API の行き先を閉じた口にする）。起動の時の出来事（SessionStart の hook・入った plugin と skill の一覧）は
API を呼ぶ前に出るので、それを読んだら止める。お金はかからない。
exit: 0=緑 / 1=赤（届かない物がある）/ 2=道具が無い・起動できない（既定で赤）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKET = "agent-foundation"
KAKU_HEAD = "# 振る舞いの核（agent-foundation）"
# 守りの hook が止めるべき作り物の入力（試験の file から有料の上流の鍵を読む線）。guard の pre は必ず deny を返す。
ROOT_CAUSE = ("直し: 届かない物を 1 つずつ足し直すだけで済ませず、届かない形になった原因を細目 §3「まず構造を疑う」で探して直す"
              "（届くべき物は正本を直に読む形か・配りの器と正本が 2 つになっていないか）")
GUARD_PROBE = {"tool_name": "Write", "session_id": "smoke", "tool_input": {
    "file_path": "/smoke/tests/test_probe.py", "content": 'os.environ["OPENAI_API_KEY"]'}}


def expected(repo: Path) -> dict:
    plugins = sorted(p.parent.parent.name for p in repo.glob("plugins/*/.claude-plugin/plugin.json"))
    skills = sorted(f"{s.parent.parent.parent.name}:{s.parent.name}" for s in repo.glob("plugins/*/skills/*/SKILL.md"))
    hooks = sorted(p.parent.parent.name for p in repo.glob("plugins/*/hooks/hooks.json"))
    kaku = (repo / "plugins" / "core" / "核.md").read_text(encoding="utf-8").rstrip("\n")
    return {"plugins": plugins, "skills": skills, "hooks": hooks, "kaku": kaku}


DOC = "docs/核の届け方.md"
FOUNDATION = "ynishikawa-coder/agent-foundation-public"


def setup_block(repo: Path) -> str:
    """使う側が貼る setup script の塊（docs/核の届け方.md の `setup-script` の印の次の bash の塊）を正本から直に読む。"""
    text = (repo / DOC).read_text(encoding="utf-8")
    m = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", text, re.S)
    if not m or FOUNDATION not in m.group(1):
        raise ValueError(f"{DOC} に setup script の塊（印 setup-script の次の bash・{FOUNDATION} を足す行）が無い")
    return "\n".join(line.strip() for line in m.group(1).splitlines())


def sh(args, env, timeout=300):
    return subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout)


def start_session(env, cwd: Path, timeout: int = 120) -> list[dict]:
    """鍵なしの窓を 1 つ起動し、init の出来事までを読んで止める。"""
    args = ["claude", "-p", "smoke", "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--max-turns", "1"]
    p = subprocess.Popen(args, env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    events, end, buf = [], time.time() + timeout, ""
    try:
        while time.time() < end:
            r, _, _ = select.select([p.stdout], [], [], 1)
            if not r:
                if p.poll() is not None:
                    break
                continue
            line = p.stdout.readline()
            if not line:
                break
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            events.append(ev)
            if ev.get("type") == "system" and ev.get("subtype") == "init":
                break
    finally:
        p.kill()
        try:
            _, buf = p.communicate(timeout=10)
        except subprocess.SubprocessError:
            pass
    if not any(e.get("subtype") == "init" for e in events):
        raise RuntimeError("窓が起動の出来事（init）を出さなかった: " + (buf or "")[-500:])
    return events


def run_hook(command: str, root: Path, payload: dict, env) -> subprocess.CompletedProcess:
    """入った plugin の hooks.json に書かれた命令を、Claude Code と同じく CLAUDE_PLUGIN_ROOT を渡して回す。"""
    e = dict(env, CLAUDE_PLUGIN_ROOT=str(root))
    return subprocess.run(["bash", "-c", command], env=e, input=json.dumps(payload), capture_output=True,
                          text=True, timeout=60)


def smoke(source: str, repo: Path, expect_sha: str | None) -> list[str]:
    want = expected(repo)
    bad: list[str] = []
    with tempfile.TemporaryDirectory(prefix="af-smoke-") as tmp:
        home, proj = Path(tmp) / "home", Path(tmp) / "proj"
        home.mkdir()
        proj.mkdir()
        # 窓の外の設定・鍵を持ち込まない。API の行き先は閉じた口（呼べば落ちる＝お金はかからない）。
        env = {"HOME": str(home), "PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8",
               "ANTHROPIC_API_KEY": "sk-ant-smoke-dummy", "ANTHROPIC_BASE_URL": "http://127.0.0.1:9",
               "CLAUDE_PROJECT_DIR": str(proj), "DISABLE_AUTOUPDATER": "1"}
        for k in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
                  "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS", "GIT_SSL_CAINFO", "REQUESTS_CA_BUNDLE"):
            if k in os.environ:
                env[k] = os.environ[k]

        # 1. 使う側の setup script そのもの（docs/核の届け方.md の塊を、目録の repo だけ試す物に替えて回す）。
        script = setup_block(repo).replace(FOUNDATION, shlex.quote(source))
        r = sh(["bash", "-c", script], env, timeout=900)
        if r.returncode != 0:
            bad.append(f"setup script の塊が非 0 で抜けた（窓が起動しない）: {(r.stdout + r.stderr).strip()[-300:]}")
        note = home / ".claude" / "CLAUDE.md"
        for line in (note.read_text(encoding="utf-8").splitlines() if note.exists() else []):
            if line.startswith("<!-- af-plugin-missing -->"):
                bad.append(f"setup script が入れ損ねを知らせた: {line[len('<!-- af-plugin-missing -->'):].strip()[:300]}")
        if not (home / ".claude" / "af-foundation" / "setup.json").is_file():
            bad.append("setup script が土台の入口 scripts/setup_plugins.py を通っていない（入れた印が無い）")
        table = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8")
                           if (home / ".claude" / "plugins" / "installed_plugins.json").exists() else "{}")
        rows = {k.split("@")[0]: v[0] for k, v in (table.get("plugins") or {}).items() if v}
        if expect_sha:
            for name, row in rows.items():
                if row.get("gitCommitSha") != expect_sha:
                    bad.append(f"plugin {name} に入った commit {row.get('gitCommitSha')} が試したい先端 {expect_sha} でない")

        # 2. 起動する。
        try:
            events = start_session(env, proj)
        except (RuntimeError, OSError) as e:
            return bad + [f"窓を起動できない: {e}"]
        init = next(e for e in events if e.get("subtype") == "init")
        loaded = {p.get("source") for p in init.get("plugins") or []}
        for name in want["plugins"]:
            if f"{name}@{MARKET}" not in loaded:
                bad.append(f"plugin {name} が起動した窓に読み込まれていない")
        skills = set(init.get("skills") or []) | set(init.get("slash_commands") or [])
        for s in want["skills"]:
            if s not in skills:
                bad.append(f"skill {s} が起動した窓に読み込まれていない")

        # 3. 核の差し込み（SessionStart の hook の出力）。中身は正本の 核.md と一字違わず同じ。
        responses = [e for e in events if e.get("subtype") == "hook_response"]
        for e in responses:
            if e.get("exit_code") not in (0, None):
                bad.append(f"起動の hook {e.get('hook_name')} が落ちた: {(e.get('stderr') or '')[-200:]}")
        ctx = []
        for e in responses:
            try:
                ctx.append(json.loads(e.get("output") or "{}")["hookSpecificOutput"]["additionalContext"])
            except (ValueError, KeyError, TypeError):
                pass
        if not any(c.startswith(KAKU_HEAD) and want["kaku"] in c for c in ctx):
            bad.append("核が起動した窓に差し込まれていない（plugin core の SessionStart の hook）")

        # 4. 守りの hook: 入った copy の hooks.json に書かれた命令をそのまま回す。
        for name in want["hooks"]:
            root = Path(rows.get(name, {}).get("installPath") or "/nonexistent")
            hj = root / "hooks" / "hooks.json"
            if not hj.is_file():
                bad.append(f"plugin {name} の hooks.json が入った copy に無い")
                continue
            for event, groups in (json.loads(hj.read_text(encoding="utf-8")).get("hooks") or {}).items():
                for g in groups:
                    for h in g.get("hooks") or []:
                        res = run_hook(h.get("command", ""), root, {"session_id": "smoke", "hook_event_name": event}, env)
                        if res.returncode != 0:
                            bad.append(f"{name} の {event} の hook が落ちた（{h.get('command')}）: {res.stderr.strip()[-200:]}")
            if name == "guard":
                pre = [h["command"] for g in json.loads(hj.read_text(encoding="utf-8"))["hooks"].get("PreToolUse", [])
                       for h in g.get("hooks", [])]
                denied = False
                for c in pre:
                    res = run_hook(c, root, GUARD_PROBE, env)
                    try:
                        denied |= json.loads(res.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
                    except (ValueError, KeyError, TypeError):
                        pass
                if not denied:
                    bad.append("守りの hook（guard の PreToolUse）が止めるべき作り物の入力を止めない")
        if "guard" not in want["hooks"]:
            bad.append("plugin guard の hooks.json が正本に無い（守りの hook が届かない）")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True)
    ap.add_argument("--expect-sha")
    ap.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    if not shutil.which("claude"):
        print("plugin-smoke: 赤 claude の命令が無い（npm の @anthropic-ai/claude-code を入れる）")
        return 2
    try:
        bad = smoke(a.source, a.repo.resolve(), a.expect_sha)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"plugin-smoke: 赤 道具が動かない: {e}")
        return 2
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(f"plugin-smoke: 赤 ({len(bad)} 件)")
        print(ROOT_CAUSE)
        return 1
    print("plugin-smoke: 緑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
