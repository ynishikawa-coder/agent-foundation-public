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
import signal
import subprocess
import sys
import tempfile
import threading
import time
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
        cmd.append("--no-sandbox")   # sandbox が立たない機械（sandbox_blocked）か、立たずに落ちた後
    return cmd + ["--dump-dom", url]


# sandbox が立たない機械の印（Chrome を起こして落ちるのを待たずに分かる物）: root・user namespace を閉じた kernel
# （Ubuntu 23.10 以降の apparmor の既定＝GitHub の ubuntu-24.04 の runner）。
USERNS_CLOSED = (("/proc/sys/kernel/apparmor_restrict_unprivileged_userns", "1"),
                 ("/proc/sys/kernel/unprivileged_userns_clone", "0"))


def sandbox_blocked() -> str:
    """sandbox が立たないと前もって分かる時の訳か ""。"""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return "root"
    for path, closed in USERNS_CLOSED:
        try:
            if Path(path).read_text().strip() == closed:
                return path
        except OSError:
            continue
    return ""


SOCKET_MAX = 107   # unix の socket の path の上限（バイト）


def short_tmp() -> str:
    """Chrome は TMPDIR の下に dir を作りその中に socket を置く（<TMPDIR>/org.chromium.Chromium.XXXXXX/SingletonSocket）。
    TMPDIR が長い窓・試験（日本語の名の dir など）では path が上限を越えて Chrome が落ちる（2026-11-19 CI で実測）。
    越える時は短い置き場（/tmp）を使う。"""
    d = tempfile.gettempdir()
    need = len(os.path.join(d, "org.chromium.Chromium.XXXXXX", "SingletonSocket").encode())
    return d if need <= SOCKET_MAX or not os.access("/tmp", os.W_OK) else "/tmp"


def run_chrome(chrome: str, url: str) -> tuple[str | None, str]:
    """Chrome で url を開いて DOM を返す（(DOM か None, DOM が無い訳)）。Chrome の一時の置き場は短い path に置く。
    sandbox が立たないと前もって分かる機械（sandbox_blocked）は初めから sandbox なしで開く（落ちるのを待つ 1 回を省く）。
    それ以外で sandbox が立たずに落ちた時だけ、sandbox なしで開き直す。DOM が無い時の訳には、開いた回ごとの時間を書く。"""
    tries = (True,) if sandbox_blocked() else (False, True)
    seen: list[str] = []
    dom, why = None, ""
    for no_sandbox in tries:
        with tempfile.TemporaryDirectory(prefix="theory-mock-chrome-", dir=short_tmp()) as prof:
            dom, why = dump_dom(chrome_cmd(chrome, prof, url, no_sandbox))
        seen.append(("sandbox なし" if no_sandbox else "sandbox あり") + ": " + why)
        if dom is not None or "sandbox" not in why.lower():
            break
    return dom, ("" if dom is not None else " ／ ".join(seen))


def _deadline_left() -> float:
    """1 回に待てる秒。呼ぶ側（guard の page_check）が環境変数 AF_CHECK_DEADLINE（epoch 秒）で全体の締めを渡した時は、
    その残りと TIMEOUT_SEC の小さい方（上限は呼ぶ側の 1 か所で決まり、検査は締めの前に訳と時間を出して終わる）。"""
    try:
        left = float(os.environ.get("AF_CHECK_DEADLINE") or "") - time.time()
    except ValueError:
        return TIMEOUT_SEC
    return max(1.0, min(TIMEOUT_SEC, left))


def dump_dom(cmd: list[str]) -> tuple[str | None, str]:
    """Chrome の --dump-dom を読む。返すのは (DOM か None, DOM が無い訳と時間)。
    Chrome は自分の session（process group）で起こし、`</html>` を読んだ時・Chrome が終わった時・時間切れの時に
    group ごと止める。Chrome が終わっても、子（crashpad・zygote）が stdout を握ったまま残ると読み手の EOF が来ず、
    時間切れまで待っていた（sandbox が立たずに落ちた時に CI で 50 秒を越えた訳）。終わった Chrome は待たない。
    落ちた訳は、出力の終わり（EOF）と Chrome の終わり（wait の exit の番号）の両方が揃ってから決める。ある一瞬に
    poll() で終わりを覗いて分けると、EOF が先に来た時に exit の番号が消え、落ちた Chrome を時間切れと取り違えた
    （2026-11-19 のレビュー: 負荷の下で 200 回に 4 回）。
    訳には Chrome の stderr の末尾を入れる（黙って捨てると、別の機械で回せない訳が誰にも見えない）。"""
    limit = _deadline_left()
    t0 = time.monotonic()
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True, start_new_session=True,
                                env=dict(os.environ, TMPDIR=short_tmp()))
        buf: list[str] = []
        eof, exited, wake = threading.Event(), threading.Event(), threading.Event()

        def reader() -> None:
            assert proc.stdout is not None
            try:
                for line in proc.stdout:
                    buf.append(line)
                    if "</html>" in line:
                        break
            finally:
                eof.set()
                wake.set()

        def waiter() -> None:
            proc.wait()
            exited.set()
            wake.set()

        rt = threading.Thread(target=reader, daemon=True)
        rt.start()
        threading.Thread(target=waiter, daemon=True).start()
        wake.wait(max(0.0, limit - (time.monotonic() - t0)))
        if exited.is_set():
            rt.join(1.0)                  # 終わった Chrome の残りの出力だけ読む（握ったままの子は待たない）
        elif eof.is_set() and "</html>" not in "".join(buf):
            exited.wait(max(0.0, limit - (time.monotonic() - t0)))    # 出力を閉じた Chrome の終わりを待つ
        code = proc.returncode if exited.is_set() else None
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.wait()
        took = time.monotonic() - t0
        out = "".join(buf)
        if "</html>" in out:
            return out, ""
        err.seek(0)
        lines = [ln.strip() for ln in err.read().splitlines() if ln.strip()]
        loud = [ln for ln in lines if "FATAL" in ln]   # 落ちた訳の行を先に
        tail = " / ".join(loud[:4] or lines[-4:])[:600]
    why = (f"Chrome が DOM を返さずに終わった（exit {code}・{took:.1f} 秒）" if code is not None
           else f"Chrome が {limit:.0f} 秒で DOM を返さない（{took:.1f} 秒待った）")
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
