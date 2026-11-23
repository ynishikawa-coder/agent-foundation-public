"""土台の在り処探しの 1 本の口（plugin の外の土台の file・隣の plugin の file を、入った plugin と同じ版で探して読む）。

土台の plugin は市場から入ると cache/<市場>/<plugin>/<版> に置かれ、repo の根の物（public-guard/guard.py など）は
plugin の中に無い。正本を写さず直に読むために、どの plugin もここ 1 か所で探す（各 plugin の lib/ へは symlink で届く）。
plugin_root は呼ぶ plugin の根（repo の形では plugins/<plugin>・入れた形では cache/<市場>/<plugin>/<版>）。
"""
from __future__ import annotations

import os
import re
import time


def sibling_plugin_file(plugin, rel, plugin_root):
    """隣の plugin の file の path か ""。正本を写さず直に読むための在り処探し。
    repo の形: plugins/<呼ぶ plugin> と plugins/<plugin> が隣。
    入れた plugin の形: cache/<市場>/<呼ぶ plugin>/<版> と cache/<市場>/<plugin>/<同じ版>。
    同じ版だけを見る（別の版へ降りない＝正本と呼ぶ plugin の版が食い違ったまま照らさない。見つからなければ "" で、
    呼ぶ側が止めて「同じ版で入れ直す」と名指しする）。"""
    here = plugin_root
    cand = os.path.join(os.path.dirname(here), plugin, rel)
    if os.path.isfile(cand):
        return cand
    ver = os.path.basename(here)
    market = os.path.dirname(os.path.dirname(here))
    same = os.path.join(market, plugin, ver, rel)
    if os.path.isfile(same):
        return same
    # 裏の入れ直しは plugin を 1 つずつ入れる: 呼ぶ plugin が先に先端の版へ入り、隣がまだ前の版の間は同じ版が無い。
    # 錠が在る間は SIBLING_WAIT 秒まで待って引き直す（別の版へは降りない）
    lock = _refresh_lock(here)
    end = time.time() + SIBLING_WAIT
    while lock and lock_alive(lock) and time.time() < end:
        time.sleep(0.5)
        if os.path.isfile(same):
            return same
    return same if os.path.isfile(same) else ""


SIBLING_WAIT = 30   # 隣の plugin が同じ版で入るのを待つ上限（秒・hook の中で呼ばれるので短く）

# 裏の入れ直しの錠の決まり（正本はここ 1 つ）。core の kaku.py（錠を掛ける・外す）と hook_run.py（錠の間は待つ）も
# core の lib/af_place.py（symlink）からここを引く。手で写さない。
REFRESH_TIMEOUT = 600              # 裏の入れ直し（入口 setup_plugins.py）を待つ上限（秒）
LOCK_AGE = REFRESH_TIMEOUT + 60    # 錠をまだ生きているとみなす上限（秒・これより古い錠は落ちた入れ直しの残り）


def refresh_file(claude, name):
    """裏の入れ直しの file（錠 refresh.lock・結果 refresh.json）の path。claude は ~/.claude。"""
    return os.path.join(str(claude), "af-foundation", name)


def lock_alive(lock):
    """錠が在って LOCK_AGE より新しいか（入れ直しの途中か）。"""
    try:
        return time.time() - os.stat(lock).st_mtime <= LOCK_AGE
    except OSError:
        return False


def _refresh_lock(plugin_root):
    """plugin_root が入れた形 <.claude>/plugins/cache/<市場>/<plugin>/<版> なら裏の入れ直しの錠の path、違えば ""。"""
    parts = os.path.normpath(plugin_root).split(os.sep)
    if len(parts) < 6 or parts[-4] != "cache" or parts[-5] != "plugins":
        return ""
    return refresh_file(os.sep.join(parts[:-5]) or os.sep, "refresh.lock")


# foundation_file が "" を返した訳と直し方（呼ぶ側が止める文に添える。見つかった時は ""）。
MISS = ""


def _miss(why):
    global MISS
    MISS = why
    return ""


def miss_note():
    """直前の foundation_file が "" を返した訳（止める文の後ろに添える形）。無ければ ""。"""
    return f"（訳: {MISS}）" if MISS else ""


def _commit_at(clone, ver):
    return (_clone_git(clone, "rev-parse", "--verify", "-q", f"{ver}^{{commit}}") or b"").decode().strip()


def _installed_sha(plugins_dir, plugin_root, ver):
    """plugin の台帳（<plugins>/installed_plugins.json）で plugin_root に入った版の full sha（ver で始まる 40 桁）か ""。"""
    import json
    try:
        with open(os.path.join(plugins_dir, "installed_plugins.json"), encoding="utf-8") as f:
            rows = json.load(f).get("plugins") or {}
    except (OSError, ValueError, AttributeError):
        return ""
    want = os.path.realpath(plugin_root)
    for entries in rows.values() if isinstance(rows, dict) else ():
        for row in entries if isinstance(entries, list) else ():
            if not isinstance(row, dict) or os.path.realpath(str(row.get("installPath") or "")) != want:
                continue
            sha = str(row.get("gitCommitSha") or "")
            if re.fullmatch(r"[0-9a-f]{40}", sha) and sha.startswith(ver):
                return sha
    return ""


def _clone_git(clone, *args, timeout=10):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", clone, *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


KEEP_ROOTS = ("public-guard",)  # foundation_file が読む repo の根の dir（入れ直しの前に版ごとに取り置く物・正本はここ 1 つ）
KEEP_DIR = ("af-foundation", "at")  # 取り置きの置き場 <~/.claude>/af-foundation/at/<版>/<rel>


def keep_dir(claude, ver):
    """版 ver の土台の file の取り置きの dir（<~/.claude>/af-foundation/at/<版>）。"""
    return os.path.join(claude, *KEEP_DIR, ver)


def _write(out, body):
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = f"{out}.{os.getpid()}"
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, out)
    except OSError:
        return False
    return True


def keep_version(clone, commit, dest):
    """clone の commit の KEEP_ROOTS を丸ごと dest（keep_dir）へ取り置く（1 つの file でなく dir ごと＝隣の file を
    読む物も同じ版で揃う）。済み＝True。済んだ印 .kept が在れば何もしない。"""
    import io
    import tarfile
    if os.path.isfile(os.path.join(dest, ".kept")):
        return True
    body = _clone_git(clone, "archive", "--format=tar", commit, *KEEP_ROOTS)
    if body is None:
        return False
    tmp = f"{dest}.{os.getpid()}.tmp"
    try:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        with tarfile.open(fileobj=io.BytesIO(body)) as t:
            for m in t.getmembers():
                if not (m.isfile() or m.isdir()) or m.name.startswith("/") or ".." in m.name.split("/"):
                    continue
                t.extract(m, tmp, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        open(os.path.join(tmp, ".kept"), "w").close()
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.replace(tmp, dest)
    except (OSError, tarfile.TarError):
        return os.path.isfile(os.path.join(dest, ".kept"))
    return True


def foundation_file(rel, plugin_root):
    """土台の repo の根からの file（plugin の外・例 public-guard/guard.py）の、入った plugin と同じ版の path か ""。
    repo の形: plugins/<plugin> の 2 つ上が repo の根。
    入れた plugin の形: <plugins>/cache/<市場>/<plugin>/<版> → <plugins>/marketplaces/<市場>/（市場の取り出し＝repo 全体）。
    市場の取り出しの今の checkout は入った plugin と同じ版の時だけ読む（clone が先へ進んだ・古い clone が残った時に
    違う版の決まりで照らさない）。版が違えば、その版の中身を clone の歴史から取り出して読む。版は cache の dir の名（commit の頭）。
    読めた中身は版ごとに <~/.claude>/af-foundation/at/<版>/ へ取り置く。入れ直しの途中で浅い clone が先端へ進み、
    入った版が clone の歴史から消えても、取り置き（入れ直しの前に setup_plugins.py も取り置く）から同じ版を読む。
    取り置きも無ければ ""（＝呼ぶ側が止めて名指しする）。"""
    global MISS
    MISS = ""
    here = plugin_root
    cand = os.path.join(os.path.dirname(os.path.dirname(here)), rel)
    if os.path.isfile(cand):
        return cand
    market = os.path.dirname(os.path.dirname(here))
    cache = os.path.dirname(market)
    plugins = os.path.dirname(cache)
    clone = os.path.join(plugins, "marketplaces", os.path.basename(market))
    ver = os.path.basename(here)
    if not re.fullmatch(r"[0-9A-Za-z._-]{1,64}", ver or ""):
        return _miss(f"{rel} が plugin の外に無く、市場の取り出し {clone} も無い（または版の名 {ver!r} が読めない）。"
                     "土台の plugin を市場から入れ直す")
    kept = os.path.join(keep_dir(os.path.dirname(plugins), ver), rel)
    head = (_clone_git(clone, "rev-parse", "HEAD") or b"").decode().strip() if os.path.isdir(clone) else ""
    if not head:
        # clone が無い・git として読めない（入れ直しの途中）＝同じ版の取り置きだけを読む
        if os.path.isfile(kept):
            return kept
        if not os.path.isdir(clone):
            return _miss(f"{rel} が plugin の外に無く、市場の取り出し {clone} も無い（または版の名 {ver!r} が読めない）。"
                         "土台の plugin を市場から入れ直す")
        return _miss(f"市場の取り出し {clone} が git として読めない（入った版と同じか分からない）。土台の plugin を市場から入れ直す")
    at = _commit_at(clone, ver)
    if not at:
        # 市場の取り出しは浅い clone（Claude Code が先端の 1 つだけを取る）で、入った版が先端と違うと歴史に無い。
        # 入った版の full sha（plugin の台帳 installed_plugins.json）を出所から取り寄せて同じ版を読む（窓の側の手を要さない）
        full = _installed_sha(plugins, here, ver)
        if full:
            _clone_git(clone, "fetch", "--quiet", "--depth=1", "origin", full, timeout=60)
            at = _commit_at(clone, ver)
    if not at:
        # 取り寄せられない（入れ直しの途中で浅い clone が先へ進んだ等）＝同じ版の取り置きを読む
        if os.path.isfile(kept):
            return kept
        shallow = (_clone_git(clone, "rev-parse", "--is-shallow-repository") or b"").decode().strip() == "true"
        return _miss(f"入った版 {ver} が市場の取り出し {clone} の歴史に無い"
                     + ("（浅い clone で、出所から入った版を取り寄せられなかった）" if shallow else "")
                     + f"。直し: git -C {clone} fetch --unshallow をしてから回し直す（出所へ届かない時は土台の plugin を市場から入れ直す）")
    keep_version(clone, at, keep_dir(os.path.dirname(plugins), ver))
    if at == head:
        cand = os.path.join(clone, rel)
        if os.path.isfile(cand):
            return cand
        # 先端は入った版のまま取り出しの file だけが消えている間（入れ直しの途中）＝同じ版の取り置きを読む
        return kept if os.path.isfile(kept) else _miss(f"入った版 {ver} の土台に {rel} が無い")
    if os.path.isfile(kept):
        return kept
    body = _clone_git(clone, "show", f"{at}:{rel.replace(os.sep, '/')}")  # KEEP_ROOTS の外の file
    if body is None:
        return _miss(f"入った版 {ver} の土台に {rel} が無い（市場の取り出し {clone} の歴史から取り出せない）")
    return kept if _write(kept, body) else _miss(f"入った版 {ver} の {rel} を置き場へ書けない")

NEWEST_ENV = "AF_NEWEST_RAN"


def run_newest(script_file, argv=None):
    """skill から呼ぶ script の入口の頭で呼ぶ: この script が入った plugin の、入った台帳のいちばん新しい版に
    同じ script が在れば、そちらへ乗り換える（CLAUDE_PLUGIN_ROOT をその版の dir にして exec・戻らない）。
    窓が立った時の版の dir を skill の本文が指したままでも、先端の版で動く。決め方の正本は目録の clone の
    plugins/core/scripts/hook_run.py の newest（clone は起動の時に先端へ取り直す＝決め方の直しも次から効く）。
    repo の取り出し・試験の写し・clone が無い・何か壊れた時は今の版のまま続ける（止めない）。訳は stderr に名指す。"""
    import sys
    me = os.path.abspath(script_file)
    if os.environ.get(NEWEST_ENV) == me:
        return  # 乗り換えた先（同じ path へ 2 度乗り換えない）
    parts = me.split(os.sep)
    try:
        i = len(parts) - 1 - parts[::-1].index("cache")
    except ValueError:
        return  # 入った plugin の置き場でない
    if i + 2 >= len(parts) or parts[i - 1] != "plugins":
        return
    plugins = os.sep.join(parts[:i])
    hook_run = os.path.join(plugins, "marketplaces", parts[i + 1], "plugins", "core", "scripts", "hook_run.py")
    try:
        run, root, note = load_module("af_hook_run", hook_run).newest(me)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[土台] いちばん新しい版を引く口（{hook_run}）が使えない（{type(e).__name__}）。今の版で続ける\n")
        return
    if note:
        sys.stderr.write(f"[土台] {note}\n")
    if root is None or os.path.abspath(str(run)) == me:
        return
    sys.stderr.write(f"[土台] 窓が立った時の版でなく、入った中でいちばん新しい版 {root} の {os.path.basename(me)} で回す\n")
    sys.stdout.flush()
    sys.stderr.flush()
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(root), **{NEWEST_ENV: os.path.abspath(str(run))})
    args = sys.argv[1:] if argv is None else list(argv)
    os.execve(sys.executable, [sys.executable, str(run), *args], env)


def load_module(name, path):
    """path の .py を名前 name で読み込む（正本を写さず直に呼ぶ）。読めなければ例外。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
