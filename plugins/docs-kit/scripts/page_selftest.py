#!/usr/bin/env python3
"""docs-kit の型のページの ?selftest を Chrome の headless で開いて読む口（型の検査の共通の正本）。

型の template.html の枠は `?selftest` で全部を描き、結果を `<pre id="selftest">` に
`SELFTEST OK …` か `SELFTEST NG …` の行で書く。ここはそれを開いて読むだけ（型ごとの
中身は template の selftest が持つ）。Chrome の探し方・DOM の読み方は型ごとに写さず、ここ 1 つ。

使い方:
    python3 page_selftest.py <型のページ.html>

終了コード:
    0 = SELFTEST OK
    1 = SELFTEST NG（NG 行と、最後に根治の入口を指す `直し:` の行を出す）／selftest の結果が DOM に無い
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
# NG の時の最後の行（中身は細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: NG の行を 1 つずつ潰さず、細目 §3「まず構造を疑う」で原因（枠の使い方・題材の組み方）から直す"


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
class ChromeMissing(Exception):
    """Chrome が無い・起動できない・DOM を返さない＝検査できない（exit 2）。"""


def dump_dom(cmd: list[str]) -> str | None:
    """Chrome の --dump-dom を読む。DOM を吐いた後も Chrome が居座ることがある
    ため、`</html>` まで読んだら Chrome を止める。時間切れは None。"""
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


def open_dom(target: Path, query: str) -> str:
    chrome = find_chrome()
    if chrome is None:
        raise ChromeMissing("Chrome（Playwright の chromium）が無い＝検査できない")
    url = target.as_uri() + "?" + query
    with tempfile.TemporaryDirectory(prefix="af-page-chrome-") as prof:
        cmd = chrome_cmd(chrome, prof, url)
        try:
            dom = dump_dom(cmd)
        except OSError as e:
            raise ChromeMissing(f"Chrome を起動できない: {e}") from e
    if dom is None:
        raise ChromeMissing(f"Chrome が {TIMEOUT_SEC} 秒で DOM を返さない＝検査できない")
    return dom


def pre_text(dom: str, pre_id: str) -> str | None:
    m = re.search(rf'<pre id="{pre_id}"[^>]*>(.*?)</pre>', dom, re.S)
    return html.unescape(m.group(1)).strip() if m else None


def resolve(p: str) -> Path | None:
    target = Path(p).expanduser().resolve()
    if not target.is_file():
        print(f"NG ファイルが無い: {target}")
        return None
    return target


def check(path: str, root_cause: str = ROOT_CAUSE) -> int:
    target = resolve(path)
    if target is None:
        return 1
    try:
        dom = open_dom(target, "selftest")
    except ChromeMissing as e:
        print(e)
        return 2
    text = pre_text(dom, "selftest")
    if text is None:
        text = "NG selftest の結果が DOM に無い（枠が起動前に落ちた／template の枠でない）"
    print(text)
    if text.startswith("SELFTEST OK"):
        return 0
    print(root_cause)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("使い方: page_selftest.py <型のページ.html>", file=sys.stderr)
        return 1
    return check(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
