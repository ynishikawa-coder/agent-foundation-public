"""docs-kit の型の検査（blueprint・theory-mock）が Chrome を開く形: Chrome の一時の置き場（socket）を短い path に置き、
sandbox が立たずに落ちた時だけ sandbox なしで開き直す（root でない CI の Ubuntu は user namespace を閉じている）。
Chrome は TMPDIR の下に socket を置くので、TMPDIR が長い窓・試験では path の上限を越えて落ちた（CI で型どおりのページが止まった）。
Chrome は使わず dump_dom を作り物にする。"""
import importlib.util
from pathlib import Path

import pytest


PS_PATH = Path(__file__).resolve().parent.parent / "plugins" / "docs-kit" / "scripts" / "page_selftest.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dom(text):
    return '<pre id="selftest">%s</pre>' % text


def test_型の検査は_TMPDIR_が長くても_Chrome_の一時の置き場を短い_path_に置く(monkeypatch, tmp_path):
    m = _load(PS_PATH, "page_selftest")
    long_tmp = tmp_path / ("型どおりのページは通す_" * 3) / "scratch"
    long_tmp.mkdir(parents=True)
    monkeypatch.setenv("TMPDIR", str(long_tmp))
    monkeypatch.setattr(m.tempfile, "tempdir", None)          # TMPDIR を読み直させる
    seen = {}

    def fake(cmd):
        seen["tmp"] = m.short_tmp()                            # dump_dom が Chrome に渡す TMPDIR
        seen["prof"] = next(c.split("=", 1)[1] for c in cmd if c.startswith("--user-data-dir="))
        return _dom("SELFTEST OK"), ""
    monkeypatch.setattr(m, "dump_dom", fake)
    dom, _ = m.run_chrome("chrome", "file:///x.html?selftest")
    assert dom
    for d in (seen["tmp"], seen["prof"]):
        sock = Path(d) / "org.chromium.Chromium.XXXXXX" / "SingletonSocket"
        assert len(str(sock).encode()) <= m.SOCKET_MAX, f"socket の path が上限を越える: {sock}"


def test_型の検査は_Chrome_が落ちた訳の_FATAL_の行を出す(tmp_path):
    m = _load(PS_PATH, "page_selftest")
    sh = tmp_path / "fake-chrome.sh"
    sh.write_text("#!/bin/sh\necho '[1:1:FATAL:作り物.cc:1] 作り物の落ち方' >&2\nfor i in 1 2 3 4 5 6; do echo '#'$i' 0x0 作り物の stack' >&2; done\nexit 3\n",
                  encoding="utf-8")
    sh.chmod(0o755)
    dom, why = m.dump_dom([str(sh)])
    assert dom is None and "作り物の落ち方" in why and "exit 3" in why


def test_型の検査は_sandbox_が立たない機械で_sandbox_なしに開き直し_他の落ち方は開き直さない(monkeypatch):
    m = _load(PS_PATH, "page_selftest")
    monkeypatch.setattr(m, "sandbox_blocked", lambda: "")        # 前もって分からない機械
    seen = []

    def fake(cmd):
        seen.append("--no-sandbox" in cmd)
        if "--no-sandbox" in cmd:
            return _dom("SELFTEST OK"), ""
        return None, "Chrome が DOM を返さずに終わった（exit -6） stderr: FATAL: No usable sandbox!"
    monkeypatch.setattr(m, "dump_dom", fake)
    dom, _ = m.run_chrome("chrome", "file:///x.html?selftest")
    assert dom and seen == [False, True]
    seen.clear()
    monkeypatch.setattr(m, "dump_dom", lambda cmd: (seen.append(1), (None, "stderr: FATAL: 作り物の別の故障"))[1])
    dom, why = m.run_chrome("chrome", "file:///x.html?selftest")
    assert dom is None and "別の故障" in why and seen == [1]


def test_型の検査は_sandbox_が立たないと分かる機械では初めから_sandbox_なしで_1_回だけ開く(monkeypatch):
    m = _load(PS_PATH, "page_selftest")
    monkeypatch.setattr(m, "sandbox_blocked", lambda: "/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
    seen = []
    monkeypatch.setattr(m, "dump_dom", lambda cmd: (seen.append("--no-sandbox" in cmd), (_dom("SELFTEST OK"), ""))[1])
    dom, _ = m.run_chrome("chrome", "file:///x.html?selftest")
    assert dom and seen == [True]


def test_型の検査は終わった_Chrome_の子が_stdout_を握っても待たない(monkeypatch, tmp_path):
    """注入: Chrome が落ちた後も子（crashpad 等）が stdout を握って残る形。前は読み手の EOF を時間切れまで待った
    （CI の 50 秒越えの訳）。今は Chrome が終わった所で止め、訳に時間を書く。"""
    import time
    m = _load(PS_PATH, "page_selftest")
    monkeypatch.setattr(m, "TIMEOUT_SEC", 20)
    sh = tmp_path / "fake-chrome.sh"
    sh.write_text("#!/bin/sh\necho 'FATAL: No usable sandbox! 作り物' >&2\nsleep 30 &\nexit 6\n", encoding="utf-8")
    sh.chmod(0o755)
    t0 = time.monotonic()
    dom, why = m.dump_dom([str(sh)])
    took = time.monotonic() - t0
    assert dom is None and took < 8, f"{took:.1f} 秒待った: {why}"
    assert "exit 6" in why and "秒" in why and "No usable sandbox" in why


def test_型の検査は呼ぶ側の締めの前に訳と時間を出して終わる(monkeypatch, tmp_path):
    """上限は page_check の 1 か所: 締め（AF_CHECK_DEADLINE）を越えて Chrome を待たない。"""
    import time
    m = _load(PS_PATH, "page_selftest")
    sh = tmp_path / "slow-chrome.sh"
    sh.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    sh.chmod(0o755)
    monkeypatch.setenv("AF_CHECK_DEADLINE", "%.3f" % (time.time() + 2))
    t0 = time.monotonic()
    dom, why = m.dump_dom([str(sh)])
    assert dom is None and time.monotonic() - t0 < 8 and "秒で DOM を返さない" in why and "待った" in why


@pytest.mark.parametrize("gap", ["0.4", "0"], ids=["出力を閉じてから終わる", "出力を閉じるのと同時に終わる"])
def test_型の検査は出力の終わりと_Chrome_の終わりが揃ってから落ちた訳を決める(monkeypatch, tmp_path, gap):
    """注入: Chrome が stdout を閉じてから（か、閉じるのと同時に）落ちる形。前は EOF が先に来ると、その一瞬の poll() に
    終わりが見えず exit の番号が消え、落ちた Chrome を「時間切れ」と取り違えた（負荷の下で 200 回に 4 回）。
    今は出力の終わりと Chrome の終わりの両方が揃ってから決めるので、何度回しても同じ訳。"""
    m = _load(PS_PATH, "page_selftest")
    monkeypatch.setattr(m, "TIMEOUT_SEC", 20)
    sh = tmp_path / "fake-chrome.sh"
    sh.write_text("#!/bin/sh\nexec >&-\necho '[1:1:FATAL:作り物.cc:1] 作り物の落ち方' >&2\nsleep %s\nexit 3\n" % gap,
                  encoding="utf-8")
    sh.chmod(0o755)
    for _ in range(20):
        dom, why = m.dump_dom([str(sh)])
        assert dom is None and "exit 3" in why and "作り物の落ち方" in why, why
