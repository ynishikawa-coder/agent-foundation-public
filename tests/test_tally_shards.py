"""試験を K 組に分けて同時に回す形が、回らない・2 度回る試験を緑に数えないか（注入の試験）。

前の形: check_all は tests/ を 1 つの pytest で順に回し、PR ごとの検査が 20 分かかって main へ入るのが遅れた。
今の形: 入口の plugin（af_tally）が --af-shard=i/K で file ごとに組へ分け、check_all が K 組を同時に回し、
数える段の merge が K 組の結果を合わせる。組が欠ける・集めた試験が組で違う・2 つの組で回った・どの組でも回らなかった
試験があれば数える段が止まる（赤）。
"""
import subprocess
import sys
from pathlib import Path

import pytest
from test_check_all_counts_teeth import OK, box, run

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "pytest_plugin"))
import af_tally  # noqa: E402


class _It:
    def __init__(self, nodeid, module=None):
        self.nodeid, self.module = nodeid, module


def shard(i, k, ran, out, collected=None):
    return {"finished": True, "exitstatus": 0, "collected": collected or len(ran) + len(out),
            "dropped": [], "results": [{"nodeid": n, "outcome": "passed"} for n in ran], "deselected": [],
            "unrun": [], "audit": [], "unseen": [], "pytest": "9.1.1", "shard": [i, k], "sharded_out": out}


A, B, C = "tests/test_a.py::test_a", "tests/test_b.py::test_b", "tests/test_c.py::test_c"


def test_合格_組を合わせると全部の結果が1つになる():
    m = af_tally.merge([shard(0, 2, [A, B], [C]), shard(1, 2, [C], [A, B])])
    assert sorted(r["nodeid"] for r in m["results"]) == [A, B, C] and m["collected"] == 3


def test_合格_分けていない結果はそのまま():
    d = shard(0, 1, [A], [])
    d["shard"] = None
    assert af_tally.merge([d]) is d


@pytest.mark.parametrize("datas, word", [
    ([shard(0, 2, [A, B], [C])], "組が揃っていない"),
    ([shard(0, 2, [A, B], [C]), shard(0, 2, [C], [A, B])], "組が揃っていない"),
    ([shard(0, 2, [A, B], [C]), shard(1, 2, [C, B], [A])], "2 つの組で回った"),
    ([shard(0, 2, [A], [B, C]), shard(1, 2, [C], [A, B])], "どの組でも回らなかった"),
    ([shard(0, 2, [A, B], [C]), shard(1, 2, [C], [A, B], collected=4)], "集めた試験の数が組で違う"),
    ([shard(0, 2, [A, B], [C]), dict(shard(1, 2, [C], [A, B]), finished=False)], "終わりまで書かれていない"),
])
def test_注入_組を合わせられない結果は数える段が止まる(datas, word):
    with pytest.raises(ValueError, match=word):
        af_tally.merge(datas)


def test_合格_分け方は全部の_file_をちょうど1つの組へ入れ本数を均す():
    items = [_It(f"tests/test_{f}.py::t{n}") for f, k in (("a", 5), ("b", 3), ("c", 2), ("d", 2)) for n in range(k)]
    g = af_tally.assign(items, 2)
    assert sorted(sum(g, [])) == sorted({i.nodeid.split("::")[0] for i in items})
    sizes = [sum(1 for i in items if i.nodeid.split("::")[0] in grp) for grp in g]
    assert max(sizes) - min(sizes) <= 2 and af_tally.assign(list(reversed(items)), 2) == g


def test_合格_重い_file_は1つの組を占め_ほかの試験はほかの組へ寄る():
    """1 本が長い file（決まりの文を消して回す試験）は本数でなく重さで数える。ほかの組へ試験を寄せ、組の長さを均す。"""
    heavy = type("M", (), {"AF_SHARD_WEIGHT": 100})
    items = [_It(f"tests/test_h.py::t[{n}]", heavy) for n in range(3)]
    items += [_It(f"tests/test_{f}.py::t{n}") for f in "abcdef" for n in range(10)]
    g = af_tally.assign(items, 4)
    assert ["tests/test_h.py"] in g, g
    assert sorted(sum(g, [])) == sorted(["tests/test_h.py"] + [f"tests/test_{f}.py" for f in "abcdef"])


def test_合格_重い_file_も_check_all_は全部を1回ずつ数える(tmp_path):
    body = "AF_SHARD_WEIGHT = 50\nimport pytest\n\n@pytest.mark.parametrize('n', range(3))\ndef test_h(n):\n    pass\n"
    files = {f"test_{x}.py": f"def test_{x}():\n    pass\n" for x in "ab"}
    code, last, out = run(box(tmp_path, {"test_h.py": body, **files}), AF_CHECK_SHARDS="3")
    assert code == 0 and "check_all: 緑" in last, out
    assert "3 passed" in out and "6 passed" not in out, out    # 重い file の 3 本は 1 つの組で回り、ほかは別の組


def test_合格_check_all_は組に分けて回し全部を数える(tmp_path):
    files = {f"test_{x}.py": f"def test_{x}():\n    pass\n" for x in "abcde"}
    code, last, out = run(box(tmp_path, files), AF_CHECK_SHARDS="3")
    assert code == 0 and "3 組を同時に" in out and "check_all: 緑" in last, out
    assert "6 passed" not in out, out    # 1 つの組が全部を回していない


def test_注入_組の1つが結果を書かずに落ちたら赤(tmp_path):
    files = {f"test_{x}.py": f"def test_{x}():\n    pass\n" for x in "abcde"}
    files["conftest.py"] = ("import os\n"
                            "def pytest_sessionstart(session):\n"
                            "    if session.config.getoption('af_shard') == '1/3':\n"
                            "        os._exit(0)\n")
    code, last, out = run(box(tmp_path, files), AF_CHECK_SHARDS="3")
    assert code != 0 and "数える段が止まった" in last, out
