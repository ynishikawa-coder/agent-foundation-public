"""見回りの赤が「次の手」＝合流すれば呼び口の外れが消える開いた PR を名指すかを見る（注入の試験）。

起きた事: 公開 repo の呼び口が版の印のままで見回りが赤になり、直しの PR はレビューを通ったまま合流されず、
赤と issue は外れだけを並べて誰も次の手を取らなかった。見回りは外れと同じ読み手で開いた PR の先端を読み、
外れを消す PR だけを名指す（外れを消さない PR・外れの無い repo の PR は名指さない）。
"""
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "public-guard"))
import patrol  # noqa: E402

FULL = "o/x"
GOOD = ("on:\n  push:\n    branches: [main]\n  pull_request:\njobs:\n  public-guard:\n    name: public-guard\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - uses: ynishikawa-coder/agent-foundation-public/public-guard@main\n")
PINNED = GOOD.replace("@main", "@v0.4.2")


class RefGitHub(patrol.GitHub):
    """道の全体で答える作り物（枝と commit で workflow の中身を分ける）。"""

    def __init__(self, wf_at: dict[str, str], prs: list[dict]):
        super().__init__(None)
        self.routes = {f"/repos/{FULL}": {"full_name": FULL, "default_branch": "main"},
                       "/users/o/repos?type=owner&per_page=100&page=1": [{"full_name": FULL, "default_branch": "main", "private": False}],
                       f"/repos/{FULL}/branches/main": {},
                       f"/repos/{FULL}/rules/branches/main": [{"type": "required_status_checks", "parameters": {
                           "required_status_checks": [{"context": "public-guard"}]}}],
                       f"/repos/{FULL}/pulls?state=open&base=main&per_page=100&page=1": prs}
        for at, text in wf_at.items():
            self.routes[f"/repos/{FULL}/contents/.github/workflows?ref={at}"] = [
                {"type": "file", "name": "g.yml", "path": ".github/workflows/g.yml"}]
            self.routes[f"/repos/{FULL}/contents/.github/workflows/g.yml?ref={at}"] = {
                "content": base64.b64encode(text.encode()).decode()}

    def req(self, path, method="GET", body=None):
        assert method == "GET"
        return (200, self.routes[path]) if path in self.routes else (404, None)


def _pr(n, sha):
    return {"number": n, "title": f"PR {n}", "html_url": f"https://example.invalid/{n}", "head": {"sha": sha}}


def _run(wf_at, prs):
    gh = RefGitHub(wf_at, prs)
    found = patrol.patrol(gh, ["o"])
    return found, patrol.render(found, ["o"], patrol.fixes(gh, found))


def test_外れを消す開いた_PR_を次の手として名指す():
    found, text = _run({"main": PINNED, "aaa": GOOD, "bbb": PINNED}, [_pr(25, "aaa"), _pr(21, "bbb")])
    assert any("main の先端で呼んでいない" in p for p in found[FULL])
    assert "次の手: 開いている PR #25「PR 25」" in text and "https://example.invalid/25" in text
    assert "#21" not in text, "外れを消さない PR を名指した"


def test_直しの_PR_が無ければ名指さない():
    _, text = _run({"main": PINNED, "bbb": PINNED}, [_pr(21, "bbb")])
    assert "次の手" not in text


def test_呼び口の外れが無い_repo_の_PR_は読まない():
    """守りの外れ（必須の検査）は設定で、PR では消えない。呼び口が正しい repo の PR を名指さない。"""
    gh = RefGitHub({"main": GOOD, "aaa": GOOD}, [_pr(25, "aaa")])
    gh.routes[f"/repos/{FULL}/rules/branches/main"] = []
    found = patrol.patrol(gh, ["o"])
    assert any("必須の検査" in p for p in found[FULL])
    assert patrol.fixes(gh, found) == {}


def test_main_の赤と_issue_の本文に次の手が載る(monkeypatch, capsys):
    gh = RefGitHub({"main": PINNED, "aaa": GOOD}, [_pr(25, "aaa")])
    sent = []
    gh.req_orig = gh.req

    def req(path, method="GET", body=None):
        if method != "GET":
            sent.append((method, path, body))
            return 200, {}
        if path.startswith("/repos/h/issues?"):
            return 200, []
        return gh.req_orig(path, method, body)

    gh.req = req
    monkeypatch.setattr(patrol, "GitHub", lambda token=None: gh)
    monkeypatch.setenv("GITHUB_REPOSITORY", "h")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert patrol.main(["--owner", "o", "--report-issue"]) == 1, "直しの PR が在っても合流までは赤のまま"
    assert "次の手: 開いている PR #25" in capsys.readouterr().out
    assert sent and "次の手: 開いている PR #25" in sent[0][2]["body"]
