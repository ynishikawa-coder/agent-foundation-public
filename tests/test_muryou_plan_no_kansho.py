"""無料のプランの非公開 repo でも、レビューの関所が走った検査の全緑で通し、赤・走り中・衝突は拒むか。

意図: 合流の条件（核 §7 の確かめと衝突なし）だけで main へ入れ、道具の都合で止めない。
課題: 無料のプランの非公開 repo は必須の検査を持てず（rules が 403「Upgrade to GitHub Pro」）、関所が常に「まだ」を返した。
原因: 関所が「必須の検査が読めない」と「持てない」を区別していなかった。オーナーの答え 2026-11-22。
ここでは誤りの類（赤・走り中・衝突・プラン以外の 403）をわざと入れ、拒むかを見る。
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


def pr(**k):
    base = {"state": "open", "merged": False, "mergeable_state": "clean", "head": {"sha": HEAD}, "base": {"ref": "main"}}
    base.update(k)
    return base


def test_必須の検査を持てない_repo_は走った検査の全緑で通し_赤と走り中は拒む():
    # 無料のプランの非公開 repo（rules が 403「Upgrade to GitHub Pro」）: オーナーの答え 2026-11-22
    assert rg.decide(pr(), rg.PLAN_NONE, {}, [])[0] == "入ってよい"                       # 検査が 1 つも無い
    assert rg.decide(pr(), rg.PLAN_NONE, {"check": "success"}, [])[0] == "入ってよい"
    assert rg.decide(pr(), rg.PLAN_NONE, {"check": "failure"}, [])[0] == "まだ"
    assert rg.decide(pr(), rg.PLAN_NONE, {"check": "in_progress"}, [])[0] == "まだ"
    assert rg.decide(pr(mergeable_state="dirty"), rg.PLAN_NONE, {}, [])[0] == "まだ"


def test_rules_の_403_はプランの返しだけを持てない_repo_と読み_他の_403_は読めない(monkeypatch):
    import io
    import urllib.error

    def raiser(body):
        def _g(*a):
            raise urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(body))
        return _g
    monkeypatch.setattr(rg, "_get", raiser(b'{"message":"Upgrade to GitHub Pro or make this repository public"}'))
    assert rg._rules("o/r", "main", "") is rg.PLAN_NONE
    monkeypatch.setattr(rg, "_get", raiser(b'{"message":"Resource not accessible by integration"}'))
    try:
        rg._rules("o/r", "main", "")
        raise AssertionError("他の 403 を持てない repo と読んだ")
    except urllib.error.HTTPError:
        pass
