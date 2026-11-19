"""guard の page_check（docs-kit の型のページを出す前に型の検査）・ledger_row（原因の台帳の行の形）と、
見張りが壊れたまま main に入らない事（注入の試験）。入力は全部作り物。"""
import ast
import importlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

from test_guard import ROOT, denied, env, hook  # noqa: F401  （fixture と手伝い）

SCRIPTS = ROOT / "plugins" / "guard" / "scripts"
SKILLS = ROOT / "plugins" / "docs-kit" / "skills"


# ── 見張りが壊れたまま入らない（入口は実行の時に壊れを飲んで他を走らせるので、壊れは試験で拒む）──
def declared():
    out = []
    for p in sorted(SCRIPTS.glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in tree.body:
            if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "HOOKS" for t in n.targets):
                out += [(p.stem, ev, fn) for ev, fn in ast.literal_eval(n.value).items()]
    return out


def test_宣言した見張りは全部_import_でき関数が在る():
    assert declared()
    sys.path.insert(0, str(SCRIPTS))
    try:
        for mod, ev, fn in declared():
            m = importlib.import_module(mod)
            assert callable(getattr(m, fn, None)), f"{mod}.{fn}（{ev}）が無い＝入口が黙って飛ばす"
    finally:
        sys.path.remove(str(SCRIPTS))


def test_壊れた見張りはこの試験が拒む(tmp_path):
    """注入: import で壊れる見張りと、宣言した関数の無い見張りを置くと、上の試験の見方で拾う。"""
    d = tmp_path / "s"
    shutil.copytree(SCRIPTS, d, ignore=shutil.ignore_patterns("__pycache__"))
    (d / "zz_broken.py").write_text('HOOKS = {"pre": "check"}\nraise ImportError("作り物の故障")\n', encoding="utf-8")
    (d / "zz_nofunc.py").write_text('HOOKS = {"pre": "check_not_here"}\n', encoding="utf-8")
    sys.path.insert(0, str(d))
    try:
        with pytest.raises(ImportError):
            importlib.import_module("zz_broken")
        assert not callable(getattr(importlib.import_module("zz_nofunc"), "check_not_here", None))
    finally:
        sys.path.remove(str(d))
        for k in ("zz_broken", "zz_nofunc"):
            sys.modules.pop(k, None)


# ── page_check ──
def _find_chrome():
    """型の検査と同じ探し方（検査の find_chrome を直に呼ぶ＝試験の側で Chrome の在り処を写さない）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_bp_chrome", SKILLS / "blueprint" / "scripts" / "check_blueprint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.find_chrome()


CHROME = _find_chrome()
needs_chrome = pytest.mark.skipif(not CHROME, reason="Chrome が無い（型の検査は headless の Chrome で動く）")


def publish(path, **kw):
    return {"tool_name": "Artifact", "session_id": "s1", "tool_input": {"file_path": str(path), **kw}}


def broken(s):
    """注入: 型の中身の飛び先の 1 つを、どの段・画面にも無い id へ替える（型の検査が赤にする形）。"""
    out = re.sub(r"go\('(s12|r1)'", "go('zz_nai'", s, count=1)
    assert out != s
    return out


def page(tmp_path, kind, edit=None, name="p.html"):
    s = (SKILLS / kind / "references" / "template.html").read_text(encoding="utf-8")
    if edit:
        s = edit(s)
    p = tmp_path / name
    p.write_text(s, encoding="utf-8")
    return p


@needs_chrome
@pytest.mark.parametrize("kind", ["blueprint", "theory-mock"])
def test_page_check_型どおりのページは通す(env, tmp_path, kind):
    out = hook(env, "pre", publish(page(tmp_path, kind)))
    assert out.get("permissionDecision") != "deny", out.get("permissionDecisionReason")   # 止めた訳を出す


@needs_chrome
@pytest.mark.parametrize("kind", ["blueprint", "theory-mock"])
def test_page_check_型の検査が赤のページは出す前に止め直し方を返す(env, tmp_path, kind):
    # 注入: どの画面にも無い飛び先を足す（型の検査が赤にする形）
    bad = page(tmp_path, kind, broken)
    out = hook(env, "pre", publish(bad))
    assert out.get("permissionDecision") == "deny"
    r = out["permissionDecisionReason"]
    assert "型の検査を通っていない" in r and "緑（exit 0）になってから" in r and kind in r


@needs_chrome
def test_page_check_files_で足すページも見る(env, tmp_path):
    good = page(tmp_path, "theory-mock", name="a.html")
    bad = page(tmp_path, "theory-mock", broken, name="b.html")
    assert denied(env, publish(good, files={"b.html": str(bad)}))


@pytest.mark.parametrize("edit,why", [
    (lambda s: re.sub(r'<meta name="af-page"[^>]*>', "", s), "型の印"),                  # 印を外して検査を逃れる
    (lambda s: s.replace('content="blueprint"', 'content="zz-unknown"'), "知らない型"),
    (lambda s: s.replace('content="blueprint"', 'content="mindmap"'), "page-check"),       # 検査を持たない型の名
])
def test_page_check_印が無い_知らない型_検査の無い型は既定で止める(env, tmp_path, edit, why):
    out = hook(env, "pre", publish(page(tmp_path, "blueprint", edit)))
    assert out.get("permissionDecision") == "deny" and why in out["permissionDecisionReason"]


def test_page_check_検査を回せない時も止める(env, tmp_path):
    e = dict(env, CHROME=str(tmp_path / "無い-chrome"))
    out = hook(e, "pre", publish(page(tmp_path, "blueprint")))
    assert out.get("permissionDecision") == "deny" and "回せない" in out["permissionDecisionReason"]


def test_page_check_型の外のページと_publish_の外は見ない(env, tmp_path):
    p = tmp_path / "plain.html"
    p.write_text("<!doctype html><html><body><p>報告</p></body></html>", encoding="utf-8")
    assert not denied(env, publish(p))
    bp = page(tmp_path, "blueprint", lambda s: s.replace('content="blueprint"', 'content="zz-unknown"'))
    assert not denied(env, {"tool_name": "Artifact", "tool_input": {"action": "read", "url": "x", "file_path": str(bp)}})
    assert not denied(env, {"tool_name": "Write", "tool_input": {"file_path": str(bp), "content": "x"}})


def test_page_check_型の名と検査は_SKILL_の頭を直に読む():
    """正本: 検査を持つ型は SKILL.md の page-check と template の印が対で在る（見張りは型の名を持たない）。"""
    src = (SCRIPTS / "page_check.py").read_text(encoding="utf-8")
    assert "check_blueprint" not in src and "check_theory_mock" not in src
    for d in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
        head = (d / "SKILL.md").read_text(encoding="utf-8").split("\n---", 1)[0]
        has_check = "\npage-check:" in head
        tpl = d / "references" / "template.html"
        marked = tpl.is_file() and 'name="af-page"' in tpl.read_text(encoding="utf-8")
        assert has_check == marked, f"{d.name}: page-check と型の印は対で置く"
        if has_check:
            rel = re.search(r"\npage-check:\s*(\S+)", head).group(1)
            assert (d / rel).is_file(), f"{d.name}: page-check の {rel} が無い"


# ── ledger_row ──
def notion_mcp(props, tool="mcp__x__notion-create-pages"):
    return {"tool_name": tool, "tool_input": {"pages": [{"properties": props}]}}


def curl(props, method="POST"):
    body = json.dumps({"parent": {"database_id": "db"}, "properties": props}, ensure_ascii=False)
    return {"tool_name": "Bash", "tool_input": {"command": "curl -sS -X %s https://api.notion.com/v1/pages -d '%s'" % (method, body)}}


SEL = lambda v: {"select": {"name": v}}  # noqa: E731
URL = lambda v: {"url": v}  # noqa: E731
RT = lambda v: {"rich_text": [{"text": {"content": v}}]}  # noqa: E731


@pytest.mark.parametrize("payload", [
    notion_mcp({"原因": "作り物", "行き先": "直さない"}),                                         # 理由と決定が無い
    notion_mcp({"原因": "作り物", "行き先": "直さない", "直さない理由": "作り物の理由"}),           # 決定が無い
    notion_mcp({"行き先": "直す窓", "直す窓": ""}, tool="mcp__x__notion-update-page"),             # URL が空
    notion_mcp({"行き先": "あとで"}),                                                             # 行き先の外
    curl({"原因": {"title": [{"text": {"content": "作り物"}}]}, "行き先": SEL("直した")}),          # 直しが無い
    curl({"行き先": SEL("直さない"), "決定": URL("https://example.com/d")}, method="PATCH"),        # 理由が無い
])
def test_ledger_row_行き先に要る欄の無い行は出す前に止める(env, payload):
    out = hook(env, "pre", payload)
    assert out.get("permissionDecision") == "deny"
    assert "細目 §3「原因の台帳」" in out["permissionDecisionReason"]


@pytest.mark.parametrize("payload", [
    notion_mcp({"原因": "作り物", "行き先": "直す窓", "直す窓": "https://example.com/s"}),
    notion_mcp({"原因": "作り物", "行き先": "未定"}),
    curl({"行き先": SEL("直した"), "直し": RT("https://example.com/pr/1")}, method="PATCH"),
    curl({"行き先": SEL("直さない"), "直さない理由": RT("作り物の理由"), "決定": URL("https://example.com/d")}),
    curl({"名前": RT("台帳でない行")}),
    {"tool_name": "Bash", "tool_input": {"command": "echo 行き先 は台帳の列"}},
])
def test_ledger_row_形の合う行と台帳でない書き込みは通す(env, payload):
    assert not denied(env, payload)


# ── send_go（外へ送る命令の前の人の go）──
SEND_CMD = "python3 /作り物/送る口.py --to グループ"


def tlog(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return str(p)


def U(t):
    return {"type": "user", "message": {"content": t}}


def A(t):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}}


def ANSWER():
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": "答え"}]},
            "toolUseResult": {"questions": [{"question": "送りますか"}], "answers": {"送りますか": "送る"}}}


@pytest.fixture
def senv(env, tmp_path):
    vals = tmp_path / "skill-values.json"
    vals.write_text(json.dumps({"docs-kit": {"compose-message": {"send": {"send_cmd": SEND_CMD}}}}), encoding="utf-8")
    return dict(env, SKILL_VALUES=str(vals))


def send(cmd, tpath):
    return {"tool_name": "Bash", "session_id": "s1", "transcript_path": tpath, "tool_input": {"command": cmd}}


@pytest.mark.parametrize("cmd", [SEND_CMD + " --text-file /tmp/a.txt",
                                 '"$V/notebooklm" source add nb1 brief.pdf'])
@pytest.mark.parametrize("rows", [
    [U("〇〇さんに連絡して送って")],                                        # 頼みの同じターンで送る
    [U("先に資料を読んで"), U("〇〇さんに連絡して送って")],                   # 人の行が続くだけで、見せた物が無い
    [],                                                                    # 人の行が無い（人のいない窓）
])
def test_send_go_見せた後の人の_go_が無い送る命令は止める(senv, tmp_path, cmd, rows):
    out = hook(senv, "pre", send(cmd, tlog(tmp_path, rows)))
    assert out.get("permissionDecision") == "deny"
    assert "go" in out["permissionDecisionReason"] and "送る文面" in out["permissionDecisionReason"]


@pytest.mark.parametrize("rows", [
    [U("〇〇さんに連絡して"), A("（文面）これで送ってよいですか"), U("go")],
    [U("〇〇さんに連絡して"), A("（文面）"), ANSWER()],
])
def test_send_go_見せた物に人が答えた後の送る命令は通す(senv, tmp_path, rows):
    assert not denied(senv, send(SEND_CMD + " --text-file /tmp/a.txt", tlog(tmp_path, rows)))


def test_send_go_試しの形と送る口の外と値の無い_repo_は見ない(env, senv, tmp_path):
    t = tlog(tmp_path, [U("送って")])
    assert not denied(senv, send(SEND_CMD + " --text-file /tmp/a.txt --dry-run", t))
    assert not denied(senv, send("echo 送る", t))
    assert not denied(env, send(SEND_CMD + " --text-file /tmp/a.txt", t))     # 値の表に送る口が無い repo


def test_send_go_会話ログが読めない時も止める(senv, tmp_path):
    assert denied(senv, send(SEND_CMD + " --text-file /tmp/a.txt", str(tmp_path / "無い.jsonl")))


def test_send_go_送る口は_SKILL_の頭を直に読む():
    src = (SCRIPTS / "send_go.py").read_text(encoding="utf-8")
    assert "notebooklm" not in src and "send_cmd" not in src
    heads = {d.name: (d / "SKILL.md").read_text(encoding="utf-8").split("\n---", 1)[0]
             for d in sorted(SKILLS.iterdir()) if (d / "SKILL.md").is_file()}
    assert "send-gate:" in heads["compose-message"] and "send-gate:" in heads["make-deck"]


# ── qa_page: 型から作る Artifact のデータ（type_url と files）も照らす（台帳の行: 型から作る Artifact のデータを見ない）──
DOCS_KIT_DATA = ROOT / "tests" / "docs_kit"


@pytest.mark.skipif(not shutil.which("node"), reason="node が無い（qa-html の検査は node で動く）")
def test_qa_page_型から作る_Artifact_のデータも出す前に検査する(env):
    def create(src):
        return {"tool_name": "Artifact", "tool_input": {"type_url": "https://example.com/type", "title": "作り物",
                                                        "files": {"data/questions.json": str(src)}}}
    assert denied(env, create(DOCS_KIT_DATA / "bad.json"))
    assert not denied(env, create(DOCS_KIT_DATA / "good.json"))
