"""字の並びで照らす類の根治（H6 の受け持ち）の注入の試験。

行ごとに「起きた問題」の形をわざと入れ、拒む（拾う）ことを見る:
- kaku.py / 古い形.json: 核の写しの枠の正本は 1 つ・Claude Code が読む物を辿って量と枠を見る・窓へ届く物は実物から決める・
  setup の命令は cmd_read で読む・札「後の便」は開きの括弧の分類で読む
- copies.py: 1 つの写しを短い文に割っても拾う
- qa-html の check.mjs: 型に無い欄・問いの頭の番号・選択肢の記号・書かせる欄は形で読む
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "core"
TOOL = PLUGIN / "scripts" / "kaku.py"
COPIES = PLUGIN / "scripts" / "copies.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


kaku = _load("kaku_rui82_h6", TOOL)
DK = _load("docs_kit_rui82_h6", ROOT / "tests" / "test_docs_kit.py")
needs_node = DK.needs_node
LIMIT = kaku.LIMITS["各社固有"]


def run(*args, project=None, home=None, stdin=""):
    env = dict(os.environ)
    env["HOME"] = str(home or (project or Path("/nonexistent-home")))
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True,
                          timeout=60, env=env, input=stdin)


def ctx(r):
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout else ""


def repo(d, files, git=True):
    d.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body, encoding="utf-8")
    if git:
        subprocess.run(["git", "init", "-q", str(d)], check=True)
        subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    return d


ROWS = {r["id"]: r for r in kaku.olds_table()}


# ── 行 e8c94439e7cd（古い形.json af-core-frame と kaku.py FRAME_BEGIN が同じ字を 2 か所に持つ）──
def test_核の写しの枠の字は古い形の一覧の_1_か所だけ():
    assert not hasattr(kaku, "FRAME_BEGIN")
    assert "AF-CORE" not in TOOL.read_text(encoding="utf-8"), "kaku.py が枠の字を持っている（正本は 古い形.json の af-core-frame）"
    assert ROWS["af-core-frame"]["files"] == [kaku.MEMORY]


@pytest.mark.parametrize("name, body", [
    ("CLAUDE.md", "<!--AF-CORE:BEGIN -->\n核\n<!-- AF-CORE:END -->\n"),          # 空白なし
    ("CLAUDE.md", "<！-- AF-CORE：BEGIN -->\n"),                                 # 全角（flat で寄せる）
    ("AGENTS.md", "<!-- AF-CORE:BEGIN -->\n"),                                  # AGENTS.md に置いた枠
    ("sub/CLAUDE.md", "<!-- AF-CORE:BEGIN -->\n"),                              # 下の dir
    ("docs/rules.md", "<!--\nAF-CORE:BEGIN -->\n"),                             # @ の取り込みの先
])
def test_枠は空白なし_AGENTS_md_下の_dir_取り込みの先でも拾う(tmp_path, name, body):
    files = {"CLAUDE.md": "固有\n@docs/rules.md\n" if name == "docs/rules.md" else "固有\n", name: body}
    if name == "CLAUDE.md":
        files["CLAUDE.md"] = body
    proj = repo(tmp_path / "p", files)
    r = run("check", "--claude", proj / "CLAUDE.md")
    assert r.returncode == 1 and "写しの枠" in r.stdout, r.stdout
    assert any(rid == "af-core-frame" and f == name for (row, f) in kaku.find_olds(proj) for rid in [row["id"]]), kaku.find_olds(proj)


def test_取り込みでない_code_の中の_at_は辿らない(tmp_path):
    proj = repo(tmp_path / "p", {"CLAUDE.md": "固有 `@docs/rules.md`\n```\n@docs/rules.md\n```\n",
                                 "docs/rules.md": "<!-- AF-CORE:BEGIN -->\n"})
    assert run("check", "--claude", proj / "CLAUDE.md").returncode == 0


# ── 行 d9052024b2fd（check --claude と claude_md_text が根の CLAUDE.md の字だけで量を見る）──
BIG = "決" * (LIMIT // 3 + 1)
HALF = "決" * (LIMIT // 6 + 1)


@pytest.mark.parametrize("files", [
    {"CLAUDE.md": "固有\n@docs/rules.md\n", "docs/rules.md": BIG},                       # @ の取り込みへ移した
    {"CLAUDE.md": "固有\n@a.md\n", "a.md": "@b.md\n", "b.md": BIG},                       # 取り込みの取り込み
    {"CLAUDE.md": HALF, "CLAUDE.local.md": HALF},                                        # CLAUDE.local.md へ半分
    {"CLAUDE.md": HALF, "AGENTS.md": HALF},                                              # AGENTS.md へ半分
    {"CLAUDE.md": HALF, "pkg/CLAUDE.md": HALF},                                          # 下の dir の CLAUDE.md へ半分
])
def test_量は_Claude_Code_が読む物を辿って数える(tmp_path, files):
    proj = repo(tmp_path / "p", files)
    r = run("check", "--claude", proj / "CLAUDE.md")
    assert r.returncode == 1 and "各社固有" in r.stdout, r.stdout
    assert "量の上限を越えている" in ctx(run("inject", project=proj))


def test_別々の下の_dir_の物は一緒に読まれないので足さない(tmp_path):
    proj = repo(tmp_path / "p", {"CLAUDE.md": "固有\n", "a/CLAUDE.md": HALF, "b/CLAUDE.md": HALF})
    assert run("check", "--claude", proj / "CLAUDE.md").returncode == 0
    assert "量の上限を越えている" not in ctx(run("inject", project=proj))


# ── 行 d5b323c2675f（no-marketplace-update が file のどこかの字で見る）──
ADD = "claude plugin marketplace add o/agent-foundation-public --scope user || true\n"
ENTRY = 'python3 "$af/scripts/setup_plugins.py" || true\n'


@pytest.mark.parametrize("text", [
    ADD + "# claude plugin marketplace update agent-foundation\n" + ENTRY,                 # コメントの update
    ADD + "echo 'marketplace update は後で'\n" + ENTRY,                                    # 命令でない字
    "M=agent-foundation\nclaude plugin marketplace add o/$M-public --scope user\n" + ENTRY,  # 名を変数で書いた add
    ADD + "cat <<'X'\nclaude plugin marketplace update agent-foundation\nX\n" + ENTRY,      # heredoc の中は命令でない
])
def test_取り直しの命令が無い_setup_は字が在っても拾う(text):
    assert kaku.olds_hit(ROWS["no-marketplace-update"], text, "setup.sh"), text


@pytest.mark.parametrize("text", [
    ADD + "claude plugin marketplace update agent-foundation || true\n" + ENTRY,
    "M=agent-foundation\nclaude plugin marketplace add o/$M-public\nclaude plugin marketplace update $M\n" + ENTRY,
    ADD + "claude plugin marketplace update\n" + ENTRY,                                     # 名なし＝全部を取り直す
    "目録は claude plugin marketplace add で足す（地の文）\n",                               # .md の地の文は命令でない
])
def test_取り直す_setup_と地の文は拾わない(text):
    name = "README.md" if "地の文" in text else "setup.sh"
    assert not kaku.olds_hit(ROWS["no-marketplace-update"], text, name), text


def test_md_の_code_の塊の命令は読む():
    md = "手順\n\n```bash\n" + ADD + ENTRY + "```\n\n本文に claude plugin marketplace update agent-foundation と書いても命令でない\n"
    assert kaku.olds_hit(ROWS["no-marketplace-update"], md, "setup.md")


# ── 行 d50c3a3b5ba5（atonobin-tag が [・［・〔 と *.md だけ）──
@pytest.mark.parametrize("text", ["- 【後の便】整地の残り", "（後の便）に回した", "「後の便」の札", "- {後の便｜x}", "〔 後の便に回した事〕"])
def test_後の便の札は開きの括弧の分類で拾う(text):
    assert kaku.olds_hit(ROWS["atonobin-tag"], text), text


@pytest.mark.parametrize("text", ["荷物は後の便で送ります", "明日の後の便に載せる"])
def test_地の文の後の便は拾わない(text):
    assert not kaku.olds_hit(ROWS["atonobin-tag"], text), text


def test_後の便の札は_txt_yml_の中でも拾い_変更の記録は外す(tmp_path):
    proj = repo(tmp_path / "p", {"notes/a.txt": "- [後の便｜x]\n", "ci/b.yml": "# 【後の便】\n",
                                 "CHANGELOG.d/c.txt": "- [後の便｜x] を畳んだ\n"})
    got = sorted(f for r, f in kaku.find_olds(proj) if r["id"] == "atonobin-tag")
    assert got == ["ci/b.yml", "notes/a.txt"], got


# ── 行 cb8715b87b0a（CARRIERS が path の頭 plugins・.claude-plugin で見る）──
def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit(work, files, msg, links=None):
    for name, body in files.items():
        f = work / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    for name, target in (links or {}).items():
        f = work / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.symlink_to(target)
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", msg)
    _git(work, "push", "-q", "origin", "HEAD:main")
    return _git(work, "rev-parse", "HEAD")


GUARD_PY = 'import guard_common as G\nP = G.foundation_file(os.path.join("public-guard", "guard.py"))\n'


@pytest.fixture
def foundation(tmp_path):
    remote, work, home = tmp_path / "remote.git", tmp_path / "work", tmp_path / "home"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True, capture_output=True)
    manifest = json.dumps({"name": "agent-foundation", "plugins": [{"name": n, "source": f"./plugins/{n}"} for n in ("core", "guard")]})
    have = _commit(work, {".claude-plugin/marketplace.json": manifest, "plugins/core/核.md": "核\n", "plugins/guard/scripts/outbound.py": GUARD_PY,
                          "public-guard/guard.py": "1\n", "skill-values/skill_values.py": "1\n", "docs/a.md": "1\n"}, "始め",
                   links={"plugins/guard/lib/skill_values.py": "../../../skill-values/skill_values.py"})
    loc = home / ".claude" / "plugins" / "marketplaces" / "agent-foundation"
    subprocess.run(["git", "clone", "-q", str(remote), str(loc)], check=True, capture_output=True)
    plugins = home / ".claude" / "plugins"
    (plugins / "known_marketplaces.json").write_text(json.dumps({"agent-foundation": {
        "source": {"source": "github", "repo": "o/r"}, "installLocation": str(loc)}}))
    (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {"core@agent-foundation": [
        {"installPath": str(PLUGIN), "gitCommitSha": have}]}}))
    return work, home


def _stale(home):
    r = run("inject", project=home.parent, home=home, stdin=json.dumps({"session_id": "s"}))
    return ctx(r)


@pytest.mark.parametrize("files, plugin", [
    ({"public-guard/guard.py": "2\n"}, "public-guard"),                  # plugin の code が土台の根から読む file
    ({"skill-values/skill_values.py": "2\n"}, "skill-values"),           # plugin の中の symlink の先
    ({"scripts/setup_plugins.py": "2\n"}, "scripts"),                    # setup が走らせる入口
])
def test_窓へ届く物は_plugin_の外でも古い土台とみる(foundation, files, plugin):
    work, home = foundation
    _commit(work, files, "届く物を変える")
    text = _stale(home)
    assert "土台が古いまま立った窓" in text and plugin in text, text


def test_窓へ届かない文書だけの変更では古いとみない(foundation):
    work, home = foundation
    _commit(work, {"docs/a.md": "2\n", "tests/test_x.py": "1\n"}, "文書だけ")
    assert "土台が古いまま立った窓" not in _stale(home)


def test_目録が読めない先端はどの変更も届くとみる(foundation):
    work, home = foundation
    _commit(work, {".claude-plugin/marketplace.json": "{壊れた", "docs/a.md": "2\n"}, "目録を壊す")
    assert "土台が古いまま立った窓" in _stale(home)


# ── 行 dfaeb7e27632（copies.py THRESHOLD・MIN_CHARS）──
def test_写しを短い文に割っても拾う(tmp_path):
    base = tmp_path / "f"
    base.mkdir()
    (base / "a.md").write_text("戻せない操作の前には必ず人に聞いてから進める決まりにする。\n", encoding="utf-8")
    t = tmp_path / "t.md"
    t.write_text("戻せない操作の前には。\n必ず人に聞いてから進める決まりにする。\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(COPIES), str(t), "--foundation", str(base)], capture_output=True, text=True)
    assert r.returncode == 1 and "写し" in r.stdout, r.stdout
    t.write_text("今日は晴れ。\n明日は雨。\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(COPIES), str(t), "--foundation", str(base)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


# ── qa-html の check.mjs ──
def _page(tmp_path, mutate, dest="copy"):
    page = tmp_path / "確認.html"
    page.write_text(mutate(DK.filled_template(dest)), encoding="utf-8")
    return DK.run_check(page)["red"]


def _one(old, new):
    def m(raw):
        assert old in raw, old
        return raw.replace(old, new, 1)
    return m


# 行 e7cd3891e51c（DROPPED が class 名 from・contact で見る）
@needs_node
@pytest.mark.parametrize("new, expect", [
    ('<p class="sender">サンプル事務所</p><p class="hold">', "型の外に class「sender」"),
    ('<p class="tel">03-0000-0000</p><p class="hold">', "型の外に class「tel」"),
    ('<p>差出人: サンプル事務所</p><p class="hold">', "型に無い欄 <p> を header.top"),      # class なしの欄
    ('<div>連絡先: 03-0000-0000</div><p class="hold">', "型に無い欄 <div> を header.top"),
])
def test_型に無い欄は名を問わず赤(tmp_path, new, expect):
    red = _page(tmp_path, _one('<p class="hold">', new))
    assert len(red) == 1 and red[0].startswith(expect), red


@needs_node
@pytest.mark.parametrize("where, key", [("page", "sender"), ("page", "tel"), ("question", "contact"), ("option", "note")])
def test_問いのデータの型に無い欄は名を問わず赤(tmp_path, where, key):
    data = json.loads((DK.DATA / "good.json").read_text(encoding="utf-8"))
    target = {"page": data, "question": data["questions"][0], "option": data["questions"][0]["options"][0]}[where]
    target[key] = "x"
    page = tmp_path / "q.json"
    page.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    red = DK.run_check(page)["red"]
    assert len(red) == 1 and f"型に無い欄「{key}」" in red[0], red


# 行 d45dfdfcf9bf（問いの頭の番号を 1.・問 3 の形で見る）
@needs_node
@pytest.mark.parametrize("head", ["第1問 ", "Q1:", "Q1 ", "問1）", "1．", "(1) ", "No.1 "])
def test_問いの頭の番号は綴りを問わず赤(tmp_path, head):
    red = _page(tmp_path, _one("送料の端数は、どちらで計算しますか", head + "送料の端数は、どちらで計算しますか"))
    assert any(r.startswith("問い q1: 問いの頭に番号を付けない") for r in red), red


@needs_node
def test_問いの順と違う数で始まる問いは番号でない(tmp_path):
    red = _page(tmp_path, _one("送料の端数は、どちらで計算しますか", "10 月の送料の端数は、どちらですか"))
    assert red == [], red


# 行 c9f8f0cb5077（option_symbol が英字・数字・丸数字の形で見る）
@needs_node
@pytest.mark.parametrize("sym", ["ア．", "イ）", "(ウ) ", "a. ", "⑴ ", "㋐ "])
def test_選択肢の記号は字を問わず形で赤(tmp_path, sym):
    red = _page(tmp_path, _one("<b>切り捨てる", f"<b>{sym}切り捨てる"))
    assert any(r.startswith("問い q1: 選択肢に記号を付けない") for r in red), red


@needs_node
@pytest.mark.parametrize("head", ["2.5 時間で計算する", "10 月 20 日"])
def test_数で始まる中身の見出しは記号でない(tmp_path, head):
    red = _page(tmp_path, _one("<b>切り捨てる", f"<b>{head}"))
    assert not any("選択肢に記号" in r for r in red), red


# 行 dc53fc4af3b0（number_ask が数を書かせる問いの語を列挙する）
@needs_node
@pytest.mark.parametrize("field", ['<input type="number" name="q3_n">', '<input type="text" name="q3_t">'])
def test_書かせる欄は語でなく欄の形で決める(tmp_path, field):
    """判断の問い（q3・judge）に書かせる欄＝問いの語に数の語が無くても赤。"""
    red = _page(tmp_path, _one('<div class="supp"><label for="supp_q3">', field + '<div class="supp"><label for="supp_q3">'))
    assert len(red) == 1 and red[0].startswith("問い q3: 書かせる欄"), red


@needs_node
@pytest.mark.parametrize("q", ["新しい棚は何件ありますか", "送料はいくらでしたか", "来る人は何名ですか"])
def test_候補から選ばせる問いは数の語があっても書かせる問いでない(tmp_path, q):
    red = _page(tmp_path, _one("新しい棚が届く日は、どちらですか", q))
    assert not any("書かせる" in r for r in red), red
