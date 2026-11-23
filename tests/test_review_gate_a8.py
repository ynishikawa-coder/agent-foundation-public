"""レビューの関所（plugins/checker/scripts/review_gate.py）の 3 つの穴をわざと入れて拒むかを見る。

意図: 関所は、レビューの窓が判定に入ってよいかを GitHub の記録だけで決め、決められない時は訳と直し方を言う。
課題と原因:
- 題・本文だけを直した PR を同じ先端で見直せなかった＝判定を先端だけで数え、題・本文の版を持たなかった。
- 古い status の緑・同じ名の check run の緑が、新しい status の赤を隠した＝status を 1 つの名で最初の物に寄せ、run の在る名は status を捨てた。
- 窓に付いていない repo の 403 を「読めない」とだけ言い、直し方（add_repo）を言わなかった＝403 の本文を読まずに捨てた。
"""
import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_gate_a8", ROOT / "plugins" / "checker" / "scripts" / "review_gate.py")
rg = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(rg)

HEAD = "0123456789abcdef0123456789abcdef01234567"


def _pr(title="題", body="本文"):
    return {"state": "open", "merged": False, "mergeable_state": "clean", "head": {"sha": HEAD},
            "base": {"ref": "main"}, "title": title, "body": body}


def _verdict(text_line=""):
    return {"body": "レビューした窓: session_x 判定: green\n見た先端: %s\n決まりの版: aaaaaaaaaaaa\n%s" % (HEAD[:12], text_line)}


def test_題と本文を直した後は_同じ先端でも見直せる():
    old = rg.text_version(_pr(body="古い本文"))
    kind, _ = rg.decide(_pr(body="新しい本文"), ["check"], {"check": "success"}, [_verdict("見た本文: %s" % old)])
    assert kind == "入ってよい"


def test_同じ題と本文の版の判定は_済み():
    now = rg.text_version(_pr())
    kind, why = rg.decide(_pr(), ["check"], {"check": "success"}, [_verdict("見た本文: %s" % now)])
    assert kind == "済み" and now in why[0]


def test_見た本文の無い判定は_先端だけで数える():
    kind, _ = rg.decide(_pr(body="直した本文"), ["check"], {"check": "success"}, [_verdict()])
    assert kind == "済み"


def test_題と本文の版は改行の違いで変わらない():
    assert rg.text_version(_pr(body="a\r\nb")) == rg.text_version(_pr(body="a\nb"))


def test_status_は同じ名の新しい物を取る():
    st = rg.check_states([], [{"context": "ci", "state": "failure", "updated_at": "2026-11-23T02:00:00Z"},
                              {"context": "ci", "state": "success", "updated_at": "2026-11-23T01:00:00Z"}])
    assert st == {"ci": "failure"}
    st = rg.check_states([], [{"context": "ci", "state": "success", "updated_at": "2026-11-23T01:00:00Z"},
                              {"context": "ci", "state": "failure", "updated_at": "2026-11-23T02:00:00Z"}])
    assert st == {"ci": "failure"}   # 古い緑が先に並んでも、新しい赤を取る
    st = rg.check_states([], [{"context": "ci", "state": "failure", "updated_at": "2026-11-23T02:00:00Z"},
                              {"context": "ci", "state": "success", "updated_at": "2026-11-23T03:00:00Z"}])
    assert st == {"ci": "success"}   # 赤の後に走り直して緑


def test_同じ名の_status_の赤は_run_の緑で隠れず_関所を通さない():
    runs = [{"name": "check", "status": "completed", "conclusion": "success", "completed_at": "2026-11-23T01:00:00Z"}]
    st = rg.check_states(runs, [{"context": "check", "state": "failure", "updated_at": "2026-11-23T02:00:00Z"}])
    kind, why = rg.decide(_pr(), ["check"], st, [])
    assert kind == "まだ" and "failure" in why[0]


def _main_with_403(body, capsys):
    def read(repo, number, token):
        raise urllib.error.HTTPError("https://api.github.com/x", 403, "Forbidden", {}, io.BytesIO(body.encode("utf-8")))
    rc = rg.main(["--repo", "o/r", "--pr", "1"], read=read)
    return rc, capsys.readouterr().out


def test_窓に付いていない_repo_の_403_は_add_repo_の直し方を言う(capsys):
    rc, out = _main_with_403("GitHub access to this repository is not enabled for this session. Use add_repo to request access", capsys)
    assert rc == 2
    assert 'add_repo で owner=o repo=r access="push"' in out


def test_ほかの_403_は_add_repo_と言わない(capsys):
    rc, out = _main_with_403(json.dumps({"message": "Resource not accessible by integration"}), capsys)
    assert rc == 2 and "add_repo" not in out
