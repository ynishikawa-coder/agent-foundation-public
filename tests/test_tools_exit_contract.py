"""土台の道具が照らす数で黙って切らない事（原因の台帳の束 F6）。

- kaku.py olds: git の file の並びを 2000 で黙って切り、それより多い repo では残りを照らさずに緑を返した。
"""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kaku = _load("af_kaku_for_exit", ROOT / "plugins" / "core" / "scripts" / "kaku.py")


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

