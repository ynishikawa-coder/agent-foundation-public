"""setup script の塊（docs/核の届け方.md）が前の目録を外すか決める所は、出所を名の一致で比べる（注入の試験）。

前の形: `a[2] not in json.dumps(s)`＝目録の出所を JSON の文字列にして、土台の名が中に在るかで見ていた。
fork（`<名>-fork`）や、名を道に含む別の出所も「今の目録」と見なして外さず、古い目録から入った。
今の形: 目録の `repo`（GitHub の短い名）か `url` が、`marketplace add` に渡す名と同じ時だけ今の目録と見なす。
字の照らし（json.dumps の形が戻っていないか）と動きの照らし（外すか）は別の試験に分ける。字の照らしを取り出す所で
先に止めると、文書を丸ごと戻した時に動きの試験がどれも同じ所で止まり、動きの歯が効いているかが結果から読めない
（tests/test_setup_stale_catalog_source_teeth.py が片方ずつ壊して照らす）。
本物の claude は要らない（外す命令は印を打つ殻に替え、外すかの決め方だけを回す）。
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "核の届け方.md"
NAME = "ynishikawa-coder/agent-foundation-public"


def decide_text():
    """塊の頭から外す行まで（docs/核の届け方.md の字のまま）。"""
    b = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", DOC.read_text(encoding="utf-8"), re.S).group(1)
    lines = [s.strip() for s in b.splitlines()]
    end = next(i for i, s in enumerate(lines) if "marketplace remove agent-foundation" in s)
    return "\n".join(lines[: end + 1])


def decide_part():
    """外すかを決める所の、外す命令を印を打つ echo に替えた形（動きの試験が回す）。"""
    return decide_text().replace("claude plugin marketplace remove agent-foundation", "echo REMOVED")


def removes(tmp_path, source, entry=True):
    home = tmp_path / "home"
    loc = tmp_path / "cat"
    (loc / "scripts").mkdir(parents=True)
    if entry:
        (loc / "scripts" / "setup_plugins.py").write_text("", encoding="utf-8")
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "known_marketplaces.json").write_text(json.dumps(
        {"agent-foundation": {"source": source, "installLocation": str(loc)}}), encoding="utf-8")
    # 外す行の 2>/dev/null を外し、python の誤りで黙って「外さない」に倒れる形を見えるようにする
    part = decide_part().replace(' 2>/dev/null && echo REMOVED >/dev/null 2>&1', ' && echo REMOVED')
    assert '"$af_e" && echo REMOVED' in part, "外す行の形が変わった（試験の替え方を合わせる）"
    r = subprocess.run(["bash", "-c", part], capture_output=True, text=True, env={"HOME": str(home), "PATH": "/usr/bin:/bin"})
    assert "Traceback" not in r.stderr, r.stderr
    return "REMOVED" in r.stdout


def test_字_出所を文字列の包含で見る形が戻っていない():
    assert "json.dumps" not in decide_text(), "出所を文字列の包含で見る形が戻った"


def test_合格_今の目録は外さない(tmp_path):
    assert not removes(tmp_path, {"source": "github", "repo": NAME})


@pytest.mark.parametrize("source", [
    {"source": "github", "repo": NAME + "-fork"},
    {"source": "github", "repo": "someone/" + NAME.split("/")[1]},
    {"source": "git", "url": "https://example.invalid/" + NAME + "-mirror.git"},
    {"source": "github", "repo": "x/y", "note": NAME},
])
def test_注入_元の名を含む別の出所の目録は外す(tmp_path, source):
    assert removes(tmp_path, source)


def test_合格_版に止めた目録と入口の無い目録は外す(tmp_path):
    assert removes(tmp_path / "a", {"source": "github", "repo": NAME, "ref": "v1"})
    assert removes(tmp_path / "b", {"source": "github", "repo": NAME}, entry=False)


def test_合格_url_で足した目録は渡した名と同じなら外さない(tmp_path):
    """試験や plugin-smoke が名を url に替えて回す時（目録に url で残る）も、同じ名なら今の目録。"""
    url = "https://example.invalid/o/agent-foundation-public.git"
    part = decide_part().replace(NAME, url)
    assert part.count(url) == 1
    home = tmp_path / "home"
    loc = tmp_path / "cat"
    (loc / "scripts").mkdir(parents=True)
    (loc / "scripts" / "setup_plugins.py").write_text("", encoding="utf-8")
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "known_marketplaces.json").write_text(json.dumps(
        {"agent-foundation": {"source": {"source": "git", "url": url}, "installLocation": str(loc)}}), encoding="utf-8")
    r = subprocess.run(["bash", "-c", part.replace(' 2>/dev/null && echo REMOVED >/dev/null 2>&1', ' && echo REMOVED')],
                       capture_output=True, text=True, env={"HOME": str(home), "PATH": "/usr/bin:/bin"})
    assert "Traceback" not in r.stderr and "REMOVED" not in r.stdout, r.stdout + r.stderr
