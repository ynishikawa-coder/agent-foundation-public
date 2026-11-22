"""量の照らし（kaku.py grow）が、細目を節ごとの file に割った後の main の細目を読めるかを照らす。

意図: 細目の量が main より増えていないかを、細目が dir になった後も照らし続ける。
課題: main の細目が dir になった後、どの PR でも「細目.md が読めない」で kaku_growth が赤になった。
原因: dir の中身を引く git ls-tree を dir の親で呼んでいた（ls-tree は作業場所の下だけを並べるので中身が空に見え、
  割る前の 1 枚の細目.md を探して止まった）。
"""
import importlib.util
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("kaku_grow_dir", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kaku)


def test_細目が_dir_の_ref_の全文を読む():
    ref = "HEAD"   # 細目が節ごとの file の dir として在る先端
    text = kaku.base_text(ref, kaku.SAIMOKU)
    names = sorted(p.name for p in kaku.SAIMOKU.glob("*.md"))
    shown = [subprocess.run(["git", "show", f"{ref}:plugins/core/細目/{n}"], cwd=ROOT, capture_output=True).stdout.decode("utf-8")
             for n in names]
    assert text == "\n".join(shown)


def test_注入_dir_の中で_ls_tree_を呼ぶと中身が空に見える():
    # 直した呼び方（repo の頭）と壊れた呼び方（dir の親）の差を、git そのもので示す
    rel = "plugins/core/細目"
    top = subprocess.run(["git", "ls-tree", "--name-only", f"HEAD:{rel}"], cwd=ROOT, capture_output=True).stdout
    inner = subprocess.run(["git", "ls-tree", "--name-only", f"HEAD:{rel}"], cwd=ROOT / "plugins" / "core", capture_output=True).stdout
    assert top.strip() and not inner.strip()
