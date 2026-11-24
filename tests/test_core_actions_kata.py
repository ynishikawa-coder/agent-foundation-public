"""非公開の repo の Actions の workflow が既定の形から外れていると、起動の hook が file の名で知らせる試験。

意図: 非公開の repo の Actions の枠を、古い走りの止め忘れ・全部の枝の push で使い切らない（形の正本は
docs/Actions の課金と workflow の形.md）。開いた窓が外れた workflow をその仕事のついでに直せるよう、起動の時に名指す。
課題: 枠を使い切って全部の非公開 repo の job が数秒で落ちる事が 2 度起きた。1 度目の直し（古い走りを止める・job を減らす）は
1 つの repo の中だけで行われ、後で作った非公開 repo は PR の古い走りを止めず、全部の枝の push で走る workflow を持っていた。
原因: Actions の数え方の前提と workflow の既定の形が土台に無く、直しが 1 つの repo に閉じて他へ届かなかった。
"""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "core" / "scripts" / "kaku.py"
HEAD = "Actions の workflow が既定の形から外れている"

BAD = """on:
  pull_request:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""
GOOD = """on:
  pull_request:
  push:
    branches: [main]
concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: echo ok
"""


def _repo(d, workflow, origin=None):
    (d / ".github" / "workflows").mkdir(parents=True)
    (d / ".github" / "workflows" / "ci.yml").write_text(workflow, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    if origin:
        subprocess.run(["git", "-C", str(d), "remote", "add", "origin", origin], check=True)
    return d


def _fake_gh(tmp_path, private):
    """GitHub に聞く口の作り物（外へ出ない）。repos/<repo> の .private に private を答える。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    gh = bin_dir / "gh"
    gh.write_text(f"#!/bin/sh\necho {private}\n", encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}


def _inject(project, extra=None):
    env = dict(os.environ, HOME=str(project), CLAUDE_PROJECT_DIR=str(project), **(extra or {}))
    r = subprocess.run([sys.executable, str(TOOL), "inject"], capture_output=True, text=True, timeout=60, env=env,
                       input="{}")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def _section(ctx):
    """起動の知らせのうち Actions の形の節（無ければ ""）。"""
    if HEAD not in ctx:
        return ""
    rest = ctx[ctx.index(HEAD):]
    return rest.split("\n## ", 1)[0]


def test_非公開か分からない_repo_の外れた_workflow_を名指し_直した形では知らせない(tmp_path):
    """注入: PR の古い走りを止めず全部の枝の push で走る workflow → file の名と 2 つの外れが出る。直した形 → 出ない。"""
    sec = _section(_inject(_repo(tmp_path / "bad", BAD)))
    assert "`.github/workflows/ci.yml`" in sec
    assert "古い走りを止めない" in sec and "全部の枝に走る" in sec
    assert "分からない" in sec and "origin" in sec          # 見分けられない訳を添えて知らせる側へ倒す
    assert _section(_inject(_repo(tmp_path / "good", GOOD))) == ""


@pytest.mark.parametrize("workflow,why", [
    (GOOD.replace("concurrency:\n  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || "
                  "github.ref }}\n  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n", ""),
     "古い走りを止めない"),
    (GOOD.replace("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", "cancel-in-progress: false"),
     "古い走りを止めない"),
    (GOOD.replace("branches: [main]", "branches: ['**']"), "全部の枝に走る"),
    (GOOD.replace("    branches: [main]\n", "    branches-ignore: [main]\n"), "全部の枝に走る"),
    (GOOD.replace("on:\n  pull_request:\n  push:\n    branches: [main]\n", "on: [push]\n"), "全部の枝に走る"),
])
def test_注入_外れを_1_つずつ戻すと名指す(tmp_path, workflow, why):
    """注入: 直した形から外れを 1 つだけ戻す（止める印を消す・false にする・push を ** や branches-ignore や絞らない形に）→ 名指す。"""
    sec = _section(_inject(_repo(tmp_path, workflow)))
    assert why in sec, sec


def test_全部の_job_が古い走りを止めるなら知らせない(tmp_path):
    """job ごとの concurrency で全部の job が古い走りを止める形は外れでない。1 つでも止めない job があれば外れ。"""
    per_job = BAD.replace("  push:\n", "  push:\n    branches: [main]\n").replace(
        "    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    concurrency:\n      group: t-${{ github.ref }}\n"
        "      cancel-in-progress: true\n")
    assert _section(_inject(_repo(tmp_path / "all", per_job))) == ""
    one_short = per_job + "  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"
    assert "古い走りを止めない" in _section(_inject(_repo(tmp_path / "short", one_short)))


def test_GitHub_が非公開と答えた_repo_を名指し_公開と答えた_repo_には知らせない(tmp_path):
    origin = "https://github.com/example-owner/example-repo.git"
    sec = _section(_inject(_repo(tmp_path / "priv", BAD, origin), _fake_gh(tmp_path / "p", "true")))
    assert "非公開の repo" in sec and "分からない" not in sec
    assert _section(_inject(_repo(tmp_path / "pub", BAD, origin), _fake_gh(tmp_path / "q", "false"))) == ""


def test_公開の検査を呼ぶ_repo_には外れた形でも知らせない(tmp_path):
    """公開の repo（土台の action public-guard を PR・push で呼ぶ）は数えられないので知らせない。"""
    public = BAD.replace("      - run: echo ok\n",
                         "      - uses: ynishikawa-coder/agent-foundation-public/public-guard@main\n")
    assert _section(_inject(_repo(tmp_path, public))) == ""
