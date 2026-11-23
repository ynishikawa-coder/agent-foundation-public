"""土台の plugin が入らなかった時の知らせが、オーナーへ先に投げず AI が setup を直すと言う事の注入の試験。

意図: 調べれば分かる事・安く直せる事は AI が直して進む（核 §4）。setup script の形の崩れは AI が環境の道具で直せる。
課題: 届け方の setup の塊と入口 setup_plugins.py の知らせが「最初にオーナーへ知らせる」と書き、直せる物までオーナーへ回していた。
原因: 知らせの文が 3 か所に写され、直し方（届け方の「起動の時から古かった」）を指していなかった。
ここでは、塊の知らせと入口の知らせの全部が、AI が直し・直せない時だけオーナーへ知らせると言い、古い句が無い事を見る。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_setup_の知らせはAIが直してから直せない時だけオーナーへ():
    """意図: 直せる物を人へ回さない。課題: 3 か所の知らせが最初にオーナーへ知らせると書いていた。"""
    doc = (ROOT / "docs/核の届け方.md").read_text(encoding="utf-8")
    src = (ROOT / "scripts/setup_plugins.py").read_text(encoding="utf-8")
    for text in (doc, src):
        assert "最初にオーナーへ知らせる" not in text
    assert re.search(r'af_w=.*AI が setup script を直し、直せない時だけオーナーへ知らせる', doc)
    assert src.count("+ FIX)") == 2 and "直せない時" in src
