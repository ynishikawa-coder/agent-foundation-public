"""試験の入口 scripts/pytest.sh が pytest を起こす口（python3 -I -S で呼ぶ）。

前の形: `python3 -m pytest` は PYTHONPATH・site-packages の .pth・sitecustomize・usercustomize（環境の側）と、
cwd（repo の根）に置いた pytest.py・pytest/ を読んだ。どれも本物の pytest の代わりに動いて偽の出力と exit 0 を出せた。
今の形: -I（環境変数・cwd・利用者の site を読まない）と -S（site を走らせない＝.pth と sitecustomize を読まない）で
起こし、ここで入口の plugin の dir と、site-packages の dir（.pth を走らせずに道だけ）を足してから pytest を呼ぶ。
"""
import site
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
for d in [*site.getsitepackages(), site.getusersitepackages()]:
    if d not in sys.path:
        sys.path.append(d)

import pytest  # noqa: E402

sys.exit(pytest.main(sys.argv[1:]))
