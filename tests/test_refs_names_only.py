"""土台の md は土台の節を名で指すか（refs.py check を土台の自分の文書へ当てる）。

意図: 土台の文書の指しが、節を足す・並べ替えた後も同じ節を指し続ける事。
原因: refs.py は番号だけの指し（核 §<番号> の形）を赤にするが、土台の自分の文書には誰も当てていなかった。
土台が節を足す・並べ替えると、土台の skill・文書の番号の指しが黙って別の節を指した。
また名の中の 1 段の入れ子の「」（CONTRIBUTING.md の節「配り方と「壊れる:」変更」）を読めず、
refs が出す直しの案そのものが照らせなかった。
"""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core"
TOOL = CORE / "scripts" / "refs.py"
_spec = importlib.util.spec_from_file_location("af_refs_names_only", TOOL)
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


def _md_files():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.md"], capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines()
            if not p.startswith(("tests/", "CHANGELOG")) and (ROOT / p).is_file()]


def test_土台の_md_は土台の節を番号だけで指さない():
    c = R.contract(ROOT)
    bad = []
    for p in _md_files():
        inner = p.parent == CORE / "細目" or p in (CORE / "核.md", CORE / "振る舞い.md")   # 核と一緒に差し込む中の指し（同じ版で読む）
        for lno, msg in R.check_all(c, p.read_text(encoding="utf-8"), numbers_ok=inner)[0]:
            bad.append(f"{p.relative_to(ROOT)}:{lno} {msg}")
    assert not bad, "\n".join(bad)


def test_名の中の_1_段の入れ子の括弧を読む():
    c = R.contract(ROOT)
    m = R._REF.search("CONTRIBUTING.md「配り方と「壊れる:」変更」を読む")
    assert m.group("name") == "配り方と「壊れる:」変更"                       # 入れ子で切らない
    assert R.find(c, "CONTRIBUTING.md", m.group("name")) is not None          # 名で節に当たる（文の引きに逃げない）
    assert R.check_text(c, "CONTRIBUTING.md「配り方と「壊れない:」変更」を読む")      # 名が違えば赤のまま
