"""job plugin-smoke の本物の claude を要る試験が、合流した後の木（PR の枝に main を合わせた commit）で回るか（注入の試験）。

前の形: job の checkout が 1 つで、PR の枝の先端（head.sha）を取っていた。本物の claude の試験もその木で回り、
PR の枝と main の変更が合わさって初めて壊れる組み合わせは、合流の後の main への push で初めて見つかった。
今の形: 根に合わせた木（ref を書かない＝github.sha）、pr-head に PR の枝の先端を別に取り、
- GitHub から入れる試験（scripts/plugin_smoke.py）は pr-head の正本で期待の文を作る（入る物と同じ木）。
- 本物の claude の試験（pytest -m real_claude）は根＝合わせた木で回し、根が合わせた commit かを回す前に確かめる。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
MERGED_REFS = (None, "${{ github.sha }}")


def steps(yml: str) -> list[str]:
    """job plugin-smoke の step の塊の並び。"""
    m = re.search(r"(?ms)^  plugin-smoke:\n(.*?)(?=^  \S|\Z)", yml)
    assert m, "ci.yml に job plugin-smoke が無い"
    body = m.group(1).split("\n    steps:\n", 1)[1]
    return [b for b in re.split(r"(?m)^      - ", body)[1:]]


def _key(step: str, key: str):
    m = re.search(rf"(?m)^\s+{key}:\s*(.+?)\s*$", step)
    return m.group(1).strip().strip("'\"") if m else None


def problems(yml: str) -> list[str]:
    st = steps(yml)
    checkouts = [s for s in st if s.startswith("uses: actions/checkout@")]
    trees = {_key(s, "path"): _key(s, "ref") for s in checkouts}
    bad = []
    if None not in trees:
        bad.append("根（path を書かない）の checkout が無い")
    elif trees[None] not in MERGED_REFS:
        bad.append(f"根の checkout が合流した後の木でない（ref: {trees[None]}）。本物の claude の試験が合わせた木で回らない")
    if trees.get("pr-head") != "${{ github.event.pull_request.head.sha || github.sha }}":
        bad.append(f"pr-head に PR の枝の先端を取っていない（ref: {trees.get('pr-head')}）")
    runs = [(s, _key(s, "run") or "") for s in st]
    smoke = [s for s, r in runs if "plugin_smoke.py" in r]
    if not smoke or "pr-head/scripts/plugin_smoke.py --repo pr-head " not in _key(smoke[0], "run"):
        bad.append("GitHub から入れる試験が pr-head の正本で期待の文を作っていない（入る物と違う木で比べる）")
    i_pytest = next((i for i, (s, r) in enumerate(runs) if "-m real_claude" in r), None)
    if i_pytest is None:
        bad.append("本物の claude の試験の step が無い")
    else:
        if _key(st[i_pytest], "working-directory") not in (None, "."):
            bad.append("本物の claude の試験が根（合わせた木）の外で回る")
        verify = [i for i, (s, r) in enumerate(runs) if "${MERGED_SHA}" in s and "parent ${HEAD_SHA}" in s]
        if not verify or verify[0] > i_pytest:
            bad.append("本物の claude の試験の前に、根が PR の枝に main を合わせた commit かを確かめる step が無い")
    return bad


def test_本物の_claude_の試験は合わせた木で回る():
    assert problems(CI.read_text(encoding="utf-8")) == []


def test_注入_根を_PR_の枝の先端で_checkout_すると赤():
    yml = CI.read_text(encoding="utf-8")
    head = "${{ github.event.pull_request.head.sha || github.sha }}"
    bad = yml.replace("      - uses: actions/checkout@v4\n        with:\n          persist-credentials: false\n      - uses: actions/checkout@v4\n        with:\n          ref:",
                      f"      - uses: actions/checkout@v4\n        with:\n          ref: {head}\n          persist-credentials: false\n      - uses: actions/checkout@v4\n        with:\n          ref:", 1)
    assert bad != yml
    assert any("合流した後の木でない" in p for p in problems(bad))


def test_注入_前の形_checkout_が_1_つで先端を取ると赤():
    yml = CI.read_text(encoding="utf-8")
    m = re.search(r"(?ms)(      - uses: actions/checkout@v4\n.*?)(      - uses: actions/setup-python)", yml.split("  plugin-smoke:")[1])
    old = ("      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.head.sha || github.sha }}\n"
           "          persist-credentials: false\n")
    bad = yml.replace(m.group(1), old, 1).replace("pr-head/scripts/plugin_smoke.py --repo pr-head ", "scripts/plugin_smoke.py ")
    assert len(problems(bad)) >= 2


def test_注入_確かめる_step_を消すか試験の後に置くと赤():
    yml = CI.read_text(encoding="utf-8")
    st = steps(yml)
    verify = next(s for s in st if "${MERGED_SHA}" in s)
    assert problems(yml.replace("      - " + verify, "", 1))
    pytest_step = next(s for s in st if "-m real_claude" in s)
    moved = yml.replace("      - " + verify, "", 1).rstrip("\n") + "\n      - " + verify
    assert pytest_step in moved and problems(moved)


def test_注入_本物の試験を_pr_head_で回すと赤():
    yml = CI.read_text(encoding="utf-8")
    bad = yml.replace("          AF_REQUIRE_CLAUDE: \"1\"\n", "          AF_REQUIRE_CLAUDE: \"1\"\n        working-directory: pr-head\n", 1)
    assert bad != yml and problems(bad)
