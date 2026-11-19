"""plugin core の試験: 核の差し込み（写しの枠が在れば差し込まない）と、量の上限の照らし。"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "core"
TOOL = PLUGIN / "scripts" / "kaku.py"

spec = importlib.util.spec_from_file_location("kaku", TOOL)
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)
LIMITS = kaku.LIMITS


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


def test_核と細目と_hook_が_plugin_の中に在る():
    assert (PLUGIN / "核.md").is_file() and (PLUGIN / "細目.md").is_file()
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
    assert str(PLUGIN / "細目.md") in ctx


def test_CLAUDE_md_が無い_repo_にも差し込む(tmp_path):
    r = run("inject", project=tmp_path)
    assert r.returncode == 0 and "additionalContext" in r.stdout


def test_写しの枠が在る_repo_には差し込まない(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("<!-- AF-CORE:BEGIN 写し -->\n核\n<!-- AF-CORE:END -->\n固有\n",
                                         encoding="utf-8")
    r = run("inject", project=tmp_path)
    assert r.returncode == 0 and r.stdout == ""


def test_上限の数は_1_か所で_核より各社固有が小さい():
    assert set(LIMITS) == {"核", "各社固有"}
    assert LIMITS["各社固有"] < LIMITS["核"]


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


def test_写しの枠が在れば枠の外だけを各社固有として測る(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    big = "核" * (LIMITS["各社固有"] // 3 + 10)
    claude.write_text(f"<!-- AF-CORE:BEGIN x -->\n{big}\n<!-- AF-CORE:END -->\n固有\n", encoding="utf-8")
    assert run("check", "--claude", claude).returncode == 0


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


def test_核の根治は問題_原因_解決_未来の_4_段で_未来は試験の段でない():
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s3 = _節(kaku_text, 3)
    assert "問題→原因→解決→未来" in s3
    assert "仕組み・設計が悪い前提" in s3 and "別の目の助手" in s3
    assert "未来は同じ問題が起きない姿" in s3, "核 §3 の未来が直した後の姿でない"
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    for word in ["**問題**", "**原因**", "**同じ原因の他の問題**", "**解決**", "**未来**",
                 "無理・無駄・重複", "聞かせ方", "混じって", "試験を足す段ではない"]:
        assert word in s3d, f"細目 §3 に無い: {word}"


def test_MGkm_は根治の_4_段の呼び名で説明の頼みにも_4_段で答える():
    assert "問題→原因→解決→未来（MGkm）" in _節((PLUGIN / "核.md").read_text(encoding="utf-8"), 3), "核 §3 に MGkm が無い"
    s3d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 3)
    assert "**呼び名 MGkm**" in s3d, "細目 §3 に MGkm の呼び名が無い"
    line = next(l for l in s3d.splitlines() if "呼び名 MGkm" in l)
    for word in ["問題 Mondai", "原因 Genin", "解決 Kaiketsu", "未来 Mirai", "説明", "4 段の見出しで答える"]:
        assert word in line, f"MGkm の行に無い: {word}"


def test_問いは選ぶ問いと開いた問いに分け_分からないを置き_言葉を混ぜない():
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    s4 = _節(kaku_text, 4)
    for word in ["選択肢の画面", "「分からない」も置く", "開いた問い", "AI の読み", "「分からない」には問いを作り直す"]:
        assert word in s4, f"核 §4 に無い: {word}"
    assert "例え話にせず" in _節(kaku_text, 2)
    s4d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 4)
    for word in ["どの問いにも「分からない」の選択肢", "AI の今の読み", "選ぶ問いと開いた問い", "問いの言葉", "開発用語", "業界の専門用語", "決まりの言葉", "オーナーの言葉", "例え話に替えず"]:
        assert word in s4d, f"細目 §4 に無い: {word}"


def test_古い根治と聞き方の言い回しが土台に残らない():
    olds = ["根治の 4 つの問い", "①構造の原因", "いつも選択肢の画面", "返事の中で平文の問いを出さない",
            "専門用語は日常の言葉にする", "専門の語は日常の言葉に言い換え", "名前・数字など選べない答えも候補を選択肢に置き"]
    hits = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in {".git", "tests"} or p.name == "CHANGELOG.md":
            continue                       # 試験の中の古い語の一覧と、変更の記録の経緯は除く
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".html"}:
            text = p.read_text(encoding="utf-8")
            hits += [f"{rel}: {o}" for o in olds if o in text]
    assert not hits, hits


def test_一言の返事は札と締めを省き_窓の役に決まった一覧を置かない():
    """同じ原因（決まりが 1 つの形に押し込める）の残り: 短い返事に 3 行を足さない・役の名を 5 つに閉じない。古い形を戻すと赤。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    assert "一言で済む返事は札と締めを省く" in _節(kaku_text, 5)
    s5d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 5)
    assert "**一言で済む返事**" in s5d and "札を付けたら締めも付ける" in s5d
    olds = ["の 5 つだけ。他の名を足さない", "親・書く・レビュー・調べ・手 の 5 つ", "社内で確かめてから答える", "問いの形（3 つだけ）", "決まった 4 文"]
    hits = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in {".git", "tests"} or p.name == "CHANGELOG.md":
            continue
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".html"}:
            text = p.read_text(encoding="utf-8")
            hits += [f"{rel}: {o}" for o in olds if o in text]
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

    def install(self, source="github"):
        """窓が立つ時に setup script が入れた形を作る（marketplace の clone と台帳）。"""
        loc = self.home / ".claude" / "plugins" / "marketplaces" / "agent-foundation"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(loc)], check=True, capture_output=True)
        _git(loc, "checkout", "-q", self.installed)
        plugins = self.home / ".claude" / "plugins"
        (plugins / "known_marketplaces.json").write_text(json.dumps({"agent-foundation": {
            "source": {"source": source, "repo": "o/agent-foundation-public"}, "installLocation": str(loc)}}))
        (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {"core@agent-foundation": [
            {"installPath": str(PLUGIN), "gitCommitSha": self.installed}]}}))

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
    _commit(f.work, {"plugins/core/核.md": "核 2\n"}, "核を変える")
    f.install()
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
    _commit(f.work, {"plugins/core/核.md": "核 2\n"}, "核を変える")
    f.install()                                          # 入れたのは 1 つ前（f.installed）
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
    for word in ["原因の台帳", "1 行ずつ", "直す窓／直した／直さない", "オーナーが決めた理由"]:
        assert word in s3, f"核 §3 に無い: {word}"
    s7 = _節(kaku_text, 7)
    assert "「直した」か「直さない」になるまで終わったと言わない" in s7 and "直す窓の行が残れば一部" in s7
    s4 = _節(kaku_text, 4)
    assert "1 つ選ばせる問いを出さない" in s4 and "挙がった物は全部やり" in s4
    saimoku = (PLUGIN / "細目.md").read_text(encoding="utf-8")
    assert "**原因の台帳**" in _節(saimoku, 3) and "**選ばせない**" in _節(saimoku, 4) and "**根治の終わり**" in _節(saimoku, 7)
    assert "③は 1 本の列（番号の順）にせず" in _節(saimoku, 8), "引き継ぎの残りが番号の列に戻った"
    olds = ["どれを今回直す", "一番手前の未決から取る", "どれから進めますか」と聞"]
    hits = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in {".git", "tests"} or p.name == "CHANGELOG.md":
            continue
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".html"}:
            text = p.read_text(encoding="utf-8")
            hits += [f"{rel}: {o}" for o in olds if o in text]
    assert not hits, hits


def test_main_へは製品もオーナーに聞かずに入れ_絵と差がある時だけ止める():
    """「本番への出荷は聞く」を核に戻すと赤（Notion の決定と窓が読む核が食い違う形）。"""
    kaku_text = (PLUGIN / "核.md").read_text(encoding="utf-8")
    assert "本番への出荷" not in _節(kaku_text, 4), "核 §4 に「本番への出荷は聞く」が戻った"
    s7 = _節(kaku_text, 7)
    for word in ["（製品も）オーナーに聞かずに入れる", "レビュー green", "試験が緑で衝突なし", "全体の絵", "差があれば止めて聞く", "先に絵を描き"]:
        assert word in s7, f"核 §7 に無い: {word}"
    s7d = _節((PLUGIN / "細目.md").read_text(encoding="utf-8"), 7)
    assert "**main へ入れる**" in s7d and "**③の段が土台に入るまで**" in s7d
    assert "核 §7 と細目 §7 の「main へ入れる」" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
