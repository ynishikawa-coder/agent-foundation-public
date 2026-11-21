"""公開の検査のメールの形が、文字列の中の書き方 \\n の n を名の頭と読まないか（誤りの類と、拾うべき形の両方）。

前の形: 文字列の中の改行の書き方の直後に印が続く形を、名の頭の n と読んでメールの形と拾い、作り物の試験の file を
公開に置けない物と止めた。今の形: 改行・タブ・復帰の書き方を区切りと読んでから照らす。区切りの後の本当のメールは拾う。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "public-guard"))
import guard  # noqa: E402

AT = "@"


def test_書き方の_n_の後の_decorator_はメールでない():
    assert "メールアドレス" not in guard.personal_labels('"import pytest\\n\\n' + AT + 'pytest.mark.skipif(x)\\n"')


def test_注入_書き方の_n_の後の本当のメールは拾う():
    assert "メールアドレス" in guard.personal_labels('"\\ntaro' + AT + 'corp-sakura.jp"')
    assert "メールアドレス" in guard.personal_labels("taro" + AT + "corp-sakura.jp")
