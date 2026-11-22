"""照らせなかった物を、出す前に止める（知らせるだけの道へ戻さない）注入の試験。

意図: 秘密と公開の検査は安全の守り。照らせなかった物を「出した後に知らせる」だけにすると、AI が読み飛ばせば鍵・置かない語が
そのまま外へ出る。
課題: outbound と pr_text は、大きすぎる・開けない Artifact の file と、開けない・壊れた workflow を、出した後（PostToolUse）に
知らせるだけで、出す事は止めなかった。
原因: 止めに変えるかをオーナーの同意待ちにして、知らせる道を仮に置いたまま残っていた（同意は聞く線の 2026-11-22 の合意で取れた）。
ここでは、鍵が無く照らせない物だけがある時も出す前に止まる事・出した後の知らせの道がもう無い事・公開でない repo でも壊れた
workflow があれば止める事を見る。入力は全部作り物。
"""
from pathlib import Path

from test_guard import env, hook  # noqa: F401  （env は fixture）
from test_guard_unreadable_named import outbound, publish, stopped  # noqa: F401  （outbound は fixture）
from test_pr_text import gh


def test_鍵が無くても照らせない_file_だけで出す前に止める(env, tmp_path, outbound):
    """意図: 照らせない file を照らした扱いで出さない。課題: 鍵が当たらない時は、照らせない file があっても通していた。"""
    (tmp_path / "ok.html").write_text("<p>報告</p>", encoding="utf-8")
    (tmp_path / "big.json").write_text("x" * (outbound.MAX_READ + 1), encoding="utf-8")
    why = stopped(env, publish(tmp_path, file_path="ok.html", files={"data/big.json": "big.json"}))
    assert "照らせなかった" in why and "big.json" in why and "小さくするか分けて" in why
    assert "鍵・認証情報の形があるので" not in why          # 鍵が当たったとは言わない


def test_出した後の知らせの道は畳んだ(env, tmp_path, outbound):
    """意図: 止める道を 1 本にする。課題: 出した後に同じ物を知らせる道が並んでいると、止めを外しても試験が緑のまま残る。"""
    (tmp_path / "ok.html").write_text("<p>報告</p>", encoding="utf-8")
    p = publish(tmp_path, file_path="ok.html", files={"data/gone.json": "無い.json"})
    assert hook(env, "post", p).get("additionalContext", "") == ""
    assert "無い.json" in stopped(env, p)


def test_公開でない_repo_でも壊れた_workflow_があれば止める(env):
    """意図: 公開かを決められない repo へ文を出さない。課題: 壊れた workflow が公開の検査を呼ぶ唯一の物なら、
    公開でないと読まれて照らされずに出ていた。"""
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    import subprocess
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", "https://github.com/fake-owner/fake-x.git"], check=True)
    wf = proj / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "broken.yml").write_text(":::\n- - x\n  y: [\n", encoding="utf-8")
    why = stopped(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-x"))
    assert "broken.yml" in why and "公開の検査を呼ぶかを決められず" in why
