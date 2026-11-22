"""守りの hook が、秘密・公開の検査で照らせなかった file を「照らした」扱いで黙って通さず、名と訳を添えて出す前に止めるか（注入の試験）。

意図: 秘密の検査は安全の守り。照らせなかった物を照らした物と同じに通すと、鍵が入った file も黙って外へ出る。
課題: outbound の secret_hits は大きすぎる・開けない Artifact の file を、pr_text の public_target は開けない・壊れた workflow を、
黙って飛ばしていた。
原因: 読めない物を「飛ばす」で済ませ、照らせなかった事を誰にも渡さない形だった。
各類（大きすぎる file・開けない file・開けない workflow・壊れた workflow）をわざと入れ、出す前（PreToolUse）に止まり、
止めた文に名と訳が出るのを見る（知らせるだけの道は畳んだ＝聞く線のオーナー同意 2026-11-22）。入力は全部作り物。
"""
import os
import subprocess
from pathlib import Path

import pytest

from test_guard import env, hook  # noqa: F401  （env は fixture）
from test_pr_text import PUBLIC_WORD, _fake_public_repo, gh

GUARD_SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "guard" / "scripts"
KEY = "gh" + "p_" + "A1b2C3d4" * 5          # 作り物の鍵（字をつないで作る＝この file が公開の検査に当たらない）


@pytest.fixture
def outbound(monkeypatch):
    """照らす上限の正本 outbound.MAX_READ を直に読むための module（試験に上限の数を写さない）。"""
    import sys
    monkeypatch.syspath_prepend(str(GUARD_SCRIPTS))
    sys.modules.pop("outbound", None)
    import outbound as ob
    return ob


def publish(cwd, **ti):
    return {"tool_name": "Artifact", "session_id": "s1", "cwd": str(cwd), "tool_input": ti}


def stopped(env, payload):
    """出す前に止めた文（止めなければ ""）。"""
    out = hook(env, "pre", payload)
    return out.get("permissionDecisionReason", "") if out.get("permissionDecision") == "deny" else ""


def test_大きすぎる_Artifact_の_file_は出す前に止め名と訳を添える(env, tmp_path, outbound):
    (tmp_path / "ok.html").write_text("<p>報告</p>", encoding="utf-8")
    (tmp_path / "big.json").write_text("x" * (outbound.MAX_READ + 1), encoding="utf-8")     # 上限のすぐ上
    p = publish(tmp_path, file_path="ok.html", files={"data/big.json": "big.json"})
    got = stopped(env, p)
    assert "照らせなかった" in got and str(tmp_path / "big.json") in got and "大きすぎる" in got
    assert str(tmp_path / "ok.html") not in got            # 照らせた file は名指さない


def test_開けない_Artifact_の_file_は出す前に止め名と訳を添える(env, tmp_path):
    (tmp_path / "ok.html").write_text("<p>報告</p>", encoding="utf-8")
    p = publish(tmp_path, file_path="ok.html", files={"data/gone.json": "無い.json"})
    got = stopped(env, p)
    assert str(tmp_path / "無い.json") in got and "開けない" in got


def test_照らせた_file_だけの_Artifact_は止めない(env, tmp_path):
    (tmp_path / "ok.html").write_text("<p>報告</p>", encoding="utf-8")
    assert stopped(env, publish(tmp_path, file_path="ok.html")) == ""


def test_鍵で止める時も照らせなかった_file_を止めた文に添える(env, tmp_path):
    (tmp_path / "r.html").write_text("<!-- %s -->" % KEY, encoding="utf-8")
    p = publish(tmp_path, file_path="r.html", files={"data/gone.json": "無い.json"})
    out = hook(env, "pre", p)
    why = out.get("permissionDecisionReason", "")
    assert out.get("permissionDecision") == "deny" and "鍵・認証情報の形" in why
    assert "照らせなかった file" in why and "無い.json" in why and KEY not in why


def test_secret_hits_は照らせなかった_file_を呼ぶ側へ渡す(tmp_path, outbound):
    pg = outbound._public_guard()
    assert pg is not None
    big = tmp_path / "big.txt"
    big.write_text(KEY + "x" * (outbound.MAX_READ + 1 - len(KEY)), encoding="utf-8")   # 上限のすぐ上＝鍵が入っていても照らせない
    data = {"tool_name": "Artifact", "cwd": str(tmp_path), "tool_input": {"file_path": str(big)}}
    unread = []
    assert outbound.secret_hits(data, {}, pg, unread) == []
    assert unread and unread[0][0] == str(big) and "大きすぎる" in unread[0][1]


# ── pr_text: 読めない workflow ──
def _add_workflow(proj, name, text):
    (proj / ".github" / "workflows" / name).write_text(text, encoding="utf-8")


@pytest.mark.parametrize("name,text,why", [
    ("broken.yml", ":::\n- - x\n  y: [\n", "壊れている"),                  # 読み手が形を読めない
    ("nojobs.yml", "on: [pull_request]\nname: 作り物\n", "jobs が無い"),
])
def test_壊れた_workflow_は出す前に止め名と訳を添える(env, name, text, why):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    _add_workflow(proj, name, text)
    got = stopped(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public"))
    assert "workflow" in got and os.path.join(".github", "workflows", name) in got and why in got
    assert "public-guard.yml" not in got                  # 読めた workflow は名指さない


def test_開けない_workflow_は出す前に止め_公開の判定から黙って落とさない(env):
    """公開の検査を呼ぶ唯一の workflow が開けないと、公開でないと読まれ文が照らされずに出る。その時は出す前に止め名と訳を添える。"""
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    wf = proj / ".github" / "workflows" / "public-guard.yml"
    wf.unlink()
    wf.mkdir()                                            # 開けない（file でない＝IsADirectoryError）
    p = gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public")
    got = stopped(env, p)
    assert os.path.join(".github", "workflows", "public-guard.yml") in got and "開けない" in got
    assert "照らせない" in got


def test_読める_workflow_だけなら止めない(env):
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD)
    _add_workflow(Path(env["CLAUDE_PROJECT_DIR"]), "only-comments.yml", "# 中身の無い作り物\n\n")
    assert stopped(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public")) == ""


def test_壊れた_workflow_があっても読める呼び口で公開の検査は止める(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    _add_workflow(proj, "broken.yml", ":::\n- - x\n")
    out = hook(env, "pre", gh("add_issue_comment", issue_number=1, body="%s の直し" % PUBLIC_WORD, repo="fake-public"))
    assert out.get("permissionDecision") == "deny" and "[public]" in out.get("permissionDecisionReason", "")
