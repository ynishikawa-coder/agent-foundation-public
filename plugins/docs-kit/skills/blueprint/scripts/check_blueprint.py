#!/usr/bin/env python3
"""Blueprint HTML の検査と比較（/blueprint の出口）。

検査: Chrome の headless で `<html>?selftest` を開き、枠の selftest が書いた
`<pre id="selftest">` を読む。全タブを描いて、例外・console.error・飛び先の無い
data-go / data-tab-go・HOLES に無い穴番号・現状版で根拠（path:行）の無い段・
段 id の重複が 0 なら OK。

比較: 現状版と設計版の両方を `?dump` で開き、段の一覧（name・where・fate・basis）を
name で突き合わせて Markdown で出す（①片方にしか無い段 ②書き先の違い ③札の違い
④設計版で未定のまま）。差分を見せる道具で関所ではない＝差があっても exit 0。

使い方:
    python3 check_blueprint.py <blueprint.html>
    python3 check_blueprint.py compare <現状版.html> <設計版.html>

終了コード:
    0 = SELFTEST OK ／ compare できた
    1 = SELFTEST NG（NG 行を出す）／結果が DOM に無い
    2 = Chrome が無い・起動できない
標準ライブラリだけ。
"""
from __future__ import annotations

import html
import os
import json
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
FATE_TEXT = {"keep": "保存される", "lost": "消える", "calc": "その場で計算", "gap": "未定"}


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
    with tempfile.TemporaryDirectory(prefix="blueprint-chrome-") as prof:
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


def check(path: str) -> int:
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
        print("NG selftest の結果が DOM に無い（枠が起動前に落ちた／template の枠でない）")
        return 1
    print(text)
    return 0 if text.startswith("SELFTEST OK") else 1


def load_dump(target: Path) -> list[dict]:
    text = pre_text(open_dom(target, "dump"), "bpdump")
    if text is None:
        raise ValueError(f"dump の結果が DOM に無い（枠が起動前に落ちた／template の枠でない）: {target.name}")
    return json.loads(text)


def fate_label(f: str) -> str:
    return FATE_TEXT.get(f, f)


def compare(cur_path: str, des_path: str) -> int:
    cur_t, des_t = resolve(cur_path), resolve(des_path)
    if cur_t is None or des_t is None:
        return 1
    try:
        cur, des = load_dump(cur_t), load_dump(des_t)
    except ChromeMissing as e:
        print(e)
        return 2
    except ValueError as e:
        print(f"NG {e}")
        return 1
    ci = {r["name"]: r for r in cur}
    di = {r["name"]: r for r in des}

    def at(r: dict) -> str:
        return f"{r['tab']} › {r['name']}"

    only_cur = [r for r in cur if r["name"] not in di]
    only_des = [r for r in des if r["name"] not in ci]
    both = [(ci[n], di[n]) for n in ci if n in di]
    where_diff = [(c, d) for c, d in both if c["where"].strip() != d["where"].strip()]
    fate_diff = [(c, d) for c, d in both if c["fate"] != d["fate"]]
    gaps = [r for r in des if r["fate"] == "gap"]

    out = [f"# Blueprint 比較 — 現状版 {cur_t.name} ／ 設計版 {des_t.name}", ""]
    out.append(f"## ① 片方にしか無い段（現状だけ {len(only_cur)}・設計だけ {len(only_des)}）")
    out += [f"- 現状だけ: {at(r)}" for r in only_cur]
    out += [f"- 設計だけ: {at(r)}" for r in only_des]
    if not (only_cur or only_des):
        out.append("- なし")
    out += ["", f"## ② 書き先の違い（{len(where_diff)}）"]
    out += [f"- {c['name']}: 現状=`{c['where'] or '（空）'}` ／ 設計=`{d['where'] or '（空）'}`" for c, d in where_diff] or ["- なし"]
    out += ["", f"## ③ 札の違い（{len(fate_diff)}）"]
    out += [f"- {c['name']}: 現状={fate_label(c['fate'])} ／ 設計={fate_label(d['fate'])}" for c, d in fate_diff] or ["- なし"]
    out += ["", f"## ④ 設計版で未定のまま（{len(gaps)}）"]
    out += [
        "- {}: 欠け={}".format(
            at(r),
            "・".join(k for k, v in (("根拠", r["basis"]), ("書き先", r["where"])) if not v.strip()) or "札が未定",
        )
        for r in gaps
    ] or ["- なし"]
    print("\n".join(out))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "compare":
        return compare(argv[2], argv[3])
    if len(argv) == 2 and argv[1] != "compare":
        return check(argv[1])
    print("使い方: check_blueprint.py <blueprint.html>\n"
          "        check_blueprint.py compare <現状版.html> <設計版.html>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
