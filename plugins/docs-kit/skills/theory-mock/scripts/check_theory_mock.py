#!/usr/bin/env python3
"""理論モック HTML の巡回検査（/theory-mock の出口）。

Chrome の headless で `<html>?selftest` を開き、枠の selftest が書いた
`<pre id="selftest">` を読む。全画面（自動の全質問画面を含む）を描画して
例外・console.error・飛び先の無い data-go が 0 なら OK。

使い方:
    python3 check_theory_mock.py <理論モック.html>

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


def chrome_cmd(chrome: str, prof: str, url: str, no_sandbox: bool = False) -> list[str]:
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
           "--no-default-browser-check", f"--user-data-dir={prof}"]
    if no_sandbox:
        cmd.append("--no-sandbox")
    return cmd + ["--dump-dom", url]


def run_chrome(chrome: str, url: str) -> tuple[str | None, str]:
    """sandbox ありで開き、sandbox が立たずに落ちた時だけ sandbox なしで開き直す。
    sandbox が立つかは機械（コンテナの root・user namespace を閉じた CI 等）で決まり、uid では決まらない。"""
    why = ""
    for no_sandbox in (False, True):
        with tempfile.TemporaryDirectory(prefix="theory-mock-chrome-") as prof:
            dom, why = dump_dom(chrome_cmd(chrome, prof, url, no_sandbox))
        if dom is not None or "sandbox" not in why.lower():
            return dom, why
    return None, why


def dump_dom(cmd: list[str]) -> tuple[str | None, str]:
    """Chrome の --dump-dom を読む。DOM を吐いた後も Chrome が居座ることがある
    ため、`</html>` まで読んだら Chrome を止める。返すのは (DOM か None, DOM が無い訳)。
    訳には Chrome の stderr の末尾を入れる（黙って捨てると、別の機械で回せない訳が誰にも見えない）。"""
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
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
        code = proc.poll()
        proc.kill()
        proc.wait()
        out = "".join(buf)
        if ok and "</html>" in out:
            return out, ""
        err.seek(0)
        lines = [ln.strip() for ln in err.read().splitlines() if ln.strip()]
        loud = [ln for ln in lines if re.search(r"FATAL|ERROR|sandbox", ln, re.I)]   # 落ちた訳の行を先に
        tail = " / ".join(loud[:4] or lines[-4:])[:600]
    why = (f"Chrome が {TIMEOUT_SEC} 秒で DOM を返さない" if not ok
           else f"Chrome が DOM を返さずに終わった（exit {code}）")
    return None, f"{why}＝検査できない（{cmd[0]}）" + (f" stderr: {tail}" if tail else "")


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
    try:
        dom, why = run_chrome(chrome, url)
    except OSError as e:
        print(f"Chrome を起動できない: {e}")
        return 2
    if dom is None:
        print(why)
        return 2

    m = re.search(r'<pre id="selftest"[^>]*>(.*?)</pre>', dom, re.S)
    text = html.unescape(m.group(1)).strip() if m else "NG selftest の結果が DOM に無い（枠が起動前に落ちた／template の枠でない）"
    print(text)
    if text.startswith("SELFTEST OK"):
        return 0
    print(ROOT_CAUSE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
