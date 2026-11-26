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
    assert kind == "済み" and "同じレビュー対象" in why[0]
    old = [{"body": "レビューした窓: session_R1 判定: red\n見た先端: ffffffffffff\n"}]
    assert rg.decide(pr(), REQ, GREEN, old)[0] == "入ってよい"   # 前の先端の判定は見直しを止めない


def test_引用や崩れた判定はレビュー済みとして数えない():
    body = "レビューした窓: session_R1 判定: green\n見た先端: %s\n" % HEAD[:12]
    for text in ("参考の引用\n" + body, body.replace("レビューした窓:", "窓:"), "ただのコメント"):
        assert rg.decide(pr(), REQ, GREEN, [{"body": text}])[0] == "入ってよい"
    assert rg.verdict_for_head(body.replace("session_R1", "cse_R1"), HEAD) == ("session_R1", "green")


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


def test_入口の_exit_は入ってよいが_0_まだが_1(capsys, monkeypatch):
    monkeypatch.setattr(rg, "TIP", "fedcba9876543210" * 2 + "fedcba98")
    ok = lambda *a: (pr(), REQ, GREEN, [])                                    # noqa: E731
    red = lambda *a: (pr(mergeable_state="dirty"), REQ, GREEN, [])            # noqa: E731
    assert rg.main(["--repo", "o/r", "--pr", "1"], read=ok) == 0
    assert rg.main(["--repo", "o/r", "--pr", "1"], read=red) == 1
    assert "review_gate: まだ" in capsys.readouterr().out


def test_合流後だけ_CI_を回す_repo_も既存の検査を省かない(capsys):
    args = ["--repo", "o/r", "--pr", "1"]
    def read(*_, **kw):
        return pr(), [], {}, []
    assert rg.main(args, read=read) == 1
    assert rg.main(args + ["--ci-after-merge"], read=read) == 0
    assert "PR の検査なし（合流前の検証は別）" in capsys.readouterr().out
    for required, states in (([], {"workflow ci": "queued"}), ([], {"lint": "failure"}), (REQ, {})):
        assert rg.decide(pr(), required, states, [], ci_after_merge=True)[0] == "まだ"
    assert rg.decide(pr(), REQ, GREEN, [], ci_after_merge=True)[0] == "入ってよい"
    assert rg.decide(pr(mergeable_state="dirty"), [], {}, [], ci_after_merge=True)[0] == "まだ"


def test_text_correction_same_head_reopens_only_existing_review():
    from pytest import raises
    before = pr(title="誤った題", body="誤った説明")
    after = pr(title="正しい題", body="正しい説明")
    def stamp(who, verdict, rev):
        return {"body": f"レビューした窓: session_{who} 判定: {verdict}\n見た先端: {HEAD[:12]}\n"
                        f"見た本文: {rg.review_text_version(rev)}\n"}
    old = stamp("R1", "red", before)
    fixed = stamp("R1", "green", after)
    other = stamp("R2", "green", after)
    assert rg.decide(before, REQ, GREEN, [old])[0] == "済み"
    assert rg.decide(after, REQ, GREEN, [old])[0] == "入ってよい"
    assert rg.decide(after, REQ, GREEN, [old, fixed])[0] == "済み"
    current = rg.review_text_version(after)
    with raises(ValueError, match="red"):
        rg.require_green([old, other], HEAD, text_version=current)
    assert rg.require_green([old, fixed], HEAD, text_version=current) == ["session_R1"]
    with raises(ValueError, match="green"):
        rg.require_green([stamp("R1", "green", before)], HEAD, text_version=current)
    assert rg.require_green([stamp("R1", "green", before)], HEAD) == ["session_R1"]
