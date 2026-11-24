"""やり直しの無駄を消す（オーナー同意 2026-11-22）: 誤りを出た後に同じ作業をやり直させる形を入れない（注入の試験）。

前の形（2026-11-19 に入った）は、1 つの仕事のために窓を何本も立てさせ（土台が新しくなったら引き継いで閉じる・
red のたびに新しいレビューの窓・原因の台帳の行ごとに直す窓・文脈の目安で後継の窓）、同じ返事を書き直させた
（返事の形の差し戻し・目安越えの締めの差し戻し）。並走・試験・別の目のレビュー（1 回）・戻せない操作の前の守りは残す。
ここでは、古い形をわざと入れると見分けが拾うこと（赤になること）と、今の正本に古い形が無いことを見る。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_core_plugin import kaku, used_texts

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core"
GUARD_DIR = ROOT / "plugins" / "guard"
sys.path.insert(0, str(ROOT / "skill-values"))
import skill_values as SV  # noqa: E402
from saimoku import 全文 as 細目の全文, files as 細目の_files


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


# ── 1. 決まりの今の文（文をそのまま照らす＝消すと赤）──
RULES = [
    ("plugins/core/核.md", "- 最後の 2 行は `AI がこの後やること:`（締める前に動かす）と `あなたがやること:`。"),
    ("plugins/core/核.md", "- AI が立てた窓は済んだら自分で閉じる。"),
    ("plugins/core/振る舞い.md", "- **後継へ渡す残り** は 1 本の列にせず、1 つずつ持ち主（この窓・直す窓・台帳の行）を付ける。"),
    ("plugins/core/振る舞い.md", "- **同じ原因の他の問題** は書いた窓が削らず選ばず全部を原因の台帳へ。"),
    ("plugins/core/振る舞い.md", "直す窓は行ごとでなく関係しない束ごとに並べる。"),
    ("plugins/core/細目/03-直すは根治.md", "まとまりの行には同じ `直す窓` を付ける。"),
    ("plugins/core/細目/03-直すは根治.md", "直す窓は直しが合流したら自分の行を全部 `直した` に替え、立てた窓へ返す。"),
    ("plugins/core/細目/04-聞き方.md", "1 枝 1 PR に入らなかった仕事は原因の台帳の行にし、互いに関係しないまとまりごとに立てた窓を `直す窓` に付ける。"),
    ("plugins/core/細目/07-完了の4状態.md", "この窓から触れない repo は、原因の台帳の行にして repo ごとに 1 つの直す窓を `直す窓` に付ける。"),
    ("plugins/core/細目/05-返事の形.md", "- **締めの 2 行** — オーナーが最後だけ読んで、自分の番かが分かる形にする。"),
    ("plugins/core/細目/05-返事の形.md", "  - `あなたがやること: なし` ／ `あなたがやること: <何を>（問いに答える・手を打つ窓の URL）`"),
    ("plugins/core/細目/08-記録.md", "- **文脈が重い時** — 後継の窓へ移らず、自動の要約に任せてそのまま続ける。"),
    ("plugins/core/細目/04-聞き方.md", "レビュー・調べ・定型の直しの窓と助手は Sonnet（お金・戻せない操作・核に触れるレビューは Opus）。"),
    ("plugins/core/細目/04-聞き方.md", "話題が変われば新しい窓を勧める。"),
]


@pytest.mark.parametrize("rel, sentence", RULES)
def test_決まりの今の文が在る(rel, sentence):
    assert sentence in _read(rel), (rel, sentence)


# ── 2. 古い形の見分け（わざと入れると拾う・今の正本には無い）──
OLD_RULES = {
    "閉じてよいかの決まり文": re.compile(r"この窓は閉じて大丈夫です|まだ閉じないでください"),
    "進めないの決まり文": re.compile(r"これが済むまで <何> に進めません"),
    "文脈で後継の窓へ移る": re.compile(r"区切りの良い所で後継の窓へ移る|後継の URL を書く"),
    "red のたびに新しいレビューの窓": re.compile(r"書いた窓がレビューの窓を立てて頼み"),
    "台帳の行ごとに直す窓": re.compile(r"1 窓に収まらない行は窓を並べて"),
}


def old_rule_hits(text):
    return sorted(name for name, pat in OLD_RULES.items() if pat.search(text))


@pytest.mark.parametrize("name, sample", [
    ("閉じてよいかの決まり文", "  - `あなたがやること: なし。この窓は閉じて大丈夫です。`"),
    ("進めないの決まり文", "  - `あなたがやること: <何を>。これが済むまで <何> に進めません。`"),
    ("文脈で後継の窓へ移る", "- **文脈が重い時** — 重くなったら区切りの良い所で後継の窓へ移る。"),
    ("red のたびに新しいレビューの窓", "- **判定を頼む** — 書いた窓がレビューの窓を立てて頼み、返しを受けて合流まで運ぶ。"),
    ("台帳の行ごとに直す窓", "1 窓に収まらない行は窓を並べて `直す窓` にする（核 §4）。"),
])
def test_注入_古い決まりの文を入れると見分けが拾う(name, sample):
    text = 細目の全文() + "\n" + sample + "\n"
    assert name in old_rule_hits(text)


@pytest.mark.parametrize("rel", ["plugins/core/核.md", "plugins/core/振る舞い.md", *細目の_files(), "CONTRIBUTING.md",
                                 "docs/核の届け方.md", "plugins/checker/skills/review-pr/SKILL.md"])
def test_今の正本に古い決まりの文が無い(rel):
    assert old_rule_hits(_read(rel)) == []


# ── 3. 土台が新しくなった窓に引き継ぎ・閉じを求めない ──
HANDOVER = re.compile(r"create_session で|archive_session で|引き継いで閉じる|自分の窓を閉じる")


def _f():
    return {"installed": "a" * 40, "main": "b" * 40, "ref": "main", "shas": {"core": "a" * 40}, "plugins": ["guard"]}


def test_注入_引き継いで閉じる文を入れると見分けが拾う():
    old = ("## 土台が新しくなった — この窓を引き継いで閉じる\n2. claude-code-remote の create_session で、同じ repo に"
           "新しい窓を立てる。\n4. archive_session で自分の窓を閉じる。\n")
    assert HANDOVER.search(old)


def _update(f):
    return kaku.update_text(f, kaku.changed_core_text(f["main"], kaku.tip_texts(f["main"]), {}))


@pytest.mark.parametrize("make", [_update, kaku.stale_at_start_text, kaku.unknown_at_start_text,
                                  kaku.after_setup_text, lambda f: kaku.RESTART_TEXT])
def test_土台の新しさの知らせは窓をそのまま続けさせる(monkeypatch, tmp_path, make):
    monkeypatch.setenv("HOME", str(tmp_path))       # 目録が無い＝先端の本文は読めない（読めない事を 1 行で名指す）
    text = make(_f())
    assert not HANDOVER.search(text), text
    assert "そのまま頼みを続ける" in text and "create_session・archive_session をしない" in text
    if make is _update:
        assert "（main の先端の 核.md を読めなかった" in text
    else:                                            # 起動の時は核を上に 1 枚だけ差し込み、知らせに本文を重ねない
        assert "### main の先端の" not in text


def test_起動の後の知らせは同じ先端で繰り返さない():
    import inspect
    src = inspect.getsource(kaku._fresh_text)  # fresh は知らせを束ねるだけ・先端の知らせの本体はここ
    assert 'state.get("told")' in src and "handover" not in src


# ── 4. 返事の形は知らせるだけ（Stop で差し戻さない）──
def test_注入_guard_に_Stop_の見張りを足しても締めを差し戻さない(tmp_path):
    box = tmp_path / "guard"
    shutil.copytree(GUARD_DIR, box, symlinks=True, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("schema.json", "skill_values.py", "af_place.py"):
        link = box / "lib" / name
        if link.is_symlink():
            link.unlink()
            shutil.copy(ROOT / "skill-values" / name, link)
    (box / "scripts" / "zz_stop.py").write_text('HOOKS = {"stop": "f"}\n\ndef f(data, vals):\n    return "差し戻す"\n',
                                                encoding="utf-8")
    env = dict(os.environ, AF_GUARD_TMP=str(tmp_path / "t"), AF_GUARD_STATE=str(tmp_path / "s"))
    p = subprocess.run([sys.executable, str(box / "scripts" / "guard.py"), "stop"], input="{}", capture_output=True,
                       text=True, env=env)
    assert p.returncode == 0 and p.stdout == "" and "decision" not in p.stdout
    hooks = json.loads((GUARD_DIR / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert "Stop" not in hooks


# ── 5. 文脈の目安で後継の窓へ引き継がせない（自動の要約に任せる）──
def test_文脈の目安の見張りと鍵が無い():
    assert not (GUARD_DIR / "scripts" / "context_size.py").exists()
    keys = SV.schema()["sections"]["guard"]["keys"]
    assert not [k for k in keys if k.startswith("context_")]


@pytest.mark.parametrize("key, value", [("context_limit", 300000), ("context_stop_max", 2),
                                        ("context_handoff", ["^mcp__[^ ]*__create_session \\{.*\\}$"])])
def test_注入_値の表に文脈の目安の古い鍵を置くと畳んだ鍵と名指す(key, value):
    got = SV.check({"guard": {key: value}})
    assert any(("guard.%s は畳んだ鍵" % key) in g for g in got), got


# ── 消した仕組みを今も在る物として書く説明（plugin の説明・README・skill・AI に出す文）──
STALE_DESC = re.compile(r"差し戻す Stop の hook|AI だけへ差し戻す|返事の差し戻し|Stop の差し戻し|文脈の量を|文脈の量と越えた|引き継がずに締める|既に差し戻した")


@pytest.mark.parametrize("sample", [
    "崩れを AI だけへ差し戻す Stop の hook",
    "guard の一覧に「文脈の量と越えた後の締めの差し戻し」",
    "session-watch の返事の差し戻しも直に呼ぶ",
])
def test_消した仕組みの説明を入れると拾う(sample):
    assert STALE_DESC.search(sample)


def test_説明に消した仕組みが残らない():
    hits = [f"{rel}:{i}" for rel, text in used_texts(under=("plugins", "public-guard"), suffixes=(".md", ".json", ".py"))
            for i, line in enumerate(text.splitlines(), 1) if STALE_DESC.search(line)]
    assert not hits, hits


# ── 自動の要約を約 20 万 token で走らせる（setup が settings.json に置く・人の値は替えない）──
def _setup_mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("setup_plugins_t", ROOT / "scripts" / "setup_plugins.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_要約の窓を置く(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    m = _setup_mod()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"env": {"TZ": "Asia/Tokyo"}}', encoding="utf-8")
    assert m.compact_window()
    d = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert d == {"env": {"TZ": "Asia/Tokyo"}, "autoCompactWindow": 200_000}


def test_要約の窓は無い時も置く(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _setup_mod().compact_window()
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text())["autoCompactWindow"] == 200_000


def test_人が置いた要約の窓は替えない(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"autoCompactWindow": 400000}', encoding="utf-8")
    assert _setup_mod().compact_window()
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text())["autoCompactWindow"] == 400000


def test_壊れた設定は替えず知らせる(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{broken", encoding="utf-8")
    assert not _setup_mod().compact_window()
    assert (tmp_path / ".claude" / "settings.json").read_text() == "{broken"
