"""big_picture.py pick: 値の表に在り処が無く repo に docs/全体の絵.json も無い時、照らせないで止め、値の表に案件のページの名を
書く道を知らせるか（注入の試験）。

なぜ在るか: 給与の repo で、合意した絵の正が Notion の案件のページなのに値の表が在り処を指さず、pick が「絵が無い＝先に絵を
描く」とだけ言ったので、レビューの点 13 が全部止まり、直す道（値の表に書く）が見えなかった（原因の台帳の行）。
"""
import subprocess
import sys
from pathlib import Path

PICK = Path(__file__).resolve().parent.parent / "plugins/docs-kit/skills/big-picture/scripts/big_picture.py"


def run(root, *files):
    return subprocess.run([sys.executable, str(PICK), "pick", str(root), *files], capture_output=True, text=True)


def test_在り処が無ければ照らせないで止め_値の表の書き方を添える(tmp_path):
    res = run(tmp_path, "a.py")
    assert res.returncode == 2, res.stdout + res.stderr
    out = res.stdout + res.stderr
    assert "合意した絵が無い（docs/全体の絵.json）" in out
    assert "docs-kit.big-picture.agreed にそのページの名を書く" in out


def test_値の表が案件のページの名を指せば選ぶ(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/skill-values.json").write_text(
        '{"docs-kit": {"big-picture": {"agreed": "全体の絵: 作り物"}}}', encoding="utf-8")
    res = run(tmp_path, "a.py")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "全体の絵: 作り物" in res.stdout
