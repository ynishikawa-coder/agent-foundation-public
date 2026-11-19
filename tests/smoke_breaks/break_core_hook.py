"""核の hook が壊れる（入れて起動する試験の注入の 1 つ）。"""

ID = "核の hook が壊れる"
WANT = "核が起動した窓に差し込まれていない"


def breaks(d):
    f = d / "plugins" / "core" / "hooks" / "hooks.json"
    f.write_text(f.read_text(encoding="utf-8").replace("kaku.py\\\" inject", "kaku.py\\\" injct"), encoding="utf-8")
