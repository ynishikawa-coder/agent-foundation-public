"""合流の関所を機械で照らす（merge_gate.py）・頼み直しで前回の止めるを番号で照らす・窓の id の 3 つの形・使う側の点（注入の試験）。

台帳の行: 合流の関所が目で読むだけ／前回 red の止めるを照らさずに頼み直せる／判定の 1 行目が session_ だけ／
使う側の足す点の置き場が無い。どれも誤りの類を作り物で入れて、道具が拒む（入れない・形の誤り）ことを示す。
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_checker import GREEN

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins" / "checker" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
import merge_gate as MG  # noqa: E402
import verdict_form as VF  # noqa: E402

HEAD = "0123456789ab" + "0" * 28
BODY = "親窓: session_PARENT01\n書いた窓: session_WRITER01\njob: 作り物\n"
COMMIT = {"message": "作り物の直し\n\nClaude-Session: https://claude.ai/code/session_WRITER01", "parents": 1}
RED = GREEN.replace("判定: green", "判定: red").replace("見た先端: 0123456789ab", "見た先端: aaaaaaaaaaaa").replace(
    "## verdict\ngreen", "## verdict\nred\n直し: 細目 §3「まず構造を疑う」").replace(
    "- [台帳へ｜整地] 作り物の気づき", "- [止める｜実装] 作り物の 1 つ目\n- [止める｜実装] 作り物の 2 つ目")
FIXED = GREEN.replace("- [台帳へ｜整地] 作り物の気づき",
                      "- [直った｜実装] 前回の 1 番 — 作り物\n- [直った｜実装] 前回の 2 番 — 作り物")


def c(body, who="OWNER", at="2026-11-19T12:00:00Z"):
    return {"body": body, "author_association": who, "created_at": at}


def data(*comments, body=BODY, commits=(COMMIT,), head=HEAD, base="main", base_changed_at=None):
    return {"body": body, "head": head, "base": base, "default_branch": "main", "base_changed_at": base_changed_at,
            "commits": list(commits), "comments": [x if isinstance(x, dict) else c(x) for x in comments]}


def test_別の窓の_green_が今の先端に在れば入れてよい():
    ok, why = MG.judge(data(GREEN), extra={})
    assert ok, why


@pytest.mark.parametrize("name,d", [
    ("判定が無い", data()),
    ("書いた窓の名乗りが無い", data(GREEN, body="job: 作り物\n")),
    ("green が古い先端", data(GREEN.replace("0123456789ab", "bbbbbbbbbbbb"))),
    ("green の窓が書いた窓（本文）", data(GREEN.replace("session_REVIEW01", "session_WRITER01", 1))),
    ("green の窓が commit の書いた窓", data(GREEN, commits=[{"message": "x\n\nClaude-Session: https://claude.ai/code/session_REVIEW01", "parents": 1}])),
    ("green の形が崩れた", data(GREEN.replace("- 12 既定で止まる: N/A\n", ""))),
    ("前回の止めるを照らさない頼み直し", data(RED, GREEN)),
    ("先端が分からない", data(GREEN, head="")),
    # 再レビューの red で挙がった類（注入）
    ("持ち主・仲間でない人の green", data(c(GREEN, who="NONE"))),
    ("書き手の分からない字だけの green", {**data(), "comments": [GREEN]}),
    ("green の後に別の窓の red", data(GREEN, RED.replace("aaaaaaaaaaaa", "0123456789ab").replace("session_REVIEW01", "session_REVIEW02", 1))),
    ("書いた窓が cse_ で名乗り自分で green", data(GREEN.replace("session_REVIEW01", "cse_WRITER02", 1),
                                              commits=[{"message": "x\n\nClaude-Session: https://claude.ai/code/cse_WRITER02", "parents": 1}],
                                              body=BODY.replace("session_WRITER01", "session_WRITER02"))),
    ("書いた窓が UUID で名乗り別の窓の commit が混ざる", data(GREEN, commits=[COMMIT, {"message": "x\n\nClaude-Session: 0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0", "parents": 1}])),
    ("名乗りの無い commit", data(GREEN, commits=[COMMIT, {"message": "名乗りなし", "parents": 1}])),
    ("base が main でない", data(GREEN, base="claude/下の枝")),
    ("本文に積んだ基点が残る", data(GREEN, body=BODY + "積んだ基点: abcdef123456\n")),
    ("main へ向け直す前の green", data(c(GREEN, at="2026-11-19T11:00:00Z"), base_changed_at="2026-11-19T11:30:00Z")),
])
def test_関所は誤りの類を入れない(name, d):
    ok, why = MG.judge(d, extra={})
    assert not ok, name


def test_前回の止めるを全部番号で照らした_green_は入れてよい():
    ok, why = MG.judge(data(RED, FIXED), extra={})
    assert ok, why


def test_cse_と_UUID_の名乗りも書いた窓に揃えて数える():
    body = BODY.replace("session_WRITER01", "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0")
    commits = [{"message": "x\n\nClaude-Session: 0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0", "parents": 1}]
    green = GREEN.replace("書いた窓 session_WRITER01", "書いた窓 0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0")
    ok, why = MG.judge(data(green, body=body, commits=commits), extra={})
    assert ok, why
    ok, _ = MG.judge(data(green.replace("session_REVIEW01", "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0", 1), body=body, commits=commits), extra={})
    assert not ok


def test_red_の後に先端を動かして付いた_green_は入れてよい():
    ok, why = MG.judge(data(c(RED, at="2026-11-19T10:00:00Z"), c(FIXED, at="2026-11-19T11:00:00Z")), extra={})
    assert ok, why


def test_向け直した後の_green_は数える():
    ok, why = MG.judge(data(c(GREEN, at="2026-11-19T12:00:00Z"), base_changed_at="2026-11-19T11:30:00Z"), extra={})
    assert ok, why


def test_merge_の_commit_の名乗りは書いた窓に数えない():
    merge = {"message": "Merge\n\nClaude-Session: https://claude.ai/code/session_REVIEW01", "parents": 2}
    ok, why = MG.judge(data(GREEN, commits=[COMMIT, merge]), extra={})
    assert ok, why


def test_命令は材料の_JSON_で回り_入れない時は_exit_1(tmp_path):
    f = tmp_path / "pr.json"
    for d, rc in ((data(GREEN), 0), (data(), 1)):
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        res = subprocess.run([sys.executable, "-B", str(SCRIPTS / "merge_gate.py"), "--json", str(f), "--extra-points", "{}"],
                             capture_output=True, text=True)
        assert res.returncode == rc, res.stdout + res.stderr


def test_CI_は_main_の道具で回り先端の状態に書く():
    wf = (ROOT / ".github" / "workflows" / "merge-gate.yml").read_text(encoding="utf-8")
    assert "issue_comment" in wf and "statuses: write" in wf
    assert "default_branch" in wf, "PR の枝の道具で照らすと枝が道具を書き換えて自分を通せる"
    assert "pull_request_target" in wf and "\n  pull_request:" not in wf, "pull_request で回すと yml が PR の枝の物になり、枝が状態を書ける"
    assert "concurrency" in wf and "cancel-in-progress: true" in wf, "古い材料の回が後から状態を上書きする"
    assert "head.sha" not in wf and "head.ref" not in wf, "PR の枝のコードを取ると main の権限で枝のコードが回る"
    assert "merge_gate.py --github" in wf and "--status" in wf


def test_合流の手順は目で読まず_merge_gate_の状態を見る():
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "`merge-gate`（`.github/workflows/merge-gate.yml`・道具は `plugins/checker/scripts/merge_gate.py`）が success の PR だけ" in text


# ── 頼み直し（verdict_form --previous）──
def test_頼み直しで前回の止めるを欠くと誤り():
    errs = VF.check(FIXED.replace("- [直った｜実装] 前回の 2 番 — 作り物\n", ""), writer="session_WRITER01",
                    head=HEAD, previous=RED, extra={})
    assert any("前回の止める 2 番" in e for e in errs), errs


def test_頼み直しで見た先端が前回と同じなら誤り():
    errs = VF.check(FIXED, writer="session_WRITER01", head=HEAD, previous=RED.replace("aaaaaaaaaaaa", "0123456789ab"), extra={})
    assert any("前回と同じ" in e for e in errs), errs


def test_頼み直しで全部照らせば通る():
    assert VF.check(FIXED, writer="session_WRITER01", head=HEAD, previous=RED, extra={}) == []


# ── 窓の id の 3 つの形 ──
@pytest.mark.parametrize("win", ["cse_REVIEW01", "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"])
def test_判定の窓は_cse_と_UUID_も受ける(win):
    assert VF.check(GREEN.replace("session_REVIEW01", win, 1), writer="session_WRITER01", head=HEAD, extra={}) == []


def test_cse_と_session_は同じ窓として別の目を照らす():
    errs = VF.check(GREEN.replace("session_REVIEW01", "cse_WRITER01", 1), writer="session_WRITER01", head=HEAD, extra={})
    assert any("別の目でない" in e for e in errs), errs


def test_形の外の窓の_id_は誤り():
    errs = VF.check(GREEN.replace("session_REVIEW01", "window-1", 1), writer="session_WRITER01", head=HEAD, extra={})
    assert any("1 行目" in e for e in errs), errs


# ── 使う側の点 ──
EXTRA = {"J1": "作り物の点"}
WITH_EXTRA = GREEN.replace("## 所見", "## 使う側の点\n- J1 作り物の点: pass\n\n## 所見")


def test_使う側の点が全部在れば通る():
    assert VF.check(WITH_EXTRA, writer="session_WRITER01", head=HEAD, extra=EXTRA) == []


def test_使う側の点の_fail_は_red_に結ぶ():
    errs = VF.check(WITH_EXTRA.replace("J1 作り物の点: pass", "J1 作り物の点: fail（作り物）"),
                    writer="session_WRITER01", head=HEAD, extra=EXTRA)
    assert any("判定は red" in e for e in errs), errs


@pytest.mark.parametrize("text,extra", [(GREEN, EXTRA), (WITH_EXTRA, {}),
                                        (WITH_EXTRA.replace("J1 作り物", "J9 作り物"), EXTRA)])
def test_使う側の点の欠け_表に無い点は誤り(text, extra):
    assert VF.check(text, writer="session_WRITER01", head=HEAD, extra=extra)


def test_使う側の点は値の表から読む(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "skill-values.json").write_text(
        json.dumps({"checker": {"review-pr": {"extra_points": EXTRA}}}, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert VF.load_extra(starts=[str(tmp_path)]) == EXTRA


@pytest.mark.parametrize("writer,head", [(",", HEAD), ("x", HEAD), ("session_WRITER01", "x")])
def test_形の外の_writer_head_は照らさずに通さない(tmp_path, writer, head):
    f = tmp_path / "v.md"
    f.write_text(GREEN.replace("- 3 別の目: 書いた窓 session_WRITER01 ≠ この窓", "- 3 別の目: pass"), encoding="utf-8")
    res = subprocess.run([sys.executable, "-B", str(SCRIPTS / "verdict_form.py"), str(f), "--writer", writer, "--head", head,
                          "--extra-points", "{}"], capture_output=True, text=True)
    assert res.returncode == 2, res.stdout + res.stderr


def test_点_3_は別の目の形しか受けない():
    errs = VF.check(GREEN.replace("- 3 別の目: 書いた窓 session_WRITER01 ≠ この窓", "- 3 別の目: pass"),
                    writer="session_WRITER01", head=HEAD, extra={})
    assert errs
