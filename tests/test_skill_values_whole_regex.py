"""値の表の型 repo_names（skill-values/skill_values.py の bad_repo_names）が、名の全体の形かを字の頭と尻でなく
正規表現の解析で決めるか（注入の試験）。

頭にフラグを置いた (?i)^o/r$・分かれ ^a$|^b$ は全体の形（形の違いと名指さない）。尻がエスケープした \\$・
片側だけ錨の ^a|b$・頭だけ・錨なしは形の違いと名指す。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill-values"))
import skill_values as SV  # noqa: E402


@pytest.mark.parametrize("row", [
    "^o/r$",
    "(?i)^o/r$",           # 頭にフラグを置いた形（字の頭が ^ でない）
    "(?i:^o/r$)",          # 囲みのフラグ
    "^o/.*$",
    "^a/b$|^c/d$",         # 全部の道が全体の形の分かれ
    "(?:^a/b$|^c/d$)",
    r"\Ao/r\Z",            # 頭と尻の錨の別の書き方
])
def test_全体の形の行は名指さない(row):
    assert SV.bad_repo_names([row]) == []


@pytest.mark.parametrize("row", [
    "^o/",                 # 頭だけ
    "o/r",                 # 錨なし
    r"^o/r\$",             # 尻の $ をエスケープした（字の $ に当てる）
    "^a/b|c/d$",           # 片方の道だけ錨（a/b-fork・xc/d にも当たる）
    "(?i)o/r$",            # フラグの後に頭の錨が無い
    "^o/(",                # 正規表現として読めない
    5,                     # 字でない
])
def test_全体の形でない行は名指す(row):
    assert SV.bad_repo_names([row]) == [row]
