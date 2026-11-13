"""公開の検査（public-guard/guard.py）と見回り（public-guard/patrol.py）が約束どおり効くかを見る。

この repo そのものを照らすのは CI の job public-guard（手元は scripts/checks/public_guard.sh）。ここは作り物の repo で道具を確かめる。
"""
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "public-guard"))
import guard  # noqa: E402
import patrol  # noqa: E402

GUARD = ROOT / "public-guard" / "guard.py"
OK_MAIL = "1+someone@users.noreply.github.com"
ENV_KEYS = ("AF_DENY_WORDS", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE", "GITHUB_ACTIONS", "GITHUB_EVENT_PATH")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def _bundle_of(words, key=b"k" * 32):
    digests = {hmac.new(key, w.encode(), hashlib.sha256).digest()[:guard.DIGEST] for w in words}
    return "%s.%s.%s" % (guard.BUNDLE_PREFIX, base64.urlsafe_b64encode(key).decode(),
                         base64.urlsafe_b64encode(b"".join(sorted(digests))).decode())


def _git(repo, *args, email=OK_MAIL):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": email}
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("見本\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _commit(repo, files=None, msg="直した", email=OK_MAIL, remove=()):
    for name, text in (files or {}).items():
        (repo / name).write_text(text, encoding="utf-8")
    for name in remove:
        (repo / name).unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg, email=email)
    return _git(repo, "rev-parse", "HEAD")


def _pr_event(repo, base, head, title="題", body=""):
    return {"pull_request": {"title": title, "body": body, "base": {"sha": base}, "head": {"sha": head}}}


def _run(repo, event, **kw):
    return guard.run(repo, kw.get("rev_range"), kw.get("words_file"), kw.get("skip", []), event)


# ---- 形 ---------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "連絡先 taro.yamada@gmail.com",
    "電話 03-1234-5678",
    "携帯 09012345678",
    "〒100-0001",
    "https://www.notion.so/abc123",
    "https://docs.google.com/spreadsheets/d/abc",
    "ghp_" + "a" * 36,
])
def test_秘密と個人の情報の形は赤(text):
    assert guard.pattern_hits("見本", text)


@pytest.mark.parametrize("text", [
    "Co-Authored-By: Claude <noreply@anthropic.com>",
    "284810416+someone@users.noreply.github.com",
    "t@example.invalid",
    "2026-11-12 13:00",
    "@pytest.mark.parametrize",
])
def test_個人を指さない物は緑(text):
    assert not guard.pattern_hits("見本", text)


# ---- 束 ---------------------------------------------------------------------

def test_束の語は文の中でも当たる():
    bundle = guard.decode_bundle(_bundle_of(["見本商事"]))
    assert guard.customer_hits("見本", "今日は見本商事さんへ行く", [], bundle)
    assert not guard.customer_hits("見本", "今日は別の所へ行く", [], bundle)


@pytest.mark.parametrize("value", ["pct1.壊れた.値", "pct2.a.b", "pct1.!!.!!"])
def test_束の形が違えば止める(value):
    with pytest.raises(ValueError):
        guard.decode_bundle(value)


# ---- 中身・歴史・外側 ----------------------------------------------------------

def test_きれいな枝は緑(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, {"a.md": "ふつうの文\n"}, "直した\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    assert not _run(repo, _pr_event(repo, base, head))


def test_中身の個人の情報は赤(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, {"a.md": "電話 03-1234-5678\n"})
    assert any(h.startswith("a.md:") for h in _run(repo, _pr_event(repo, base, head)))


def test_消しても歴史に残る物は赤(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, {"a.md": "連絡先 taro.yamada@gmail.com\n"})
    head = _commit(repo, remove=["a.md"])
    hits = _run(repo, _pr_event(repo, base, head))
    assert hits and all(h.startswith("commit ") for h in hits), hits


def test_名義のメールは_noreply_だけ通す(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, email="t@example.invalid")  # 作り物の置き場でも、名義は noreply でなければ赤
    assert any("名義のメール" in h for h in _run(repo, _pr_event(repo, base, head)))


def test_PRの本文と題も照らす(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo)
    assert any(h.startswith("PR の本文") for h in _run(repo, _pr_event(repo, base, head, body="電話 03-1234-5678")))
    assert any(h.startswith("PR の題") for h in _run(repo, _pr_event(repo, base, head, title="https://www.notion.so/x")))


def test_置かない語の表は表そのものを除いて照らす(tmp_path):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, {"deny.txt": "# 表\n禁句\n", "b.md": "禁句がある\n"})
    hits = _run(repo, _pr_event(repo, base, head), words_file="deny.txt")
    assert any(h.startswith("b.md") for h in hits)
    assert not any("deny.txt" in h for h in hits)


def test_形を書いた所だけ形の照らしから外せる(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, {"pat.py": "EXAMPLE = '03-1234-5678'  # 見本商事\n"})
    assert not _run(repo, _pr_event(repo, base, head), skip=["pat.py"])
    # 顧客の語の照らしは外さない
    monkeypatch.setenv("AF_DENY_BUNDLE", _bundle_of(["見本商事"]))
    assert any("顧客の語" in h for h in _run(repo, _pr_event(repo, base, head), skip=["pat.py"]))


def test_全ての歴史を照らせる(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.md": "〒100-0001\n"})
    _commit(repo, remove=["a.md"])
    assert _run(repo, {}, rev_range="ALL")


def test_pushの範囲はbeforeからafter(tmp_path):
    repo = _repo(tmp_path)
    before = _git(repo, "rev-parse", "HEAD")
    after = _commit(repo, {"a.md": "〒100-0001\n"}, remove=[])
    _commit(repo, remove=["a.md"])
    assert _run(repo, {"before": before, "after": after})


# ---- 呼び口（CLI） -------------------------------------------------------------

def _cli(repo, env_extra, *args):
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env.update(env_extra)
    return subprocess.run([sys.executable, str(GUARD), "--repo", str(repo), "--range", "ALL", *args],
                          env=env, capture_output=True, text=True)


def test_CIで顧客の語が無ければ赤(tmp_path):
    res = _cli(_repo(tmp_path), {"GITHUB_ACTIONS": "true"})
    assert res.returncode == 1, res.stdout


def test_手元で顧客の語が無ければ飛ばして緑(tmp_path):
    res = _cli(_repo(tmp_path), {})
    assert res.returncode == 0, res.stdout


def test_束の形が違えば止まる(tmp_path):
    assert _cli(_repo(tmp_path), {"AF_DENY_BUNDLE": "pct1.壊れた.値"}).returncode == 2


@pytest.mark.parametrize("wrap, reason", [
    ('"{}"', "引用符"),
    ("AF_DENY_BUNDLE={}", "名前と ="),
    ("{}\n{}", "行ある"),
    ("x{}", "先頭が"),
])
def test_束の形の違いは値を出さずに理由を言う(tmp_path, wrap, reason):
    good = _bundle_of(["見本商事"])
    res = _cli(_repo(tmp_path), {"AF_DENY_BUNDLE": wrap.format(good, good)})
    assert res.returncode == 2 and reason in res.stdout, res.stdout
    assert good.split(".")[1] not in res.stdout and good.split(".")[2] not in res.stdout


def test_顧客の語は赤の時も出力に出ない(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.md": "今日は見本商事さんへ行く\n"}, msg="見本商事の件")
    for extra in ({"AF_DENY_WORDS": "見本商事"}, {"AF_DENY_BUNDLE": _bundle_of(["見本商事"])}):
        res = _cli(repo, extra)
        out = res.stdout + res.stderr
        assert res.returncode == 1, out
        assert "見本商事" not in out, "顧客の語が出力に出た"


def test_action_は本体を呼ぶ():
    text = (ROOT / "public-guard" / "action.yml").read_text(encoding="utf-8")
    assert "github.action_path }}/guard.py" in text
    assert "fetch-depth: 0" in text


def test_雛形は版の印で呼び_job_の名が決まっている():
    text = (ROOT / "public-guard" / "caller-template.yml").read_text(encoding="utf-8")
    assert "agent-foundation-public/public-guard@vX.Y.Z" in text
    assert "  public-guard:\n    name: public-guard" in text
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "  public-guard:\n    name: public-guard" in ci and "uses: ./public-guard" in ci


# ---- 見回り -------------------------------------------------------------------

class FakeGitHub(patrol.GitHub):
    def __init__(self, routes):
        super().__init__(None)
        self.routes = routes
        self.sent = []

    def req(self, path, method="GET", body=None):
        if method != "GET":
            self.sent.append((method, path, body))
            return 200, {}
        for prefix, value in self.routes.items():
            if path.startswith(prefix):
                return 200, value
        return 404, None


def _wf(text):
    return {"content": base64.b64encode(text.encode()).decode()}


def _routes(full, wf_text=None, contexts=(), rules=()):
    r = {f"/users/{full.split('/')[0]}/repos": [{"full_name": full, "default_branch": "main", "private": False}],
         f"/repos/{full}/branches/main": {"protection": {"required_status_checks": {"contexts": list(contexts)}}},
         f"/repos/{full}/rules/branches/main": [{"type": "required_status_checks", "parameters": {
             "required_status_checks": [{"context": c} for c in rules]}}]}
    if wf_text is not None:
        r[f"/repos/{full}/contents/.github/workflows?"] = [{"type": "file", "name": "g.yml", "path": ".github/workflows/g.yml"}]
        r[f"/repos/{full}/contents/.github/workflows/g.yml"] = _wf(wf_text)
    return r


CALLER = "    steps:\n      - uses: ynishikawa-coder/agent-foundation-public/public-guard@v0.5.0\n"


def test_見回り_呼び口と守りがあれば外れ0():
    gh = FakeGitHub(_routes("o/x", CALLER, rules=["public-guard"]))
    assert patrol.patrol(gh, ["o"]) == {}


def test_見回り_枝の保護の必須でもよい():
    gh = FakeGitHub(_routes("o/x", CALLER, contexts=["public-guard"]))
    assert patrol.patrol(gh, ["o"]) == {}


def test_見回り_呼び口が無ければ外れ():
    found = patrol.patrol(FakeGitHub(_routes("o/x", None, rules=["public-guard"])), ["o"])
    assert "呼び口が無い" in found["o/x"][0]


def test_見回り_守りが無ければ外れ():
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER)), ["o"])
    assert any("必須の検査" in p for p in found["o/x"])


def test_見回り_版の印で固定していなければ外れ():
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER.replace("@v0.5.0", "@main"), rules=["public-guard"])), ["o"])
    assert any("版の印" in p for p in found["o/x"])


def test_見回り_非公開とarchiveは見ない():
    gh = FakeGitHub({"/users/o/repos": [{"full_name": "o/p", "private": True},
                                        {"full_name": "o/a", "private": False, "archived": True}]})
    assert patrol.patrol(gh, ["o"]) == {}


def test_見回り_土台は自分の枝の物を呼んでよい():
    full = patrol.FOUNDATION
    gh = FakeGitHub(_routes(full, "      - uses: ./public-guard\n", rules=["public-guard"]))
    assert patrol.patrol(gh, [full.split("/")[0]]) == {}


def test_見回り_外れはissueで知らせ_0なら閉じる():
    gh = FakeGitHub({"/repos/h/issues?": []})
    patrol.report_issue(gh, "h", {"o/x": ["外れ"]}, "本文")
    assert gh.sent == [("POST", "/repos/h/issues", {"title": patrol.ISSUE_TITLE, "body": "本文"})]
    gh = FakeGitHub({"/repos/h/issues?": [{"number": 3, "title": patrol.ISSUE_TITLE}]})
    patrol.report_issue(gh, "h", {}, "外れ 0")
    assert ("PATCH", "/repos/h/issues/3", {"state": "closed", "state_reason": "completed"}) in gh.sent


def test_見回りの相手が決まっている():
    owners = json.loads((ROOT / "public-guard" / "patrol.json").read_text(encoding="utf-8"))["owners"]
    assert owners and all(isinstance(o, str) and o for o in owners)


def test_中身だけを照らせる(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.md": "〒100-0001\n"}, email="t@example.invalid")
    _commit(repo, remove=["a.md"])
    assert not guard.run(repo, "ALL", None, [], {}, files_only=True)
    assert guard.run(repo, "ALL", None, [], {})
