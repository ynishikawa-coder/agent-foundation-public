#!/usr/bin/env python3
"""土台の plugin を、使う側と同じ入れ方で入れて窓を起動し、届く物が全部届くかを見る（CI の job `plugin-smoke`）。

土台は版で止めず main の先端をそのまま配る。合流した物は次に立つ全部の窓へ届くので、合流の前にここで
「入れる → 起動する → 核が差し込まれる・守りの hook が止める・skill が読み込まれる」を、使う側と同じ道で確かめる。

  python3 scripts/plugin_smoke.py --source <marketplace の出所> [--expect-sha SHA] [--repo DIR]

  --source      `claude plugin marketplace add` に渡す物。CI は使う側と同じ `<owner>/<repo>#<枝>`（GitHub から取る）、
                試験は作り物の dir。
  --expect-sha  入った commit がこれでなければ赤（PR の先端を試したかの証明）。
  --repo        「届くべき物」の正本を読む checkout（既定はこの repo）。plugin は plugins/*/.claude-plugin/plugin.json、
                skill は plugins/*/skills/*/SKILL.md、毎回差し込む物は plugins/core/scripts/kaku.py の injected()
                （差し込む口そのものが読む一覧）を直に読む（写した一覧・決め打ちの file 名を持たない）。

窓は鍵なしで立てる（API の行き先を閉じた口にする）。起動の時の出来事（SessionStart の hook・入った plugin と skill の一覧）は
API を呼ぶ前に出るので、それを読んだら止める。お金はかからない。
exit: 0=緑 / 1=赤（届かない物がある）/ 2=道具が無い・起動できない（既定で赤）
"""
from __future__ import annotations

import argparse
import importlib.util
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


def _kaku(repo: Path):
    """正本の repo の差し込む口 kaku.py（毎回別に読む＝片方の書き換えが他へ漏れない）。"""
    path = repo / "plugins" / "core" / "scripts" / "kaku.py"
    spec = importlib.util.spec_from_file_location("af_smoke_kaku", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"差し込む口が読めない: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def injected_texts(repo: Path) -> dict[str, str]:
    """毎回差し込む物 {file 名: 中身}。一覧は正本の repo の kaku.py の injected() をそのまま読む
    （差し込む口と照らす口が同じ 1 つの一覧を見る＝差し込む物を足しても照らしから漏れない）。"""
    path = repo / "plugins" / "core" / "scripts" / "kaku.py"
    files = tuple(_kaku(repo).injected())
    if not files:
        raise ValueError(f"差し込む物の一覧が空: {path}")
    return {f.name: f.read_text(encoding="utf-8").rstrip("\n") for f in files}


def expected(repo: Path) -> dict:
    plugins = sorted(p.parent.parent.name for p in repo.glob("plugins/*/.claude-plugin/plugin.json"))
    skills = sorted(f"{s.parent.parent.parent.name}:{s.parent.name}" for s in repo.glob("plugins/*/skills/*/SKILL.md"))
    hooks = sorted(p.parent.parent.name for p in repo.glob("plugins/*/hooks/hooks.json"))
    return {"plugins": plugins, "skills": skills, "hooks": hooks, "injected": injected_texts(repo),
            "inject": inject_pattern(repo)}


_SAIMOKU_MARK = "\x00細目の在り処\x00"


def inject_pattern(repo: Path) -> re.Pattern:
    """差し込む核の部（正本の kaku.py の inject_text() そのもの）に頭から一字違わず当たる形。入った copy ごとに違う細目の
    在り処だけを 1 行の中の任意の字にする（その字を印に揃えるのにも使う＝normalize）。"""
    mod = _kaku(repo)
    mod.SAIMOKU = Path(_SAIMOKU_MARK)
    head, sep, tail = mod.inject_text().partition(_SAIMOKU_MARK)
    return re.compile(re.escape(head) + (r"([^\n]+)" + re.escape(tail) if sep else ""))


def normalize(text: str, pattern: re.Pattern) -> str:
    """核の部の細目の在り処を印に揃えた text（核の部が正本どおりでなければそのまま）。"""
    m = pattern.match(text)
    if not m or not m.groups():
        return text
    return text[:m.start(1)] + _SAIMOKU_MARK + text[m.end(1):]


def expected_context(repo: Path, env: dict, cwd: Path, session_id: str) -> str:
    """正本の repo の差し込む口 kaku.py inject を、起動した窓と同じ箱（HOME・repo の根）と同じ窓の id で回した文脈の全体。
    同じ窓の 2 回目なので、起動の時の記録を読み外へは見に行かない＝起動した窓の hook と同じ材料で作る。"""
    p = subprocess.run([sys.executable, str(repo / "plugins" / "core" / "scripts" / "kaku.py"), "inject"],
                       input=json.dumps({"session_id": session_id, "hook_event_name": "SessionStart"}), env=env,
                       cwd=cwd, capture_output=True, text=True, timeout=120)
    try:
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        raise ValueError(f"正本の差し込む口が文脈を出さない: {(p.stdout + p.stderr).strip()[-300:]}") from None


def core_problems(ctx: list[str], want: dict, expected: str | None = None) -> list[str]:
    """起動の hook の文脈 ctx に、毎回差し込む物が正本と一字違わず届いたか。外れの名指し（空なら届いた）。
    expected（正本の差し込む口が同じ材料で出した文脈の全体）を渡せば、核の部だけでなく文脈の全体を一字違わず比べる
    （核の部の後ろに改行を挟んで足された文も外れ）。渡さなければ核の部を頭から比べ、その後ろは見ない。"""
    core = [c for c in ctx if c.startswith(KAKU_HEAD)]
    if not core:
        return ["核が起動した窓に差し込まれていない（plugin core の SessionStart の hook）"]
    pat = want["inject"]
    if expected is None:
        if any(pat.match(c) for c in core):
            return []
    elif any(normalize(c, pat) == normalize(expected, pat) for c in core):
        return []
    # 外れの時だけ、どの file が欠けたかを名指す（決めるのは上の全体の一致）
    lost = [name for name, text in want["injected"].items() if not any(text in c for c in core)]
    return ([f"{name} が起動した窓に差し込まれていない・中身が正本と違う（plugin core の SessionStart の hook）" for name in lost]
            or ["差し込まれた文が正本の差し込む口（kaku.py inject）の出す文と一字違わず同じでない（核・振る舞いの既定の前後か間に足された物がある）"])


def installed_rows(table: dict) -> dict[str, dict]:
    """入った台帳 installed_plugins.json の、土台の目録（MARKET）から入った plugin だけ {名: 行}。
    名だけで束ねると、同じ名の plugin を別の目録から入れた行と取り違える。"""
    rows = {}
    for key, v in (table.get("plugins") or {}).items():
        name, at, market = str(key).rpartition("@")
        if at and market == MARKET and v:
            rows[name] = v[0]
    return rows


DOC = "docs/核の届け方.md"
FOUNDATION = "ynishikawa-coder/agent-foundation-public"
# 土台の名を 1 つの語として見る（前後が名に使える字・道・版の印なら別の物＝fork や名を道に含む出所を取り違えない）
_NAME_EDGE = r"[\w.#/-]"
FOUNDATION_WORD = re.compile(rf"(?<!{_NAME_EDGE}){re.escape(FOUNDATION)}(?!{_NAME_EDGE})")
# add の前に付く旗（`--scope user` のように値を取る物も）を飛ばす。古い形.json の同じ行の読み方と同じ形にする
_ADD_FLAGS = r"(?:--?[\w-]+(?:[ =](?:user|project|local))?\s+)*"
_ADD = re.compile(r"\bmarketplace\s+add\s+" + _ADD_FLAGS + r"([^\s;|&]+)")


def marketplace_adds(script: str) -> list[str]:
    """setup script の `marketplace add` に渡す出所（囲みの引用符を外した語）の並び。"""
    return [m.group(1).strip("'\"") for m in _ADD.finditer(script)]


def script_for(block: str, source: str) -> str:
    """塊の土台の名（1 つの語として在る所だけ）を試す出所に替える。"""
    return FOUNDATION_WORD.sub(lambda _m: shlex.quote(source), block)
# クラウドの窓の道具 update_environment が setup script を運べる上限（1 行のバイト数は改行を除く）。超える行があると
# AI の窓が環境に貼れない（2026-11-19 に 207・317 バイトの行で貼れず、人の手で貼った）。
LINE_BYTES, MAX_LINES = 200, 100


def over_limits(script: str) -> list[str]:
    """setup script が道具の上限を超える所を名指す（空なら収まる）。"""
    lines = script.splitlines()
    bad = [f"{i} 行目が {n} バイト（上限 {LINE_BYTES}）" for i, n in
           ((i, len(s.encode("utf-8"))) for i, s in enumerate(lines, 1)) if n > LINE_BYTES]
    if len(lines) > MAX_LINES:
        bad.append(f"{len(lines)} 行（上限 {MAX_LINES}）")
    return bad


def setup_block(repo: Path) -> str:
    """使う側が貼る setup script の塊（docs/核の届け方.md の `setup-script` の印の次の bash の塊）を正本から直に読む。"""
    text = (repo / DOC).read_text(encoding="utf-8")
    m = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", text, re.S)
    block = "\n".join(line.strip() for line in m.group(1).splitlines()) if m else ""
    if FOUNDATION not in marketplace_adds(block):
        raise ValueError(f"{DOC} に setup script の塊（印 setup-script の次の bash・{FOUNDATION} をそのまま足す"
                         f" marketplace add の行）が無い")
    bad = over_limits(block)
    if bad:
        raise ValueError(f"{DOC} の setup script の塊が道具（update_environment）の上限を超え、AI の窓が貼れない: " + "・".join(bad))
    return block


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

        # 1. 使う側の setup script そのもの（docs/核の届け方.md の塊を、目録の repo だけ試す物に替えて、set -e の下で回す）。
        script = script_for(setup_block(repo), source)
        r = sh(["bash", "-ec", script], env, timeout=900)  # 貼る先が set -e でも抜けない
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
        rows = installed_rows(table)
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

        # 3. 毎回差し込む物（SessionStart の hook の出力）。injected() の一覧の全部が、正本と一字違わず同じ中身で届く。
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
        try:
            expect = expected_context(repo, env, proj, str(init.get("session_id") or "smoke"))
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            return bad + [f"正本の差し込む口を回せない: {e}"]
        bad += core_problems(ctx, want, expect)

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
