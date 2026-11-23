#!/usr/bin/env python3
"""土台の hook の入口: 入った台帳の今いちばん新しい版の script を回す（窓が古い版の dir で立っても先端の hook が効く）。

意図: 合流した守りの hook の直しが、古い土台で立った窓にも次の呼び出しから効く。
課題: 作り置きの箱で立った窓は、箱を作った時の版の hook で動き続け、合流した直し（窓を立て直させる知らせ・返事の
  差し戻しを畳んだ直し）が箱の作り直しまで効かなかった。
原因: hooks.json の命令が版の dir（${CLAUDE_PLUGIN_ROOT}）の script を直に指していた。Claude Code は窓の途中で plugin を
  入れ直しても hook の dir を替えない（「Restart to apply changes」・2.1.330 で確かめた）。
形: 土台の hooks.json の命令は、目録の clone（~/.claude/plugins/marketplaces/agent-foundation）のこの入口へ
  自分の script の path と引数を渡す（入口が無ければ自分の script を直に回す）:
    f=…/hook_run.py; [ -f "$f" ] || f=; python3 ${f:+"$f"} "${CLAUDE_PLUGIN_ROOT}/scripts/<script>" <引数>
  入口は目録の clone の物＝起動の時に plugin core が先端へ取り直す（kaku.py の refresh）ので、入口の直しも次の呼び出しから効く。
やる事: 渡された script が属する plugin（呼ばれた dir の plugin.json の名）の、入った台帳（~/.claude/plugins/installed_plugins.json）の今読まれる行
  （kaku.current_row＝dir が在る行のうち最後に入れた行）の dir を引き、それが呼ばれた dir と違えば、その版の
  同じ script を CLAUDE_PLUGIN_ROOT をその dir にして回す。その版の hooks.json に同じ命令が無ければ（先端が外した hook）
  何もせず 0 で抜ける。引けない・読めない・何か壊れた時は、渡された script をそのまま回す（前の版で続ける・止めない）。
秘密は読まない（読むのは台帳と hooks.json だけ）。

skill から呼ぶ script も同じ口で先端へ乗り換える（newest・lib/af_place.py の run_newest が呼ぶ）:
  課題: 窓の途中で土台が入れ直されても、skill の本文が指す ${CLAUDE_PLUGIN_ROOT} は窓が立った時の版の dir のままで、
    skill から呼ぶ script（codex_pack・seal・review の判定の型など）が古い版で動いた。
  形: script の置き場の形（cache/<目録>/<plugin>/<版>）から plugin と版を引き、台帳の今読まれる行の版の同じ script を回す。
    hook と違い hooks.json の照らしは無い（skill は hooks.json に載らない）。裏の入れ直しの途中（錠が在る）なら
    済むのを WAIT 秒まで待つ（入れ直しの途中の半端な版を掴まない）。先端の版に同じ script が無い・待ち切れない・
    入れ直しが失敗した時は、その訳を名指して今の版で続ける（止めない・黙らない）。
  命令から: hook_run.py --where <script> で回す path を 1 行で出す（python でない入口・check.mjs が使う）。
  hook として回す時は、窓が立った時の dir を AF_HOOK_STARTED_ROOT に残す（守りの hook が「窓が読んだ skill の本文の版」を知る口）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

WAIT = 120          # 裏の入れ直しの錠が外れるのを待つ上限（秒）
STARTED_ENV = "AF_HOOK_STARTED_ROOT"


def _rows_of(root: Path, table: dict) -> list[dict] | None:
    """root（呼ばれた dir）の plugin の、土台の目録の user scope の行の並び。無ければ None。
    plugin は root の .claude-plugin/plugin.json の名で引く（Claude Code は入れ直すと台帳の行を新しい版の行に
    置き換え、呼ばれた古い dir の行は台帳に残らない・2.1.330 で確かめた）。dir が消えていれば置き場の形から、
    それでも引けなければ installPath で引く。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kaku  # 台帳の読み方・今読まれる行の決め方の正本（写さない）

    rows = kaku.user_rows(table, kaku.MARKET)
    try:
        name = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("name")
    except (OSError, ValueError, AttributeError):
        # 古い版の dir が掃除で消えた: Claude Code の置き場の形 cache/<目録>/<plugin>/<版> から名を引く
        name = root.parent.name if root.parent.parent.name == kaku.MARKET else None
    if name in rows:
        return rows[name]
    for found in rows.values():
        if any(r.get("installPath") and Path(str(r["installPath"])).resolve() == root for r in found):
            return found
    return None


def _same_hook(new_root: Path, rel: str, args: list[str]) -> bool:
    """新しい版の hooks.json に、同じ script を同じ引数で回す命令が在るか。"""
    hooks = (json.loads((new_root / "hooks" / "hooks.json").read_text(encoding="utf-8")).get("hooks") or {})
    want = "${CLAUDE_PLUGIN_ROOT}/" + rel + '"' + "".join(" " + a for a in args)
    return any(str(h.get("command", "")).endswith(want)
               for groups in hooks.values() for g in groups for h in (g.get("hooks") or []))


def target(script: Path, args: list[str], env: dict, home: Path) -> tuple[Path, Path | None] | None:
    """(回す script, その plugin の dir＝渡す CLAUDE_PLUGIN_ROOT。None なら替えない)。
    None＝先端の版はこの hook を外した（何もしない）。決められなければ渡された script のまま。"""
    try:
        root = Path(env.get("CLAUDE_PLUGIN_ROOT") or "").resolve()
        rel = script.resolve().relative_to(root).as_posix()
        table = json.loads((home / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        rows = _rows_of(root, table)
        if not rows:
            return script, None
        import kaku

        row = kaku.current_row(rows)
        new_root = Path(str(row["installPath"])).resolve() if row else root
        if new_root == root:
            return script, None
        if not _same_hook(new_root, rel, args):
            return None
        new = new_root / rel
        return (new, new_root) if new.is_file() else (script, None)
    except Exception:  # noqa: BLE001  入口が壊れても守りの hook は止めない＝渡された script を回す
        return script, None


def plugin_root_of(script: Path) -> Path | None:
    """script が入った plugin の置き場の形 <.claude>/plugins/cache/<目録>/<plugin>/<版>/… なら、その <版> の dir。
    違う形（repo の取り出し・試験の写し）なら None（乗り換えない）。symlink は辿らない（lib の正本へ降りない）。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import kaku

    p = Path(os.path.abspath(script))
    for d in p.parents:
        if len(d.parents) >= 4 and d.parents[1].name == kaku.MARKET and d.parents[2].name == "cache" \
                and d.parents[3].name == "plugins":
            return d
    return None


def _wait_refresh(claude: Path, wait: float) -> str:
    """裏の入れ直しの錠が在る間は wait 秒まで待つ。残る訳（待ち切れない・前の入れ直しの失敗）の 1 行か ""。"""
    import kaku

    lock = claude / "af-foundation" / "refresh.lock"
    end = time.time() + wait
    told = False
    while lock.exists() and time.time() - lock.stat().st_mtime <= kaku.REFRESH_TIMEOUT + 60:
        if time.time() >= end:
            return f"土台の裏の入れ直しが {int(wait)} 秒で済まなかった（錠 {lock}）。今入っている中でいちばん新しい版で続ける"
        if not told:
            sys.stderr.write("[土台] 裏で先端の版を入れ直している。済むのを待つ\n")
            told = True
        time.sleep(1)
    try:
        r = json.loads((claude / "af-foundation" / "refresh.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if isinstance(r, dict) and r.get("code") not in (0, None):
        return (f"土台の裏の入れ直しが {r.get('code')} で抜けていた（{r.get('line') or '訳は出ていない'}）。"
                "入っている中でいちばん新しい版で続ける")
    return ""


def newest_dir(path) -> tuple[Path | None, Path | None]:
    """path が入った plugin の (path の版の dir, 入った台帳の今読まれる行の dir)。置き場の形でない・台帳に行が無ければ
    片方か両方が None。待たない（裏の入れ直しの錠を見ない）。守りの hook の知らせ（guard の stale_path）も使う。"""
    root = plugin_root_of(Path(os.path.abspath(path)))
    if root is None:
        return None, None
    table = json.loads((root.parents[4] / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    rows = _rows_of(root, table)
    import kaku

    row = kaku.current_row(rows) if rows else None
    return root, (Path(os.path.abspath(str(row["installPath"]))) if row else None)


def newest(script, wait: float = WAIT) -> tuple[Path, Path | None, str]:
    """(回す script, 渡す CLAUDE_PLUGIN_ROOT〔None なら替えない〕, 名指す訳〔"" なら無し〕)。
    script と同じ plugin の、入った台帳の今読まれる行の版の同じ script。決められなければ渡された script のまま。"""
    script = Path(os.path.abspath(script))
    try:
        root = plugin_root_of(script)
        if root is None:
            return script, None, ""
        note = _wait_refresh(root.parents[4], wait)
        _, new_root = newest_dir(script)
        if new_root is None or new_root == root:
            return script, None, note
        new = new_root / script.relative_to(root)
        if not new.is_file():
            return script, None, (f"いちばん新しい版（{new_root.name}）に {script.relative_to(root)} が無い。"
                                  f"窓が立った時の版（{root.name}）で続ける。skill の本文を {new_root} から読み直す")
        return new, new_root, note
    except Exception as e:  # noqa: BLE001  入口が壊れても止めない＝渡された script のまま
        return script, None, f"いちばん新しい版を引けなかった（{type(e).__name__}: {e}）。今の版で続ける"


def main(argv: list[str]) -> int:
    if not argv:
        return 0
    if argv[0] == "--where":
        if len(argv) < 2:
            return 0
        run, _, note = newest(argv[1])
        if note:
            sys.stderr.write(f"[土台] {note}\n")
        print(run)
        return 0
    script, args = Path(argv[0]), argv[1:]
    home = Path(os.environ.get("HOME") or "~").expanduser() / ".claude"
    got = target(script, args, dict(os.environ), home)
    if got is None:
        return 0
    run, root = got
    env = dict(os.environ, **({"CLAUDE_PLUGIN_ROOT": str(root)} if root else {}))
    if os.environ.get("CLAUDE_PLUGIN_ROOT") and STARTED_ENV not in os.environ:
        env[STARTED_ENV] = os.environ["CLAUDE_PLUGIN_ROOT"]
    sys.stdout.flush()
    os.execve(sys.executable, [sys.executable, str(run), *args], env)
    return 0  # 届かない（execve は戻らない）


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
