#!/usr/bin/env python3
"""理論モック HTML の巡回検査（/theory-mock の出口）。

Chrome の headless で `<html>?selftest` を開き、枠の selftest が書いた
`<pre id="selftest">` を読む。全画面（自動の全質問画面を含む）を描画して
例外・console.error・飛び先の無い data-go が 0 なら OK。

使い方:
    python3 check_theory_mock.py <理論モック.html>

終了コード:
    0 = SELFTEST OK
    1 = SELFTEST NG（NG 行を出す）／selftest の結果が DOM に無い
    2 = Chrome が無い・起動できない
標準ライブラリだけ。
"""
from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

CHROME_ENV = "CHROME"   # 明示の時だけ（既定は下の探し方）
TIMEOUT_SEC = 90


def find_chrome() -> str | None:
    """headless で DOM を吐ける Chromium を探す。Mac の path 決め打ちをやめ、Playwright の chromium を先に見る
    （クラウドのコンテナは /opt/pw-browsers・Mac は ~/Library/Caches/ms-playwright に入る）。無ければ None。"""
    if os.environ.get(CHROME_ENV):
        return os.environ[CHROME_ENV] if Path(os.environ[CHROME_ENV]).is_file() else None
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers",
             "~/.cache/ms-playwright", "~/Library/Caches/ms-playwright"]
    # headless shell が先（コンテナでは full の chromium が --dump-dom で返らない＝2026-10-27 実測）
    pats = ["chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
            "chromium", "chromium-*/chrome-linux*/chrome", "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"]
    for root in filter(None, roots):
        base = Path(root).expanduser()
        for pat in pats:
            hits = sorted(p for p in base.glob(pat) if p.is_file())
            if hits:
                return str(hits[-1])
    for name in ("chromium", "chromium-browser", "google-chrome"):
        if shutil.which(name):
            return shutil.which(name)
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return mac if Path(mac).is_file() else None


def chrome_cmd(chrome: str, prof: str, url: str) -> list[str]:
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
           "--no-default-browser-check", f"--user-data-dir={prof}"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.append("--no-sandbox")   # コンテナの root では sandbox が立たない
    return cmd + ["--dump-dom", url]


def dump_dom(cmd: list[str]) -> str | None:
    """Chrome の --dump-dom を読む。DOM を吐いた後も Chrome が居座ることがある
    （本機で実測）ため、`</html>` まで読んだら Chrome を止める。時間切れは None。"""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    buf: list[str] = []
    done = threading.Event()

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            buf.append(line)
            if "</html>" in line:
                break
        done.set()

    threading.Thread(target=reader, daemon=True).start()
    ok = done.wait(TIMEOUT_SEC)
    proc.kill()
    proc.wait()
    out = "".join(buf)
    return out if ok and "</html>" in out else None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("使い方: check_theory_mock.py <理論モック.html>", file=sys.stderr)
        return 1
    target = Path(argv[1]).expanduser().resolve()
    if not target.is_file():
        print(f"NG ファイルが無い: {target}")
        return 1
    chrome = find_chrome()
    if chrome is None:
        print("Chrome（Playwright の chromium）が無い＝検査できない")
        return 2

    url = target.as_uri() + "?selftest"
    with tempfile.TemporaryDirectory(prefix="theory-mock-chrome-") as prof:
        cmd = chrome_cmd(chrome, prof, url)
        try:
            dom = dump_dom(cmd)
        except OSError as e:
            print(f"Chrome を起動できない: {e}")
            return 2
    if dom is None:
        print(f"Chrome が {TIMEOUT_SEC} 秒で DOM を返さない＝検査できない")
        return 2

    m = re.search(r'<pre id="selftest"[^>]*>(.*?)</pre>', dom, re.S)
    if not m:
        print("NG selftest の結果が DOM に無い（枠が起動前に落ちた／template の枠でない）")
        return 1
    text = html.unescape(m.group(1)).strip()
    print(text)
    return 0 if text.startswith("SELFTEST OK") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
