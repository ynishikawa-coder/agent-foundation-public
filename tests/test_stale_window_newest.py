"""古い版で立った窓・入れ直しの途中でも、skill から呼ぶ道具は先端の版で動くか（安全側で止まり訳を出すか）の注入の試験。

問題: 窓の途中で土台が先端の版へ入れ直されても、skill の本文が指す ${CLAUDE_PLUGIN_ROOT} は窓が立った時の版の dir の
まま。skill から呼ぶ script（codex_pack・seal・check.mjs・判定の型など）・skill の本文・雛形が古い版で動き、
入れ直しの途中では守りの hook が入った版の public-guard/guard.py を見失った。
形: script は入口の 1 行（lib/af_place.py の run_newest・check.mjs の runNewest）で目録の clone の hook_run.py の newest
へ聞き、台帳の今読まれる行の版の同じ script へ乗り換える。乗り換えた時に skill の本文が先端で変わっていれば、その本文の path を名指す（見張りは足さない）。
入れ直しの前に入った版の土台の根の file を取り置く（setup_plugins.keep_installed → af_place.keep_version）。
ここは本物の claude なしで、作り物の箱（目録の clone・古い版と新しい版の dir・台帳）に古い版の状態をわざと作って照らす。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core"
AF_PLACE = ROOT / "skill-values" / "af_place.py"
sys.path.insert(0, str(CORE / "scripts"))
import kaku  # noqa: E402

sys.path.insert(0, str(ROOT / "skill-values"))
import af_place  # noqa: E402

OLD, NEW = "oldoldoldold", "newnewnewnew"
PROBE = ('import os, sys\nsys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))\n'
         'import af_place\naf_place.run_newest(__file__)\n'
         'print("{ver}", os.environ.get("CLAUDE_PLUGIN_ROOT"), *sys.argv[1:])\n')


def make_box(tmp: Path, plugins_of: dict, scripts: dict | None = None) -> dict:
    """作り物の箱。plugins_of={plugin 名: {"old": {rel: 中身}, "new": {rel: 中身}}}。
    台帳は新しい版の行だけ（Claude Code が入れ直した後の形）。目録の clone には正本の core を写す。"""
    home = tmp / "home"
    plugins = home / ".claude" / "plugins"
    shutil.copytree(CORE, plugins / "marketplaces" / kaku.MARKET / "plugins" / "core",
                    ignore=shutil.ignore_patterns("__pycache__"))
    table, dirs = {}, {}
    for name, vers in plugins_of.items():
        for ver, files in vers.items():
            d = plugins / "cache" / kaku.MARKET / name / (OLD if ver == "old" else NEW)
            (d / ".claude-plugin").mkdir(parents=True)
            (d / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
            (d / "lib").mkdir()
            shutil.copy(AF_PLACE, d / "lib" / "af_place.py")
            for rel, body in files.items():
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                (d / rel).write_text(body, encoding="utf-8")
            dirs[(name, ver)] = d
        table[f"{name}@{kaku.MARKET}"] = [{"scope": "user", "installPath": str(dirs[(name, "new")]),
                                           "gitCommitSha": "b" * 40, "lastUpdated": "2026-11-23T01:00:00Z"}]
    (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": table}), encoding="utf-8")
    return {"home": home, "claude": home / ".claude", "plugins": plugins, "dirs": dirs}


def run_py(script: Path, box: dict, *args, **env) -> subprocess.CompletedProcess:
    e = {k: v for k, v in os.environ.items() if k not in (af_place.NEWEST_ENV, "CLAUDE_PLUGIN_ROOT")}
    e.update(HOME=str(box["home"]), CLAUDE_PLUGIN_ROOT=str(script.parents[2]), **env)
    return subprocess.run([sys.executable, str(script), *args], env=e, capture_output=True, text=True, timeout=60)


def probe_box(tmp, new_has=True):
    rel = "skills/x/probe.py"
    return make_box(tmp, {"docs-kit": {"old": {rel: PROBE.format(ver="old")},
                                       "new": {rel: PROBE.format(ver="new")} if new_has else {}}}), rel


# ── skill から呼ぶ script: 古い版の dir から呼ばれても先端の版で回る ──

def test_古い版の_script_は先端の版へ乗り換えて_CLAUDE_PLUGIN_ROOT_も先端になる(tmp_path):
    box, rel = probe_box(tmp_path)
    r = run_py(box["dirs"][("docs-kit", "old")] / rel, box, "a1")
    new = box["dirs"][("docs-kit", "new")]
    assert r.stdout.split() == ["new", str(new), "a1"], (r.stdout, r.stderr)
    assert "いちばん新しい版" in r.stderr


def test_先端の版で呼べば乗り換えずそのまま回る(tmp_path):
    box, rel = probe_box(tmp_path)
    new = box["dirs"][("docs-kit", "new")]
    r = run_py(new / rel, box)
    assert r.stdout.split() == ["new", str(new)], (r.stdout, r.stderr)
    assert r.stderr == ""


def test_先端の版に同じ_script_が無ければ今の版で続けて読み直す先を名指す(tmp_path):
    box, rel = probe_box(tmp_path, new_has=False)
    old = box["dirs"][("docs-kit", "old")]
    r = run_py(old / rel, box)
    assert r.stdout.split()[0] == "old"
    assert "が無い" in r.stderr and "読み直す" in r.stderr and NEW in r.stderr


def test_裏の入れ直しが失敗していれば訳を名指して入った中の先端で回る(tmp_path):
    box, rel = probe_box(tmp_path)
    (box["claude"] / "af-foundation").mkdir(parents=True)
    (box["claude"] / "af-foundation" / "refresh.json").write_text(json.dumps({"code": 1, "line": "取れなかった"}),
                                                                   encoding="utf-8")
    r = run_py(box["dirs"][("docs-kit", "old")] / rel, box)
    assert r.stdout.split()[0] == "new"
    assert "1 で抜けていた" in r.stderr and "取れなかった" in r.stderr


def test_入れ直しの途中は錠が外れるまで待ち_待ち切れなければ訳を返す(tmp_path):
    box, rel = probe_box(tmp_path)
    lock = box["claude"] / "af-foundation" / "refresh.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("1", encoding="utf-8")
    hr = af_place.load_module("t_hook_run", box["plugins"] / "marketplaces" / kaku.MARKET / "plugins" / "core"
                              / "scripts" / "hook_run.py")
    run, root, note = hr.newest(box["dirs"][("docs-kit", "old")] / rel, wait=0.3)
    assert "済まなかった" in note and root is not None and run.parent.parent.parent.name == NEW


def _hook_box(tmp):
    hooks = json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"type": "command",
                                                             "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/h.py"'}]}]}})
    files = {"scripts/h.py": "print(1)\n", "hooks/hooks.json": hooks}
    box = make_box(tmp, {"guard": {"old": files, "new": files}})
    hr = af_place.load_module("t_hook_run_t", box["plugins"] / "marketplaces" / kaku.MARKET / "plugins" / "core"
                              / "scripts" / "hook_run.py")
    return box, hr


def test_hook_は入れ直しの途中なら待たずに窓が立った時の揃った版で回る(tmp_path):
    box, hr = _hook_box(tmp_path)
    old, new = box["dirs"][("guard", "old")], box["dirs"][("guard", "new")]
    env = {"CLAUDE_PLUGIN_ROOT": str(old)}
    assert hr.target(old / "scripts" / "h.py", [], env, box["claude"]) == (new / "scripts" / "h.py", new)
    lock = box["claude"] / "af-foundation" / "refresh.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("1", encoding="utf-8")
    assert hr.target(old / "scripts" / "h.py", [], env, box["claude"]) == (old / "scripts" / "h.py", None)
    os.utime(lock, (1, 1))  # 古すぎる錠（落ちた入れ直しの残り）は見ない
    assert hr.target(old / "scripts" / "h.py", [], env, box["claude"]) == (new / "scripts" / "h.py", new)


def test_隣の_plugin_が同じ版で入るのを入れ直しの間だけ待つ(tmp_path, monkeypatch):
    import threading

    rel = os.path.join("skills", "qa-html", "check.mjs")
    box = make_box(tmp_path, {"guard": {"old": {}, "new": {}}, "docs-kit": {"old": {rel: "x"}, "new": {}}})
    guard_new = str(box["dirs"][("guard", "new")])
    want = box["dirs"][("docs-kit", "new")] / rel
    assert af_place.sibling_plugin_file("docs-kit", rel, guard_new) == ""  # 錠が無ければ待たない・別の版へ降りない
    lock = box["claude"] / "af-foundation" / "refresh.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("1", encoding="utf-8")
    monkeypatch.setattr(af_place, "SIBLING_WAIT", 0.5)
    assert af_place.sibling_plugin_file("docs-kit", rel, guard_new) == ""  # 待ち切れなければ空（呼ぶ側が名指す）
    monkeypatch.setattr(af_place, "SIBLING_WAIT", 10)

    def land():
        want.parent.mkdir(parents=True, exist_ok=True)
        want.write_text("x", encoding="utf-8")
    threading.Timer(0.6, land).start()
    assert af_place.sibling_plugin_file("docs-kit", rel, guard_new) == str(want)


def test_目録の_clone_が無ければ今の版で続けて訳を出す(tmp_path):
    box, rel = probe_box(tmp_path)
    shutil.rmtree(box["plugins"] / "marketplaces")
    r = run_py(box["dirs"][("docs-kit", "old")] / rel, box)
    assert r.stdout.split()[0] == "old" and "使えない" in r.stderr


def test_repo_の取り出しから回す時は乗り換えない(tmp_path):
    d = tmp_path / "repo" / "plugins" / "docs-kit"
    (d / "lib").mkdir(parents=True)
    shutil.copy(AF_PLACE, d / "lib" / "af_place.py")
    (d / "skills" / "x").mkdir(parents=True)
    (d / "skills" / "x" / "probe.py").write_text(PROBE.format(ver="repo"), encoding="utf-8")
    r = run_py(d / "skills" / "x" / "probe.py", {"home": tmp_path})
    assert r.stdout.split()[0] == "repo" and r.stderr == ""


# ── check.mjs（python でない入口）も同じ口で乗り換える ──

@pytest.mark.skipif(shutil.which("node") is None, reason="node が無い")
def test_check_mjs_は古い版から呼ばれても先端の版で回る(tmp_path):
    rel = "skills/qa-html/check.mjs"
    real = (ROOT / "plugins" / "docs-kit" / rel).read_text(encoding="utf-8")
    box = make_box(tmp_path, {"docs-kit": {"old": {rel: real},
                                           "new": {rel: 'console.log("new", process.env.CLAUDE_PLUGIN_ROOT ?? "", '
                                                        '...process.argv.slice(2));\n'}}})
    old = box["dirs"][("docs-kit", "old")] / rel
    shutil.copytree(ROOT / "plugins" / "docs-kit" / "skills" / "qa-html", old.parent, dirs_exist_ok=True)  # 古い版の一式
    e = dict(os.environ, HOME=str(box["home"]), CLAUDE_PLUGIN_ROOT=str(old.parents[2]))
    e.pop(af_place.NEWEST_ENV, None)
    r = subprocess.run(["node", str(old), "x.html"], env=e, capture_output=True, text=True, timeout=60)
    assert r.stdout.split() == ["new", str(box["dirs"][("docs-kit", "new")]), "x.html"], (r.stdout, r.stderr)


# ── 入口の 1 行が抜けた道具が無い（skill から呼ぶ script の全部） ──

SKILL_SCRIPTS = [
    "plugins/dev-flow/skills/codex/codex_pack.py",
    "plugins/dev-flow/skills/spec-doc/seal.py",
    "plugins/docs-kit/skills/big-picture/scripts/big_picture.py",
    "plugins/docs-kit/skills/blueprint/scripts/check_blueprint.py",
    "plugins/docs-kit/skills/theory-mock/scripts/check_theory_mock.py",
    "plugins/docs-kit/skills/make-deck/scripts/render_prompt.py",
    "plugins/docs-kit/skills/make-deck/scripts/finish_deck.py",
    "plugins/guard/scripts/values_keys.py",
    "plugins/guard/scripts/unanswered.py",
    "plugins/checker/scripts/verdict_form.py",
    "plugins/checker/scripts/pr_writer.py",
    "plugins/session-watch/scripts/session_watch.py",
    "skill-values/skill_values.py",
]


@pytest.mark.parametrize("rel", SKILL_SCRIPTS)
def test_skill_から呼ぶ_script_は入口で先端の版へ乗り換える(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    main = text.split('if __name__ == "__main__":', 1)
    assert len(main) == 2 and "af_place.run_newest(__file__)" in main[1], rel


def test_skill_の本文が指す_script_は乗り換えの一覧に載る():
    """SKILL.md が ${CLAUDE_PLUGIN_ROOT}/… で指す .py は、乗り換える（上の一覧）か自分で先端を取る（review_gate の
    ensure_tip）か hook の入口（guard.py＝hook_run が回す）かのどれか。新しい道具が一覧から漏れると赤。"""
    own = {"scripts/review_gate.py": "ensure_tip", "scripts/guard.py": None}
    for skill in ROOT.glob("plugins/*/skills/*/SKILL.md"):
        plugin = skill.parents[2]
        for rel in set(re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w/.-]+\.py)", skill.read_text(encoding="utf-8"))):
            if rel in own:
                continue
            path = (plugin / rel).resolve()
            assert path.is_file(), (skill, rel)
            assert "af_place.run_newest(__file__)" in path.read_text(encoding="utf-8"), (skill, rel)


def test_lib_の_af_place_は正本への_symlink():
    for p in ROOT.glob("plugins/*/lib/af_place.py"):
        assert p.is_symlink() and p.resolve() == AF_PLACE.resolve(), p


# ── 入れ直しの途中: 守りの hook が入った版の public-guard を見失わない ──

def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True)


def _clone(plugins: Path, body: str) -> tuple[Path, str]:
    clone = plugins / "marketplaces" / "market"
    if clone.exists():
        shutil.rmtree(clone)
    (clone / "public-guard").mkdir(parents=True)
    (clone / "public-guard" / "guard.py").write_text(body, encoding="utf-8")
    _git(clone, "init", "-q")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", body.strip())
    sha = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return clone, sha


def test_浅い_clone_が先へ進み入った版が歴史から消えても取り置きから同じ版を読む(tmp_path):
    plugins = tmp_path / ".claude" / "plugins"
    clone, sha = _clone(plugins, "入った版\n")
    guard_root = plugins / "cache" / "market" / "guard" / sha[:12]
    guard_root.mkdir(parents=True)
    rel = os.path.join("public-guard", "guard.py")
    assert Path(af_place.foundation_file(rel, str(guard_root))).read_text(encoding="utf-8") == "入った版\n"
    _clone(plugins, "先へ進んだ版\n")  # 入れ直しの途中: 浅い clone を取り直し、入った版の commit が消えた
    got = af_place.foundation_file(rel, str(guard_root))
    assert got and Path(got).read_text(encoding="utf-8") == "入った版\n", got


def test_取り置きも無く入った版が歴史に無ければ空を返す_読み違えない(tmp_path):
    plugins = tmp_path / ".claude" / "plugins"
    _clone(plugins, "先へ進んだ版\n")
    guard_root = plugins / "cache" / "market" / "guard" / ("c" * 12)
    guard_root.mkdir(parents=True)
    assert af_place.foundation_file(os.path.join("public-guard", "guard.py"), str(guard_root)) == ""


def test_取り置きは_dir_ごと_隣の_file_も同じ版で揃う(tmp_path):
    plugins = tmp_path / ".claude" / "plugins"
    clone, sha = _clone(plugins, "入った版\n")
    (clone / "public-guard" / "workflow_reader.py").write_text("隣\n", encoding="utf-8")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "隣")
    sha = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dest = af_place.keep_dir(str(tmp_path / ".claude"), sha[:12])
    assert af_place.keep_version(str(clone), sha, dest)
    assert (Path(dest) / "public-guard" / "workflow_reader.py").read_text(encoding="utf-8") == "隣\n"


def test_入れ直しは目録の_clone_を取り直す前に入った版を取り置く():
    src = (ROOT / "scripts" / "setup_plugins.py").read_text(encoding="utf-8")
    body = src.split("def refresh(", 1)[1].split("\ndef ", 1)[0]
    assert "keep_installed(" in body
    first_git = min(i for i in (body.find('"fetch"'), body.find('"pull"'), body.find("marketplace")) if i >= 0)
    assert body.find("keep_installed(") < first_git


def test_foundation_file_が読む物は全部取り置く根の下():
    calls = []
    for p in ROOT.glob("plugins/**/*.py"):
        calls += re.findall(r'"((?:public-guard|plugins)/[\w/.-]+)"', p.read_text(encoding="utf-8")) \
            if "foundation_file(" in p.read_text(encoding="utf-8") else []
    sw = (ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py").read_text(encoding="utf-8")
    plain = re.findall(r'\("AF_\w+", "([^"]+)", None, None\)', sw)  # 隣の plugin で引けない物だけ foundation_file へ
    for rel in plain + ["public-guard/guard.py", "public-guard/workflow_reader.py"]:
        assert rel.split("/", 1)[0] in af_place.KEEP_ROOTS, rel


# ── skill の本文: 乗り換えの口が先端の本文の path を名指す（知らせるだけ・見張りは足さない） ──

def _body_box(tmp, old_body, new_body):
    rel = "skills/x/probe.py"
    old = {rel: PROBE.format(ver="old"), "skills/x/SKILL.md": old_body}
    new = {rel: PROBE.format(ver="new")}
    if new_body is not None:
        new["skills/x/SKILL.md"] = new_body
    return make_box(tmp, {"docs-kit": {"old": old, "new": new}}), rel


def test_古い版の_skill_の本文で動いた時は先端の版の本文を名指す(tmp_path):
    box, rel = _body_box(tmp_path, "古い本文\n", "新しい本文\n")
    r = run_py(box["dirs"][("docs-kit", "old")] / rel, box)
    assert r.stdout.split()[0] == "new"
    assert str(box["dirs"][("docs-kit", "new")] / "skills" / "x" / "SKILL.md") in r.stderr


def test_本文が同じなら本文は名指さない(tmp_path):
    box, rel = _body_box(tmp_path, "同じ\n", "同じ\n")
    r = run_py(box["dirs"][("docs-kit", "old")] / rel, box)
    assert r.stdout.split()[0] == "new"
    assert "SKILL.md" not in r.stderr


def test_先端の版で_skill_の本文が畳まれていれば畳まれたと知らせる(tmp_path):
    box, rel = _body_box(tmp_path, "古い本文\n", None)
    r = run_py(box["dirs"][("docs-kit", "old")] / rel, box)
    assert "畳まれた" in r.stderr


def test_古い本文の知らせは見張りを足さず乗り換えの口の中だけ():
    assert not (ROOT / "plugins" / "guard" / "scripts" / "stale_path.py").exists()
    assert "_body_note" in (CORE / "scripts" / "hook_run.py").read_text(encoding="utf-8")


def test_入れ直しの錠の決まりは_af_place_の_1_つを_core_も引く(tmp_path, monkeypatch):
    """錠の置き場と生きている秒の正本は skill-values/af_place.py。core の kaku.py・hook_run.py は core の lib/af_place.py
    （symlink）から引き、手で写さない。正本の秒を変えると core の両方の判定が一緒に変わる（写しなら変わらず赤）。"""
    sys.path.insert(0, str(ROOT / "tests"))
    from uses import py_code
    link = CORE / "lib" / "af_place.py"
    assert link.is_symlink() and link.resolve() == AF_PLACE.resolve()
    for f in ("kaku.py", "hook_run.py"):
        code = py_code((CORE / "scripts" / f).read_text(encoding="utf-8"))
        assert not re.search(r"REFRESH_TIMEOUT\s*\+|\b660\b|\b600\b", code), f   # 秒を写すと赤（置き場は下で動かして照らす）
    import hook_run
    claude = tmp_path / ".claude"
    lock = Path(af_place.refresh_file(claude, "refresh.lock"))
    lock.parent.mkdir(parents=True)
    lock.write_text("", encoding="utf-8")
    old = __import__("time").time() - 100
    os.utime(lock, (old, old))
    monkeypatch.setattr(af_place, "LOCK_AGE", 50)
    assert hook_run._refreshing(claude) is False and hook_run._wait_refresh(claude, 0) == ""
    monkeypatch.setattr(af_place, "LOCK_AGE", 200)
    assert hook_run._refreshing(claude) is True
    monkeypatch.setenv("HOME", str(tmp_path))
    assert kaku._refresh_file("refresh.lock") == lock and kaku._lock_rule() is af_place
    # 正本の置き場を動かすと core の両方が一緒に動く（kaku・hook_run が置き場を手で組み直すと、元の所を見て赤）
    moved = tmp_path / "動かした置き場"
    moved.mkdir()
    monkeypatch.setattr(af_place, "refresh_file", lambda c, name: str(moved / name))
    assert kaku._refresh_file("refresh.lock") == moved / "refresh.lock"
    assert kaku._refresh_file("refresh.json") == moved / "refresh.json"
    assert hook_run._refreshing(claude) is False                     # 元の所の錠は見ない
    (moved / "refresh.lock").write_text("", encoding="utf-8")
    assert hook_run._refreshing(claude) is True
    (moved / "refresh.lock").unlink()
    (moved / "refresh.json").write_text('{"code": 1, "line": "動かした所の結果"}', encoding="utf-8")
    assert "動かした所の結果" in hook_run._wait_refresh(claude, 0)    # 前の入れ直しの結果も動かした所から読む
