"""レビューの関所（plugins/checker/scripts/review_gate.py）が、GitHub の無料の版の非公開の repo でも照らして通し、ほかの読めない時は止めるか。

意図: 関所はどの repo のレビューにも使える土台の道具であること。
課題: 無料の版の非公開の repo では、ルールセットの口が 403 を返し、関所が毎回「読めない」で止まった。
原因: 「この版にはその機能が無い」の答え（＝決まりが無い事実）と「読めない」を区別する形が無かった。
ここでは誤りの類（機能が無い版の 403 を全止めに畳む／ほかの 403・401 を「決まりが無い」に畳んで通す／遅い検査の前に通す／401 の訳を隠す）をわざと入れ、関所が拒むかを見る。
"""
import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_gate_free_plan", ROOT / "plugins" / "checker" / "scripts" / "review_gate.py")
rg = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(rg)

HEAD = "0123456789abcdef0123456789abcdef01234567"
GREEN = {"check": "success", "public-guard": "success", "plugin-smoke": "success", "overlap": "success"}


def pr(**k):
    base = {"state": "open", "merged": False, "mergeable_state": "clean", "head": {"sha": HEAD}, "base": {"ref": "main"}}
    base.update(k)
    return base


def _http(code, body):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", {}, io.BytesIO(raw))


def _raiser(err):
    def get(path, token):
        raise err
    return get


def test_機能が無い版の_403_は必須の検査の決まりが無いと読む():
    assert rg._rules("o/r", "main", "", get=_raiser(_http(403, {"message": rg.PLAN_LACKS}))) is None


def test_ほかの_403_401_404_と本文の読めない_403_は止める():
    for err in (_http(403, {"message": "Resource not accessible by integration"}),
                _http(403, {"message": rg.PLAN_LACKS + " extra"}),
                _http(403, b"not json"),
                _http(403, ["list"]),
                _http(401, {"message": rg.PLAN_LACKS}),
                _http(404, {"message": rg.PLAN_LACKS})):
        with pytest.raises(urllib.error.HTTPError):
            rg._rules("o/r", "main", "", get=_raiser(err))


def test_決まりが無い版は先端の検査を全部照らし_ほかの照らしはそのまま():
    assert rg.decide(pr(), None, GREEN, []) == ("入ってよい", [])
    kind, why = rg.decide(pr(), None, dict(GREEN, overlap="failure"), [])
    assert kind == "まだ" and any("overlap が failure" in w for w in why)
    assert rg.decide(pr(), None, dict(GREEN, check="in_progress"), [])[0] == "まだ"
    assert rg.decide(pr(), None, {}, [])[0] == "まだ"                       # 検査が 1 つも無い所は通さない
    assert rg.decide(pr(mergeable_state="dirty"), None, GREEN, [])[0] == "まだ"
    assert rg.decide(pr(state="closed"), None, GREEN, [])[0] == "まだ"
    done = [{"body": "レビューした窓: session_R1 判定: green\n見た先端: %s\n" % HEAD[:12]}]
    assert rg.decide(pr(), None, GREEN, done)[0] == "済み"


def _fake_github(rules_err):
    def get(path, token):
        if "/rules/branches/" in path:
            raise rules_err
        if path.startswith("/repos/o/r/pulls/1"):
            return pr()
        if "/check-runs" in path:
            return {"check_runs": [{"name": "build", "status": "completed", "conclusion": "success",
                                    "completed_at": "2026-11-22T01:00:00Z"}]}
        if "/actions/runs" in path:
            return {"workflow_runs": [{"name": "ci", "status": "completed", "conclusion": "success",
                                       "created_at": "2026-11-22T01:00:00Z"}]}
        if path.startswith("/repos/o/r?") or path == "/repos/o/r":
            return {"default_branch": "main"}
        return []
    return get


def test_入口から_機能が無い版は通り_権限の無い_403_は_exit_2(monkeypatch, capsys):
    monkeypatch.setattr(rg, "_get", _fake_github(_http(403, {"message": rg.PLAN_LACKS})))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 0
    assert "必須の検査の決まりを置けない" in capsys.readouterr().out
    monkeypatch.setattr(rg, "_get", _fake_github(_http(403, {"message": "Must have admin rights to Repository."})))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 2
    monkeypatch.setattr(rg, "_get", _fake_github(_http(401, {"message": "Bad credentials"})))
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 2


def test_決まりが無い版は_workflow_の走りが終わるまで通さない(monkeypatch):
    def get(path, token):
        if "/actions/runs" in path:
            return {"workflow_runs": [{"name": "ci", "status": "in_progress", "conclusion": None,
                                       "created_at": "2026-11-22T01:00:00Z"}]}
        return _fake_github(_http(403, {"message": rg.PLAN_LACKS}))(path, token)
    monkeypatch.setattr(rg, "_get", get)
    assert rg.main(["--repo", "o/r", "--pr", "1"]) == 1   # 速い検査 build だけ緑・workflow ci は走り中＝まだ
    assert rg.workflow_states([{"name": "ci", "status": "completed", "conclusion": "failure", "created_at": "1"},
                               {"name": "ci", "status": "completed", "conclusion": "success", "created_at": "2"}]) \
        == {"workflow ci": "success"}


def test_鍵の効かない_401_は鍵なしの_404_に訳を隠さない(monkeypatch):
    calls = []

    def urlopen(req, timeout):
        calls.append(req.headers.get("Authorization"))
        raise _http(401 if req.headers.get("Authorization") else 404, {"message": "x"})
    monkeypatch.setattr(rg.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError) as got:
        rg._get("/repos/o/r", "tok")
    assert got.value.code == 401 and len(calls) == 2
