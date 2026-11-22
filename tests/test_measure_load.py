"""量を数える道具（scripts/measure_load.py）が、起動・毎ターン・skill・写しの量を数え違えない。

意図: 土台が窓の文脈に入れる量を減らす仕事で、前→後を同じ物差しで数えて PR に書けるようにする。
課題: 数え方が窓ごとに揃わず、減ったかを記録で言えなかった。
原因: 量の数えが核・振る舞い・細目だけにあり、skill の説明文・本文・毎ターンの知らせを数える道具が無かった。
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("measure_load", ROOT / "scripts" / "measure_load.py")
ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml)


def _skill(root, plugin, name, desc, body, extra=None):
    d = root / plugin / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n{body}", encoding="utf-8")
    for fn, text in (extra or {}).items():
        (d / fn).write_text(text, encoding="utf-8")


def test_skillの説明文と本文と他のfileを分けて数える(tmp_path):
    _skill(tmp_path, "p", "a", "あいう", "本文12345", {"ref.md": "xy", "pic.png": "bin"})
    [s] = ml.skills(tmp_path)
    assert s == {"skill": "p:a", "説明文": 3, "本文": 7, "他の file": 2}


def test_説明文が太ると数が増える(tmp_path):
    _skill(tmp_path / "前", "p", "a", "短い", "b")
    _skill(tmp_path / "後", "p", "a", "短い" + "太" * 50, "b")
    assert ml.skills(tmp_path / "後")[0]["説明文"] - ml.skills(tmp_path / "前")[0]["説明文"] == 50


def test_根治の1文の写しを行で数える(tmp_path):
    (tmp_path / "plugins" / "x").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "plugins" / "x" / "a.py").write_text(f'A = "{ml.COPY_MARK}"\nB = "{ml.COPY_MARK}"\n', encoding="utf-8")
    (tmp_path / "scripts" / "b.py").write_text("C = 1\n", encoding="utf-8")
    assert ml.copies(tmp_path) == {"行": 2, "file": {"plugins/x/a.py": 2}}


def test_この_repo_を数えて全部の欄を出す():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "measure_load.py"), "--json"],
                       capture_output=True, text=True, check=True)
    m = json.loads(r.stdout)
    assert m["起動"]["skill の説明文"]["skill の数"] == len(list((ROOT / "plugins").glob("*/skills/*/SKILL.md")))
    assert m["起動"]["核の差し込み"]["字"] > 0
    assert m["起動"]["計（字）"] == m["起動"]["skill の説明文"]["字"] + m["起動"]["核の差し込み"]["字"]
    assert all(v["字"] > 0 for v in m["毎ターン"].values())
