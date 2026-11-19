"""公開の検査（public-guard/guard.py）と見回り（public-guard/patrol.py）が約束どおり効くかを見る。

この repo そのものを照らすのは CI の job public-guard（手元は scripts/checks/public_guard.sh）。ここは作り物の repo で道具を確かめる。
"""
import base64
import hashlib
import hmac
import json
import os
import re
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
ENV_KEYS = ("AF_DENY_WORDS", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE", "AF_DENY_SOURCE_TOKEN", "GITHUB_ACTIONS",
            "GITHUB_EVENT_PATH", "GITHUB_REPOSITORY_OWNER", "GITHUB_STEP_SUMMARY")


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
    rng = [] if "--range" in args else ["--range", "ALL"]
    return subprocess.run([sys.executable, str(GUARD), "--repo", str(repo), *rng, *args],
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


# ---- 顧客の語の正本（持ち主ごとに 1 か所・検査が直に読む） ----------------------------

OWNER = "ynishikawa-coder"


def _source(monkeypatch, text=None, error=None):
    """正本の置き場の読み口を作り物にする（網に出ない）。読んだ置き場を返す。"""
    seen = []

    def fake(src, token):
        seen.append((src, token))
        if error:
            raise error
        return text

    monkeypatch.setattr(guard, "fetch_source_text", fake)
    return seen


def _main(repo, capsys, *args):
    code = guard.main(["--repo", str(repo), "--files-only", *args])
    return code, capsys.readouterr().out


def test_正本の鍵があれば正本の束で照らし_古い写しは使わない(tmp_path, monkeypatch, capsys):
    """写しの secret に語が足されていなくても、正本に足した語で赤になる（注入の試験＝古い写しを置く）。"""
    repo = _repo(tmp_path)
    _commit(repo, {"a.md": "新しい顧客の新規商事へ行く\n"})
    seen = _source(monkeypatch, "# 正本\n" + _bundle_of(["見本商事", "新規商事"]) + "\n")
    monkeypatch.setenv("AF_DENY_SOURCE_TOKEN", "t")
    monkeypatch.setenv("AF_DENY_BUNDLE", _bundle_of(["見本商事"]))  # 古い写し
    code, out = _main(repo, capsys, "--owner", OWNER)
    assert code == 1 and "顧客の語" in out, out
    assert "新規商事" not in out
    assert seen[0][0]["repo"] and seen[0][1] == "t"


def test_正本の鍵があれば写しが無くてもCIで照らせる(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    _source(monkeypatch, _bundle_of(["見本商事"]))
    for k, v in {"AF_DENY_SOURCE_TOKEN": "t", "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY_OWNER": OWNER}.items():
        monkeypatch.setenv(k, v)
    code, out = _main(repo, capsys)
    assert code == 0 and "正本の置き場から直に読んだ" in out, out
    assert "写し" not in out.split("正本")[0]


def test_正本が読めなければ黙って通さず赤(tmp_path, monkeypatch, capsys):
    """鍵が切れた・置き場が無い時に写しへ落ちて緑にしない（注入の試験）。"""
    _source(monkeypatch, error=guard.SourceError("顧客の語の正本を読めない: HTTP 404"))
    monkeypatch.setenv("AF_DENY_SOURCE_TOKEN", "t")
    monkeypatch.setenv("AF_DENY_BUNDLE", _bundle_of(["見本商事"]))
    code, out = _main(_repo(tmp_path), capsys, "--owner", OWNER)
    assert code == 1 and "正本を読めない" in out, out


def test_正本の読み口は_HTTP_の誤りを名指しの誤りにする(monkeypatch):
    import urllib.error

    def boom(req, timeout):
        assert req.full_url.startswith(guard.API + "/repos/") and req.get_header("Authorization") == "Bearer t"
        raise urllib.error.HTTPError(req.full_url, 401, "x", {}, None)

    monkeypatch.setattr(guard.urllib.request, "urlopen", boom)
    with pytest.raises(guard.SourceError, match="HTTP 401"):
        guard.fetch_source_text({"repo": "o/s", "path": "b.txt", "ref": "main"}, "t")


def test_置き場の決まりの無い持ち主は止める(tmp_path, monkeypatch, capsys):
    _source(monkeypatch, _bundle_of(["見本商事"]))
    monkeypatch.setenv("AF_DENY_SOURCE_TOKEN", "t")
    code, out = _main(_repo(tmp_path), capsys, "--owner", "知らない持ち主")
    assert code == 2 and "deny-source.json に無い" in out, out


@pytest.mark.parametrize("text", ["", "pct1.壊れた.値", _bundle_of(["a"]) + "\n" + _bundle_of(["b"])])
def test_正本の中身が束の1行でなければ止める(tmp_path, monkeypatch, capsys, text):
    _source(monkeypatch, text)
    monkeypatch.setenv("AF_DENY_SOURCE_TOKEN", "t")
    code, out = _main(_repo(tmp_path), capsys, "--owner", OWNER)
    assert code == 2, out


def test_置き場の表に知らない鍵があれば止める(tmp_path, monkeypatch):
    table = tmp_path / "s.json"
    table.write_text(json.dumps({"owners": {"o": {"repo": "o/s", "path": "b", "branch": "x"}}}), encoding="utf-8")
    monkeypatch.setattr(guard, "SOURCES", table)
    with pytest.raises(guard.SourceError, match="知らない鍵"):
        guard.source_of("o")


def test_置き場の表は持ち主ごとに_repo_と_path_を持つ():
    table = json.loads((ROOT / "public-guard" / "deny-source.json").read_text(encoding="utf-8"))
    assert table["owners"], "置き場が 1 つも無い"
    for owner, entry in table["owners"].items():
        assert guard.source_of(owner)["repo"].startswith(owner + "/")


def test_CIで写しだけで照らした時は名指しで知らせる(tmp_path, monkeypatch, capsys):
    """2 段の 1 段目: 写しでも止めないが、写しである事を Actions の注記と要約に出す。"""
    summary = tmp_path / "summary.md"
    for k, v in {"GITHUB_ACTIONS": "true", "AF_DENY_BUNDLE": _bundle_of(["見本商事"]),
                 "GITHUB_STEP_SUMMARY": str(summary)}.items():
        monkeypatch.setenv(k, v)
    code, out = _main(_repo(tmp_path), capsys)
    assert code == 0, out
    assert "::warning title=顧客の語が写し::" in out and "AF_DENY_SOURCE_TOKEN" in out
    assert "写し" in summary.read_text(encoding="utf-8")


def test_action_と雛形と土台の_ci_は正本の鍵を渡す():
    action = (ROOT / "public-guard" / "action.yml").read_text(encoding="utf-8")
    assert "deny-source-token:" in action and "AF_DENY_SOURCE_TOKEN: ${{ inputs.deny-source-token }}" in action
    line = "deny-source-token: ${{ secrets.AF_DENY_SOURCE_TOKEN }}"
    assert line in TEMPLATE_TEXT and line in CI_TEXT


def test_action_は本体を呼ぶ():
    text = (ROOT / "public-guard" / "action.yml").read_text(encoding="utf-8")
    assert "github.action_path }}/guard.py" in text
    assert "fetch-depth: 0" in text


def test_雛形は_main_の先端で呼び_job_の名が決まっている():
    text = (ROOT / "public-guard" / "caller-template.yml").read_text(encoding="utf-8")
    assert "agent-foundation-public/public-guard@main\n" in text
    assert not re.search(r"public-guard@v\d|@vX", text), "雛形に版の印が残っている"
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


def _routes(full, wf_text=None, contexts=(), rules=(), name="public-guard.yml", extra=None):
    r = {f"/users/{full.split('/')[0]}/repos": [{"full_name": full, "default_branch": "main", "private": False}],
         f"/repos/{full}/branches/main": {"protection": {"required_status_checks": {"contexts": list(contexts)}}},
         f"/repos/{full}/rules/branches/main": [{"type": "required_status_checks", "parameters": {
             "required_status_checks": [{"context": c} for c in rules]}}]}
    files = dict(extra or {})
    if wf_text is not None:
        files[name] = wf_text
    if files:
        r[f"/repos/{full}/contents/.github/workflows?"] = [
            {"type": "file", "name": n, "path": f".github/workflows/{n}"} for n in files]
        for n, t in files.items():
            r[f"/repos/{full}/contents/.github/workflows/{n}?"] = _wf(t)
    return r


TEMPLATE_TEXT = (ROOT / "public-guard" / "caller-template.yml").read_text(encoding="utf-8")
CALLER = TEMPLATE_TEXT
CI_TEXT = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_見回り_呼び口と守りがあれば外れ0():
    gh = FakeGitHub(_routes("o/x", CALLER, rules=["public-guard"]))
    assert patrol.patrol(gh, ["o"]) == {}


def test_見回り_枝の保護の必須でもよい():
    gh = FakeGitHub(_routes("o/x", CALLER, contexts=["public-guard"]))
    assert patrol.patrol(gh, ["o"]) == {}


def test_見回り_呼び口が無ければ外れ():
    found = patrol.patrol(FakeGitHub(_routes("o/x", None, rules=["public-guard"])), ["o"])
    assert "呼び口" in found["o/x"][0] and "が無い" in found["o/x"][0]


def test_見回り_守りが無ければ外れ():
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER)), ["o"])
    assert any("必須の検査" in p for p in found["o/x"])


@pytest.mark.parametrize("ref", ["v0.5.0", "1ce8fa37f665eb40216d290d45c25c44de4ca320", "claude/20261119-x"])
def test_見回り_main_の先端で呼んでいなければ外れ(ref):
    """版の印・SHA・枝で止めた呼び口は、直した検査が届かない（注入の試験）。"""
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER.replace("@main", "@" + ref), rules=["public-guard"])), ["o"])
    assert any("main の先端で呼んでいない" in p for p in found["o/x"])


@pytest.mark.parametrize("label, old, new", [
    ("on の edited が落ちた", "types: [opened, edited, synchronize, reopened]", "types: [opened, synchronize, reopened]"),
    ("permissions が広い", "contents: read", "contents: write"),
    ("with の入力名がずれた", "deny-source-token:", "deny-token:"),
    ("正本の鍵を渡していない（古い雛形の写し）", "          deny-source-token: ${{ secrets.AF_DENY_SOURCE_TOKEN }}\n", ""),
    ("job の名が違う", "    name: public-guard", "    name: guard"),
    ("行が足された", "    runs-on: ubuntu-latest", "    runs-on: ubuntu-latest\n    continue-on-error: true"),
])
def test_見回り_呼び口が雛形と違えば外れ(label, old, new):
    """写した呼び口の on・permissions・with がずれたら、@main でも外れ（注入の試験）。"""
    assert old in CALLER, label
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER.replace(old, new), rules=["public-guard"])), ["o"])
    assert any("雛形と違う" in p for p in found["o/x"]), label


def test_見回り_呼び口の注釈と行末の空白は比べない():
    text = "# 自分の注釈\n" + CALLER.replace("name: public-guard\n", "name: public-guard   \n", 1).replace("\n", "\r\n")
    assert patrol.patrol(FakeGitHub(_routes("o/x", text, rules=["public-guard"])), ["o"]) == {}


def test_見回り_呼び口が決まった名のfileに無ければ外れ():
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER, rules=["public-guard"], name="guard.yml")), ["o"])
    assert any("呼び口 .github/workflows/public-guard.yml が無い" in p for p in found["o/x"])


def test_見回り_ほかの_workflow_で版の印で呼んでも外れ():
    extra = {"other.yml": "      - uses: ynishikawa-coder/agent-foundation-public/public-guard@v0.4.2\n"}
    found = patrol.patrol(FakeGitHub(_routes("o/x", CALLER, rules=["public-guard"], extra=extra)), ["o"])
    assert any("@v0.4.2" in p for p in found["o/x"])


@pytest.mark.parametrize("old, new", [
    ("types: [opened, edited, synchronize, reopened]", "types: [opened, synchronize, reopened]"),
    ("          deny-source-token: ${{ secrets.AF_DENY_SOURCE_TOKEN }}\n", ""),
    ("  contents: read\n", "  contents: write\n"),
])
def test_見回り_土台の_ci_が雛形とずれたら外れ(old, new):
    """土台そのものの呼び口（ci.yml）も、雛形の on・permissions・with を外れたら外れ（注入の試験）。"""
    full = patrol.FOUNDATION
    assert old in CI_TEXT
    found = patrol.patrol(FakeGitHub(_routes(full, CI_TEXT.replace(old, new), rules=["public-guard", "plugin-smoke"],
                                             name="ci.yml")), [full.split("/")[0]])
    assert found.get(full), "外れにならない"


def test_見回り_非公開とarchiveは見ない():
    gh = FakeGitHub({"/users/o/repos": [{"full_name": "o/p", "private": True},
                                        {"full_name": "o/a", "private": False, "archived": True}]})
    assert patrol.patrol(gh, ["o"]) == {}


def test_見回り_土台は自分の枝の物を呼んでよい():
    full = patrol.FOUNDATION
    gh = FakeGitHub(_routes(full, CI_TEXT, rules=["public-guard", "plugin-smoke"], name="ci.yml"))
    assert patrol.patrol(gh, [full.split("/")[0]]) == {}


def test_見回り_土台は_plugin_smoke_が必須でなければ外れ():
    """main の先端を配る代わりの守り（入れて起動する試験）が合流の必須から外れたら知らせる（注入の試験）。"""
    full = patrol.FOUNDATION
    found = patrol.patrol(FakeGitHub(_routes(full, CI_TEXT, rules=["public-guard"], name="ci.yml")),
                          [full.split("/")[0]])
    assert any("plugin-smoke" in p for p in found[full])


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


# ---- レビュー（PR #12）で見つかった抜けの見張り -----------------------------------------

TOKEN = "ghp_" + "a" * 36


def test_日本語の名のファイルの歴史も照らす(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"設計.md": f"鍵 {TOKEN}\n"})
    _commit(repo, remove=["設計.md"])
    hits = _run(repo, {}, rev_range="ALL")
    assert any("設計.md" in h and "GitHub のトークン" in h for h in hits), hits


def test_プラス2つで始まる行で見出しを取り違えない(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"a.md": f"++ 見出しのふり\n鍵 {TOKEN}\n"})
    _commit(repo, remove=["a.md"])
    hits = _run(repo, {}, rev_range="ALL")
    assert any(h.startswith("commit ") and "a.md" in h and "GitHub のトークン" in h for h in hits), hits


@pytest.mark.parametrize("name", ['q"t.md', "ta\tb.md", "ba\\ck.md"])
def test_引用符つきで出る名のファイルの歴史も照らす(tmp_path, name):
    repo = _repo(tmp_path)
    _commit(repo, {name: f"鍵 {TOKEN}\n"})
    _commit(repo, remove=[name])
    hits = _run(repo, {}, rev_range="ALL")
    assert any(h.startswith("commit ") and name in h and "GitHub のトークン" in h for h in hits), hits


def test_diff_pathは引用を解き読めない名も捨てない():
    assert guard.diff_path("/dev/null") is None
    assert guard.diff_path("b/a.md") == "a.md"
    assert guard.diff_path('"b/q\\"t\\tx\\346\\227\\245.md"') == 'q"t\tx日.md'
    assert guard.diff_path('"b/x\\q"') == guard.UNREADABLE_PATH
    assert guard.diff_path("c/odd") == guard.UNREADABLE_PATH


def test_mergeでだけ足された行も照らす(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, {"a.md": "一\n"})
    _git(repo, "checkout", "-q", "-")
    _commit(repo, {"a.md": "二\n"})
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": OK_MAIL,
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": OK_MAIL}
    res = subprocess.run(["git", "merge", "-q", "side"], cwd=repo, env=env, capture_output=True, text=True)
    assert (repo / ".git" / "MERGE_HEAD").exists(), res.stdout + res.stderr  # 衝突で merge の途中に居る
    (repo / "a.md").write_text(f"鍵 {TOKEN}\n", encoding="utf-8")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-q", "--no-edit")
    _commit(repo, remove=["a.md"])
    assert any("GitHub のトークン" in h for h in _run(repo, {}, rev_range="ALL"))


def test_名に顧客の語があるファイルは名を伏せる(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, {"見本商事の台帳.md": "ふつうの文\n"})
    for extra in ({"AF_DENY_WORDS": "見本商事"}, {"AF_DENY_BUNDLE": _bundle_of(["見本商事"])}):
        res = _cli(repo, extra)
        out = res.stdout + res.stderr
        assert res.returncode == 1, out
        assert "見本商事" not in out and "名に置かない物があるファイル #" in out, out


def test_照らす範囲が読めない時は理由を出して赤(tmp_path):
    res = _cli(_repo(tmp_path), {}, "--range", "0" * 40 + ".." + "1" * 40)
    assert res.returncode == 1 and "照らす範囲を読めない" in res.stdout, res.stdout + res.stderr
