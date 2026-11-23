"""レビューの関所（plugins/checker/scripts/review_gate.py）が、同じ workflow を走らせ直した新しい suite の結果で古い suite の
結果を上書きする約束（古い赤のまま止めない・別の workflow の同名の赤は隠さない）。

意図: 関所は先端の必須の検査が今どうかで通す・止める。
課題: PR の本文を直す（pull_request の edited）と、同じ先端に同じ workflow の新しい走り＝新しい check suite が出来る。
      本文を直す前の赤（古い suite）が残り、直した後の緑（新しい suite）が在っても関所は赤のまま止めた。
原因: check_states が check run を (名, app, check_suite) で束ね、suite が違えば別の検査として赤を残した。suite が同じ
      workflow の走り直しか、別の workflow かを見ていなかった（同じ先端の workflow の走りを読んでいなかった）。
ここでは誤りの類（走り直しの古い赤を残す・別の workflow の同名の赤を新しい緑で隠す・push と pull_request を混ぜる）を
わざと入れ、正しく分けるかを見る。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_gate_hashiri_naoshi", ROOT / "plugins" / "checker" / "scripts" / "review_gate.py")
rg = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(rg)

HEAD = "0123456789abcdef0123456789abcdef01234567"


def _cr(conclusion, when, suite, status="completed", name="check"):
    return {"name": name, "status": status, "conclusion": conclusion, "completed_at": when, "started_at": when,
            "app": {"id": 15368, "slug": "github-actions"}, "check_suite": {"id": suite}}


def _wr(suite, wf, created, event="pull_request", conclusion="success"):
    return {"check_suite_id": suite, "workflow_id": wf, "name": "ci", "event": event, "created_at": created,
            "status": "completed", "conclusion": conclusion}


def _github(runs, wruns):
    def get(path, token):
        if "/rules/branches/" in path:
            return [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "check"}]}}]
        if path.startswith("/repos/o/r/pulls/1"):
            return {"state": "open", "merged": False, "mergeable_state": "clean", "head": {"sha": HEAD}, "base": {"ref": "main"}}
        if "/check-runs" in path:
            return {"check_runs": runs}
        if "/actions/runs" in path:
            return {"workflow_runs": wruns}
        return []
    return get


def test_本文を直した走り直しの緑で古い赤を上書きして通す(monkeypatch):
    """注入: 同じ workflow 5 の suite 10（古い・赤）と suite 11（edited の走り直し・緑）→ 関所は通す。"""
    monkeypatch.setattr(rg, "TIP", "fedcba987654")
    monkeypatch.setattr(rg, "_get", _github([_cr("failure", "2026-11-23T01:00:00Z", 10), _cr("success", "2026-11-23T01:05:00Z", 11)],
                                            [_wr(10, 5, "2026-11-23T00:59:00Z"), _wr(11, 5, "2026-11-23T01:04:00Z")]))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 0


def test_走り直しは_run_の時刻でなく_suite_の生まれで新しい方():
    """新しい suite の run が古い suite の run より早く終わっても（並びの時刻のずれ）、新しい suite の結果を取る。"""
    runs = [_cr("failure", "2026-11-23T01:09:00Z", 10), _cr("success", "2026-11-23T01:05:00Z", 11)]
    wruns = [_wr(10, 5, "2026-11-23T00:59:00Z"), _wr(11, 5, "2026-11-23T01:04:00Z")]
    assert rg.check_states(runs, [], wruns) == {"check": "success"}
    runs = [_cr("success", "2026-11-23T01:00:00Z", 10), _cr("failure", "2026-11-23T01:05:00Z", 11)]
    assert rg.check_states(runs, [], wruns) == {"check": "failure"}    # 走り直しが赤なら赤


def test_別の_workflow_の同名の赤は新しい緑で隠れない(monkeypatch):
    """注入: workflow 5 の check が赤・workflow 6 の同名の check が緑（新しい）→ 関所は通さない。"""
    monkeypatch.setattr(rg, "_get", _github([_cr("failure", "2026-11-23T01:00:00Z", 10), _cr("success", "2026-11-23T01:05:00Z", 11)],
                                            [_wr(10, 5, "2026-11-23T00:59:00Z"), _wr(11, 6, "2026-11-23T01:04:00Z")]))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 1


def test_同じ_workflow_でも_event_が違えば別に数える():
    runs = [_cr("failure", "2026-11-23T01:00:00Z", 10), _cr("success", "2026-11-23T01:05:00Z", 11)]
    wruns = [_wr(10, 5, "2026-11-23T00:59:00Z", event="push"), _wr(11, 5, "2026-11-23T01:04:00Z")]
    assert rg.check_states(runs, [], wruns) == {"check": "failure"}


def test_workflow_の走りに無い_suite_は今までどおり別に数える():
    runs = [_cr("failure", "2026-11-23T01:00:00Z", 10), _cr("success", "2026-11-23T01:05:00Z", 11)]
    assert rg.check_states(runs, [], [_wr(11, 5, "2026-11-23T01:04:00Z")]) == {"check": "failure"}
    assert rg.check_states(runs, []) == {"check": "failure"}


def test_走り直しが飛ばした_run_は前の赤を消さない():
    """注入: edited の走りで job を飛ばした（skipped）新しい suite → 前の suite の赤を残す。"""
    runs = [_cr("failure", "2026-11-23T01:00:00Z", 10), _cr("skipped", "2026-11-23T01:05:00Z", 11)]
    wruns = [_wr(10, 5, "2026-11-23T00:59:00Z"), _wr(11, 5, "2026-11-23T01:04:00Z")]
    assert rg.check_states(runs, [], wruns) == {"check": "failure"}


def test_同じ先端を持つ別の_PR_の走りで赤を消さない():
    """注入: 新しい緑の suite が別の PR（2 番）の走り → この PR（1 番）の赤を残す。"""
    runs = [_cr("failure", "2026-11-23T01:00:00Z", 10), _cr("success", "2026-11-23T01:05:00Z", 11)]
    wruns = [dict(_wr(10, 5, "2026-11-23T00:59:00Z"), pull_requests=[{"number": 1}]),
             dict(_wr(11, 5, "2026-11-23T01:04:00Z"), pull_requests=[{"number": 2}])]
    assert rg.check_states(runs, [], wruns, 1) == {"check": "failure"}
    wruns[1]["pull_requests"] = [{"number": 1}]
    assert rg.check_states(runs, [], wruns, 1) == {"check": "success"}


def test_Actions_を読めない鍵でも必須の検査が緑なら関所は今までどおり通す(monkeypatch):
    """注入: /actions/runs が 403 → 走りを束ねず suite ごとに数える（読めないから止める・通すにしない）。"""
    import io
    import urllib.error
    base = _github([_cr("success", "2026-11-23T01:00:00Z", 10)], [])

    def get(path, token):
        if "/actions/runs" in path:
            raise urllib.error.HTTPError(path, 403, "Resource not accessible", {}, io.BytesIO(b"{}"))
        return base(path, token)
    monkeypatch.setattr(rg, "TIP", "fedcba987654")
    monkeypatch.setattr(rg, "_get", get)
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 0
