"""レビューの関所（plugins/checker/scripts/review_gate.py）が、必須の検査を持てない repo で遅い検査の前に通らず、鍵の効かない 401 の訳を隠さないか。

意図: 関所は「走った検査が全部緑」を GitHub の記録から確かめ、読めない時は本当の訳を出して止まる。
課題: 必須の検査を持てない repo（無料のプランの非公開 repo）では、先に終わった速い検査の check run だけが先端に在り、
遅い job の check run がまだ作られていない間に通りえた。鍵の効かない 401 を鍵なしで読み直すと、非公開の repo では 404 になり訳が隠れた。
原因: 「走った検査」を check run だけで数え、走り始めた workflow を見ていなかった。読み直しの失敗で元の訳を捨てていた。
ここでは誤りの類（workflow が走り中・workflow が赤・401 を 404 に差し替え）をわざと入れ、拒むかを見る。
"""
import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_gate_hashiri", ROOT / "plugins" / "checker" / "scripts" / "review_gate.py")
rg = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(rg)

HEAD = "0123456789abcdef0123456789abcdef01234567"
PLAN_403 = {"message": "Upgrade to GitHub Pro or make this repository public to enable this feature."}


def _http(code, body):
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", {}, io.BytesIO(json.dumps(body).encode("utf-8")))


def _github(rules_err, wf_status="completed", wf_conclusion="success"):
    def get(path, token):
        if "/rules/branches/" in path:
            raise rules_err
        if path.startswith("/repos/o/r/pulls/1"):
            return {"state": "open", "merged": False, "mergeable_state": "clean", "head": {"sha": HEAD}, "base": {"ref": "main"}}
        if "/check-runs" in path:
            return {"check_runs": [{"name": "lint", "status": "completed", "conclusion": "success",
                                    "completed_at": "2026-11-22T01:00:00Z"}]}
        if "/actions/runs" in path:
            return {"workflow_runs": [{"name": "ci", "status": wf_status, "conclusion": wf_conclusion,
                                       "created_at": "2026-11-22T01:00:00Z"}]}
        return []
    return get


def test_必須の検査を持てない_repo_は_workflow_の走りが終わって緑になるまで通さない(monkeypatch):
    monkeypatch.setattr(rg, "_get", _github(_http(403, PLAN_403), "in_progress", None))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 1          # 速い検査 lint だけ緑・workflow ci は走り中
    monkeypatch.setattr(rg, "_get", _github(_http(403, PLAN_403), "completed", "failure"))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 1
    monkeypatch.setattr(rg, "_get", _github(_http(403, PLAN_403)))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 0
    monkeypatch.setattr(rg, "_get", _github(_http(403, {"message": "Must have admin rights to Repository."})))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 2          # 権限の 403 は今までどおり止める


def test_workflow_の走りは同じ名の新しい物を取る():
    assert rg.workflow_states([{"name": "ci", "status": "completed", "conclusion": "failure", "created_at": "1"},
                               {"name": "ci", "status": "completed", "conclusion": "success", "created_at": "2"},
                               {"name": "e2e", "status": "queued", "conclusion": None, "created_at": "1"}]) \
        == {"workflow ci": "success", "workflow e2e": "queued"}


def test_鍵の効かない_401_は鍵なしの_404_に訳を隠さない(monkeypatch):
    calls = []

    def urlopen(req, timeout):
        calls.append(req.headers.get("Authorization"))
        raise _http(401 if req.headers.get("Authorization") else 404, {"message": "x"})
    monkeypatch.setattr(rg.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError) as got:
        rg._get("/repos/o/r", "tok")
    assert got.value.code == 401 and len(calls) == 2
