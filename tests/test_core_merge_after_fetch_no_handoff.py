"""setup script が正しい形で、目録を取り直した後に main へ合流しただけの差では、窓に引き継ぎと閉じを求めない。

起動の hook（plugin core の kaku.py inject）は、入った土台が main の先端より古い窓に知らせを出す。古さには 2 つある:
- setup script の形の誤り（版を指す・目録を取り直さない・入れ損ね）: 立て直しても同じ物が入る＝直してから引き継ぐ。
- 正しい形の setup script が目録を取り直した後に、main へ合流があった（窓の箱の作成と合流が数秒重なった）:
  直す物は無く、引き継ぐと窓を立て替えるだけ（系譜が深くなる）＝知らせだけで頼みを続ける。
見分けは入口 scripts/setup_plugins.py が書く印（~/.claude/af-foundation/setup.json の refreshed・catalog_sha・fetched）と、
入った commit から先端までの合流の時。remote は作り物の git、合流の時は GIT_COMMITTER_DATE で決める。
"""
import json
import os
import subprocess
import time

import pytest

from test_core_plugin import Foundation
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
