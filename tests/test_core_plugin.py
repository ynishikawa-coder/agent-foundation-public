"""plugin core の試験: 核の差し込み（いつも正本）・使う側に残った写しと古い形の名指し・量の上限の照らし。"""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from entry_box import box_env, copy_entry

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "core"
TOOL = PLUGIN / "scripts" / "kaku.py"

spec = importlib.util.spec_from_file_location("kaku", TOOL)
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)
LIMITS = kaku.LIMITS


def old_words_left(olds):
    """土台の文（.md .py .json .mjs .html・試験と .git を除く）に残る古い言い回しを「path: 語」で返す。
    変更の記録は CHANGELOG.d/ の .txt（経緯として古い語を持つ）なので、拡張子で外れる＝file 名で除かない。"""
    hits = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        # 古い形.json は使う側に残る古い形を見つける一覧＝古い名を持つのが役目（見つけ方の正しさは古い形の試験が照らす）。
        # 値の表の鍵の一覧（skill-values/schema.json と plugin の lib/ の symlink）も畳んだ鍵を名指す所（retired）なので同じ
        if rel.parts[0] in {".git", "tests"} or p == PLUGIN / "古い形.json" or p.name == "schema.json" and (
                rel.parts[0] == "skill-values" or "lib" in rel.parts):
            continue
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".html"}:
            text = p.read_text(encoding="utf-8")
            hits += [f"{rel}: {o}" for o in olds if o in text]
    return hits


def size(text: str) -> int:
    return len(text.encode("utf-8"))


def run(*args, project=None, home=None, stdin="", extra=None):
    env = dict(os.environ)
    # 試験は窓の実の home（入った plugin の台帳）を読まない。新しさの見張りは作り物の home で見る。
    env["HOME"] = str(home or (project or Path("/nonexistent-home")))
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    env.update(extra or {})
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True,
                          timeout=60, env=env, input=stdin)


def test_核と振る舞いと細目と_hook_が_plugin_の中に在る():
    assert all((PLUGIN / n).is_file() for n in ["核.md", "振る舞い.md", "細目.md"])
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    cmd = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/kaku.py" in cmd and cmd.endswith(" inject")
    cmd = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/kaku.py" in cmd and cmd.endswith(" fresh")


def test_写しの枠が無い_repo_には核と細目の在り処を差し込む(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# 固有の決まり\n", encoding="utf-8")
    r = run("inject", project=tmp_path)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    ctx = out["additionalContext"]
    assert ctx.startswith((PLUGIN / "核.md").read_text(encoding="utf-8").rstrip("\n"))
    assert (PLUGIN / "振る舞い.md").read_text(encoding="utf-8").rstrip("\n") in ctx, "振る舞いの既定が毎回差し込まれない"
    assert str(PLUGIN / "細目.md") in ctx
    assert "形に迷った時" not in ctx, "細目の案内が「形の細目」と分からない言葉に戻った"


def test_CLAUDE_md_が無い_repo_にも差し込む(tmp_path):
    r = run("inject", project=tmp_path)
    assert r.returncode == 0 and "additionalContext" in r.stdout


def _ctx(r):
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def test_写しの枠が在る_repo_にも正本の核を差し込み_枠を名指しする(tmp_path):
    """注入: 使う側の CLAUDE.md に古い核の写しの枠を戻す → 写しでなく正本が差し込まれ、枠が file の名で知らされる。"""
    (tmp_path / "CLAUDE.md").write_text("<!-- AF-CORE:BEGIN 写し -->\n古い核\n<!-- AF-CORE:END -->\n固有\n",
                                         encoding="utf-8")
    ctx = _ctx(run("inject", project=tmp_path))
    assert ctx.startswith((PLUGIN / "核.md").read_text(encoding="utf-8").rstrip("\n"))
    assert "古い形（写し）が残っている" in ctx and "CLAUDE.md: CLAUDE.md の核の写しの枠" in ctx


def test_古い形の一覧の行は形が揃い_例が自分の形に当たる():
    rows = kaku.olds_table()
    assert {r["id"] for r in rows} >= {"af-core-frame", "plugin-name-copy"}
    for r in rows:
        assert r["re"].search(r["example"]), f"{r['id']} の例が形に当たらない（見つける力が無い）"


@pytest.mark.parametrize("line", [
    "claude plugin install core@agent-foundation --scope user",
    "claude plugins install core@agent-foundation",
    "claude plugin i core@agent-foundation",
    "claude plugin install --scope user core@agent-foundation",
    "claude plugin install -s user guard@agent-foundation || true",
    'for p in core guard; do claude plugin install "$p@agent-foundation"; done',
    # 名を変数に置く・行を継ぐ（レビューの赤）。入れ方の綴りに頼らず「土台の目録を足すのに入口を呼ばない」形でも当たる
    'MARKET=agent-foundation\nclaude plugin install "$p@$MARKET"',
    'AF="agent-foundation"\nfor p in core guard; do claude plugin install "${p}@${AF}"; done',
    'claude plugin install \\\n  core@agent-foundation --scope user',
    'claude plugin marketplace add ynishikawa-coder/agent-foundation-public --scope user\nfor p in $want; do claude plugin install "$p@$m"; done',
])
def test_plugin_を入れる行は綴りが違っても古い形に当たる(line):
    """注入: 同じ意味の別の綴り（plugins・i・名の前の option）で偽の「古い形 0」にならない。"""
    row = next(r for r in kaku.olds_table() if r["id"] == "plugin-name-copy")
    assert row["re"].search(line), line


def test_入口を呼ぶ_setup_は古い形に当たらない():
    """入口 scripts/setup_plugins.py を通る形（docs の塊）は、目録を足していても古い形ではない。"""
    row = next(r for r in kaku.olds_table() if r["id"] == "plugin-name-copy")
    doc = (ROOT / "docs" / "核の届け方.md").read_text(encoding="utf-8")
    block = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", doc, re.S).group(1)
    assert "marketplace add" in block and not row["re"].search(block)


def test_古い形の見張りは時間の上限で打ち切り_黙って一部だけにしない(tmp_path):
    """注入: 1 つの file の照らしだけで上限を越える形（正規表現の後戻りが爆ぜる行と file）→ file の合間を待たず、
    上限の秒で打ち切って TimeoutError（起動では「見張りが動かなかった」と名指し）。上限の内なら当たりを返す。"""
    import time
    _olds_repo(tmp_path / "p", {"CLAUDE.md": "<!-- AF-CORE:BEGIN -->\n", "slow.md": "a" * 64 + "b\n"})
    table = tmp_path / "古い形.json"
    row = {"id": "slow", "what": "遅い形", "files": ["slow.md"], "pattern": "(a+)+$", "fix": "-", "example": "a"}
    table.write_text(json.dumps({"olds": [row]}), encoding="utf-8")
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        kaku.find_olds_bounded(tmp_path / "p", budget=1, table=table)
    assert time.monotonic() - t0 < 10
    found = kaku.find_olds_bounded(tmp_path / "p", budget=60)["found"]
    assert [(r["id"], f) for r, f in found] == [("af-core-frame", "CLAUDE.md")]


def test_古い形の一覧の欄が欠けると読めない(tmp_path):
    bad = tmp_path / "古い形.json"
    bad.write_text(json.dumps({"olds": [{"id": "x", "files": ["a"], "pattern": "a"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        kaku.olds_table(bad)


def _olds_repo(d, files):
    d.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)


def test_plugin_の名を写した_setup_の行が在る_repo_を名指しする(tmp_path):
    """注入: 使う側の setup script に plugin の名を写して入れる行を戻す → 起動の hook と olds が file を名指しする。"""
    proj = tmp_path / "p"
    _olds_repo(proj, {"scripts/env/setup.sh": 'for p in core guard; do claude plugin install "$p@agent-foundation"; done\n',
                     "README.md": "ふつう\n"})
    ctx = _ctx(run("inject", project=proj))
    assert "scripts/env/setup.sh: 土台の目録を足して plugin を入れるのに" in ctx and "README.md" not in ctx
    r = run("olds", proj)
    assert r.returncode == 1 and "plugin-name-copy" in r.stdout
    (proj / "scripts/env/setup.sh").write_text("python3 \"$af\" || true\n", encoding="utf-8")
    r = run("olds", proj)
    assert r.returncode == 0 and "古い形 0" in r.stdout
    assert "古い形（写し）" not in _ctx(run("inject", project=proj))


def test_土台そのものに古い形が残らない(tmp_path):
    """照らすのはこの commit の中身（olds は使う側の main を読むので、ROOT のままだと土台の main を照らし、古い形を消して
    古い形の行を足す 1 段目の PR が合流まで赤になる）。HEAD の木を main に置いた作り物の repo で照らす。"""
    import io
    import tarfile
    arc = subprocess.run(["git", "-C", str(ROOT), "archive", "HEAD"], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(arc)) as t:
        t.extractall(tmp_path, filter="data")
    g = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    for a in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "x"],
              ["update-ref", "refs/remotes/origin/main", "HEAD"]):
        subprocess.run(g + a, capture_output=True, check=True)
    r = run("olds", tmp_path)
    assert r.returncode == 0, r.stdout


def test_CLAUDE_md_が上限を越えた_repo_は起動の時に名指しする(tmp_path):
    """使う側は kaku.py も LIMITS も写して持たない＝起動の hook が照らす。"""
    (tmp_path / "CLAUDE.md").write_text("決" * (LIMITS["各社固有"] // 3 + 1), encoding="utf-8")
    assert "量の上限を越えている" in _ctx(run("inject", project=tmp_path))
    (tmp_path / "CLAUDE.md").write_text("決" * (LIMITS["各社固有"] // 3), encoding="utf-8")
    assert "量の上限を越えている" not in _ctx(run("inject", project=tmp_path))


def catalog_commit(loc):
    """作り物の目録の clone を git にして今の中身を 1 commit にし、その commit（入った版）を返す。"""
    g = lambda *a: subprocess.run(["git", "-C", str(loc), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                                  check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q")
    g("add", "-A")
    g("commit", "-qm", "名簿")
    return g("rev-parse", "HEAD")


def _installed_home(tmp_path, names, have, entry):
    """GitHub から目録を足した窓の home（目録の clone・入った plugin の台帳・入口の印）を作る。"""
    home = tmp_path / "home"
    loc = home / ".claude" / "plugins" / "marketplaces" / "agent-foundation"
    (loc / ".claude-plugin").mkdir(parents=True)
    (loc / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
        {"name": "agent-foundation", "plugins": [{"name": n} for n in names]}), encoding="utf-8")
    (home / ".claude" / "plugins" / "known_marketplaces.json").write_text(json.dumps({"agent-foundation": {
        "source": {"source": "github", "repo": kaku.UPSTREAM}, "installLocation": str(loc)}}), encoding="utf-8")
    sha = catalog_commit(loc)  # 名簿は入った版（commit）の物を読む＝目録の clone は git
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"version": 2, "plugins": {f"{n}@agent-foundation": [{"scope": "user", "installPath": str(PLUGIN), "gitCommitSha": sha,
                                                              "lastUpdated": "2026-11-19T11:57:05.000Z"}] for n in have}}),
        encoding="utf-8")
    (home / ".claude" / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {f"{n}@agent-foundation": True for n in have}}), encoding="utf-8")
    if entry:
        (home / ".claude" / "af-foundation").mkdir(parents=True)
        (home / ".claude" / "af-foundation" / "setup.json").write_text(json.dumps(
            {"catalog_sha": sha, "at": "2026-11-19T20:57:09+0900"}), encoding="utf-8")
    return home


def test_古い形の_setup_script_と入っていない_plugin_を名指しする(tmp_path):
    """注入: 土台が plugin を足したのに、名を写した古い setup script がそれを入れない → 窓の起動で名指し。"""
    home = _installed_home(tmp_path, ["core", "guard", "new-one"], ["core", "guard"], entry=False)
    ctx = _ctx(run("inject", project=tmp_path / "proj", home=home))
    assert "setup script が古い形" in ctx and "enabled になっていない: new-one" in ctx


def test_入口で全部入った窓には入れ方の知らせを出さない(tmp_path):
    home = _installed_home(tmp_path, ["core", "guard"], ["core", "guard"], entry=True)
    assert "入れ方が古い" not in _ctx(run("inject", project=tmp_path / "proj", home=home))


def test_上限の数は_1_か所で_核より各社固有が小さい():
    assert set(LIMITS) == {"核", "振る舞い", "各社固有"}
    assert LIMITS["各社固有"] < LIMITS["核"] and LIMITS["振る舞い"] < LIMITS["核"]


def test_今の核と_この_repo_の_CLAUDE_md_は上限の内():
    r = run("check", "--claude", ROOT / "CLAUDE.md")
    assert r.returncode == 0, r.stdout


def test_各社固有が上限を越えると赤で_上限ちょうどは緑(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("決" * (LIMITS["各社固有"] // 3), encoding="utf-8")
    assert size(claude.read_text(encoding="utf-8")) <= LIMITS["各社固有"]
    assert run("check", "--claude", claude).returncode == 0
    claude.write_text("決" * (LIMITS["各社固有"] // 3 + 1), encoding="utf-8")
    r = run("check", "--claude", claude)
    assert r.returncode == 1 and "各社固有" in r.stdout
    assert "細目 §3「まず構造を疑う」" in r.stdout.strip().splitlines()[-1], "越えた時に文を移させるだけの古い形に戻った"


def test_写しの枠が残る_CLAUDE_md_は量の照らしで赤(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("<!-- AF-CORE:BEGIN x -->\n核\n<!-- AF-CORE:END -->\n固有\n", encoding="utf-8")
    r = run("check", "--claude", claude)
    assert r.returncode == 1 and "写しの枠" in r.stdout


def test_核が上限を越えると赤(monkeypatch, tmp_path, capsys):
    fat = tmp_path / "核.md"
    fat.write_text("足" * (LIMITS["核"] // 3 + 1), encoding="utf-8")
    monkeypatch.setattr(kaku, "KAKU", fat)
    assert kaku.check(None) == 1
    assert "核" in capsys.readouterr().out


def _節(text, n):
    a = text.index(f"## {n}. ")
    b = text.find("\n## ", a + 1)
    return text[a:] if b < 0 else text[a:b]


def test_核の根治は意図_課題_原因_解決_未来の_5_段で_未来は試験の段でない():
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s3 = _節(kaku_text, 3)
    assert "意図→課題→原因→解決→未来" in s3
    assert "仕組み・設計）が悪い前提" in s3 and "別の目の助手" in s3
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    assert "意図が果たされ、同じ課題と同じ原因の他の問題が起きない状態" in s3d, "細目 §3 の未来が直した後の姿でない"
    for word in ["**意図**", "**課題**", "**原因**", "**同じ原因の他の問題**", "**解決**", "**未来**",
                 "無理・無駄・重複", "聞かせ方", "混じって", "試験を足す段ではない"]:
        assert word in s3d, f"細目 §3 に無い: {word}"


def test_MGK_は根治の_5_段の呼び名で説明の頼みにも_5_段で答える():
    assert "意図→課題→原因→解決→未来" in _節((PLUGIN / "核.md").read_text(encoding="utf-8"), 3), "核 §3 に 5 段が無い"
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    assert "（呼び名 MGK。" in s3d, "細目 §3 に MGK の呼び名が無い"
    line = next(l for l in (PLUGIN / "振る舞い.md").read_text(encoding="utf-8").splitlines() if "**MGK**" in l)
    for word in ["説明", "根治の 5 段の見出しで答える"]:
        assert word in line, f"振る舞いの既定の MGK の行に無い: {word}"


def test_問いは選ぶ問いと開いた問いに分け_分からないを置き_言葉を混ぜない():
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s4 = _節(kaku_text, 4)
    for word in ["選択肢の画面", "開いた問い", "AI の読み"]:
        assert word in s4, f"核 §4 に無い: {word}"
    assert "例え話にせず" in _節(kaku_text, 2)
    s4d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 4)
    for word in ["どの問いにも「分からない」の選択肢", "「分からない」が返った", "AI の今の読み", "選ぶ問いと開いた問い", "問いの言葉", "開発用語", "業界の専門用語", "決まりの言葉", "オーナーの言葉", "例え話に替えず"]:
        assert word in s4d, f"細目 §4 に無い: {word}"


def test_聞き方は見せてから聞き_前提の出所を分け_推奨の印は分かれ道だけ_待つ間は答えに頼らない事だけ():
    """原因の台帳の 4 行（2026-11-19）: 問いの文に全部を詰める・推奨の印が済んだかにも付く・前提に AI の推測を事実として置く・
    「待つ間も止まらない」が合意の要る事まで進める と読まれる。古い文を戻すと赤。"""
    s4 = _節((PLUGIN / "核.md").read_text(encoding="utf-8"), 4)
    for word in ["案と前提をチャットで先に見せ", "画面の問いは 1 文に", "推奨の印は作り方の分かれ道だけ",
                 "済んだかは AI が確かめてから", "答えを待つ間は答えに頼らない事を進める"]:
        assert word in s4, f"核 §4 に無い: {word}"
    s4d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 4)
    for word in ["**見せてから聞く**", "1〜2 文まで", "選択肢の説明へ", "**前提の出所**", "オーナーの言葉／記録の事実／AI の読み",
                 "「ずれ」と決め込まない", "「なぜこの形か」を問う", "**推奨の印**", "済んだかの確認には付けない",
                 "**答えを待つ間**", "推奨で先に進めない", "「終わった」「うまくいかない」「分からない」・推奨の印は付けない"]:
        assert word in s4d, f"細目 §4 に無い: {word}"
    mock = (ROOT / "plugins" / "docs-kit" / "skills" / "theory-mock" / "SKILL.md").read_text(encoding="utf-8")
    assert "作り方の分かれ道（画面・データ・流れをどう作るか）だけを置き" in mock and "推奨を付けずにチャットで聞く" in mock
    reminder = (ROOT / "plugins" / "guard" / "scripts" / "unanswered.py").read_text(encoding="utf-8")
    assert "この答えに頼らない作業だけを進めて" in reminder
    olds = ["答えを待つ間も止まらない", "①決めること ②なぜ今 ③材料", "推奨を 1 つ目に `(推奨)`", "「終わった（推奨）」",
            "戻せる作業だけを推奨案で進めて", "答え待ちで推奨を採った", "質問（`Q`）は必ず推奨と", "推奨を 1 つ目・", "推奨を 1 つ目・1 画面 4 問まで", "推奨で決めて"]
    hits = old_words_left(olds)
    assert not hits, hits


def test_古い根治と聞き方の言い回しが土台に残らない():
    olds = ["根治の 4 つの問い", "①構造の原因", "いつも選択肢の画面", "返事の中で平文の問いを出さない",
            "専門用語は日常の言葉にする", "専門の語は日常の言葉に言い換え", "名前・数字など選べない答えも候補を選択肢に置き"]
    hits = old_words_left(olds)
    assert not hits, hits


def test_一言の返事は札と締めを省き_窓の役に決まった一覧を置かない():
    """同じ原因（決まりが 1 つの形に押し込める）の残り: 短い返事に 3 行を足さない・役の名を 5 つに閉じない。古い形を戻すと赤。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    assert "一言で済む返事は札と締めを省く" in _節(kaku_text, 5)
    s5d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 5)
    assert "**一言で済む返事**" in s5d and "札を付けたら締めも付ける" in s5d
    olds = ["の 5 つだけ。他の名を足さない", "親・書く・レビュー・調べ・手 の 5 つ", "社内で確かめてから答える", "問いの形（3 つだけ）", "決まった 4 文"]
    hits = old_words_left(olds)
    assert not hits, hits


def test_核の根治は誤りが入れない形と注入の試験を持つ():
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s3 = _節(kaku_text, 3)
    for word in ["誤りが入れない形", "1 つの正本", "写さない", "既定で止める", "証明", "人の関所", "わざと入れて"]:
        assert word in s3, f"核 §3 に無い: {word}"
    assert "申告でなく記録" in _節(kaku_text, 7)
    saimoku = (PLUGIN / "細目.md").read_text(encoding="utf-8")
    s3d = _節(saimoku, 3)
    for word in ["写す工程を無くす", "誤った物が入れない", "正しい道だけが外へ出す", "防げない物は名指しで人の関所へ", "注入の試験", "古い道は残さず"]:
        assert word in s3d, f"細目 §3 に無い: {word}"
    assert "記録で確かめる" in _節(saimoku, 7)


# ── 古い土台で立った窓を見つける（入っている物と main の先端を比べる）。remote は作り物の git ──

def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit(work, files, msg):
    for name, body in files.items():
        f = work / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", msg)
    _git(work, "push", "-q", "origin", "HEAD:main")
    return _git(work, "rev-parse", "HEAD")


class Foundation:
    """作り物の土台: remote（bare）・書く側の clone・窓の home（入れた時の marketplace の clone と台帳）。"""

    def __init__(self, tmp):
        self.tmp, self.remote, self.work, self.home = tmp, tmp / "remote.git", tmp / "work", tmp / "home"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.work)], check=True, capture_output=True)
        self.installed = _commit(self.work, {"plugins/core/核.md": "核 1\n", "docs/a.md": "1\n"}, "始め")

    def install(self, source="github", main_at_setup=None):
        """窓が立つ時に setup script が入れた形を作る（marketplace の clone と台帳）。main_at_setup を渡すと、
        入口が書く setup の時の main の先端の記録（setup.json）も置く。"""
        loc = self.home / ".claude" / "plugins" / "marketplaces" / "agent-foundation"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(loc)], check=True, capture_output=True)
        _git(loc, "checkout", "-q", self.installed)
        plugins = self.home / ".claude" / "plugins"
        (plugins / "known_marketplaces.json").write_text(json.dumps({"agent-foundation": {
            "source": {"source": source, "repo": kaku.UPSTREAM}, "installLocation": str(loc)}}))
        (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {"core@agent-foundation": [
            {"installPath": str(PLUGIN), "gitCommitSha": self.installed}]}}))
        if main_at_setup:
            (self.home / ".claude" / "af-foundation").mkdir(parents=True, exist_ok=True)
            (self.home / ".claude" / "af-foundation" / "setup.json").write_text(json.dumps(
                {"entry": "scripts/setup_plugins.py", "main_at_setup": main_at_setup, "catalog_sha": self.installed,
                 "at": "2026-11-19T20:57:09+0900"}))

    def hook(self, event, sid="s1", source="startup"):
        r = run(event, project=self.tmp, home=self.home, stdin=json.dumps({"session_id": sid, "source": source}),
                extra={"AF_FRESH_INTERVAL": "0"})
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout else ""


def test_起動の後に_plugin_が変わったら引き継いで閉じるよう知らせる(tmp_path):
    """注入: 窓が立った後に main の先端で plugin を変える → 次の問いで引き継ぎの手順が出る。"""
    f = Foundation(tmp_path)
    f.install()
    assert "土台が古い" not in f.hook("inject")
    assert f.hook("fresh") == ""                         # まだ先端と同じ
    _commit(f.work, {"plugins/guard/x.py": "x\n"}, "守りを変える")
    text = f.hook("fresh")
    assert "引き継いで閉じる" in text and "create_session" in text and "archive_session" in text
    assert "guard" in text and "人の作業は新しい窓で止まらず続く" in text
    assert "引き継いで閉じる" in f.hook("fresh")        # 引き継ぐまで問いのたびに知らせる


@pytest.mark.parametrize("source", ["compact", "clear", "resume"])
def test_途中で古くなった窓は圧縮や_resume_を通っても引き継ぎが消えない(tmp_path, source):
    """注入: 起動 → main を進める → SessionStart がもう 1 回（圧縮・/clear・resume）→ fresh は引き継ぎを出し続ける。"""
    f = Foundation(tmp_path)
    f.install()
    f.hook("inject")
    _commit(f.work, {"plugins/guard/x.py": "x\n"}, "守りを変える")
    again = f.hook("inject", source=source)
    assert "土台が古いまま立った窓" not in again           # 「起動の時から古い」と取り違えない
    assert "引き継いで閉じる" in f.hook("fresh")


def test_起動の時から古い窓は圧縮の後も同じ知らせを出す(tmp_path):
    f = Foundation(tmp_path)
    tip = _commit(f.work, {"plugins/core/核.md": "核 2\n"}, "核を変える")
    f.install(main_at_setup=tip)
    f.hook("inject")
    assert "土台が古いまま立った窓" in f.hook("inject", source="compact")


def test_文書と試験だけの変更では窓を替えない(tmp_path):
    f = Foundation(tmp_path)
    f.install()
    f.hook("inject")
    _commit(f.work, {"docs/a.md": "2\n", "tests/test_x.py": "1\n"}, "文書だけ")
    assert f.hook("fresh") == ""


def test_起動の時から古い窓は_setup_script_を直してから引き継ぐよう知らせる(tmp_path):
    """注入: setup script が古い物を入れた（版を指したまま）→ 直してから引き継ぐ。直せない時だけ引き継がない（輪にしない）。"""
    f = Foundation(tmp_path)
    tip = _commit(f.work, {"plugins/core/核.md": "核 2\n"}, "核を変える")
    f.install(main_at_setup=tip)                         # setup の時の main は tip なのに、入れたのは 1 つ前
    text = f.hook("inject")
    assert "土台が古いまま立った窓" in text and "core" in text
    assert "update_environment" in text and "create_session" in text and "archive_session" in text
    assert "直せない時" in text and "連絡板" in text
    assert "# 振る舞いの核" in text                       # 核の差し込みは止めない
    assert f.hook("fresh") == ""


def test_比べられない時は窓を替えない(tmp_path):
    """手元の dir から入れた試し・remote に出られない時は、知らない値で人の作業を止めない。"""
    f = Foundation(tmp_path)
    f.install(source="directory")
    f.hook("inject")
    _commit(f.work, {"plugins/core/核.md": "核 3\n"}, "核を変える")
    assert f.hook("fresh") == ""
    g = Foundation(tmp_path / "g")
    g.install()
    g.hook("inject", sid="s2")
    _commit(g.work, {"plugins/core/核.md": "核 3\n"}, "核を変える")
    g.remote.rename(g.tmp / "gone.git")                 # remote に出られない
    assert g.hook("fresh", sid="s2") == ""


def test_起動の記録が無い窓は見に行かない(tmp_path):
    f = Foundation(tmp_path)
    f.install()
    _commit(f.work, {"plugins/core/核.md": "核 4\n"}, "核を変える")
    assert f.hook("fresh", sid="記録の無い窓") == ""


def test_挙げた原因は全部台帳に行き先つきで持ち_全部済むまで終わったと言わない():
    """原因が 5 つ挙がって 1 つしか直らない形を戻すと赤（1 つ選ぶ・一番手前から取る・どれを今回直すか）。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s3 = _節(kaku_text, 3)
    for word in ["原因の台帳", "全部", "行き先"]:
        assert word in s3, f"核 §3 に無い: {word}"
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    for word in ["1 つ 1 行", "`直す窓`", "`直した`", "`直さない`", "オーナーが決めた理由"]:
        assert word in s3d, f"細目 §3 の原因の台帳に無い: {word}"   # 行き先の細かさは細目が正本（核は芯だけ）
    s7 = _節(kaku_text, 7)
    assert "「直した」か「直さない」になるまで終わったと言わない" in s7 and "直す窓の行が残れば一部" in s7
    s4 = _節(kaku_text, 4)
    assert "並べて 1 つ選ばせる問いを出さない" in s4 and "全部やり、分け方は AI が決める" in s4
    saimoku = (PLUGIN / "細目.md").read_text(encoding="utf-8")
    assert "**原因の台帳**" in _節(saimoku, 3) and "**選ばせない**" in _節(saimoku, 4) and "**根治の終わり**" in _節(saimoku, 7)
    assert "1 本の列にせず" in (PLUGIN / "振る舞い.md").read_text(encoding="utf-8"), "引き継ぎの残りが番号の列に戻った"
    olds = ["どれを今回直す", "一番手前の未決から取る", "どれから進めますか」と聞"]
    hits = old_words_left(olds)
    assert not hits, hits


# 残りの受け皿: 各所が自分の名の受け皿（後の便・🎯箱・他の窓へ回す・残りに書く…）を持たず、原因の台帳 1 つへ向ける。
# (path, その所を見分ける語) — 語はちょうど 1 行に当たり、その行に「原因の台帳」が無ければ赤。
残りの所 = [
    ("plugins/core/細目.md", "**一時しのぎ**"),
    ("plugins/core/細目.md", "③道具・仕組みの都合"),
    ("plugins/core/細目.md", "どの窓にも分けなかった論点"),
    ("plugins/core/細目.md", "**大きい仕事の並べ方**"),
    ("plugins/core/細目.md", "| 一部 |"),
    ("plugins/dev-flow/skills/design-mode/SKILL.md", "どちらで出る時も"),
    (".github/pull_request_template.md", "## 残り"),
    ("CONTRIBUTING.md", "1 本に入らなかった仕事"),
    ("CONTRIBUTING.md", "`合流済` が届いた枝"),
    ("plugins/checker/skills/review-pr/SKILL.md", "`[台帳へ｜<段>]`"),
    # codex の値の表の `task_rule` は細目 §3 の写しなので畳んだ（受け皿は本文の 6. DEFER の行だけ）
    ("plugins/dev-flow/skills/codex/SKILL.md", "`[DEFER]`"),
    ("plugins/dev-flow/skills/codex/SKILL.md", "**RETURN_TO_DESIGN**"),
    ("plugins/dev-flow/skills/codex/SKILL.md", "6. **DEFER"),
    ("plugins/dev-flow/skills/verify/SKILL.md", "**一時しのぎを含めば Partially**"),
    ("plugins/dev-flow/skills/verify/SKILL.md", "**設計と実物の差分を必ず書く**"),
    ("plugins/docs-kit/skills/qa-html/SKILL.md", "0. **聞く前に引く**"),
    ("plugins/docs-kit/skills/theory-mock/SKILL.md", "範囲（やる／やらない／後で"),
    ("plugins/docs-kit/skills/theory-mock/SKILL.md", "**Q 番号・画面番号で元と突き合わせる**"),
    ("plugins/docs-kit/skills/theory-mock/SKILL.md", "外すとやり直しになる分かれ道"),
    ("plugins/docs-kit/skills/mindmap/SKILL.md", "外すとやり直しになる分かれ道"),
    ("plugins/docs-kit/skills/blueprint/SKILL.md", "外すとやり直しになる分かれ道"),
    ("plugins/dev-flow/skills/spec-doc/SKILL.md", "4. **右サイズを提示**"),
    ("plugins/dev-flow/skills/spec-doc/SKILL.md", "部分にする正当な理由"),
    ("plugins/dev-flow/skills/preimpl-cleanup/SKILL.md", "`[後片付け]`（"),
    ("plugins/dev-flow/skills/preimpl-cleanup/SKILL.md", "**同梱の片付けの返し**"),
    ("plugins/dev-flow/skills/preimpl-cleanup/整地受領証.template.md", "**畳む物**"),
    ("plugins/dev-flow/skills/preimpl-cleanup/整地受領証.template.md", "**残る穴**"),
]


def test_残りの受け皿は原因の台帳_1_つで_名だけの受け皿を持たない():
    """古い形（自分の名の受け皿・A/B を 1 つ選ばせて捨てる・相談を出ると論点が消える）を戻すと赤。"""
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    assert "**残りの受け皿は原因の台帳 1 つ**" in s3d
    for word in ["`台帳へ` の札", "DEFER", "一時しのぎ", "「一部」の残り", "どの窓も持たなかった論点", "選ばれなかった案",
                 "1 窓 1 枝 1 PR に入らなかった仕事", "合流の後の続き", "道具の都合", "正本は台帳"]:
        assert word in s3d, f"細目 §3 の残りの受け皿に無い: {word}"
    missing = []
    for rel, key in 残りの所:
        lines = [ln for ln in (ROOT / rel).read_text(encoding="utf-8").splitlines() if key in ln]
        if len(lines) != 1 or "原因の台帳" not in lines[0]:   # 2 行に当たる語は、片方を古い形に戻しても緑になる
            missing.append(f"{rel}: {key}")
    assert not missing, missing
    olds = ["他の窓へ回す", "後の便", "🎯箱 か PR 本文", "残りに書", "直す側へ回す", "必要になった段で足す",
            "論点として残す", "1つ選んで決めてもらう", "1 つ選んで決めてもらう", "残りを書いて引き継ぐ",
            "回す先", "cleanup_followup"]
    hits = old_words_left(olds)
    assert not hits, hits


def test_main_へは製品もオーナーに聞かずに入れ_絵と差がある時だけ止める():
    """「本番への出荷は聞く」を核に戻すと赤（Notion の決定と窓が読む核が食い違う形）。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    assert "本番への出荷" not in _節(kaku_text, 4), "核 §4 に「本番への出荷は聞く」が戻った"
    s7 = _節(kaku_text, 7)
    for word in ["（製品も）オーナーに聞かずに入れる", "レビュー green", "試験が緑で衝突なし", "全体の絵", "差がある・照らせない時は止めて聞く", "先に絵を描き"]:
        assert word in s7, f"核 §7 に無い: {word}"
    s7d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 7)
    assert "**main へ入れる**" in s7d and "**③の照らし方**" in s7d
    assert "review-pr 点 13" in s7d and "③の段が土台に入るまで" not in s7d   # 照らす段が入った後に「一言を取る」間の扱いを残さない
    assert "核 §7 の「照らせない時」" in s7d, "照らせない時の止めが核から読めない形に戻った"
    assert "核 §7 と細目 §7 の「main へ入れる」" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_土台の直しは使う側の写しの残りも同じ仕事で直し_合流まで終わったと言わない():
    """写しの残りを洗い出すだけで終わる形（直す持ち主が無い）を戻すと赤。"""
    s7d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 7)
    line = [ln for ln in s7d.splitlines() if "**土台の直しの終わり**" in ln]
    assert len(line) == 1, "細目 §7 に「土台の直しの終わり」が無い"
    for word in ["使う側の repo", "同じ仕事の中で直す", "洗い出しだけで終わらせない", "使う側の写しの残り", "合流するまで「終わった」と言わない", "原因の台帳の行"]:
        assert word in line[0], f"土台の直しの終わりに無い: {word}"
    assert "## 使う側の写しの残り" in (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert "土台の直しの終わり" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    dm = [ln for ln in (ROOT / "plugins/dev-flow/skills/design-mode/SKILL.md").read_text(encoding="utf-8").splitlines() if ln.startswith("   | 写しの残り |")]
    assert len(dm) == 1 and "同じ仕事の中" in dm[0], "design-mode の写しの残りが洗い出すだけに戻った"


def test_ミスが出たらまず構造を疑い_単発と言うのは絵の上で示せた時だけ():
    """根治の入口を「直す・作る時」だけに戻す・単発で片付ける道を戻す・規律を 2 度目まで足し続ける形を戻すと赤。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s3 = _節(kaku_text, 3)
    first = s3.split("\n- ", 1)[1]
    assert first.startswith("ミスが出た時（画面の見た目を除く）と直す・作る時の既定は根治"), "根治の入口が直す・作る時だけに戻った"
    for word in ["まず構造（上位の前提", "単発の誤りと言うのは全体の絵の上で構造に原因が無いと示せた時だけ",
                 "守り（確かめ・決まり）を足さず"]:
        assert word in s3, f"核 §3 に無い: {word}"
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    assert "**まず構造を疑う**" in s3d
    for word in ["作業の途中・レビュー・検査・引き継ぎ", "画面の見た目の崩れだけは除く", "示した所（絵のどこを見たか）を書く",
                 "根に届いていない合図で、原因の段へ戻る"]:
        assert word in s3d, f"細目 §3 の「まず構造を疑う」に無い: {word}"
    rr = (ROOT / "plugins" / "dev-flow" / "skills" / "register-rule" / "SKILL.md").read_text(encoding="utf-8")
    assert "細目 §3「まず構造を疑う」" in rr, "register-rule が規律を足す前に原因の段へ戻さない"
    assert "細目 §3「まず構造を疑う」" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"), "red を単発の手直しで済ませる形に戻った"
    olds = ["同じ種類の失敗が 2 度なら", "原因は仕組み・設計が悪い前提で探し"]
    hits = old_words_left(olds)
    assert not hits, hits


def test_核から細目へ移した物が細目に在る():
    """量を空けるために核から移した物が、どこにも無くならない。"""
    saimoku = (PLUGIN / "細目.md").read_text(encoding="utf-8")
    assert "「ほぼ終わった」と書かない" in _節(saimoku, 7)
    s8 = _節(saimoku, 8)
    assert "Javis は Notion と Drive" in s8 and "**またぐ連絡**" in s8


# ---- 振る舞いの既定（AI の癖と逆を求める物）は核と一緒に毎回差し込む ----

FURUMAI_WORDS = {  # 既定の要の語: 振る舞い.md だけに在り、細目に戻らない（2 か所に書かない）
    "並走": ["着手と言われたら確認させずに進め", "5 分を超える作業は窓・助手を並べて同時に進める",
             "読むだけの調べは助手", "書く仕事と互いに待たない長い仕事は窓"],
    "後継": ["1 本の列にせず"],
    "範囲": ["止まる条件は狭く", "黙って縮めない"],
    "聞かない": ["自分の枝への push の前に聞かない", "依頼文の出来を人に見てもらわない"],
    "引く": ["決定の記録と問いの表を問いと同じ言葉で引く"],
    "人の手": ["まず Claude in Chrome に貼る文"],
    "正本": ["「無い」「止まった」と言い切る前に正本を読む"],
    "ぼかさない": ["「たぶん」「概ね」「〜と思われます」と書かず", "前→後"],
    "逃げ場": ["「できれば」「間に合わなければ後で」と書かない"],
    "呼び出し": ["2 回で打ち方を変えるか止める"],
    "一覧": ["削らない・選ばない"],
    "MGK": ["「MGK して」と言ったら"],
}


def test_振る舞いの既定は全部_振る舞い_md_に在り細目に戻らない():
    furumai = (PLUGIN / "振る舞い.md").read_text(encoding="utf-8")
    saimoku = (PLUGIN / "細目.md").read_text(encoding="utf-8")
    missing = [w for ws in FURUMAI_WORDS.values() for w in ws if w not in furumai]
    assert not missing, f"振る舞いの既定に無い: {missing}"
    olds = ["自分の枝への push の前", "「無い」「止まった」と言い切る前", "間に合わなければ後で", "2 回で打ち方を変える",
            "「たぶん」「概ね」", "削らない・選ばない", "5 分を超え", "③は 1 本の列", "説明・振り返りの頼みでもこの 4 段",
            "広く任された物として進め", "依頼文の出来を人に求めない"]
    back = [o for o in olds if o in saimoku]
    assert not back, f"振る舞いの既定が細目にも書かれた（2 か所）: {back}"


def test_振る舞いの正本が無いと_check_は赤で_inject_は欠けを名指しする(monkeypatch, tmp_path, capsys):
    gone = tmp_path / "振る舞い.md"            # わざと消す
    monkeypatch.setattr(kaku, "FURUMAI", gone)
    assert kaku.check(None) == 2
    assert "振る舞い.md が読めない" in capsys.readouterr().out
    ctx = kaku.inject_text()
    assert "振る舞いの既定" in ctx and "差し込まれていない" in ctx and str(gone) in ctx


def test_振る舞いが上限を越えると赤で_上限ちょうどは緑(monkeypatch, tmp_path, capsys):
    f = tmp_path / "振る舞い.md"
    monkeypatch.setattr(kaku, "FURUMAI", f)
    f.write_text("既" * (LIMITS["振る舞い"] // 3), encoding="utf-8")
    assert kaku.check(None) == 0
    f.write_text("既" * (LIMITS["振る舞い"] // 3 + 1), encoding="utf-8")
    assert kaku.check(None) == 1
    assert "振る舞いの既定" in capsys.readouterr().out


def test_inject_は振る舞いを核の後に毎回入れる(monkeypatch, tmp_path):
    f = tmp_path / "振る舞い.md"
    f.write_text("# 既定\n- 印の既定\n", encoding="utf-8")
    monkeypatch.setattr(kaku, "FURUMAI", f)
    ctx = kaku.inject_text()
    assert ctx.index("# 振る舞いの核") < ctx.index("- 印の既定")


# 赤・red・抜けを返す skill と道具（台帳の原因「skill と道具が赤・red・抜けを単発の手直しや付け足しで返す」）
赤を返す所 = {
    "plugins/checker/skills/review-pr/SKILL.md": ["red は書いた窓へ直に 1 行（`判定 <PR> <枝>@<SHA12> verdict=green|red レビューした窓=<自分> 物差し=<最後の行>`）。"],
    "plugins/docs-kit/skills/theory-mock/SKILL.md": ["NG なら直してから（"],
    "plugins/docs-kit/skills/blueprint/SKILL.md": ["が出たら直してから渡す。"],
    "plugins/docs-kit/skills/qa-html/SKILL.md": ["**緑でなければ渡さない**（"],
    "plugins/dev-flow/skills/spec-doc/SKILL.md": ["**違反は設計書を直す**"],
    "plugins/docs-kit/skills/pdf-read/SKILL.md": ["必ず特定してから渡す。"],
    "plugins/docs-kit/skills/make-deck/SKILL.md": ["前案件で漏れた表現を次案件の禁止に足す（add-one）"],
    "plugins/docs-kit/skills/compose-message/SKILL.md": ["`recipient_rules` に 1 行足す"],
    "plugins/guard/skills/guard-rules/SKILL.md": [],
    "plugins/session-watch/skills/watch-log/SKILL.md": [],
    "plugins/dev-flow/skills/verify/SKILL.md": ["＋恒久の対応を残りに書く"],
    "CONTRIBUTING.md": ["試験を飛ばして緑にしない。赤を消すために試験を消さない。", "red の時は、同じ枝に直して push し"],
    "plugins/guard/scripts/unanswered.py": [],
    "scripts/check_all.sh": ['本: ${failed[*]})"'],
}
# 道具（script・hook）の側は上に手で載せない。下の試験が、失敗で終わる道具を repo から自分で拾う。


# 失敗で終わる・止める道具の印（exit 1・return 1・hook の deny・緑でなければ 1）
失敗で終わる = re.compile(r'sys\.exit\(1\)|\breturn 1\b|^\s*exit 1\b|process\.exit\(1\)|\? 0 : 1|"deny"|1 if \w+ else 0', re.M)


def test_失敗で終わる道具は一覧に載せなくても全部根治の入口を指す():
    """新しい道具が赤・NG・止めの文で根治の入口を指さずに足されたら、一覧へ手で足すのを待たずに赤。"""
    out = subprocess.run(["git", "ls-files", "plugins", "scripts", "public-guard"], cwd=ROOT, capture_output=True, text=True, check=True)
    tools = [r for r in out.stdout.split() if r.endswith((".py", ".sh", ".mjs", ".js"))]
    found = [r for r in tools if 失敗で終わる.search((ROOT / r).read_text(encoding="utf-8"))]
    assert "public-guard/guard.py" in found and "plugins/guard/scripts/guard.py" in found, "拾い方が壊れた"
    entry = re.compile(r"細目(?:\s*§\s*\d+)?「まず構造を疑う」")  # 番号は付けても付けなくても（合うかは refs.py が照らす）
    missing = [r for r in found if not entry.search((ROOT / r).read_text(encoding="utf-8"))]
    assert not missing, f"失敗で終わるのに根治の入口を指さない道具: {missing}"


# 古い形の類（直した文だけでなく、同じ file のどこに残っても拾う）
# ・語の類: 一覧を育てる・add-one（漏れを 1 行足して片付ける形）
# ・文の類: ミスの語（漏れ・赤・NG・落ち・抜け・拾われ）と、その場だけの直し（1 行足す・直してから・出し直す・残りに書く）が
#   同じ文に在るのに、根治の入口を指さない文
単発の語 = re.compile(r"add-one|育てる")
ミスの語 = re.compile(r"漏れ|赤|落ち|抜け|拾われ|(?<![A-Za-z])(NG|red)(?![A-Za-z])")
その場の直し = re.compile(r"1 行足す|(?<!見)直して(から|出し直)|出し直す|残りに書く")


def 単発の手直しの文(text):
    for s in re.split(r"[。\n]", text):
        if 単発の語.search(s):
            yield s
        elif ミスの語.search(s) and その場の直し.search(s) and "まず構造を疑う" not in s:
            yield s


@pytest.mark.parametrize("rel", sorted(赤を返す所))
def test_赤を返す所は根治の入口を指し単発の手直しの形が無い(rel):
    """赤・red・抜けを返す所が、直して出し直す・1 行足すだけの古い形に戻ると赤。指す先の正本が無くなっても赤。"""
    assert "**まず構造を疑う**" in _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3), "指す先の正本が無い"
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "細目 §3「まず構造を疑う」" in text, f"{rel} が根治の入口（細目 §3「まず構造を疑う」）を指さない"
    for old in 赤を返す所[rel]:
        assert old not in text, f"{rel} に単発の手直しの古い形が残る: {old}"
    left = list(単発の手直しの文(text))
    assert not left, f"{rel} に単発の手直しの類が残る: {left}"


def test_読めない中身でも_inject_は止まらず欠けを名指しし_check_は赤(monkeypatch, tmp_path, capsys):
    """UTF-8 でない中身（わざと壊す）で inject が落ちて核ごと抜ける穴を戻すと赤。"""
    bad = tmp_path / "振る舞い.md"
    bad.write_bytes(b"\xff\xfe\x00broken")
    monkeypatch.setattr(kaku, "FURUMAI", bad)
    ctx = kaku.inject_text()
    assert ctx.startswith("# 振る舞いの核") and "差し込まれていない" in ctx
    assert kaku.check(None) == 2
    badk = tmp_path / "核.md"
    badk.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(kaku, "KAKU", badk)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert kaku.inject() == 0
    assert "核.md が読めない" in capsys.readouterr().err
    assert kaku.check(None) == 2


def test_読めない_CLAUDE_md_でも_inject_は落ちない(tmp_path):
    (tmp_path / "CLAUDE.md").write_bytes(b"\xff\xfe broken")
    r = run("inject", project=tmp_path)
    assert r.returncode == 0 and "additionalContext" in r.stdout


def test_検査の入口の赤の最後の行は根治の入口を指し緑は指さない(tmp_path):
    """check_all.sh の赤が落ちた本の名だけを返す古い形（赤を 1 つずつ潰させる）に戻すと赤。"""
    copy_entry(tmp_path)
    (tmp_path / "tests").mkdir()
    test = tmp_path / "tests" / "test_x.py"
    run = lambda: subprocess.run(["bash", str(tmp_path / "scripts" / "check_all.sh")], capture_output=True, text=True,
                                 env=box_env())
    test.write_text("def test_x():\n    assert False\n", encoding="utf-8")
    red = run()
    last = red.stdout.strip().splitlines()[-1]
    assert red.returncode == 1 and last.startswith("check_all: 赤") and "細目 §3「まず構造を疑う」" in last
    test.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    green = run()
    assert green.returncode == 0 and "まず構造を疑う" not in green.stdout


def _git_repo(tmp_path, text, monkeypatch):
    """作り物の git repo に 核.md と細目.md を 1 commit で置き、核.md の path を返す。
    grow は細目も照らす（guarded）ので、細目も作り物へ向ける（本物の作業中の細目に試験が左右されない）。"""
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q")
    g("config", "user.email", "t@example.invalid")
    g("config", "user.name", "t")
    f = tmp_path / "核.md"
    f.write_text(text, encoding="utf-8")
    (tmp_path / "細目.md").write_text("細目\n", encoding="utf-8")
    monkeypatch.setattr(kaku, "SAIMOKU", tmp_path / "細目.md")
    g("add", "-A")
    g("commit", "-q", "-m", "元")
    return f


def test_毎回差し込む物が元より増えると赤で_同じか減れば緑(monkeypatch, tmp_path, capsys):
    """上限の内でも純増は赤（足すなら同じ変更で同じだけ畳む）。わざと 1 字足すと赤になる注入の試験。"""
    f = _git_repo(tmp_path, "元の核\n", monkeypatch)
    monkeypatch.setattr(kaku, "injected", lambda: (f,))
    assert kaku.grow("HEAD") == 0                       # 同じ
    f.write_text("元の核\n足\n", encoding="utf-8")
    assert kaku.grow("HEAD") == 1                       # 1 字でも増えたら赤
    out = capsys.readouterr().out
    assert "増えた" in out and "同じだけ畳む" in out.strip().splitlines()[-1]
    f.write_text("核\n", encoding="utf-8")
    assert kaku.grow("HEAD") == 0                       # 減った


def test_比べる元が読めないと増え方の照らしは緑にせず止まる(monkeypatch, tmp_path, capsys):
    f = _git_repo(tmp_path, "元の核\n", monkeypatch)
    monkeypatch.setattr(kaku, "injected", lambda: (f,))
    assert kaku.grow("無い枝") == 2
    new = tmp_path / "新.md"                            # 元の時に無い file
    new.write_text("x", encoding="utf-8")
    monkeypatch.setattr(kaku, "injected", lambda: (new,))
    assert kaku.grow("HEAD") == 2
    assert "照らせない" in capsys.readouterr().out


def test_差し込む物を足すと増え方の照らしもそれを見る(monkeypatch, tmp_path, capsys):
    """差し込む一覧と照らす一覧が別の写しに戻ると、足した物が黙って照らされず赤。"""
    f = _git_repo(tmp_path, "元の核\n", monkeypatch)
    third = tmp_path / "三つ目.md"
    third.write_text("三\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "三"], cwd=tmp_path, check=True)
    monkeypatch.setattr(kaku, "injected", lambda: (f, third))
    assert "三" in kaku.inject_text()                   # 差し込む
    third.write_text("三\n足\n", encoding="utf-8")
    assert kaku.grow("HEAD") == 1                       # 照らす
    assert "三つ目.md" in capsys.readouterr().out


def test_増え方の照らしは検査の入口から回る():
    assert kaku.injected() == (kaku.KAKU, kaku.FURUMAI)
    sh = (ROOT / "scripts" / "checks" / "kaku_growth.sh").read_text(encoding="utf-8")
    assert "kaku.py grow --base" in sh and "origin/main" in sh
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    check_job = ci.split("public-guard:")[0]
    assert "fetch-depth: 0" in check_job, "CI の check が origin/main を取らず、比べる元が無くなる"
