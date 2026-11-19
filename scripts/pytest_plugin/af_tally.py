"""試験の結果を人に見せる文でなく構造で残す plugin と、その結果を数える判定（check_all・conftest_teeth が使う）。

前の形: check_all は pytest の -rs の文（行頭 SKIPPED [n] file:line: 理由）と要約の「N deselected」を正規表現で読んだ。
文は色・fold_skipped・改行・pytest の版で形が変わり、[n] は試験の本数でなく、xfail・xpass は数えず、外した試験の印も見ず、
「待ち: <path>」は理由の文の字を読むだけで、飛ばす条件（PICTURE.is_file() など）と結ばれていなかった。
今の形:
- 入口 scripts/pytest.sh が必ずこの plugin を読む（-p af_tally）。AF_PYTEST_TALLY=<file> の時、試験ごとの結果
  （passed / failed / skipped / xfailed / xpassed / error）・飛ばした理由・待つ path（tests/waits.py の wait_for が
  例外に持たせた値。理由の文は読まない）・外した試験と印・集めたのに回らなかった試験を JSON に書く。
- `python3 af_tally.py judge <file>` が JSON だけを読んで数え、緑に数えない物を名指す。JSON が無い・壊れた・
  終わりまで書かれていない時は exit 2（数える段が止まった＝check_all は赤）。
"""
import json
import os
import sys
from pathlib import Path

import pytest

OUT_ENV = "AF_PYTEST_TALLY"
WAIT_ATTR = "af_wait_path"          # tests/waits.py の wait_for が飛ばす例外に付ける印（理由の文は読まない）
WAITS_FILE = "tests/waits.txt"      # 待つ物の表（ここに無い path を待つ飛ばしは赤）
REAL_CLAUDE = "real_claude"         # CI の job check で外してよい印（job plugin-smoke が回す）


# ---- plugin（pytest の中で動く） -------------------------------------------------------------

class _Tally:
    def __init__(self, path):
        self.path = path
        self.results = {}       # nodeid → {"outcome", "reason", "wait"}
        self.collect_skips = []  # module の段の飛ばし（中の本数は分からないので module ごとに 1 つ）
        self.deselected = []
        self.items = []

    def set(self, nodeid, outcome, reason="", wait=None):
        cur = self.results.get(nodeid)
        # 1 本の試験の結果は悪い方を残す（setup の飛ばし・call の失敗・teardown の誤り）
        rank = {"passed": 0, "skipped": 1, "xfailed": 1, "xpassed": 2, "failed": 3, "error": 3}
        if cur is None or rank[outcome] >= rank[cur["outcome"]]:
            self.results[nodeid] = {"outcome": outcome, "reason": reason, "wait": wait}

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        rep = outcome.get_result()
        wait = getattr(call.excinfo.value, WAIT_ATTR, None) if call.excinfo is not None else None
        rep.af_wait = wait

    def pytest_runtest_logreport(self, report):
        reason = _reason(report)
        wait = getattr(report, "af_wait", None)
        if hasattr(report, "wasxfail"):
            if report.skipped:
                self.set(report.nodeid, "xfailed", report.wasxfail or reason, wait)
            elif report.passed:
                self.set(report.nodeid, "xpassed", report.wasxfail)
            else:
                self.set(report.nodeid, "failed", reason)
        elif report.skipped:
            self.set(report.nodeid, "skipped", reason, wait)
        elif report.failed:
            self.set(report.nodeid, "failed" if report.when == "call" else "error", reason)
        elif report.when == "call":
            self.set(report.nodeid, "passed")

    def pytest_collectreport(self, report):
        if report.skipped:
            self.collect_skips.append({"nodeid": report.nodeid, "outcome": "skipped", "reason": _reason(report),
                                       "wait": None})

    def pytest_deselected(self, items):
        for it in items:
            self.deselected.append({"nodeid": it.nodeid, "markers": sorted({m.name for m in it.iter_markers()})})

    def pytest_collection_finish(self, session):
        self.items = [it.nodeid for it in session.items]

    def pytest_sessionfinish(self, session, exitstatus):
        unrun = [n for n in self.items if n not in self.results]
        data = {"finished": True, "exitstatus": int(exitstatus), "collected": len(self.items),
                "results": [dict(nodeid=k, **v) for k, v in self.results.items()] + self.collect_skips,
                "deselected": self.deselected, "unrun": unrun}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.path)


def _reason(report):
    lr = report.longrepr
    if isinstance(lr, tuple) and len(lr) == 3:
        text = str(lr[2])
        return text[len("Skipped: "):] if text.startswith("Skipped: ") else text
    return str(lr or "").splitlines()[-1] if lr else ""


def pytest_configure(config):
    path = os.environ.get(OUT_ENV)
    if path:
        config.pluginmanager.register(_Tally(path), "af_tally_writer")


# ---- 判定（check_all・conftest_teeth が JSON を読む） ---------------------------------------------

def read_waits(root):
    p = Path(root) / WAITS_FILE
    if not p.is_file():
        return set()
    return {ln.split()[0] for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}


def judge(data, root, ci, only_passed=False):
    """(数えた値, 緑に数えない物の一覧) を返す。only_passed＝回った試験が全部 passed でなければ赤（conftest_teeth）。"""
    if not isinstance(data, dict) or data.get("finished") is not True:
        raise ValueError("試験の結果が終わりまで書かれていない（pytest が途中で止まった）")
    waits = read_waits(root)
    n = {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "wait": 0, "xfailed": 0, "xpassed": 0,
         "deselected_real_claude": 0}
    bad = []
    for r in data["results"]:
        o, where, why, wait = r["outcome"], r["nodeid"], r.get("reason", ""), r.get("wait")
        n[o] += 1
        if only_passed and o != "passed":
            bad.append(f"{where}: {o}（{why}）")
            continue
        if o == "xpassed":
            bad.append(f"{where}: 落ちる印（xfail）なのに通った（前提が満ちた。印を外す）")
        elif o in ("skipped", "xfailed"):
            kind = "飛んだ" if o == "skipped" else "xfail で落ちた"
            if wait:
                if wait not in waits:
                    bad.append(f"{where}: 待つ物 {wait} が待つ物の表（{WAITS_FILE}）に無い")
                elif (Path(root) / wait).exists():
                    bad.append(f"{where}: 待つ物 {wait} が在るのに{kind}（飛ばす条件が残っている）")
                else:
                    n["wait"] += 1
            elif ci:
                bad.append(f"{where}: CI で{kind}（{why}）")
    for d in data["deselected"]:
        if REAL_CLAUDE not in d["markers"]:
            bad.append(f"{d['nodeid']}: 印 {REAL_CLAUDE} の無い試験を外した")
        elif not ci:
            bad.append(f"{d['nodeid']}: CI の外で印 {REAL_CLAUDE} の試験を外した")
        else:
            n["deselected_real_claude"] += 1
    for u in data["unrun"]:
        bad.append(f"{u}: 集めたのに回らないまま終わった（pytest.exit などで止めた）")
    if n["passed"] == 0:
        bad.append("通った試験が 0 本（1 本も回っていない）")
    return n, bad


def main(argv):
    if len(argv) < 2 or argv[0] != "judge":
        print("使い方: af_tally.py judge <結果の JSON> [--only-passed]", file=sys.stderr)
        return 2
    ci = os.environ.get("GITHUB_ACTIONS") == "true"
    try:
        data = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        n, bad = judge(data, ".", ci, only_passed="--only-passed" in argv)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"数える段が止まった: {e.__class__.__name__}: {e}")
        return 2
    note = f"pytest で飛ばした {n['skipped']} 本"
    if n["wait"]:
        note += f"（待ち {n['wait']} 本）"
    if n["xfailed"] or n["xpassed"]:
        note += f"・xfail {n['xfailed']} 本・xpass {n['xpassed']} 本"
    if n["deselected_real_claude"]:
        note += f"・印 {REAL_CLAUDE} で外した {n['deselected_real_claude']} 本（job plugin-smoke が回す）"
    print(note)
    for b in bad:
        print(b)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
