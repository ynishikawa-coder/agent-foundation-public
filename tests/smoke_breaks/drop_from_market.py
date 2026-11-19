"""配りの器から plugin が落ちる（入れて起動する試験の注入の 1 つ）。"""
import json

ID = "配りの器から plugin が落ちる"
WANT = "plugin guard が起動した窓に読み込まれていない"


def breaks(d):
    f = d / ".claude-plugin" / "marketplace.json"
    m = json.loads(f.read_text(encoding="utf-8"))
    m["plugins"] = [p for p in m["plugins"] if p["name"] != "guard"]
    f.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
