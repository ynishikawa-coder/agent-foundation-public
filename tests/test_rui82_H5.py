"""字の並びで照らす類の根治（H5 の受け持ち）の注入の試験。

公開の検査（public-guard/guard.py）・見回り（public-guard/patrol.py）・Codex へ渡すパック（codex_pack.py）・
部品の流れ（scripts/call_flows.py）に、各行の「起きた問題」の形をわざと入れて、拒む（拾う）かを見る。
この file も公開の検査に照らされる＝鍵・電話・URL・メールの形は字のまま書かず、実行時に組む。
"""
import base64
import importlib.util
import io
import os
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "public-guard"))
import guard  # noqa: E402
import patrol  # noqa: E402

ENV_KEYS = ("AF_DENY_WORDS", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE", "GITHUB_ACTIONS", "GITHUB_EVENT_PATH")
OK_MAIL = "1+t@users.noreply.github.com"
SEP = "-"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def _rnd_key(n, seed="rui82"):
    """作り物の乱れた英数字（鍵の体の形）。"""
    import hashlib
    abc = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    d = hashlib.sha256(seed.encode()).digest() * 4
    return "".join(abc[b % len(abc)] for b in d[:n])


def _git(repo, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": OK_MAIL,
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": OK_MAIL}
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True).stdout


def _repo_with(tmp_path, files: dict[str, bytes]):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    for name, data in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "x")
    return repo


def _files_hits(repo, words=None, skip=()):
    g = guard.Guard(repo, words or [], set(skip))
    return g.check_files()


# ---- 行 …8152b3a6fd256d8a1558: 置かない語を小文字の部分一致だけで見る -------------------------------

@pytest.mark.parametrize("label,text", [
    ("全角の英字", "これは ＡＣＭＥＷＩＤＧＥＴ の話"),
    ("語の間の空白", "これは acme widget の話"),
    ("語の間の中黒", "作り物・ノ語 の直し"),
    ("語の間の全角空白", "作り物　ノ語 の直し"),
])
def test_置かない語は全角や空白_中黒を挟んでも当たる(label, text):
    words = ["acmewidget", "作り物ノ語"]
    assert guard.word_hits("見本", text, words), label
    assert guard.customer_hits("見本", text, words, None), label
    # 直す前は小文字の部分一致だけ＝全角・挟んだ字で外れていた


def test_置かない語の寄せは別の語まで当てない():
    assert not guard.word_hits("見本", "acme の別の widget", ["acmewidget"])


# ---- 行 …8169-98cb-f04ece60dd7a: 電話・郵便番号・URL の形を列挙する ---------------------------------

def _phones():
    a, b, c = "03", "1234", "5678"
    return [" ".join((a, b, c)), "+81" + SEP + "3" + SEP + b + SEP + c, "(" + a + ") " + b + SEP + c,
            "０３" + "−" + "１２３４" + "−" + "５６７８"]


@pytest.mark.parametrize("text", _phones())
def test_区切りの違う電話番号も当たる(text):
    assert any("電話番号" in h for h in guard.pattern_hits("見本", text)), text


def test_notion_の別の登録の名の_url_も当たる():
    url = "www." + "notion" + ".com/abc"
    assert any("Notion" in h for h in guard.pattern_hits("見本", url))


@pytest.mark.parametrize("text", ["2026" + SEP + "11" + SEP + "19 13:00", "1700000000", "v1.2.3",
                                  "https://www." + "google" + ".com/search?q=x", "ID 0123456789012345"])
def test_電話でも文書でもない数と_url_は当てない(text):
    assert not guard.pattern_hits("見本", text), text


# ---- 行 …8161-a4c7-e4fd3f6a65eb: UTF-8 で読めない file を空として見る -----------------------------------

def _mail():
    return "taro" + "@" + "gmail.com"


def _docx(body_xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", body_xml)
    return buf.getvalue()


def _pdf(text: str) -> bytes:
    stream = zlib.compress(("BT (" + text + ") Tj ET").encode())
    return b"%PDF-1.4\n1 0 obj << /Filter /FlateDecode >>\nstream\n" + stream + b"\nendstream\nendobj\n%%EOF\n"


@pytest.mark.parametrize("label,name,data,want", [
    ("Shift_JIS の文書の置かない語", "a.txt", "これは作り物ノ語です".encode("cp932"), "置かない語"),
    ("EUC-JP の文書の置かない語", "b.txt", "これは作り物ノ語です".encode("euc_jp"), "置かない語"),
    ("Shift_JIS の文書のメール", "c.txt", ("連絡 " + "先 ").encode("cp932") + _mail().encode(), "メールアドレス"),
    (".docx の札で割れた鍵", "d.docx",
     _docx("<w:t>gh" + "p_</w:t><w:t>" + _rnd_key(36) + "</w:t>"), "GitHub のトークン"),
    (".xlsx の置かない語", "e.xlsx", _docx("<si><t>作り物ノ語</t></si>"), "置かない語"),
    (".pdf の圧縮した流れの鍵", "f.pdf", _pdf("AK" + "IA" + "ABCDEFGHIJKLMNOP"), "AWS の鍵 ID"),
])
def test_utf8_で読めない_file_も中を起こして照らす(tmp_path, label, name, data, want):
    repo = _repo_with(tmp_path, {name: data})
    hits = _files_hits(repo, words=["作り物ノ語"])
    assert any(h.startswith(name) and want in h for h in hits), (label, hits)
    # 直す前は UnicodeDecodeError で空の字として照らし、名だけを見ていた


def test_どの符号でも読めない_file_は名指しして止める(tmp_path):
    repo = _repo_with(tmp_path, {"g.bin.txt": b"abc\x85\x86\xfd\xfe"})
    assert any("g.bin.txt" in h and "読めないファイル" in h for h in _files_hits(repo))


def test_ふつうの画像は止めない(tmp_path):
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(range(256))
    repo = _repo_with(tmp_path, {"p.png": png})
    assert not _files_hits(repo)


# ---- 行 …81e6-894f-d05fefb1d40f: 形の照らしを path の名で丸ごと外す ----------------------------------

def test_外す_file_でも本物の鍵の形は当たる(tmp_path):
    key = "gh" + "p_" + _rnd_key(36)
    repo = _repo_with(tmp_path, {"tests/test_public_guard.py": ("KEY = '%s'\n" % key).encode()})
    hits = _files_hits(repo, skip=["tests/test_public_guard.py"])
    assert any("GitHub のトークン" in h for h in hits), hits
    # 直す前は skip の path は pattern_hits を丸ごと飛ばしていた


def test_外す_file_の見本の印の形と個人の形の見本は通す(tmp_path):
    sample = "gh" + "p_" + "a" * 36
    phone = "03" + SEP + "1234" + SEP + "5678"
    repo = _repo_with(tmp_path, {"pat.py": ("S = '%s'\nP = '%s'\n" % (sample, phone)).encode()})
    assert not _files_hits(repo, skip=["pat.py"])
    assert _files_hits(repo)    # 外さない file では見本も当たる（強さは変えない）


# ---- 行 …818b-b717-f29f2bbaea5f: codex_pack が秘密の形の表を写しで持つ ------------------------------

def _codex():
    path = ROOT / "plugins" / "dev-flow" / "skills" / "codex" / "codex_pack.py"
    spec = importlib.util.spec_from_file_location("codex_pack_h5", path)
    mod = importlib.util.module_from_spec(spec)
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


def test_codex_pack_の秘密の形は公開の検査の正本と同じ物を直に読む(monkeypatch):
    cp = _codex()
    tok = "gh" + "p_" + "k3m9" * 6            # 20〜35 字・小文字と数字＝前は codex_pack だけで止まり、公開の検査は通した
    blocks, _ = cp.scan("x = 1\n" + tok + "\n", environ={})
    assert "GitHub のトークン" in blocks
    assert guard.secret_labels(tok) == ["GitHub のトークン"]
    assert not set(cp.EXTRA_PATTERNS) & set(guard.SECRET_PATTERNS), "正本の札の写しが残っている"
    pg = cp.public_guard()
    monkeypatch.setitem(pg.SECRET_PATTERNS, "作り物の鍵", r"FAKEKEY-\d{4}")
    assert "作り物の鍵" in cp.scan("FAKEKEY-" + "1234", environ={})[0]


def test_codex_pack_は正本が見つからなければ止める(monkeypatch, tmp_path):
    cp = _codex()
    monkeypatch.setattr(cp, "PLUGIN_ROOT", tmp_path / "a" / "b" / "c")
    monkeypatch.setenv("AF_PUBLIC_GUARD", str(tmp_path / "none.py"))
    with pytest.raises(cp.Abort):
        cp.scan("x", environ={})


# ---- 行 …8162-981f-c235389ff2fa: 鍵らしい環境変数を名の字で選ぶ --------------------------------------

@pytest.mark.parametrize("name,value", [
    ("STRIPE_SK", "rk" + "_" + _rnd_key(12, "s")),
    ("DB_PWD", "Tr0" + "ub4d&r3x"),
    ("SIGNING_SALT", "q7Zp" + "2Lm9"),
])
def test_名が鍵らしくない環境変数でも値が秘密の形なら止める(name, value):
    cp = _codex()
    text = "x = 1\nV = '%s'\n" % value
    assert not cp.scan(text, environ={})[0], "値の照らしを外しても止まる＝試験が値の段を見ていない"
    blocks, _ = cp.scan(text, environ={name: value})
    assert f"窓が持つ秘密の値（環境変数 {name}）" in blocks
    # 直す前は SECRET_NAME（KEY・TOKEN・SECRET・PASS・CRED・AUTH・PRIVATE）に当たらない名は照らす段に入らなかった


def test_語の並びの環境変数の値はパックに在っても止めない():
    cp = _codex()
    env = {"LANG": "C.UTF-8", "MODEL": "claude-opus-5-5", "HOME_DIR": "/home/user/work", "LEVEL": "production"}
    text = "\n".join(env.values())
    assert not cp.scan(text, environ=env)[0]


# ---- 見回り（patrol）の作り物 --------------------------------------------------------------------

class FakeGitHub(patrol.GitHub):
    def __init__(self, routes):
        super().__init__(None)
        self.routes = routes

    def req(self, path, method="GET", body=None):
        for prefix, value in self.routes.items():
            if path.startswith(prefix):
                return 200, value
        return 404, None


def _routes(full, wf_text, rules):
    return {f"/users/{full.split('/')[0]}/repos": [{"full_name": full, "default_branch": "main", "private": False}],
            f"/repos/{full}/branches/main": {},
            f"/repos/{full}/rules/branches/main": [{"type": "required_status_checks", "parameters": {
                "required_status_checks": [{"context": c} for c in rules]}}],
            f"/repos/{full}/contents/.github/workflows?": [{"type": "file", "name": "g.yml", "path": ".github/workflows/g.yml"}],
            f"/repos/{full}/contents/.github/workflows/g.yml": {"content": base64.b64encode(wf_text.encode()).decode()}}


USES = "uses: ynishikawa-coder/agent-foundation-public/public-guard@main"


def _wf(*jobs, on="[pull_request]"):
    body = "".join(jobs)
    return f"name: w\non: {on}\njobs:\n{body}"


def _job(jid, name=None, step=f"- {USES}", cond=None):
    head = f"  {jid}:\n" + (f"    name: {name}\n" if name else "") + (f"    if: {cond}\n" if cond else "")
    return head + f"    runs-on: x\n    steps:\n      {step}\n"


def _problems(wf, rules):
    return patrol.patrol(FakeGitHub(_routes("o/x", wf, rules)), ["o"]).get("o/x", [])


# ---- 行 …81b2-b327-d18654766d1d: 必須の検査を名の字 public-guard で見る --------------------------------

def test_何も照らさない_job_が_public_guard_を名乗っても外れと出る():
    wf = _wf(_job("call", "guard-call"), _job("decoy", "public-guard", step="- run: echo ok"))
    probs = _problems(wf, ["public-guard"])
    assert any("必須の検査に公開の検査を呼ぶ job（guard-call）が無い" in p for p in probs), probs
    # 直す前は必須の検査の名に public-guard の字が在れば外れなしだった


def test_呼ぶ_job_と同じ名を呼ばない_job_も名乗れば外れ():
    wf = _wf(_job("a", "public-guard"), _job("b", "public-guard", step="- run: echo ok"))
    assert any("でない job も名乗る" in p for p in _problems(wf, ["public-guard"]))


def test_呼ぶ_job_の名が必須なら外れ0():
    assert _problems(_wf(_job("call", "guard-call")), ["guard-call"]) == []


# ---- 行 …8170-ac22-d0e35d68b934: 呼び口を workflow の字の並びで見る -----------------------------------

@pytest.mark.parametrize("label,wf", [
    ("# で消した行", _wf(_job("j", "public-guard", step="- run: echo x\n      # - " + USES))),
    ("if: false の job", _wf(_job("j", "public-guard", cond="false"))),
    ("if: ${{ false }} の step", _wf(_job("j", "public-guard", step=f"- if: ${{{{ false }}}}\n        {USES}"))),
    ("PR にも push にも走らない workflow", _wf(_job("j", "public-guard"), on="[workflow_dispatch]")),
    ("run の文の中の字", _wf(_job("j", "public-guard", step="- run: echo '" + USES + "'"))),
])
def test_走らない呼び口は呼び口と数えない(label, wf):
    probs = _problems(wf, ["public-guard"])
    assert any("呼び口が無い" in p for p in probs), (label, probs)
    # 直す前は workflow の字に uses: …/public-guard@main の並びが在れば呼び口と数えた


def test_YAML_として読めない_workflow_は外れ():
    probs = _problems("on: [push\njobs: {", ["public-guard"])
    assert any("YAML として読めない" in p for p in probs)


# ---- 行 …8136-a734-fde6abee1a02: plugin の間の呼び出しを道具の file 名・path の字で拾う --------------------

def _put(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def flows_repo(tmp_path):
    r = tmp_path / "repo"
    for n in ("alpha", "beta"):
        _put(r, f"plugins/{n}/.claude-plugin/plugin.json", "{}")
    _put(r, "plugins/beta/scripts/common.py", "x = 1\n")
    _put(r, "scripts/common.py", "x = 2\n")                      # 外にも同じ名＝名だけでは拾えない
    _put(r, "plugins/beta/tmpl/受領.template.md", "# 雛形\n")
    return r


def _flows(r):
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    spec = importlib.util.spec_from_file_location("call_flows_h5", ROOT / "scripts" / "call_flows.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.flows(r)


@pytest.mark.parametrize("label,rel,text", [
    ("名を割る呼び方（Python の並び）", "plugins/alpha/scripts/a.py",
     "import os\nTOOL = ('beta', os.path.join('scripts', 'common.py'), 'AF_X')\n"),
    ("名を割る呼び方（Path の /）", "plugins/alpha/scripts/b.py",
     "from pathlib import Path\nP = Path(__file__).parent / 'beta' / 'scripts' / 'common.py'\n"),
    ("道具でない拡張子の file を読む", "plugins/alpha/scripts/c.py",
     "import os\nT = ('beta', os.path.join('tmpl', '受領.template.md'))\n"),
    ("JS の名を割る呼び方", "plugins/alpha/scripts/d.mjs",
     "const p = path.join(root, 'beta', 'scripts', 'common.py');\n"),
])
def test_名を割る呼び方と道具でない_file_を読む流れも拾う(flows_repo, label, rel, text):
    _put(flows_repo, rel, text)
    got = _flows(flows_repo)
    assert any(ev.startswith(rel) for ev in got.get(("alpha", "beta"), [])), (label, got)
    # 直す前は道具の file 名・path の字の並びだけで見た（外にも同じ名の common.py は名で拾えず、.md は道具でない）


def test_文書が文書の_path_を挙げるだけは流れでない(flows_repo):
    _put(flows_repo, "plugins/alpha/skills/s/SKILL.md", "詳しくは plugins/beta/tmpl/受領.template.md。\n")
    assert _flows(flows_repo) == {}
