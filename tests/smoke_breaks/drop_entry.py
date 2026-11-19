"""入口が無い（入れて起動する試験の注入の 1 つ）。"""

ID = "入口が無い"
WANT = "土台の入口 scripts/setup_plugins.py を通っていない"


def breaks(d):
    (d / "scripts" / "setup_plugins.py").unlink()
