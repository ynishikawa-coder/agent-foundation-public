"""docs-kit の型の検査（blueprint・theory-mock）が Chrome を開く形: Chrome の一時の置き場（socket）を短い path に置く。
Chrome は TMPDIR の下に socket を置くので、TMPDIR が長い窓・試験では path の上限を越えて落ちた（CI で型どおりのページが止まった）。
Chrome は使わず dump_dom を作り物にする。"""
import importlib.util
from pathlib import Path


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
