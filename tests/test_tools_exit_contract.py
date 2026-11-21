"""土台の道具の exit の約束（0=合う／1=外れが在る／2=照らせない）と、照らす数で黙って切らない事（原因の台帳の束 F6）。

- values_keys.py: 値の表が読めない時も 1（問題の鍵が在る時と同じ）で返し、使う側は「照らせない」を「ずれが在る」と取り違えた。
- kaku.py olds: git の file の並びを 2000 で黙って切り、それより多い repo では残りを照らさずに緑を返した。
- copies.py: 正本を path で指すだけの行を、path の字の重なりで写しと呼んだ（直し方どおり指す形にしても赤）。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VK = ROOT / "plugins" / "guard" / "scripts" / "values_keys.py"
COPIES = ROOT / "plugins" / "core" / "scripts" / "copies.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kaku = _load("af_kaku_for_exit", ROOT / "plugins" / "core" / "scripts" / "kaku.py")


def run(tool, *args):
    return subprocess.run([sys.executable, "-B", str(tool), *map(str, args)], capture_output=True, text=True)


def test_値の表が読めない時は_2_で鍵の問題の_1_と分ける(tmp_path):
    bad = tmp_path / "skill-values.json"
    bad.write_text("{ 作り物の壊れた JSON", encoding="utf-8")
    res = run(VK, bad)
    assert res.returncode == 2 and "照らせない" in res.stdout, res.stdout
    assert run(VK, tmp_path / "無い.json").returncode == 2


def test_照らす_file_を数で切らない(tmp_path):
    """注入: 2100 file の repo の最後の file にだけ古い形を置く。前は 2000 で切って緑だった。"""
    repo = tmp_path / "repo"
    (repo / "d").mkdir(parents=True)
    for i in range(2100):
        (repo / "d" / f"{i:05d}.md").write_text("作り物\n", encoding="utf-8")
    (repo / "d" / "02099.md").write_text("作り物の古い形 OLDMARK\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    rows = [{"id": "作り物", "what": "w", "files": ["d/*.md"], "pattern": "OLDMARK", "fix": "f", "example": "e"}]
    for r in rows:
        r["re"] = __import__("re").compile(r["pattern"])
    hits = kaku._hits(rows, kaku._checkout_texts(repo))
    assert [f for _, f in hits] == ["d/02099.md"]


def test_正本を_path_で指すだけの行は写しと呼ばない(tmp_path):
    f = tmp_path / "使う側の雛形.md"
    f.write_text("- PR を出す（本文の型の正本: 土台の .github/pull_request_template.md）\n", encoding="utf-8")
    res = run(COPIES, f, "--foundation", ROOT)
    assert res.returncode == 0, res.stdout


def test_path_を添えた写しは今も拾う(tmp_path):
    """path を除いても、決まりの文そのものが重なれば写し（指す字を除くのは字の並びの照らしだけ）。"""
    f = tmp_path / "使う側の決まり.md"
    f.write_text("- 戻せない操作の前に人に聞く — 強制 push・DB の削除・人の手が入った物や git に無い一点物の削除"
                 "（plugins/core/核.md）。\n", encoding="utf-8")
    assert run(COPIES, f).returncode == 1


def test_日本語の文をインラインのコードで囲んだ写しは今も拾う(tmp_path):
    """注入（PR #114 のレビュー）: 指す字の除外が `…` の全部を消すと、核の文を `…` で囲むだけで写しの関所を迂回できた。"""
    f = tmp_path / "使う側の決まり.md"
    f.write_text("- `戻せない操作の前に人に聞く — 強制 push・DB の削除・人の手が入った物や git に無い一点物の削除`\n",
                 encoding="utf-8")
    assert run(COPIES, f).returncode == 1
