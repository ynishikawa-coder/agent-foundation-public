"""docs-kit の型の検査（blueprint・theory-mock）が Chrome を開く形: sandbox が立つかは機械で決まる（uid では決まらない）。
Chrome は使わず dump_dom を作り物にする。"""
import importlib.util
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent / "plugins" / "docs-kit" / "skills"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dom(text):
    return '<pre id="selftest">%s</pre>' % text


@pytest.mark.parametrize("kind,mod", [("blueprint", "check_blueprint"), ("theory-mock", "check_theory_mock")])
def test_型の検査は_sandbox_が立たない機械で_sandbox_なしに開き直し_他の落ち方は訳を返す(monkeypatch, kind, mod):
    """sandbox を uid で決めると、root でない CI（user namespace を閉じた機械）で Chrome が落ちて検査が回らなかった。
    Chrome は使わず dump_dom を作り物にする。"""
    m = _load(SKILLS / kind / "scripts" / f"{mod}.py", mod)
    seen = []

    def fake(cmd):
        seen.append("--no-sandbox" in cmd)
        if "--no-sandbox" in cmd:
            return _dom("SELFTEST OK"), ""
        return None, "Chrome が DOM を返さずに終わった（exit -6） stderr: FATAL: No usable sandbox!"
    monkeypatch.setattr(m, "dump_dom", fake)
    dom, _ = m.run_chrome("chrome", "file:///x.html?selftest")
    assert dom and seen == [False, True]                 # 先は sandbox あり・落ちた時だけ外す
    seen.clear()
    monkeypatch.setattr(m, "dump_dom", lambda cmd: (seen.append(1), (None, "Chrome が DOM を返さずに終わった stderr: FATAL: 別の故障"))[1])
    dom, why = m.run_chrome("chrome", "file:///x.html?selftest")
    assert dom is None and "別の故障" in why and seen == [1]   # sandbox の外の落ち方は開き直さず訳を返す
