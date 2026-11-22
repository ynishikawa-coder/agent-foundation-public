"""試験が形の細目（plugins/core/細目/ の節ごとの file）を読む 1 か所。読み方の正本は kaku.saimoku_text（写さない）。"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "plugins" / "core" / "細目"
_spec = importlib.util.spec_from_file_location("kaku_for_saimoku", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kaku)


def 全文() -> str:
    """節ごとの file をつないだ細目の全文（kaku.saimoku_text そのもの）。"""
    return kaku.saimoku_text(DIR)


def files() -> list[str]:
    """節ごとの file の repo の相対 path（名の順）。"""
    return [f.relative_to(ROOT).as_posix() for f in kaku.saimoku_files(DIR)]
