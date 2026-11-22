"""試験の結果を人に見せる文でなく構造で残す plugin と、その結果を数える判定（check_all・conftest_teeth・plugin-smoke が使う）。

前の形: check_all は pytest の -rs の文（行頭 SKIPPED [n] file:line: 理由）と要約の「N deselected」を正規表現で読んだ。
文は色・fold_skipped・改行・pytest の版で形が変わり、[n] は試験の本数でなく、xfail・xpass は数えず、外した試験の印も見ず、
「待ち: <path>」は理由の文の字を読むだけで、飛ばす条件（PICTURE.is_file() など）と結ばれていなかった。
その後も、結果を書くのが pytest の中の報告だけだったので、次が緑に数えられた（原因の台帳 束 F1）:
- conftest の hook（pytest_runtest_logreport の tryfirst・makereport・report_teststatus）が報告の outcome を書き換える
- conftest の pytest_plugins・PYTHONPATH の sitecustomize・.pth・根に置いた pytest.py が本物の代わりに動く
- file の名・__test__ = False・__init__ の在る class・collect_ignore・pytest_ignore_collect で試験を集めない
  （外しにも飛ばしにも出ないので、試験が減っても緑）
- 待つ物の表の path をどの試験も待てる
- CI が入れる pytest の版が止まっていない
今の形:
- 入口 scripts/pytest.sh が必ずこの plugin を読む（-p af_tally）。AF_PYTEST_TALLY=<file> の時、試験ごとの結果
  （passed / failed / skipped / xfailed / xpassed / error）・飛ばした理由・待つ path（tests/waits.py の wait_for が
  例外に持たせた値。理由の文は読まない）・外した試験と印・集めたのに回らなかった試験を JSON に書く。
- 結果は報告を作った所（makereport の一番外の包み）で決め、後の hook が報告を書き換えたら「書き換えた」と残す。
- 読まれた plugin を全部照らす: pytest 自身と入口の plugin と tests/ の conftest の外は「知らない plugin」。conftest が
  持ってよい hook は CONFTEST_HOOKS だけ（結果・集めを変える hook は持たない）。collect_ignore も持たない。
- 呼ばれた path の .py を読んで（AST）書いた試験の関数を全部挙げ、集めた試験と照らす（集めていない試験は赤）。
- 待つ物の表は「path・待つ試験の file・何か」の 3 つ組。表の試験の file の外から待つと赤。
- pytest の版は scripts/pytest_plugin/requirements.txt の 1 か所（CI はこの file で入れる）。違う版は CI で赤。
- `python3 af_tally.py judge <file>` が JSON だけを読んで数え、緑に数えない物を名指す。JSON が無い・壊れた・
  終わりまで書かれていない時は exit 2（数える段が止まった＝check_all は赤）。
- `--af-judge=real-claude`（CI の job plugin-smoke）: pytest の中で同じ判定を回し、印 real_claude の試験が 1 本でも
  passed の外（飛ばし・xfail・外し）なら pytest を赤で終える。
"""
import ast
import json
import os
import re
import sys
from pathlib import Path

import pytest

OUT_ENV = "AF_PYTEST_TALLY"
WAIT_ATTR = "af_wait_path"          # tests/waits.py の wait_for が飛ばす例外に付ける印（理由の文は読まない）
WAITS_FILE = "tests/waits.txt"      # 待つ物の表（ここに無い path・表の外の試験の file から待つ飛ばしは赤）
REAL_CLAUDE = "real_claude"         # CI の job check で外してよい印（job plugin-smoke が回す）
REQUIREMENTS = Path(__file__).resolve().parent / "requirements.txt"   # pytest の版の 1 か所
# tests/ の conftest が持ってよい hook（印の登録と、印 real_claude の試験を飛ばす条件だけ）。結果・集めを変える hook は持たない。
CONFTEST_HOOKS = {"pytest_configure", "pytest_runtest_setup"}
RANK = {"passed": 0, "skipped": 1, "xfailed": 1, "xpassed": 2, "failed": 3, "error": 3}


def pinned_version():
    for ln in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"\s*pytest==(\S+)\s*", ln)
        if m:
            return m.group(1)
    raise ValueError(f"{REQUIREMENTS} に pytest==<版> の行が無い")


def _outcome(rep):
    if hasattr(rep, "wasxfail"):
        if rep.skipped:
            return "xfailed"
        return "xpassed" if rep.passed else "failed"
    if rep.skipped:
        return "skipped"
    if rep.failed:
        return "failed" if rep.when == "call" else "error"
    return "passed"


def _origin(plugin):
    """plugin の在る file（module ならその file、物ならその型の module の file）。"""
    f = getattr(plugin, "__file__", None)
    if f is None:
        mod = sys.modules.get(type(plugin).__module__)
        f = getattr(mod, "__file__", None)
    return Path(f).resolve() if f else None


def _known_dirs():
    import _pytest
    import pluggy
    return [Path(_pytest.__file__).resolve().parent, Path(pytest.__file__).resolve().parent,
            Path(pluggy.__file__).resolve().parent]


def _under(p, d):
    try:
        p.relative_to(d)
        return True
    except ValueError:
        return False


# ---- plugin（pytest の中で動く） -------------------------------------------------------------

class _Tally:
    def __init__(self, path, config):
        self.path = path
        self.config = config
        self.root = Path(str(config.rootpath)).resolve()
        self.results = {}       # nodeid → {"outcome", "reason", "wait"}
        self.collect_skips = []  # module の段の飛ばし（中の本数は分からないので module ごとに 1 つ）
        self.skipped_files = set()
        self.deselected = []
        self.items = []
        self.collected = []      # 集めた試験の全部（collect の報告の result が正本。外しの hook を通ったかに頼らない）
        self.tampered = []
        self.shard = _shard_of(config)
        self.sharded_out = []    # 分けて回す時、ほかの組が回す試験（集めは全部の組が同じにする）

    def set(self, nodeid, outcome, reason="", wait=None):
        cur = self.results.get(nodeid)
        # 1 本の試験の結果は悪い方を残す（setup の飛ばし・call の失敗・teardown の誤り）
        if cur is None or RANK[outcome] >= RANK[cur["outcome"]]:
            self.results[nodeid] = {"outcome": outcome, "reason": reason, "wait": wait}

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        rep = outcome.get_result()
        wait = getattr(call.excinfo.value, WAIT_ATTR, None) if call.excinfo is not None else None
        rep.af_wait = wait
        # 結果は報告を作った所で決める（後の hook が rep.outcome を書き換えても、ここで決めた方を数える）
        rep.af_made = _outcome(rep)
        self.set(item.nodeid, rep.af_made, _reason(rep), wait if rep.af_made in ("skipped", "xfailed") else None)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logreport(self, report):
        made = getattr(report, "af_made", None)
        if made is not None and _outcome(report) != made:
            self.tampered.append(f"{report.nodeid}: 報告の結果が作った後に {made} から {_outcome(report)} へ書き換えられた")

    def pytest_collectreport(self, report):
        self.collected += [x.nodeid for x in (report.result or []) if isinstance(x, pytest.Item)]
        if report.skipped:
            self.skipped_files.add(report.nodeid.split("::")[0])
            self.collect_skips.append({"nodeid": report.nodeid, "outcome": "skipped", "reason": _reason(report),
                                       "wait": None})

    def pytest_deselected(self, items):
        for it in items:
            self.deselected.append({"nodeid": it.nodeid, "markers": sorted({m.name for m in it.iter_markers()})})

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, session, config, items):
        """--af-shard=i/K の時、-m などで外した後の試験を file ごとに K 組へ分け、i 組の物だけを回す。
        分け方は集めた試験だけで決まる（どの組も同じ試験を集めるので同じ分け方になる）。外した物は sharded_out に残し、
        組を合わせる判定（merge）が「どの試験もちょうど 1 つの組で回った」を照らす。"""
        if self.shard is None:
            return
        i, k = self.shard
        keep = set(assign(items, k)[i])
        self.sharded_out = [it.nodeid for it in items if unit(it)[0] not in keep]
        items[:] = [it for it in items if unit(it)[0] in keep]

    def pytest_collection_finish(self, session):
        self.items = [it.nodeid for it in session.items]

    # -- 読まれた plugin と conftest の hook を照らす --
    def audit(self):
        bad = []
        pm = self.config.pluginmanager
        known = _known_dirs()
        me = Path(__file__).resolve()
        tests = self.root / "tests"
        confs = set()
        for plugin in pm.get_plugins():
            o = _origin(plugin)
            if o is None or o == me or any(_under(o, d) for d in known):
                continue
            if o.name == "conftest.py" and _under(o, tests):
                confs.add(id(plugin))
                for var in ("collect_ignore", "collect_ignore_glob", "pytest_plugins"):
                    if hasattr(plugin, var):
                        bad.append(f"{_rel(o, self.root)}: conftest が {var} を持つ（試験を黙って集めない・別の plugin を読む道）")
                continue
            bad.append(f"{_rel(o, self.root)}: 知らない plugin が読まれた（pytest 自身・入口の plugin・tests/ の conftest の外）")
        for name in dir(pm.hook):
            if not name.startswith("pytest_"):
                continue
            for impl in getattr(pm.hook, name).get_hookimpls():
                if id(impl.plugin) in confs and name not in CONFTEST_HOOKS:
                    bad.append(f"{_rel(_origin(impl.plugin), self.root)}: conftest が hook {name} を持つ"
                               f"（持ってよいのは {', '.join(sorted(CONFTEST_HOOKS))} だけ。結果・集めを変えうる）")
        if _under(Path(pytest.__file__).resolve(), self.root):
            bad.append(f"{_rel(Path(pytest.__file__).resolve(), self.root)}: repo の中の pytest が本物の代わりに読まれた")
        return bad

    # -- 書いた試験を読んで、集めた試験と照らす --
    def unseen(self):
        got = {re.sub(r"\[.*\]$", "", n) for n in self.collected}
        out = []
        for f in _scan_files(self.config, self.root):
            rel = _rel(f, self.root)
            if rel in self.skipped_files:
                continue
            for nid in written_tests(f, rel):
                if nid not in got:
                    out.append(f"{nid}: 書いた試験を集めていない（file の名・__test__・__init__・集めない hook）")
        return out

    def pytest_sessionfinish(self, session, exitstatus):
        if self.shard and not self.items and self.sharded_out and exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED:
            # 試験がほかの組へ全部行った組は「何も集めなかった」でなく空の組（集めた 0 本は合わせた後の数で見る）
            exitstatus = session.exitstatus = pytest.ExitCode.OK
        unrun = [n for n in self.items if n not in self.results]
        kept = set(self.items) | {d["nodeid"] for d in self.deselected} | set(self.sharded_out)
        dropped = [n for n in dict.fromkeys(self.collected) if n not in kept]
        data = {"finished": True, "exitstatus": int(exitstatus), "collected": len(set(self.collected)),
                "dropped": dropped,
                "results": [dict(nodeid=k, **v) for k, v in self.results.items()] + self.collect_skips,
                "deselected": self.deselected, "unrun": unrun,
                "audit": self.audit() + self.tampered, "unseen": self.unseen(),
                "pytest": pytest.__version__,
                "shard": list(self.shard) if self.shard else None, "sharded_out": self.sharded_out}
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        mode = self.config.getoption("af_judge")
        if mode:
            try:
                n, bad, _ = judge(data, str(self.root), ci=True, mode=mode)
            except (ValueError, KeyError) as e:
                bad = [f"数える段が止まった: {e}"]
            tr = self.config.pluginmanager.get_plugin("terminalreporter")
            for b in bad:
                (tr.write_line if tr else print)(f"af_judge 赤: {b}")
            if bad and session.exitstatus == 0:
                session.exitstatus = 1


def _rel(p, root):
    try:
        return str(Path(p).relative_to(root))
    except ValueError:
        return str(p)


def _scan_files(config, root):
    """呼ばれた path（引数）の .py を全部。node の id で 1 本を選んだ file は照らさない（選んだ物だけが集まる）。"""
    files = set()
    for a in config.args:
        if "::" in str(a):
            continue
        p = Path(str(a))
        p = p if p.is_absolute() else Path(str(config.invocation_params.dir)) / p
        p = p.resolve()
        if p.is_dir():
            files |= {q for q in p.rglob("*.py") if "__pycache__" not in q.parts and q.name != "conftest.py"}
        elif p.suffix == ".py" and p.is_file():
            files.add(p)
    return sorted(f for f in files if _under(f, root))


def written_tests(path, rel):
    """file に書いた試験の関数の node id（module の def test*・class Test* の中の def test*）。"""
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []   # 読めない file は pytest の集めで誤りになる
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            out.append(f"{rel}::{node.name}")
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            out += [f"{rel}::{node.name}::{m.name}" for m in node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith("test")]
    return out


def _reason(report):
    lr = report.longrepr
    if isinstance(lr, tuple) and len(lr) == 3:
        text = str(lr[2])
        return text[len("Skipped: "):] if text.startswith("Skipped: ") else text
    return str(lr or "").splitlines()[-1] if lr else ""


def _shard_of(config):
    v = config.getoption("af_shard")
    if not v:
        return None
    m = re.fullmatch(r"(\d+)/(\d+)", v)
    if not m or not 0 <= int(m.group(1)) < int(m.group(2)):
        raise pytest.UsageError(f"--af-shard は i/K（0 <= i < K）: {v}")
    return int(m.group(1)), int(m.group(2))


def unit(it):
    """(分ける単位, 試験 1 本の重さ)。単位は既定で file、重さは既定で 1。module が AF_SHARD_WEIGHT = N を持つ時は、
    重さ N で試験 1 本ずつを単位にする（1 本が数分かかる試験＝決まりの文を消して回す試験。file ごとに束ねると、
    その file の組だけが長くなる）。"""
    w = getattr(getattr(it, "module", None), "AF_SHARD_WEIGHT", None)
    return (it.nodeid.split("::")[0], 1) if w is None else (it.nodeid, w)


def assign(items, k):
    """試験の単位（file か、重い試験 1 本）を K 組へ分ける（重い単位から、今いちばん軽い組へ。重さは試験の本数×unit の重さ）。組ごとの単位の並びを返す。"""
    count = {}
    for it in items:
        f, w = unit(it)
        count[f] = count.get(f, 0) + w
    groups, load = [[] for _ in range(k)], [0] * k
    for f in sorted(count, key=lambda f: (-count[f], f)):
        j = load.index(min(load))
        groups[j].append(f)
        load[j] += count[f]
    return groups


def pytest_addoption(parser):
    parser.addoption("--af-shard", dest="af_shard", default=None,
                     help="i/K: 試験を file ごとに K 組へ分け、i 組だけを回す（check_all が K 組を同時に回して merge で合わせる）")
    parser.addoption("--af-judge", dest="af_judge", default=None, choices=["real-claude"],
                     help="pytest の中で結果を判定し、緑に数えない物があれば赤で終える（real-claude: job plugin-smoke）")


def pytest_configure(config):
    path = os.environ.get(OUT_ENV)
    if path or config.getoption("af_judge"):
        config.pluginmanager.register(_Tally(path, config), "af_tally_writer")


# ---- 判定（check_all・conftest_teeth が JSON を読む） ---------------------------------------------

def read_waits(root):
    """{待つ path: 待ってよい試験の file}。形の崩れた行は ValueError（数える段が止まる＝赤）。"""
    p = Path(root) / WAITS_FILE
    if not p.is_file():
        return {}
    out = {}
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = ln.split()
        if len(parts) < 2 or not re.fullmatch(r"tests/(?:.*/)?test_[^/]*\.py", parts[1]):
            raise ValueError(f"{WAITS_FILE} の行が「path 待つ試験の file 何か」の形でない: {ln}")
        out[parts[0]] = parts[1]
    return out


def merge(datas):
    """分けて回した K 組の結果を 1 つにする。組が揃わない・集めた試験が組で違う・どの組でも回らない／2 つの組で回った
    試験があれば ValueError（数える段が止まった＝赤）。組が 1 つで分けていなければそのまま返す。"""
    if len(datas) == 1 and not datas[0].get("shard"):
        return datas[0]
    for d in datas:
        if not isinstance(d, dict) or d.get("finished") is not True:
            raise ValueError("試験の結果が終わりまで書かれていない組がある（pytest が途中で止まった）")
    k = len(datas)
    if sorted(tuple(d.get("shard") or ()) for d in datas) != [(i, k) for i in range(k)]:
        raise ValueError(f"組が揃っていない（{k} 組の 0..{k - 1} が 1 つずつ要る）")
    if len({d["collected"] for d in datas}) != 1:
        raise ValueError("集めた試験の数が組で違う（組ごとに別の物を集めた）")
    ran = {}
    for d in datas:
        mine = {r["nodeid"] for r in d["results"]} | set(d["unrun"])
        for nid in mine - {r["nodeid"] for r in d["results"] if "::" not in r["nodeid"]}:
            ran[nid] = ran.get(nid, 0) + 1
    twice = sorted(n for n, c in ran.items() if c > 1)
    if twice:
        raise ValueError(f"2 つの組で回った試験がある: {twice[:3]}")
    everyone = set().union(*(set(d["sharded_out"]) for d in datas))
    nobody = sorted(everyone - set(ran))
    if nobody:
        raise ValueError(f"どの組でも回らなかった試験がある: {nobody[:3]}")

    def uniq(key, by=None):
        seen, out = set(), []
        for d in datas:
            for x in d[key]:
                h = x[by] if by else x
                if h not in seen:
                    seen.add(h)
                    out.append(x)
        return out

    vers = {d["pytest"] for d in datas}
    return {"finished": True, "exitstatus": max(d["exitstatus"] for d in datas), "collected": datas[0]["collected"],
            "dropped": uniq("dropped"), "results": uniq("results", "nodeid"), "deselected": uniq("deselected", "nodeid"),
            "unrun": uniq("unrun"), "audit": uniq("audit"), "unseen": uniq("unseen"),
            "pytest": vers.pop() if len(vers) == 1 else "組で違う版"}


def judge(data, root, ci, only_passed=False, mode=None):
    """(数えた値, 緑に数えない物の一覧, 名指すだけの物の一覧) を返す。
    only_passed＝回った試験が全部 passed でなければ赤（conftest_teeth）。mode="real-claude"＝job plugin-smoke の形
    （印 real_claude の試験は全部 passed・外してよいのは印の無い試験だけ）。"""
    if not isinstance(data, dict) or data.get("finished") is not True:
        raise ValueError("試験の結果が終わりまで書かれていない（pytest が途中で止まった）")
    waits = read_waits(root)
    strict = only_passed or mode == "real-claude"
    n = {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "wait": 0, "xfailed": 0, "xpassed": 0,
         "deselected_real_claude": 0}
    bad, named = [], []
    for r in data["results"]:
        o, where, why, wait = r["outcome"], r["nodeid"], r.get("reason", ""), r.get("wait")
        n[o] += 1
        if strict and o != "passed":
            bad.append(f"{where}: {o}（{why}）")
            continue
        if o == "xpassed":
            bad.append(f"{where}: 落ちる印（xfail）なのに通った（前提が満ちた。印を外す）")
        elif o in ("skipped", "xfailed"):
            kind = "飛んだ" if o == "skipped" else "xfail で落ちた"
            if wait:
                waiter = waits.get(wait)
                if waiter is None:
                    bad.append(f"{where}: 待つ物 {wait} が待つ物の表（{WAITS_FILE}）に無い")
                elif where.split("::")[0] != waiter:
                    bad.append(f"{where}: 待つ物 {wait} を待ってよいのは表の {waiter} だけ（別の試験が表の path で飛んだ）")
                elif (Path(root) / wait).exists():
                    bad.append(f"{where}: 待つ物 {wait} が在るのに{kind}（飛ばす条件が残っている）")
                else:
                    n["wait"] += 1
                    named.append(f"待ち: {where}（{wait}）")
            elif ci:
                bad.append(f"{where}: CI で{kind}（{why}）")
            else:
                named.append(f"{kind}: {where}（{why}）")
    for d in data["deselected"]:
        has = REAL_CLAUDE in d["markers"]
        if mode == "real-claude":
            if has:
                bad.append(f"{d['nodeid']}: 印 {REAL_CLAUDE} の試験を外した（job plugin-smoke で回らない）")
        elif not has:
            bad.append(f"{d['nodeid']}: 印 {REAL_CLAUDE} の無い試験を外した")
        elif not ci:
            bad.append(f"{d['nodeid']}: CI の外で印 {REAL_CLAUDE} の試験を外した")
        else:
            n["deselected_real_claude"] += 1
    for d in data["dropped"]:
        bad.append(f"{d}: 集めたのに外しの印も無く黙って外した（conftest などが items から抜いた）")
    for u in data["unrun"]:
        bad.append(f"{u}: 集めたのに回らないまま終わった（pytest.exit などで止めた）")
    bad += list(data["audit"]) + list(data["unseen"])
    want = pinned_version()
    if data["pytest"] != want:
        msg = f"pytest の版 {data['pytest']} が scripts/pytest_plugin/requirements.txt の {want} と違う（結果の形が版で変わる）"
        (bad if ci else named).append(msg)
    if n["passed"] == 0:
        bad.append("通った試験が 0 本（1 本も回っていない）")
    return n, bad, named


def main(argv):
    files = [a for a in argv[1:] if not a.startswith("--")]
    if len(argv) < 2 or argv[0] != "judge" or not files:
        print("使い方: af_tally.py judge <結果の JSON>... [--only-passed]（分けて回した組は全部を渡す）", file=sys.stderr)
        return 2
    ci = os.environ.get("GITHUB_ACTIONS") == "true"
    try:
        data = merge([json.loads(Path(f).read_text(encoding="utf-8")) for f in files])
        n, bad, named = judge(data, ".", ci, only_passed="--only-passed" in argv)
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
    for x in named:
        print(f"名指し: {x}")
    for b in bad:
        print(f"赤: {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
