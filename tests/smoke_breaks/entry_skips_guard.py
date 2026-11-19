"""入口が plugin を落とす（入れて起動する試験の注入の 1 つ）。"""

ID = "入口が plugin を落とす"
WANT = "入っていない: guard"


def breaks(d):
    f = d / "scripts" / "setup_plugins.py"
    f.write_text(f.read_text(encoding="utf-8").replace("    for n in names:\n", "    for n in [x for x in names if x != \"guard\"]:\n"),
                 encoding="utf-8")
