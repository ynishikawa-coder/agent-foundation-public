"""レビューの関所（plugins/checker/scripts/review_gate.py）が、名が同じで event が違う workflow の走りを両方照らす約束。

意図: 必須の検査を持てない repo では、関所は先端で走った workflow を全部緑と確かめてから通す。
課題: 同じ名の workflow が pull_request と push で 2 本走り、古い方が check run を作る前に赤で終わっても、
新しい方の緑だけで関所が通りえた。
原因: workflow の走りを名だけで束ね、同じ名は新しい 1 本だけを残していた（event の違う別の走りを走り直しと同じに扱った）。
ここでは誤りの類（古い同名の走りの赤・まだ走り中）をわざと入れ、拒むかを見る。
"""
import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_gate_onaji_na", ROOT / "plugins" / "checker" / "scripts" / "review_gate.py")
rg = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(rg)

HEAD = "0123456789abcdef0123456789abcdef01234567"
PLAN_403 = {"message": "Upgrade to GitHub Pro or make this repository public to enable this feature."}


def _github(wruns):
    def get(path, token):
        if "/rules/branches/" in path:
            raise urllib.error.HTTPError("https://api.github.com/x", 403, "err", {},
                                         io.BytesIO(json.dumps(PLAN_403).encode("utf-8")))
        if path.startswith("/repos/o/r/pulls/1"):
            return {"state": "open", "merged": False, "mergeable_state": "clean", "head": {"sha": HEAD}, "base": {"ref": "main"}}
        if "/check-runs" in path:
            return {"check_runs": [{"name": "test", "status": "completed", "conclusion": "success",
                                    "completed_at": "2026-11-23T01:00:00Z"}]}
        if "/actions/runs" in path:
            return {"workflow_runs": wruns}
        return []
    return get


def _run(name, event, conclusion, when, status="completed"):
    return {"name": name, "event": event, "status": status, "conclusion": conclusion, "created_at": when}


def test_古い同名の_workflow_の赤は新しい同名の緑で隠れない(monkeypatch):
    """注入: pull_request の ci が赤（古い）・push の ci が緑（新しい）→ 関所は通さない。"""
    monkeypatch.setattr(rg, "_get", _github([_run("ci", "pull_request", "failure", "2026-11-23T01:00:00Z"),
                                             _run("ci", "push", "success", "2026-11-23T01:00:05Z")]))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 1


def test_古い同名の_workflow_が走り中なら通さない(monkeypatch):
    monkeypatch.setattr(rg, "_get", _github([_run("ci", "push", None, "2026-11-23T01:00:00Z", "in_progress"),
                                             _run("ci", "pull_request", "success", "2026-11-23T01:00:05Z")]))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 1


def test_両方の_event_が緑なら通す(monkeypatch):
    monkeypatch.setattr(rg, "_get", _github([_run("ci", "pull_request", "success", "2026-11-23T01:00:00Z"),
                                             _run("ci", "push", "success", "2026-11-23T01:00:05Z")]))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 0


def test_同じ名と同じ_event_の走り直しは新しい物を取る():
    """走り直し（同じ名・同じ event）は今までどおり新しい方だけを見る（赤を直して走り直した後に通れる）。"""
    assert rg.workflow_states([_run("ci", "pull_request", "failure", "1"), _run("ci", "pull_request", "success", "2"),
                               _run("ci", "push", "failure", "1")]) \
        == {"workflow ci (pull_request)": "success", "workflow ci (push)": "failure"}
