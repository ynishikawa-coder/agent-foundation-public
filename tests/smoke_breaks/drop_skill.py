"""skill が欠ける（入れて起動する試験の注入の 1 つ）。"""

ID = "skill が欠ける"
WANT = "skill docs-kit:qa-html"


def breaks(d):
    (d / "plugins" / "docs-kit" / "skills" / "qa-html" / "SKILL.md").unlink()
