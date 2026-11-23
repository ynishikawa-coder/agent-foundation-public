"""pr_text が照らされる側の作業の木・枝で書き足した物（値の表・判定の道具・雛形・公開の検査）で緩まないか（注入の試験）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pr_text import EXEMPT_TABLE, PUBLIC_WORD, STRANGER, _fake_gh, _fake_public_repo, deny_reason, env, gh, verdict_comment  # noqa: E402,F401


def test_pr_text_手元や枝の値の表で書き足した外す行では外れない(env, tmp_path):
    """窓の取り出し（作業の木）の値の表・SKILL_VALUES の表に外す行を足しても、出す先の既定の枝に無ければ照らす。"""
    _fake_gh(env)                                                   # 既定の枝の表は引けない
    table = tmp_path / "values.json"
    table.write_text(json.dumps(EXEMPT_TABLE), encoding="utf-8")
    env["SKILL_VALUES"] = str(table)
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    (proj / "config").mkdir()
    (proj / "config" / "skill-values.json").write_text(json.dumps(EXEMPT_TABLE), encoding="utf-8")
    body = "## 何をどう変えたか\n直す窓 %s\n" % STRANGER
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body))
    assert "[cleanup]" in why and "[words]" in why
    # 既定の枝の表が別の repo の行だけなら外れない
    _fake_gh(env, contents={"fake-owner/fake-private": {"guard": {"pr_cleanup_exempt_repos": ["^fake-owner/other$"]}}})
    assert "[cleanup]" in deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body))


def test_pr_text_作業の木に置いた緩い判定の道具と雛形は使わない(env):
    """照らす枝の写し（窓の repo の plugins/…）に、いつも通す判定の道具と見出しを減らした雛形を置いても、入った版で照らす。"""
    _fake_gh(env)
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    vf = proj / "plugins" / "checker" / "scripts" / "verdict_form.py"
    vf.parent.mkdir(parents=True)
    vf.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    tpl = proj / "plugins" / "dev-flow" / "skills" / "preimpl-cleanup" / "整地受領証.template.md"
    tpl.parent.mkdir(parents=True)
    tpl.write_text("---\n---\n\n## 1. 意図\n〔…〕\n", encoding="utf-8")
    assert "[verdict]" in deny_reason(env, gh("add_issue_comment", issue_number=1, body=verdict_comment(head="")))
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body="## 1. 意図\n作り物。\n"))
    assert "[cleanup]" in why and "5. 未来" in why


def test_pr_text_出す先の取り出しに置いた緩い公開の検査は使わない(env):
    """土台そのものへ出す時も、取り出しの public-guard/guard.py（いつも通す）ではなく入った版で照らす。"""
    _fake_gh(env, visibility="public")
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    pg = proj / "public-guard" / "guard.py"
    pg.parent.mkdir(parents=True)
    pg.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    why = deny_reason(env, gh("create_pull_request", repo="fake-public", title="作り物",
                              head="b", base="main", body="整地: 不要（作り物）\n" + PUBLIC_WORD + "\n"))
    assert "[public]" in why
