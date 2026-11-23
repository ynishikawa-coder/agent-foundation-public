"""レビューの関所（plugins/checker/scripts/review_gate.py）が、名が同じで app か check_suite が違う check run を別に数える約束。

意図: 関所は先端の必須の検査が全部緑と確かめてから通す。
課題: 同じ名の check run が別の app・別の check_suite で 2 本在り、片方が赤でも、新しい方の緑だけで関所が通りえた。
原因: check_states が check run を名だけで束ね、同じ名は新しい 1 本だけを残していた（別の suite の run を走り直しと同じに扱った）。
ここでは誤りの類（別の suite・別の app の同名の赤・走り中）をわざと入れ、拒むかを見る。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_gate_check_suite", ROOT / "plugins" / "checker" / "scripts" / "review_gate.py")
rg = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(rg)

HEAD = "0123456789abcdef0123456789abcdef01234567"


def _cr(conclusion, when, app=1, suite=10, status="completed", name="test"):
    return {"name": name, "status": status, "conclusion": conclusion, "completed_at": when, "started_at": when,
            "app": {"id": app, "slug": "app%d" % app}, "check_suite": {"id": suite}}


def _github(runs):
    def get(path, token):
        if "/rules/branches/" in path:
            return [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "test"}]}}]
        if path.startswith("/repos/o/r/pulls/1"):
            return {"state": "open", "merged": False, "mergeable_state": "clean", "head": {"sha": HEAD}, "base": {"ref": "main"}}
        if "/check-runs" in path:
            return {"check_runs": runs}
        if "/actions/runs" in path:   # どの suite も workflow の走りに無い＝別の検査として数える
            return {"workflow_runs": []}
        return []
    return get


def test_別の_check_suite_の同名の赤は新しい緑で隠れない(monkeypatch):
    """注入: suite 10 の test が赤（古い）・suite 11 の test が緑（新しい）→ 関所は通さない。"""
    monkeypatch.setattr(rg, "_get", _github([_cr("failure", "2026-11-23T01:00:00Z", suite=10),
                                             _cr("success", "2026-11-23T01:00:05Z", suite=11)]))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 1


def test_別の_app_の同名の赤は新しい緑で隠れない(monkeypatch):
    monkeypatch.setattr(rg, "_get", _github([_cr("success", "2026-11-23T01:00:05Z", app=1, suite=10),
                                             _cr("failure", "2026-11-23T01:00:00Z", app=2, suite=20)]))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 1


def test_別の_suite_の同名が走り中なら通さない(monkeypatch):
    monkeypatch.setattr(rg, "_get", _github([_cr(None, "2026-11-23T01:00:00Z", suite=10, status="in_progress"),
                                             _cr("success", "2026-11-23T01:00:05Z", suite=11)]))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 1


def test_別の_suite_が両方緑なら通す(monkeypatch):
    monkeypatch.setattr(rg, "TIP", "fedcba987654")   # main の先端の版（判定が従う決まりの版）
    monkeypatch.setattr(rg, "_get", _github([_cr("success", "2026-11-23T01:00:00Z", suite=10),
                                             _cr("success", "2026-11-23T01:00:05Z", suite=11)]))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 0


def test_同じ_app_同じ_suite_の走り直しは新しい物を取る():
    """走り直し（同じ名・同じ app・同じ suite）は今までどおり新しい方だけを見る（赤を直して走り直した後に通れる）。"""
    assert rg.check_states([_cr("failure", "2026-11-23T01:00:00Z"), _cr("success", "2026-11-23T01:00:05Z")], []) \
        == {"test": "success"}
    assert rg.check_states([_cr("success", "2026-11-23T01:00:00Z"), _cr("failure", "2026-11-23T01:00:05Z")], []) \
        == {"test": "failure"}


def test_順に依らず赤を残す():
    """並びが逆（緑の suite が先・赤の suite が後）でも、名の状態は緑でない方。"""
    runs = [_cr("success", "2026-11-23T01:00:05Z", suite=11), _cr("cancelled", "2026-11-23T01:00:00Z", suite=10)]
    assert rg.check_states(runs, []) == {"test": "cancelled"}
    assert rg.check_states(list(reversed(runs)), []) == {"test": "cancelled"}
