"""公開の検査（public-guard/guard.py）が CI で PR の event を読めない時に、空の event として通さず止める試験。

前の形は load_event が event の file が無い・読めない時に {} を返し（壊れた JSON は落ちる）、CI でも PR の題・本文を照らさずに
当たり 0 の緑（exit 0）になりえた。注入: CI で event の file が無い → exit 3（照らしていない）、壊れた JSON・dict でない
event → exit 2。手元（CI でない）で event が無いのは前のまま（手元には PR の event が無いと名指す）。
"""
import os
import subprocess
import sys

from public_guard_box import CLEAN_CUSTOMER, ENV_KEYS, GUARD, make_repo


def _cli(repo, env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env.update({"AF_DENY_WORDS": CLEAN_CUSTOMER, **env_extra})
    return subprocess.run([sys.executable, str(GUARD), "--repo", str(repo), "--range", "ALL"],
                          env=env, capture_output=True, text=True, timeout=60)


def test_注入_CI_で_event_の_file_が無いと照らしていないで止まる(tmp_path):
    repo = make_repo(tmp_path / "r")
    r = _cli(repo, {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_PATH": str(tmp_path / "無い.json")})
    assert r.returncode == 3 and "GITHUB_EVENT_PATH の event の file が無い" in r.stdout, r.stdout + r.stderr
    r = _cli(repo, {"GITHUB_ACTIONS": "true"})
    assert r.returncode == 3 and "PR の題・本文" in r.stdout, r.stdout + r.stderr


def test_注入_壊れた_event_は_exit_2_で止まる(tmp_path):
    repo = make_repo(tmp_path / "r")
    for body in ("{壊れた", "[1, 2]", "\udcff"):
        ev = tmp_path / "ev.json"
        ev.write_bytes(body.encode("utf-8", "surrogateescape"))
        for ci in ({"GITHUB_ACTIONS": "true"}, {}):
            r = _cli(repo, {**ci, "GITHUB_EVENT_PATH": str(ev)})
            assert r.returncode == 2 and "event を読めない" in r.stdout, (body, ci, r.stdout + r.stderr)


def test_読める_event_の_PR_の本文は照らす(tmp_path):
    """直した後も、読める event の PR の題・本文は照らす（止める側へ倒しすぎて照らす道を塞いでいない）。"""
    import json
    repo = make_repo(tmp_path / "r")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    ev = tmp_path / "ev.json"
    ev.write_text(json.dumps({"pull_request": {"title": "t", "body": "ghp_" + "c" * 36,
                                               "base": {"sha": head, "ref": "main"}, "head": {"sha": head}}}),
                  encoding="utf-8")
    r = _cli(repo, {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_PATH": str(ev)})
    assert r.returncode == 1 and "PR の本文" in r.stdout, r.stdout + r.stderr


