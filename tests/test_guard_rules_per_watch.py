"""guard の見張りは 1 見張り 1 file で足せるか（並ぶ PR が同じ所へ足して衝突する形が戻らないかの注入の試験）。

見張りを足す PR が全部、skill guard-rules の SKILL.md の表と値の表の例・plugin の説明・plugins/README.md・
guard_common.py の DEFAULTS へ行を足して、続けて衝突した。見張りの正本は見張りの file の頭（HOOKS）と
skills/guard-rules/見張り/<名>.md、鍵・型・既定の正本は土台の skill-values/schema.json（値の表の 1 本の口）だけにし、
皆の所には見張りの名も鍵も並べない。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "plugins" / "guard"
HEADS = ("## 止められた・知らされた時の直し方", "## 値の表の鍵", "## 射程の外")


def _common(root):
    """root の guard_common と、それが読む root の lib/skill_values（鍵の一覧）を読み直す。"""
    sys.path.insert(0, str(root / "scripts"))
    try:
        import importlib
        sys.modules.pop("skill_values", None)
        sys.modules.pop("guard_common", None)
        return importlib.import_module("guard_common")
    finally:
        sys.path.pop(0)


def _section(text, head):
    """見出し head の節の本文（次の ## まで）。無ければ ""。"""
    m = re.search(r"^%s\n(.*?)(?=^## |\Z)" % re.escape(head), text, re.M | re.S)
    return m.group(1) if m else ""


def problems(root: Path) -> list[str]:
    """guard の plugin の dir（root）を照らした崩れの並び。空なら緑。
    鍵・型・既定の正本は lib/schema.json（土台の skill-values/ への symlink）の guard の欄。各鍵の持ち主は、
    その鍵を「## 値の表の鍵」の節の値の表の例（`"鍵":`）に書いた 見張り/<名>.md（1 つだけ）か、
    SKILL.md の「## 値の表（皆の鍵）」の例。"""
    G = _common(root)
    errs = []
    docs = root / "skills" / "guard-rules" / "見張り"
    names = []
    for p in G.watcher_files(str(root / "scripts")):
        name = Path(p).stem
        if not isinstance(G.declared(p).get("HOOKS"), dict):
            continue                                   # 宣言の無い file は見張りでない（手伝いの部品）
        names.append(name)
    have = {p.stem for p in docs.glob("*.md")}
    for name in sorted(set(names) - have):
        errs.append(f"{name}: 直し方の file 見張り/{name}.md が無い")
    for name in sorted(have - set(names)):
        errs.append(f"見張り/{name}.md: 見張りの file scripts/{name}.py が無い（消した見張りの直し方は一緒に消す）")
    skill = (root / "skills" / "guard-rules" / "SKILL.md").read_text(encoding="utf-8")
    keys = list(G.SV.keys_of("guard") or {})
    common = [k for k in keys if f'"{k}":' in _section(skill, "## 値の表（皆の鍵）")]
    owner = {}
    for name in sorted(set(names) & have):
        sec = _section((docs / f"{name}.md").read_text(encoding="utf-8"), "## 値の表の鍵")
        for k in keys:
            if f'"{k}":' in sec:
                if k in common or k in owner:
                    errs.append(f"見張り/{name}.md: 鍵 {k} は {owner.get(k, '皆の鍵（SKILL.md）')} と重なる"
                                f"（鍵の値の表の例は 1 つの見張りか皆の鍵のどちらか 1 か所）")
                owner.setdefault(k, name)
    for k in keys:
        if k not in common and k not in owner:
            errs.append(f"鍵 {k}（schema.json の guard の欄）の書き方（値の表の例の \"{k}\":）が、どの 見張り/<名>.md の"
                        f"「## 値の表の鍵」にも SKILL.md の「## 値の表（皆の鍵）」にも無い")
    shared = {
        "skills/guard-rules/SKILL.md": skill,
        ".claude-plugin/plugin.json": json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["description"],
        "scripts/guard_common.py": (root / "scripts" / "guard_common.py").read_text(encoding="utf-8"),
        "scripts/guard.py": (root / "scripts" / "guard.py").read_text(encoding="utf-8"),
    }
    readme = root.parent / "README.md"
    if readme.is_file():
        shared["plugins/README.md"] = "\n".join(ln for ln in readme.read_text(encoding="utf-8").splitlines()
                                                if ln.startswith("- **guard**"))
    for name in sorted(set(names) & have):
        text = (docs / f"{name}.md").read_text(encoding="utf-8")
        first = text.splitlines()[0] if text else ""
        if not first.startswith(f"# {name}"):
            errs.append(f"見張り/{name}.md: 1 行目が「# {name}（呼び名）」でない")
        for h in HEADS:
            if h not in text:
                errs.append(f"見張り/{name}.md: 欄「{h}」が無い")
        call = re.search(r"（(.+?)）", first)
        words = [name] + [k for k, n in owner.items() if n == name] + ([call.group(1)] if call else [])
        for where, body in shared.items():
            for w in words:
                if re.search(r"(?<![0-9A-Za-z_])%s(?![0-9A-Za-z_])" % re.escape(w), body):
                    errs.append(f"{where}: 見張り {name} の「{w}」を並べた（並ぶ PR が全部ここへ足して衝突する。"
                                f"見張り/{name}.md に置く）")
    return errs


def test_今の土台は緑():
    assert problems(GUARD) == []


@pytest.fixture
def copy(tmp_path):
    d = tmp_path / "plugins" / "guard"
    shutil.copytree(GUARD, d, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "plugins" / "README.md", tmp_path / "plugins" / "README.md")
    return d


def _edit(path, old, new):
    t = path.read_text(encoding="utf-8")
    assert old in t, f"{path} の形が変わった（この注入を合わせる）"
    path.write_text(t.replace(old, new, 1), encoding="utf-8")


def test_SKILL_の表へ見張りの行を足すと赤(copy):
    f = copy / "skills" / "guard-rules" / "SKILL.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n| spec_gate（設計書の型の gate を直に呼ぶ手） | PreToolUse | 止める | 直す |\n",
                 encoding="utf-8")
    assert any("SKILL.md" in e and "spec_gate" in e for e in problems(copy))


def test_皆の鍵の節へ見張りの鍵を足すと赤(copy):
    _edit(copy / "skills" / "guard-rules" / "SKILL.md", '"state_dir": "~/.claude/af-guard"',
          '"state_dir": "~/.claude/af-guard",\n    "context_limit": 300000')
    assert any("context_limit" in e and "重なる" in e for e in problems(copy))


def test_plugin_の説明と_README_に見張りを並べると赤(copy):
    p = copy / ".claude-plugin" / "plugin.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["description"] += "未回答の台帳を持つ。"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    _edit(copy.parent / "README.md", "- **guard**（A5）: 守りの hook を", "- **guard**（A5）: 守りの hook（irreversible ほか）を")
    errs = problems(copy)
    assert any("plugin.json" in e and "未回答の台帳" in e for e in errs)
    assert any("README.md" in e and "irreversible" in e for e in errs)


def test_直し方の_file_の無い見張りは赤(copy):
    (copy / "scripts" / "zz_sakumono.py").write_text('HOOKS = {"pre": "check"}\n\n\ndef check(data, vals):\n    return ""\n',
                                                     encoding="utf-8")
    assert any("zz_sakumono" in e and "見張り/zz_sakumono.md" in e for e in problems(copy))


def _add_schema_key(copy, key):
    f = copy / "lib" / "schema.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["sections"]["guard"]["keys"][key] = {"type": "list", "default": []}
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def test_書き方の無い鍵と_2_つの見張りに書いた鍵は赤(copy):
    _add_schema_key(copy, "spec_sakumono")
    errs = problems(copy)
    assert any("spec_sakumono" in e and "書き方" in e for e in errs)
    f = copy / "skills" / "guard-rules" / "見張り" / "spec_gate.md"
    _edit(f, "## 値の表の鍵\n", '## 値の表の鍵\n\n```json\n{"guard": {"ask_term_allow": []}}\n```\n')
    assert any("spec_gate.md" in e and "ask_term_allow" in e and "重なる" in e for e in problems(copy))


def test_見張りの無い直し方の_file_は赤(copy):
    (copy / "scripts" / "spec_gate.py").unlink()
    assert any("見張り/spec_gate.md" in e for e in problems(copy))


def test_既定は_schema_の_guard_の欄から組み_見張りの_file_に写さない(copy):
    G = _common(GUARD)
    assert G.DEFAULTS["context_limit"] == 300_000 and G.DEFAULTS["state_dir"].endswith("af-guard")
    assert G.DEFAULTS["context_stop_max"] == 2 and G.DEFAULTS["ask_prior_lookup"] == []
    for p in G.watcher_files():
        assert not re.search(r"^VALUES\s*=", Path(p).read_text(encoding="utf-8"), re.M), f"{p} に値の既定を写した"
    _common(GUARD)


def test_止めた文は見張りの直し方の_file_を指し_その_file_が在る(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), AF_GUARD_STATE=str(tmp_path / "st"))
    env.pop("SKILL_VALUES", None)
    p = subprocess.run([sys.executable, "-B", str(GUARD / "scripts" / "guard.py"), "pre"], capture_output=True, text=True,
                       env=env, cwd=tmp_path, input=json.dumps({"tool_name": "Bash", "session_id": "s1", "cwd": str(tmp_path),
                                                                "tool_input": {"command": "python3 型/check_spec_doc.py x --lock"}}))
    reason = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    m = re.search(r"直し方と値の表の鍵: (\S+\.md)", reason)
    assert m and Path(m.group(1)).is_file() and Path(m.group(1)).stem == "spec_gate", reason
