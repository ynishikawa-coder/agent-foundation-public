"""土台の在り処探し（skill-values/af_place.py の foundation_file）が、浅い市場の clone で入った版を見失わない試験。

前の形: Claude Code は市場の取り出し（plugins/marketplaces/<市場>）を浅い clone（先端の 1 つだけ）で取る。入った版
（plugins/cache/<市場>/<plugin>/<版>）が clone の先端と違うと、版が clone の歴史に無く "" を返し、守りの hook は
「public-guard/guard.py が見つからない・入れ直す」とだけ言って止めた（cache 側に無く marketplaces 側に在るのに）。
窓の側が git fetch --unshallow を手で打つまで止まり続けた。
今の形: 入った版の full sha を plugin の台帳（installed_plugins.json）から引いて出所から取り寄せ、同じ版を読む。
取り寄せられなければ "" のまま（止める側）で、止める文に訳と直し方（fetch --unshallow）を添える。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill-values"))
import af_place  # noqa: E402

REL = os.path.join("public-guard", "guard.py")


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def _layout(tmp_path, ledger=True):
    """出所（入った版 → 先へ進んだ版）と、先端だけの浅い市場の clone と、入った版の cache を作る。"""
    src = tmp_path / "src"
    (src / "public-guard").mkdir(parents=True)
    _git(src.parent, "init", "-q", "-b", "main", str(src))
    (src / "public-guard" / "guard.py").write_text("入った版\n", encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "commit", "-qm", "入った版")
    full = _git(src, "rev-parse", "HEAD")
    (src / "public-guard" / "guard.py").write_text("先へ進んだ版\n", encoding="utf-8")
    _git(src, "commit", "-qam", "進む")
    plugins = tmp_path / "plugins"
    clone = plugins / "marketplaces" / "market"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{src}", str(clone)], check=True)
    assert _git(clone, "rev-parse", "--is-shallow-repository") == "true"
    root = plugins / "cache" / "market" / "guard" / full[:12]
    root.mkdir(parents=True)
    if ledger:
        (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {"guard@market": [
            {"installPath": str(root), "version": full[:12], "gitCommitSha": full}]}}), encoding="utf-8")
    return clone, root


def test_注入_浅い_clone_で入った版が先端と違っても出所から取り寄せて同じ版を読む(tmp_path):
    clone, root = _layout(tmp_path)
    path = af_place.foundation_file(REL, str(root))
    assert path and Path(path).read_text(encoding="utf-8") == "入った版\n", af_place.MISS
    assert af_place.miss_note() == ""


def test_注入_取り寄せられなければ止める側の_空_で訳と直し方を添える(tmp_path):
    clone, root = _layout(tmp_path, ledger=False)   # 台帳に入った版の full sha が無い＝取り寄せられない
    assert af_place.foundation_file(REL, str(root)) == ""
    note = af_place.miss_note()
    assert "歴史に無い" in note and "浅い clone" in note and "fetch --unshallow" in note, note


def test_注入_台帳が壊れていても止める側(tmp_path):
    clone, root = _layout(tmp_path, ledger=False)
    (root.parents[3] / "installed_plugins.json").write_text("{壊れた", encoding="utf-8")
    assert af_place.foundation_file(REL, str(root)) == "" and "fetch --unshallow" in af_place.miss_note()


def test_注入_台帳の_sha_が入った版と違えば取り寄せない(tmp_path):
    clone, root = _layout(tmp_path, ledger=False)
    (root.parents[3] / "installed_plugins.json").write_text(json.dumps({"plugins": {"guard@market": [
        {"installPath": str(root), "gitCommitSha": "f" * 40}]}}), encoding="utf-8")
    assert af_place.foundation_file(REL, str(root)) == ""


def test_守りの_hook_の止める文に訳が載る(tmp_path, monkeypatch):
    clone, root = _layout(tmp_path, ledger=False)
    sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
    try:
        import guard_common as G
    finally:
        sys.path.pop(0)
    assert G.foundation_file(REL, str(root)) == "" and "fetch --unshallow" in G.miss_note()


def test_見つかった時は前の訳を残さない(tmp_path):
    clone, root = _layout(tmp_path, ledger=False)
    af_place.foundation_file(REL, str(root))
    assert af_place.MISS
    assert af_place.foundation_file(REL, str(ROOT / "plugins" / "guard")) == str(ROOT / REL)
    assert af_place.miss_note() == ""
