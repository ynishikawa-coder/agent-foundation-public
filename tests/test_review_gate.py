"""レビューの関所（plugins/checker/scripts/review_gate.py）が、CI が赤・main と衝突・同じ先端に判定が在る PR を通さないか。

意図: レビューの窓が見るのは中身だけにし、機械で分かる事でレビューを回さない（1 つの先端に判定は 1 つ）。
課題: CI の赤や main との衝突のままレビューを頼み、同じ先端に判定が 2 つ出て、レビューを 5 回回した。
原因: PR の状態を GitHub の記録から読む関所が無く、頼む・入るを窓の判断に任せていた。
ここでは誤りの類（検査の赤・走り中・無い・衝突・遅れ・閉じた・同じ先端の判定・読めない）をわざと入れ、関所が拒むかを見る。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_gate", ROOT / "plugins" / "checker" / "scripts" / "review_gate.py")
rg = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(rg)

HEAD = "0123456789abcdef0123456789abcdef01234567"
REQ = ["check", "public-guard", "plugin-smoke"]
GREEN = {"check": "success", "public-guard": "success", "plugin-smoke": "success", "overlap": "success"}


def pr(**k):
    base = {"state": "open", "merged": False, "mergeable_state": "clean", "head": {"sha": HEAD}, "base": {"ref": "main"}}
    base.update(k)
    return base


def test_必須の検査が全部緑で衝突なしなら入ってよい():
    assert rg.decide(pr(), REQ, GREEN, []) == ("入ってよい", [])


def test_CI_が赤の_PR_ではレビューに入らない():
    kind, why = rg.decide(pr(), REQ, dict(GREEN, check="failure"), [])
    assert kind == "まだ" and any("check が failure" in w for w in why)


def test_CI_が走り中か先端に無い_PR_ではレビューに入らない():
    assert rg.decide(pr(), REQ, dict(GREEN, check="in_progress"), [])[0] == "まだ"
    states = {k: v for k, v in GREEN.items() if k != "plugin-smoke"}
    kind, why = rg.decide(pr(), REQ, states, [])
    assert kind == "まだ" and any("plugin-smoke が先端" in w for w in why)


def test_衝突のある_PR_ではレビューに入らない():
    kind, why = rg.decide(pr(mergeable_state="dirty"), REQ, GREEN, [])
    assert kind == "まだ" and any("衝突" in w for w in why)


def test_clean_でない_mergeable_state_は全部まだ():
    for ms in ("behind", "blocked", "unstable", "draft", "unknown", None):
        assert rg.decide(pr(mergeable_state=ms), REQ, GREEN, [])[0] == "まだ", ms


def test_閉じた_PR_と必須の検査が読めない所ではレビューに入らない():
    assert rg.decide(pr(state="closed"), REQ, GREEN, [])[0] == "まだ"
    assert rg.decide(pr(), [], GREEN, [])[0] == "まだ"


def test_同じ先端に判定が在れば_2_つ目を出さない():
    done = [{"body": "レビューした窓: session_R1 判定: red\n見た先端: %s\n" % HEAD[:12]}]
    kind, why = rg.decide(pr(), REQ, GREEN, done)
    assert kind == "済み" and "2 つ目" in why[0]
    old = [{"body": "レビューした窓: session_R1 判定: red\n見た先端: ffffffffffff\n"}]
    assert rg.decide(pr(), REQ, GREEN, old)[0] == "入ってよい"   # 前の先端の判定は見直しを止めない


def test_check_run_は新しい物を取り_status_は無い名だけ():
    runs = [{"name": "check", "status": "completed", "conclusion": "failure", "completed_at": "2026-11-22T01:00:00Z"},
            {"name": "check", "status": "completed", "conclusion": "success", "completed_at": "2026-11-22T02:00:00Z"},
            {"name": "plugin-smoke", "status": "in_progress", "conclusion": None, "started_at": "2026-11-22T02:00:00Z"}]
    st = rg.check_states(runs, [{"context": "public-guard", "state": "success"}, {"context": "check", "state": "failure"}])
    assert st == {"check": "success", "plugin-smoke": "in_progress", "public-guard": "success"}


def test_必須の検査の名は_rules_の返しから読む():
    rules = [{"type": "deletion"}, {"type": "required_status_checks", "parameters": {"required_status_checks": [
        {"context": "check"}, {"context": "public-guard"}]}}]
    assert rg.required_contexts(rules) == ["check", "public-guard"]


def test_記録が読めない時は入ってよいと言わず_exit_2(capsys):
    def broken(*a):
        raise OSError("網が無い")
    assert rg.main(["--repo", "o/r", "--pr", "1"], read=broken) == 2
    assert "読めない" in capsys.readouterr().out


def test_入口の_exit_は入ってよいが_0_まだが_1(capsys):
    ok = lambda *a: (pr(), REQ, GREEN, [])                                    # noqa: E731
    red = lambda *a: (pr(mergeable_state="dirty"), REQ, GREEN, [])            # noqa: E731
    assert rg.main(["--repo", "o/r", "--pr", "1"], read=ok) == 0
    assert rg.main(["--repo", "o/r", "--pr", "1"], read=red) == 1
    assert "review_gate: まだ" in capsys.readouterr().out


def test_材料を_file_で受ける口が無い():
    """窓が書いた材料（JSON の file）で関所を通せない。"""
    src = (ROOT / "plugins" / "checker" / "scripts" / "review_gate.py").read_text(encoding="utf-8")
    assert "add_argument(\"--repo\"" in src and "add_argument(\"--pr\"" in src
    assert src.count("add_argument(") == 2


# --- GitHub の無料の版の非公開の repo（ルールセットの口が 403 で「この版には無い」と答える）---
# 誤りの類: 機能が無い版の 403 を「読めない」に畳んで全部止める／ほかの 403・401 を「決まりが無い」に畳んで通す。

import io
import json
import urllib.error


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
    import pytest
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
    import pytest
    calls = []

    def urlopen(req, timeout):
        calls.append(req.headers.get("Authorization"))
        raise _http(401 if req.headers.get("Authorization") else 404, {"message": "x"})
    monkeypatch.setattr(rg.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError) as got:
        rg._get("/repos/o/r", "tok")
    assert got.value.code == 401 and len(calls) == 2
