"""古い形の見張り（plugin core の 古い形.json の plugin-name-copy）の約束: 入口 scripts/setup_plugins.py を呼ぶ file でも、
土台の plugin を名で入れる行・目録の名を置く変数が残れば古い形として名指しする（入口の名で外すのは目録を足す行だけ）。"""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kaku", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)


def test_入口を呼ぶ_file_に名で入れる行が残れば古い形に当たる():
    """注入: docs の新しい形（入口を呼ぶ）に、土台の plugin を名で入れる行・目録の名の変数を足す → 入口の名が在っても当たる。"""
    row = next(r for r in kaku.olds_table() if r["id"] == "plugin-name-copy")
    doc = (ROOT / "docs" / "核の届け方.md").read_text(encoding="utf-8")
    block = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", doc, re.S).group(1)
    for extra in ("claude plugin install guard@agent-foundation --scope user || true",
                  'for p in core guard; do claude plugin install "$p@agent-foundation"; done',
                  'M=agent-foundation\nclaude plugin install "core@$M"'):
        assert row["re"].search(block + "\n" + extra), extra
