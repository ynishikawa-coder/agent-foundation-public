"""PR の event が在るのに読めない時、PR の先端を「PR の外」と同じに扱わず止める約束（scripts/pr_shape.py の pr_head・check_all）。

意図: CI の PR の照らしは PR の先端（event の head.sha）を名指す。HEAD は main と合わせた merge の commit で、PR の先端でない。
課題: GITHUB_EVENT_PATH の event が読めない・壊れている・head.sha が無い時、check_all は黙って HEAD の merge の commit を
      照らした先端として書いた（PR の先端と照らす人に、別の commit の結果を PR の結果と読ませた）。
原因: pr_head が「読めない」を None＝「PR の外」と同じ値で返し、呼ぶ側が 2 つを分けられなかった。
ここでは誤りの類（壊れた event・無い event・head.sha の無い PR の event・形の崩れた PR_HEAD_SHA）をわざと入れ、拒むかを見る。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from entry_box import box_env
from test_core_plugin import _git

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("pr_shape_yomenai", ROOT / "scripts" / "pr_shape.py")
ps = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(ps)
SHAPE = [sys.executable, str(ROOT / "scripts" / "pr_shape.py"), "--print-head"]


def _event(tmp_path, body):
    p = tmp_path / "event.json"
    p.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
    return str(p)


@pytest.mark.parametrize("body", ["{壊れた", "[]", {"pull_request": {}}, {"pull_request": {"head": {"sha": "xyz"}}},
                                  {"pull_request": {"head": None}}, {"pull_request": "壊れた"}])
def test_読めない_PR_の_event_は_PR_の外と言わない(tmp_path, body):
    """注入: event を壊す・PR の event から head.sha を抜く → None（PR の外）でなく EventUnreadable。"""
    with pytest.raises(ps.EventUnreadable):
        ps.pr_head({"GITHUB_EVENT_PATH": _event(tmp_path, body)})


def test_在るはずの_event_が無いのも読めない(tmp_path):
    with pytest.raises(ps.EventUnreadable):
        ps.pr_head({"GITHUB_EVENT_PATH": str(tmp_path / "無い.json")})


def test_形の崩れた_PR_HEAD_SHA_も読めない():
    with pytest.raises(ps.EventUnreadable):
        ps.pr_head({"PR_HEAD_SHA": "main"})


def test_PR_の外は今までどおり_None(tmp_path):
    assert ps.pr_head({}) is None
    assert ps.pr_head({"GITHUB_EVENT_PATH": _event(tmp_path, {"ref": "refs/heads/main"})}) is None   # main への push
    assert ps.pr_head({"GITHUB_EVENT_PATH": _event(tmp_path, {"pull_request": {"head": {"sha": "a" * 40}}})}) == "a" * 40


def test_print_head_は読めない時に_PR_の外の_3_と分けて_2(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("PR_HEAD_SHA", "GITHUB_EVENT_PATH")}
    r = subprocess.run(SHAPE, capture_output=True, text=True, env=dict(env, GITHUB_EVENT_PATH=_event(tmp_path, "{壊れた")))
    assert r.returncode == 2 and not r.stdout.strip() and "PR の先端を読めない" in r.stderr
    r = subprocess.run(SHAPE, capture_output=True, text=True, env=env)
    assert r.returncode == 3


def test_check_all_は_PR_の先端を読めない時_merge_の_commit_を先端と書かず赤(tmp_path):
    """注入: CI の PR で event を壊す → 結果の行は赤で、HEAD（merge の commit）を PR の先端として名指さない。"""
    repo = tmp_path / "r"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "check_all.sh", repo / "scripts" / "check_all.sh")
    shutil.copy2(ROOT / "scripts" / "pr_shape.py", repo / "scripts" / "pr_shape.py")
    (repo / "scripts" / "pytest.sh").write_text("echo '1 passed'\n", encoding="utf-8")
    (repo / "tests").mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "merge の代わり")
    merge = _git(repo, "rev-parse", "HEAD")
    r = subprocess.run(["bash", "scripts/check_all.sh"], cwd=repo, capture_output=True, text=True,
                       env=box_env(GITHUB_EVENT_NAME="pull_request", PR_HEAD_SHA="",
                                   GITHUB_EVENT_PATH=_event(tmp_path, "{壊れた")))
    last = r.stdout.strip().splitlines()[-1]
    assert r.returncode == 1 and last.startswith("check_all: 赤") and "PR の先端（CI の event から読めない）" in last, last
    assert f"@{merge[:12]}" not in last and "PR の先端は不明" in last, last
