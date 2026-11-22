"""試験が要る部品（node・playwright・ブラウザ）の有る無しを見て飛ばす 1 か所。

前の形: 試験の file ごとに、集める時に subprocess や import を走らせる skipif を書き（test_docs_kit・test_qa_html_shohon）、
ブラウザを起こせない時は例外の 1 行目を理由に飛ばし（起こせない訳が部品の無さか別の誤りかを分けない）、test_guard は
作り物の file を書いた後の本体の中ほどで node を見て飛ばした（原因の台帳 束 F1: 飛ばす理由が条件と結ばれない）。
今の形: 部品ごとに条件と理由を同じ所から作る関数を置き、試験はその頭で呼ぶ（集める時には何も走らせない）。
ブラウザは「入った playwright の版のブラウザの file が在るか」だけで飛ばし、在るのに起こせなければ赤（飛ばさない）。
CI では飛ばしは全部赤（check_all）。
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def node():
    """node の命令の path。無ければ飛ばす。"""
    path = shutil.which("node")
    if not path:
        pytest.skip("node が無い（qa-html の検査は node で動く）")
    return path


def py_playwright():
    """python の playwright の sync_playwright。無ければ飛ばす。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("python の playwright が無い（型の JS を実ブラウザで動かす）")
    return sync_playwright


def chromium(p):
    """python の playwright p で使うブラウザの file。QA_CHROMIUM か、入った版のブラウザ。file が無ければ飛ばす。"""
    exe = os.environ.get("QA_CHROMIUM") or p.chromium.executable_path
    if not Path(exe).is_file():
        pytest.skip(f"playwright のブラウザの file が無い（{exe}。playwright install chromium で入る）")
    return exe


def node_playwright():
    """node の playwright が入っていれば node の path。無ければ飛ばす。ブラウザの file も在るかを見る。"""
    n = node()
    r = subprocess.run([n, "-e", "const {chromium}=require('playwright');process.stdout.write(chromium.executablePath())"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        pytest.skip("node の playwright が無い（型の JS を実ブラウザで動かす）")
    if not Path(r.stdout.strip()).is_file():
        pytest.skip(f"node の playwright のブラウザの file が無い（{r.stdout.strip()}）")
    return n
