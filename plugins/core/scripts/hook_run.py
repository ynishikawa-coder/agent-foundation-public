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
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


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


def main(argv: list[str]) -> int:
    if not argv:
        return 0
    script, args = Path(argv[0]), argv[1:]
    home = Path(os.environ.get("HOME") or "~").expanduser() / ".claude"
    got = target(script, args, dict(os.environ), home)
    if got is None:
        return 0
    run, root = got
    env = dict(os.environ, **({"CLAUDE_PLUGIN_ROOT": str(root)} if root else {}))
    sys.stdout.flush()
    os.execve(sys.executable, [sys.executable, str(run), *args], env)
    return 0  # 届かない（execve は戻らない）


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
