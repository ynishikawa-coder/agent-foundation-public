"""値の表（config/skill-values.json）を、どの道具・どの書き方で書いても、知らない鍵を残せば道具の後に知らされるか（注入の試験）。

前の形は Write・Edit・MultiEdit だけを照らし、Bash の書き換え（sed -i・リダイレクト・python -c）では知らない鍵を残せた。
今の形は書き方の字の形を並べない: 道具の前（PreToolUse）に値の表の中身を控え、道具の後（PostToolUse）に中身で比べる。
ここでは本当に命令を走らせて値の表を書き換え、前と後の hook を回す。入力は全部作り物。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "plugins" / "guard" / "scripts" / "guard.py"
今の表 = {"guard": {"context_limit": 1000}, "dev-flow": {"preimpl-cleanup": {"ledger": "1 行ずつ"}}}


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    (p / "config").mkdir(parents=True)
    (p / "config" / "skill-values.json").write_text(json.dumps(今の表, ensure_ascii=False, indent=1), encoding="utf-8")
    (tmp_path / "scratch").mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(p), "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(tmp_path / "scratch")})
    return p, e


def hook(env, event, payload):
    p = subprocess.run([sys.executable, str(GUARD), event], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = p.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else {}


def tool(proj, cmd, tool_name="Bash", tid="t1", post=True):
    """AI の道具 1 回: 前の hook → 命令を本当に走らせる → 後の hook（post=False は道具が失敗して後の hook が来ない形）。"""
    p, env = proj
    payload = {"session_id": "s1", "tool_use_id": tid, "tool_name": tool_name, "cwd": str(p),
               "tool_input": {"command": cmd}}
    pre = hook(env, "pre", {**payload, "hook_event_name": "PreToolUse"})
    assert pre.get("permissionDecision") != "deny", pre
    subprocess.run(cmd, shell=True, cwd=p, check=False, env=env)
    if not post:
        return ""
    return hook(env, "post", {**payload, "hook_event_name": "PostToolUse"}).get("additionalContext", "")


# 知らない鍵を足す書き方（並べる網ではなく、どの書き方でも同じ照らしになる事を見る見本）。
足す = {
    "sed -i": "sed -i 's/\"context_limit\": 1000/\"context_limit\": 1000, \"zz_old_key\": 1/' config/skill-values.json",
    "リダイレクト": "echo '{\"guard\": {\"zz_old_key\": 1}}' > config/skill-values.json",
    "python -c": "python3 -c \"import json;p='config/skill-values.json';t=json.load(open(p));"
                 "t['dev-flow']['preimpl-cleanup']['zz_old_key']=1;json.dump(t,open(p,'w'))\"",
    "cp": "printf '%s' '{\"common\": {\"zz_old_key\": 1}}' > \"$TMPDIR/x.json\" && cp \"$TMPDIR/x.json\" config/skill-values.json",
    "tee": "echo '{\"guard\": {\"zz_old_key\": 1}}' | tee config/skill-values.json >/dev/null",
}


@pytest.mark.parametrize("how", list(足す))
def test_どの書き方で知らない鍵を残しても道具の後に戻すよう知らせる(proj, how):
    ctx = tool(proj, 足す[how])
    assert "zz_old_key" in ctx and "元へ戻す" in ctx, (how, ctx)


def test_Bash_でない道具が書いても同じ照らし(proj):
    ctx = tool(proj, 足す["python -c"], tool_name="mcp__作り物__write_file")
    assert "zz_old_key" in ctx


def test_値の表に触れない道具と_知っている鍵だけの書き換えは知らせない(proj):
    assert tool(proj, "echo hello > other.txt") == ""
    assert tool(proj, "sed -i 's/1000/2000/' config/skill-values.json", tid="t2") == ""


def test_前から在る知らない鍵は_触れない道具では知らせず_減らす書き換えは通す(proj):
    p, _ = proj
    (p / "config" / "skill-values.json").write_text(
        json.dumps({"guard": {"context_limit": 1, "zz_a": 1, "zz_b": 2}}), encoding="utf-8")
    assert tool(proj, "echo hello > other.txt") == ""
    drop = "python3 -c \"import json;p='config/skill-values.json';t=json.load(open(p));t['guard'].pop('zz_a');json.dump(t,open(p,'w'))\""
    assert tool(proj, drop, tid="t2") == ""
    keep = "sed -i 's/\"context_limit\": 1/\"context_limit\": 2/' config/skill-values.json"
    assert "zz_b" in tool(proj, keep, tid="t3")      # 知らない鍵を残したまま他を書き換える＝Write・Edit の止めと同じ線


def test_道具が失敗して後の_hook_が来なくても_次の道具の後に知らせる(proj):
    assert tool(proj, 足す["sed -i"] + " && false", tid="t1", post=False) == ""
    assert "zz_old_key" in tool(proj, "echo hello > other.txt", tid="t2")


def test_知らせは直すまで続き_戻すと止む(proj):
    assert "zz_old_key" in tool(proj, 足す["sed -i"], tid="t1")
    assert "zz_old_key" in tool(proj, "echo hello > other.txt", tid="t2")
    back = "sed -i 's/, \"zz_old_key\": 1//' config/skill-values.json"
    assert tool(proj, back, tid="t3") == ""
    assert tool(proj, "echo hello > other.txt", tid="t4") == ""


def test_壊れた_JSON_にする書き換えも知らせる(proj):
    assert "JSON として読めない" in tool(proj, "echo '{ 壊れた' > config/skill-values.json")


def test_値の表が無い所で知らない鍵の値の表を作っても知らせる(proj):
    p, _ = proj
    (p / "config" / "skill-values.json").unlink()
    assert "zz_old_key" in tool(proj, 足す["リダイレクト"])


def test_守りの宣言は前と後の両方で回る():
    import ast
    tree = ast.parse((ROOT / "plugins/guard/scripts/values_keys.py").read_text(encoding="utf-8"))
    hooks = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 and any(getattr(t, "id", "") == "HOOKS" for t in n.targets))
    assert hooks.get("pre") == "check" and hooks.get("post") == "after"
