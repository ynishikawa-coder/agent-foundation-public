"""setup script が正しい形で、目録を取り直した後に main へ合流しただけの差では、窓に引き継ぎと閉じを求めない。

起動の hook（plugin core の kaku.py inject）は、入った土台が main の先端より古い窓に知らせを出す。古さには 2 つある:
- setup script の形の誤り（版を指す・目録を取り直さない・入れ損ね）: 立て直しても同じ物が入る＝直してから引き継ぐ。
- 正しい形の setup script が目録を取り直した後に、main へ合流があった（窓の箱の作成と合流が数秒重なった）:
  直す物は無く、引き継ぐと窓を立て替えるだけ（系譜が深くなる）＝知らせだけで頼みを続ける。
見分けは入口 scripts/setup_plugins.py が書く印（~/.claude/af-foundation/setup.json の refreshed・catalog_sha・fetched）と、
入った commit から先端までの合流の時。remote は作り物の git、合流の時は GIT_COMMITTER_DATE で決める。
見張りの時間（深く取る fetch を含む git の全部）は 1 つの区切りの内で、越えても核の差し込みは止めない。
遅い・数える git は PATH の前に置いた作り物の git（本物の git へ渡し、決めた形の fetch だけ眠る）で作る。
"""
import json
import os
import shutil
import subprocess
import time

import pytest

from test_core_plugin import Foundation, run
from test_setup_plugins import foundation, run as run_entry

HANDOFF = ("create_session", "archive_session", "update_environment")
NOW = int(time.time())


def _merge(f, files, at):
    """main へ at（epoch 秒）に合流した commit を作る（合流の時＝first-parent の commit の committer の時）。"""
    for name, body in files.items():
        p = f.work / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    env = dict(os.environ, GIT_COMMITTER_DATE=f"{at} +0000", GIT_AUTHOR_DATE=f"{at} +0000")
    for args in (["add", "-A"], ["commit", "-q", "-m", "合流"], ["push", "-q", "origin", "HEAD:main"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=f.work,
                       env=env, check=True, capture_output=True)


def _mark(f, **over):
    """入口が書く印（正しい形で全部入った時の形）。over で欄を替える・None で欄を消す。"""
    state = {"entry": "scripts/setup_plugins.py", "market": "agent-foundation", "plugins": ["core"], "missing": [],
             "stale": [], "refreshed": True, "catalog_sha": f.installed, "fetched": NOW - 600}
    state.update(over)
    state = {k: v for k, v in state.items() if v is not None}
    d = f.home / ".claude" / "af-foundation"
    d.mkdir(parents=True, exist_ok=True)
    (d / "setup.json").write_text(json.dumps(state), encoding="utf-8")


def _box(tmp_path, merged_at, source=None, **mark):
    f = Foundation(tmp_path)
    f.install()
    if source is not None:
        p = f.home / ".claude" / "plugins" / "known_marketplaces.json"
        m = json.loads(p.read_text(encoding="utf-8"))
        m["agent-foundation"]["source"].update(source)
        p.write_text(json.dumps(m), encoding="utf-8")
    _mark(f, **mark)
    _merge(f, {"plugins/guard/x.py": "x\n"}, merged_at)
    return f


def test_正しい形で取り直しの後に合流した差は知らせだけで引き継ぎを求めない(tmp_path):
    """注入: 正しい形の印＋取り直しの数秒後に main へ合流 → 引き継ぎ・閉じ・setup script の直しを求めない。"""
    f = _box(tmp_path, merged_at=NOW - 600 + 3)
    text = f.hook("inject")
    assert "取り直しの後に入った差" in text and "guard" in text and "頼みを続ける" in text
    assert "土台が古いまま立った窓" not in text
    assert not [w for w in HANDOFF if w in text], text
    assert "# 振る舞いの核" in text                      # 核の差し込みは止めない
    assert f.hook("fresh") == ""                          # 問いのたびにも引き継ぎを出さない
    again = f.hook("inject", source="compact")            # 圧縮の後も同じ見分け
    assert "取り直しの後に入った差" in again and "archive_session" not in again


def test_古い形の_setup_script_で立った窓には引き継ぎを求め続ける(tmp_path):
    """注入: 入口の印が無い（古い形）→ 合流が取り直しの後でも、直してから引き継ぐ知らせ。"""
    f = Foundation(tmp_path)
    f.install()
    _merge(f, {"plugins/guard/x.py": "x\n"}, NOW)
    text = f.hook("inject")
    assert "土台が古いまま立った窓" in text and all(w in text for w in HANDOFF)
    assert "取り直しの後に入った差" not in text


@pytest.mark.parametrize("why, kw", [
    ("取り直しより前に合流していた（版を指した目録など）", {"merged_at": NOW - 600 - 3600}),
    ("取り直せなかった", {"refreshed": False}),
    ("入れ損ねた plugin が在る", {"missing": ["guard"]}),
    ("名簿の版に揃わない", {"stale": ["guard"]}),
    ("入った commit が取り直した名簿の版と違う", {"catalog_sha": "0" * 40}),
    ("取り直しの時が無い古い印", {"fetched": None}),
    ("目録が版を指す", {"source": {"ref": "v0.4.18"}}),
])
def test_形の誤りの印が_1_つでも在れば引き継ぎを求める(tmp_path, why, kw):
    """注入: 正しい形の印のどれか 1 つを外す → 「取り直しの後に入った差」と見ず、直してから引き継ぐ知らせのまま。"""
    merged_at = kw.pop("merged_at", NOW - 600 + 3)
    f = _box(tmp_path, merged_at, **kw)
    text = f.hook("inject")
    assert "土台が古いまま立った窓" in text and all(w in text for w in HANDOFF), why
    assert "取り直しの後に入った差" not in text, why


def test_入口は目録を取り直した時を印に書く(tmp_path):
    """起動の hook が見分けに使う fetched を、入口が取り直しの直後に書く（無いと見分けられず引き継ぎ側に倒れる）。"""
    before = time.time()
    r, _, _, home = run_entry(tmp_path, foundation(tmp_path, ["core"]))
    assert r.returncode == 0, r.stdout
    state = json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text(encoding="utf-8"))
    assert isinstance(state.get("fetched"), (int, float)) and before - 1 <= state["fetched"] <= time.time() + 1


def _shallow(f):
    """目録の clone を本番の形（浅い・1 commit）に替える。"""
    loc = f.home / ".claude" / "plugins" / "marketplaces" / "agent-foundation"
    shutil.rmtree(loc)
    subprocess.run(["git", "clone", "-q", "--depth=1", f"file://{f.remote}", str(loc)], check=True, capture_output=True)
    head = subprocess.run(["git", "-C", str(loc), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    assert head.stdout.strip() == f.installed


def _merges(tmp_path, times, shallow):
    f = Foundation(tmp_path)
    f.install()
    if shallow:
        _shallow(f)
    _mark(f)
    for i, at in enumerate(times):
        _merge(f, {f"plugins/guard/x{i}.py": "x\n"}, at)
    return f


SHALLOW = pytest.mark.parametrize("shallow", [True, False], ids=["浅い clone", "浅くない clone"])


@SHALLOW
def test_間の合流が全部取り直しの後なら知らせだけ(tmp_path, shallow):
    """注入: 合流 3 本が全部取り直しの後 → 浅い clone でも間を全部読み、知らせだけ。"""
    f = _merges(tmp_path, [NOW - 600 + 3, NOW - 600 + 5, NOW - 600 + 9], shallow)
    text = f.hook("inject")
    assert "取り直しの後に入った差" in text and not [w for w in HANDOFF if w in text], text


@SHALLOW
def test_取り直しの前と後の合流が混ざれば引き継ぎを求める(tmp_path, shallow):
    """注入: 取り直しの 1 時間前の合流＋取り直しの 3 秒後の合流 → 先端の時だけで代わりにせず、形の誤り（引き継ぎ）。"""
    f = _merges(tmp_path, [NOW - 600 - 3600, NOW - 600 + 3], shallow)
    text = f.hook("inject")
    assert "土台が古いまま立った窓" in text and all(w in text for w in HANDOFF), text
    assert "取り直しの後に入った差" not in text


@SHALLOW
def test_間の合流の時が読めなければ引き継ぎを求める(tmp_path, shallow):
    """注入: main を入った commit の続きでない履歴へ書き換える（合流は取り直しの後）→ 先端から入った commit に
    辿り着けず、間の合流の時を全部は読めない → 形の誤り（引き継ぎ）。"""
    f = _merges(tmp_path, [], shallow)
    env = dict(os.environ, GIT_COMMITTER_DATE=f"{NOW - 600 + 3} +0000", GIT_AUTHOR_DATE=f"{NOW - 600 + 3} +0000")
    subprocess.run(["git", "checkout", "-q", "--orphan", "other"], cwd=f.work, check=True, capture_output=True)
    (f.work / "plugins" / "guard").mkdir(parents=True, exist_ok=True)
    (f.work / "plugins" / "guard" / "x.py").write_text("x\n", encoding="utf-8")
    for args in (["add", "-A"], ["commit", "-q", "-m", "書き換え"], ["push", "-q", "-f", "origin", "HEAD:main"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=f.work,
                       env=env, check=True, capture_output=True)
    text = f.hook("inject")
    assert "土台が古いまま立った窓" in text and all(w in text for w in HANDOFF), text
    assert "取り直しの後に入った差" not in text


def test_知らせだけの窓も起動の後に入った_plugin_の変更では引き継ぎを求める(tmp_path):
    """注入: 知らせだけの窓が立つ → 起動の時の先端までは数え済みで fresh は黙る → 文書だけの変更でも黙る →
    main で plugin が変わる → fresh が引き継ぎを求める（圧縮の後も知らせは同じで、引き継ぎも消えない）。"""
    f = _merges(tmp_path, [NOW - 600 + 3], shallow=True)
    assert "取り直しの後に入った差" in f.hook("inject")
    assert f.hook("fresh") == ""
    _merge(f, {"docs/a.md": "2\n"}, NOW)
    assert f.hook("fresh") == ""
    _merge(f, {"plugins/core/y.py": "y\n"}, NOW)
    text = f.hook("fresh")
    assert "引き継いで閉じる" in text and all(w in text for w in ("create_session", "archive_session", "core")), text
    assert "取り直しの後に入った差" in f.hook("inject", source="compact")
    assert "引き継いで閉じる" in f.hook("fresh")


# ── 見張りの時間の区切りと、深く取る fetch を走らせる所 ──

DEEP = "--depth=50"


def _shim(tmp_path, sleep_on=None, secs=30):
    """本物の git へ渡す作り物の git を作る。全ての呼びの引数を log へ 1 行ずつ書き、sleep_on を含む呼びは secs 秒眠る
    （exec で眠る＝時間切れで殺せば終わる）。返すのは (PATH に足す dir, log の path)。"""
    d = tmp_path / "shim"
    d.mkdir()
    log = tmp_path / "git.log"
    real = shutil.which("git")
    body = f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{log}"\n'
    if sleep_on:
        body += f'case "$*" in *"{sleep_on}"*) exec sleep {secs};; esac\n'
    body += f'exec "{real}" "$@"\n'
    (d / "git").write_text(body, encoding="utf-8")
    (d / "git").chmod(0o755)
    return d, log


def _hook(f, event, shim, sid="s1", **env):
    extra = {"AF_FRESH_INTERVAL": "0", "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}", **env}
    t = time.monotonic()
    r = run(event, project=f.tmp, home=f.home, stdin=json.dumps({"session_id": sid, "source": "startup"}), extra=extra)
    took = time.monotonic() - t
    assert r.returncode == 0, r.stderr
    return (json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout else ""), took


def test_深く取る_fetch_が遅くても見張りは区切りの内で終わり核を差し込む(tmp_path):
    """注入: 正しい形の印＋浅い clone（合流の時を読むのに深く取る）＋深く取る fetch が 30 秒眠る、区切り 3 秒 →
    hook は区切りの内で終わり、核を差し込み、合流の時は読めない＝形の誤りの側（引き継ぎ）に倒れる。"""
    f = _merges(tmp_path, [NOW - 600 + 3], shallow=True)
    shim, log = _shim(tmp_path, sleep_on=DEEP)
    text, took = _hook(f, "inject", shim, AF_FRESH_BUDGET="3")
    assert DEEP in log.read_text(encoding="utf-8")         # 眠る fetch まで届いた（作り物が効いた）
    assert took < 3 + 5, took
    assert "# 振る舞いの核" in text
    assert "土台が古いまま立った窓" in text and "取り直しの後に入った差" not in text


def test_先端を取る_fetch_が遅くても区切りの内で終わり核を差し込む(tmp_path):
    """注入: 先端を浅く取る fetch が 30 秒眠る、区切り 3 秒 → 区切りの内で比べられない（何も言わない）で終わり、核は差し込む。"""
    f = _merges(tmp_path, [NOW - 600 + 3], shallow=True)
    shim, _ = _shim(tmp_path, sleep_on="--depth=1")
    text, took = _hook(f, "inject", shim, AF_FRESH_BUDGET="3")
    assert took < 3 + 5, took
    assert "# 振る舞いの核" in text and "土台が古い" not in text


def test_見張りが上限を越えても核は先に差し込む(tmp_path):
    """注入: 見張りの区切りを 60 秒に広げ、fetch を 30 秒眠らせ、hook が待つ上限を 1 秒にする → 見張りを待たずに
    核と「時間内に終わらなかった」の知らせを出す（見張りの結果に核の差し込みが頼らない）。"""
    f = _merges(tmp_path, [NOW - 600 + 3], shallow=True)
    shim, _ = _shim(tmp_path, sleep_on="fetch")
    text, took = _hook(f, "inject", shim, AF_FRESH_BUDGET="60", AF_INJECT_LIMIT="1")
    assert took < 1 + 5, took
    assert "# 振る舞いの核" in text and "時間内に終わらなかった" in text


def test_問いのたびの見張りは深く取らない(tmp_path):
    """注入: 起動の時は先端と同じ窓 → main で plugin が変わる → fresh は引き継ぎを出すが、深く取る fetch も合流の時の
    log も走らせない（fresh は合流の時を使わない）。"""
    f = Foundation(tmp_path)
    f.install()
    _shallow(f)
    _mark(f)
    shim, log = _shim(tmp_path)
    assert "土台が古い" not in _hook(f, "inject", shim)[0]
    _merge(f, {"plugins/guard/x.py": "x\n"}, NOW)
    log.write_text("", encoding="utf-8")
    text, _ = _hook(f, "fresh", shim)
    assert "引き継いで閉じる" in text
    calls = log.read_text(encoding="utf-8")
    assert "fetch" in calls and DEEP not in calls and "--first-parent" not in calls, calls


@pytest.mark.parametrize("why, kw", [
    ("入口の印が無い（古い形）", {"mark": False}),
    ("取り直せなかった", {"refreshed": False}),
    ("目録が版を指す", {"source": {"ref": "v0.4.18"}}),
])
def test_形の誤りの印の窓は合流の時を読みに行かない(tmp_path, why, kw):
    """注入: 印が正しい形と言わない窓 → 引き継ぎの知らせは出し、深く取る fetch も合流の時の log も走らせない。"""
    f = Foundation(tmp_path)
    f.install()
    _shallow(f)
    if kw.pop("mark", True):
        _mark(f, **{k: v for k, v in kw.items() if k != "source"})
    if "source" in kw:
        p = f.home / ".claude" / "plugins" / "known_marketplaces.json"
        m = json.loads(p.read_text(encoding="utf-8"))
        m["agent-foundation"]["source"].update(kw["source"])
        p.write_text(json.dumps(m), encoding="utf-8")
    _merge(f, {"plugins/guard/x.py": "x\n"}, NOW - 600 + 3)
    shim, log = _shim(tmp_path)
    text, _ = _hook(f, "inject", shim)
    assert "土台が古いまま立った窓" in text, why
    calls = log.read_text(encoding="utf-8")
    assert DEEP not in calls and "--first-parent" not in calls, (why, calls)
