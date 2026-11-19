"""CI と見回りの python の道具が、正本 requirements-ci.txt から入るかを見る。

道具の名を workflow ごとに手で並べると、新しく import した道具を入れ忘れ、手元に偶々在る作業機だけで緑になる
（見回りが PyYAML を使い始めた時、CI の作業機に無く試験が赤になった）。正本を 1 つにし、
- scripts/・public-guard/・tests/ が import する標準でない道具は、正本に載る（または任意の行に載る）
- python を回す job は、回す前に正本から入れ、名を手で並べない
を照らす。"""
from __future__ import annotations

import ast
import pathlib
import re
import shlex
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
REQ = ROOT / "requirements-ci.txt"
WORKFLOWS = ROOT / ".github" / "workflows"
SCANNED = ("scripts", "public-guard", "tests")


def read_requirements(text: str) -> tuple[set[str], set[str]]:
    """正本から (入れる道具の import の名, 任意の道具の import の名) を読む。
    行は `<配る名>` か `<配る名>  # import <import の名>`。任意は `# 任意…: a, b` の行。"""
    need, optional = set(), set()
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"#\s*任意[^:：]*[:：]\s*(.+)$", s)
        if m:
            optional |= {w.strip() for w in m.group(1).split(",") if w.strip()}
            continue
        if not s or s.startswith("#"):
            continue
        dist, _, comment = s.partition("#")
        m = re.match(r"\s*import\s+(\S+)", comment)
        need.add(m.group(1) if m else re.split(r"[<>=!~\[ ]", dist.strip())[0].lower())
    return need, optional


def _local_names(root: pathlib.Path) -> set[str]:
    names = set()
    for p in root.rglob("*"):
        if ".git" in p.parts:
            continue
        if p.suffix == ".py":
            names.add(p.stem)
        elif p.is_dir():
            names.add(p.name)
    return names


def third_party_imports(files: list[tuple[str, str]], local: set[str]) -> dict[str, set[str]]:
    """file の (名, 中身) の並びから、標準でも repo の中でもない import の頭の名 → file の名。"""
    std = set(sys.stdlib_module_names) | {"__future__"}
    found: dict[str, set[str]] = {}
    for name, text in files:
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            else:
                continue
            for mod in mods:
                head = mod.split(".")[0]
                if head not in std and head not in local:
                    found.setdefault(head, set()).add(name)
    return found


def missing_imports(files, local, req_text) -> dict[str, set[str]]:
    need, optional = read_requirements(req_text)
    return {m: f for m, f in third_party_imports(files, local).items() if m not in need | optional}


def _runs(step) -> list[list[str]]:
    run = step.get("run") if isinstance(step, dict) else None
    if not isinstance(run, str):
        return []
    out = []
    for line in run.splitlines():
        try:
            words = shlex.split(line, comments=True)
        except ValueError:
            words = line.split()
        if words:
            out.append(words)
    return out


def _is_pip_install(words: list[str]) -> bool:
    return "pip" in words and "install" in words


def _runs_python(words: list[str]) -> bool:
    return bool(words) and (words[0].startswith("python") or words[0] in ("pytest", "bash")) and not _is_pip_install(words)


def workflow_problems(path: str, text: str) -> list[str]:
    """python を回す job が、回す前に正本から道具を入れているか。手で名を並べた pip install も拒む。"""
    wf = yaml.safe_load(text)
    problems = []
    for jid, job in (wf.get("jobs") or {}).items():
        installed = False
        for st in job.get("steps") or []:
            for words in _runs(st):
                if _is_pip_install(words):
                    rest = words[words.index("install") + 1:]
                    pkgs = [w for w in rest if not w.startswith("-") and w != "requirements-ci.txt"]
                    if "requirements-ci.txt" not in rest or pkgs:
                        problems.append(f"{path} の job {jid}: 道具を requirements-ci.txt 以外から入れる（{' '.join(words)}）")
                    else:
                        installed = True
                elif _runs_python(words) and not installed:
                    problems.append(f"{path} の job {jid}: 道具を requirements-ci.txt から入れる前に python を回す（{' '.join(words)}）")
    return problems


# ── 本物を照らす ──

def test_repo_imports_are_in_requirements():
    files = [(str(p.relative_to(ROOT)), p.read_text(encoding="utf-8"))
             for d in SCANNED for p in (ROOT / d).rglob("*.py")]
    assert missing_imports(files, _local_names(ROOT), REQ.read_text(encoding="utf-8")) == {}


def test_workflows_install_from_requirements():
    problems = []
    for p in sorted(WORKFLOWS.glob("*.yml")):
        problems += workflow_problems(p.name, p.read_text(encoding="utf-8"))
    assert problems == []


def test_patrol_needs_yaml_from_requirements():
    need, _ = read_requirements(REQ.read_text(encoding="utf-8"))
    assert "yaml" in need


# ── 誤りの類をわざと入れて拒むか ──

REQ_SAMPLE = "pytest\nPyYAML  # import yaml\n# 任意（無ければ飛ばす）: playwright\n"


def test_rejects_unlisted_import():
    files = [("public-guard/x.py", "import yaml\nimport requests\n")]
    assert missing_imports(files, set(), REQ_SAMPLE) == {"requests": {"public-guard/x.py"}}


def test_accepts_listed_optional_stdlib_and_local():
    files = [("tests/t.py", "import os\nimport pytest\nfrom playwright.sync_api import x\nimport patrol\n")]
    assert missing_imports(files, {"patrol"}, REQ_SAMPLE) == {}


def test_rejects_job_running_python_without_install():
    wf = "jobs:\n  a:\n    steps:\n      - run: python3 public-guard/patrol.py\n"
    assert len(workflow_problems("w.yml", wf)) == 1


def test_rejects_hand_listed_install():
    wf = ("jobs:\n  a:\n    steps:\n      - run: python3 -m pip install --quiet pytest\n"
          "      - run: python3 -m pytest\n")
    probs = workflow_problems("w.yml", wf)
    assert any("以外から入れる" in p for p in probs) and any("入れる前に" in p for p in probs)


def test_rejects_install_after_python():
    wf = ("jobs:\n  a:\n    steps:\n      - run: python3 x.py\n"
          "      - run: python3 -m pip install -r requirements-ci.txt\n")
    assert len(workflow_problems("w.yml", wf)) == 1


def test_accepts_install_then_python():
    wf = ("jobs:\n  a:\n    steps:\n      - run: python3 -m pip install --quiet -r requirements-ci.txt\n"
          "      - run: |\n          python3 x.py\n          bash scripts/check_all.sh\n")
    assert workflow_problems("w.yml", wf) == []
