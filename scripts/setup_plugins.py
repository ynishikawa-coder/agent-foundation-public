#!/usr/bin/env python3
"""土台の plugin を全部入れる入口（使う側の環境の setup script が、土台の目録を足した後にこの 1 本を呼ぶ）。

使う側は plugin の名を写して持たない。入れる物は、この file と同じ checkout の配りの器
（`.claude-plugin/marketplace.json`）を直に読む。土台が plugin を足せば、次に立つ窓から黙って入る。

やる事:
  0. `claude plugin marketplace update <目録>` で目録の clone を出所の先端へ取り直す（前の setup の clone が残る容器では
     `marketplace add` が「already on disk」で何もせず、`plugin update` も目録を進めないので、打たないと古い名簿のまま入る）。
     取り直して入口そのものが変わっていれば、新しい入口へ 1 度だけ移る（古い入口の手順で新しい名簿を入れない）。
  1. 取り直した配りの器の plugin を全部 `claude plugin install <名>@<目録> --scope user` し、`claude plugin update` で追いつかせる。
  2. `claude plugin list --json` で全部が user scope で enabled か、入った台帳（installed_plugins.json の gitCommitSha）が
     目録の clone の HEAD（＝名簿の版）と同じかを照らす。台帳は installPath が list の読まれる dir と同じ行だけを読み、
     無ければ「分からない」と名指す（別の dir の行の版で揃ったと見ない）。取り直しに失敗した時も名指す（古い名簿で入れたと分かるように）。
  3. 入っていない・名簿の版に揃っていない物があれば、窓が起動時に必ず読む `~/.claude/CLAUDE.md` に名指しの知らせを 1 行書く（全部入れば消す）。
  4. この入口で入れた印を `~/.claude/af-foundation/setup.json` に書く（plugin core の起動の hook が、印の無い窓＝
     古い形の setup script で立った窓を名指しする）。印には、入れた時の出所の main の先端（main_at_setup）も書く
     （起動の hook が、入った commit をこれと比べて「setup が古い物を入れた」と「setup の後に main が進んだ」を分ける）。

使い方（setup script の形は docs/核の届け方.md）: python3 <目録の checkout>/scripts/setup_plugins.py
  CLAUDE_BIN で claude の場所を差し替えられる（既定 claude）。
exit: 0=全部が名簿の版で入った / 1=入っていない・版が揃わない・目録を取り直せない（知らせは書いた）/ 2=配りの器が読めない（知らせは書いた）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".claude-plugin" / "marketplace.json"
MARK = "<!-- af-plugin-missing -->"
REEXEC = "AF_SETUP_REEXEC"  # 取り直した新しい入口へ移った印（2 度は移らない）
FROM_CLONE = "AF_SETUP_FROM_CLONE"  # 目録の clone の入口へ移った印（2 度は移らない）
sys.path.insert(0, str(ROOT / "plugins" / "core" / "scripts"))
import kaku  # noqa: E402  目録の枝・出所の先端の聞き方の正本（起動の hook と同じ物を読む・写さない）
STATE = "setup.json"  # plugin core の kaku.py が読む印の file 名（~/.claude/af-foundation/ の下）
ROOT_CAUSE = "直し: 意図（窓が土台の plugin を全部入れて立つ）とのずれから入り、入らない形になった原因を細目 §3「まず構造を疑う」で探して直す（1 つずつ入れ直すだけで済ませない）"


def home() -> Path:
    return Path(os.environ.get("HOME") or "~").expanduser() / ".claude"


def catalog(manifest: Path = MANIFEST) -> tuple[str, list[str]]:
    """配りの器の (目録の名, plugin の名の並び)。読めない・空なら ValueError（黙って 0 本で進まない）。"""
    try:
        m = json.loads(manifest.read_text(encoding="utf-8"))
        name = m["name"]
        names = [p["name"] for p in m["plugins"]]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f"配りの器 {manifest} が読めない（{e}）") from e
    if not (isinstance(name, str) and name and names and all(isinstance(n, str) and n for n in names)):
        raise ValueError(f"配りの器 {manifest} に目録の名か plugin が無い")
    return name, names


def claude(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run([os.environ.get("CLAUDE_BIN") or "claude", *args], capture_output=True, text=True,
                              timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None


def listed() -> dict[str, str | None]:
    """{plugin の id: 読まれる dir（installPath）}（`claude plugin list --json` の user scope で enabled の物）。"""
    r = claude("plugin", "list", "--json")
    try:
        rows = json.loads(r.stdout) if r and r.returncode == 0 else []
    except ValueError:
        rows = []
    return {x.get("id"): x.get("installPath") for x in rows if isinstance(x, dict) and x.get("scope") == "user" and x.get("enabled")}


def catalog_entry(market: str) -> dict:
    """目録の登録（known_marketplaces.json の行）。無ければ {}。"""
    try:
        rows = json.loads((home() / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    m = rows.get(market) if isinstance(rows, dict) else None
    return m if isinstance(m, dict) else {}


def root_is_clone(market: str) -> bool:
    """この入口の在り処（ROOT）が目録の clone（installLocation）と同じ dir か。違えば名簿の版も出所も ROOT から読まない。"""
    return _same_dir(catalog_entry(market).get("installLocation"), ROOT)


def catalog_head(market: str | None = None) -> str | None:
    """目録の clone の HEAD（名簿の版）。分からなければ None（揃ったと見なさない）。
    入口が目録の clone の外（開発の checkout など）で回った時は None（作業の枝の HEAD を名簿の版と取らない）。"""
    if market is not None and not root_is_clone(market):
        return None
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def _same_dir(a, b) -> bool:
    try:
        return bool(a) and bool(b) and Path(a).resolve() == Path(b).resolve()
    except (OSError, ValueError):
        return False


def installed_shas(market: str, where: dict[str, str | None]) -> dict[str, str | None]:
    """{plugin の名: 入った commit}（Claude Code が入れた時に書く台帳 ~/.claude/plugins/installed_plugins.json から）。

    読むのは installPath が、その plugin の読まれる dir（where＝`claude plugin list` の installPath）と同じ行だけ。
    合う行が無ければ None（＝分からない）。最初の行・別の dir の行（project scope・前に別の所へ入った）の版で揃いを決めない。"""
    try:
        table = json.loads((home() / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        rows = table.get("plugins") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    out = {}
    for key, row in rows.items() if isinstance(rows, dict) else []:
        name, _, m = str(key).partition("@")
        if m != market:
            continue
        hit = [r for r in row if isinstance(r, dict) and _same_dir(r.get("installPath"), where.get(key))] \
            if isinstance(row, list) else []
        out[name] = (hit[0].get("gitCommitSha") or None) if hit else None
    return out


def main_tip(market: str | None = None) -> str | None:
    """目録が追う枝（source の ref＝`marketplace add <repo>#<枝>`。無ければ main）の先端を、目録の clone の出所へ直に聞く
    （取り直した clone の HEAD でなく出所の今の先端）。正本は kaku.source_ref・source_tip（起動の hook と同じ比べ方）。
    読めない・入口が目録の clone の外で回った時は None（起動の hook は「分からない」と名指す）。"""
    if market is not None and not root_is_clone(market):
        return None
    entry = catalog_entry(market) if market is not None else {}
    return kaku.source_tip(str(ROOT), kaku.source_ref(entry))


def notice(text: str | None) -> None:
    """~/.claude/CLAUDE.md の知らせの行を替える（text が None なら消すだけ）。"""
    path = home() / "CLAUDE.md"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        old = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
        keep = [line for line in old if not line.startswith(MARK)]
        if text:
            if keep and not keep[-1].endswith("\n"):
                keep[-1] += "\n"
            keep.append(f"{MARK} {text}\n")
        path.write_text("".join(keep), encoding="utf-8")
    except OSError as e:
        print(f"✗ {path} に知らせを書けない: {e}", file=sys.stderr)


def save_state(state: dict) -> None:
    try:
        d = home() / "af-foundation"
        d.mkdir(parents=True, exist_ok=True)
        (d / STATE).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        if state.get("catalog_sha"):
            # 版ごとにも残す: 起動の時に別の口がこの入口を回し直すと setup.json は新しい版の記録に替わる。窓の中で
            # 動いている版の記録を、並んで走る起動の hook（plugin core の kaku.py）が版の名で引けるようにする。
            (d / f"setup-{state['catalog_sha']}.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError as e:  # 印が無いと起動の hook が「古い形の setup script」と取り違えるので、書けなかった事を残す
        print(f"✗ 入れた印を書けない（起動の時に古い形と取り違えられる）: {e}", file=sys.stderr)


def refresh(market: str) -> bool:
    """目録の clone を出所の先端へ取り直す。入口そのものが変わったら新しい入口へ移る（戻らない）。"""
    before = Path(__file__).read_bytes()
    r = claude("plugin", "marketplace", "update", market)
    if not (r and r.returncode == 0):
        return False
    try:
        after = Path(__file__).read_bytes()
    except OSError:  # 取り直した出所で入口が消えた・名が変わった: 移る先が無いので今の入口で入れる（名簿は読み直す・揃いは照らす）
        after = before
    if os.environ.get(REEXEC) != "1" and after != before:
        sys.stdout.flush()
        os.execve(sys.executable, [sys.executable, str(Path(__file__).resolve())], dict(os.environ, **{REEXEC: "1"}))
    return True


def main() -> int:
    try:
        market, _ = catalog()
        clone = Path(str(catalog_entry(market).get("installLocation") or ""))
        if not root_is_clone(market) and os.environ.get(FROM_CLONE) != "1" and (clone / "scripts" / "setup_plugins.py").is_file():
            # 入口が目録の clone の外で回った（開発の checkout から呼んだ等）: 名簿も版も clone の物なので clone の入口へ移る
            sys.stdout.flush()
            os.execve(sys.executable, [sys.executable, str(clone / "scripts" / "setup_plugins.py")],
                      dict(os.environ, **{FROM_CLONE: "1"}))
        fresh = refresh(market)
        # setup の時の main の先端は、入れる物を決める取り直しの直後に読む（入れ終わった後に読むと、その間の
        # push で記録が入れた物より新しくなり、正しい setup を「古い物を入れた」と取り違える）。取り直しと読む間に
        # push が入って食い違えば、1 度だけ取り直して揃える。
        at_setup = main_tip(market)
        if fresh and at_setup and at_setup != catalog_head(market):
            fresh = refresh(market)
            at_setup = main_tip(market)
        market, names = catalog()  # 取り直した名簿を読み直す
    except ValueError as e:
        notice(f"土台の plugin を入れられなかった: {e}。核と守りの hook がこの窓で効いていない。最初にオーナーへ知らせる。")
        print(f"✗ {e} {ROOT_CAUSE}")
        return 2
    for n in names:
        claude("plugin", "install", f"{n}@{market}", "--scope", "user")
        claude("plugin", "update", f"{n}@{market}")  # 前の setup で入った古い物を名簿の版へ追いつかせる
    where = listed()
    lack = [n for n in names if f"{n}@{market}" not in where]
    tip, shas = catalog_head(market), installed_shas(market, where)
    stale = [n for n in names if n not in lack and (not tip or shas.get(n) != tip)]
    unknown = [n for n in stale if shas.get(n) is None]
    bad = []
    if not fresh:
        bad.append(f"土台の目録 {market} を出所の先端へ取り直せなかった（claude plugin marketplace update が失敗）。"
                   "前の setup の古い名簿で入れている")
    if lack:
        bad.append(f"土台の plugin が入っていない: {' '.join(lack)}（目録 {market}）")
    if stale:
        bad.append(f"土台の plugin が名簿の版 {(tip or '（分からない）')[:12]} に揃っていない: {' '.join(stale)}")
    if unknown:
        bad.append(f"入った版が分からない（入った台帳に installPath が読まれる dir と同じ行が無い）: {' '.join(unknown)}")
    if bad:
        notice("。".join(bad) + "。その plugin の決まりと守りの hook がこの窓で古いか効いていない。最初にオーナーへ知らせる。")
    else:
        notice(None)
    save_state({"entry": "scripts/setup_plugins.py", "market": market, "plugins": names, "missing": lack,
                "stale": stale, "refreshed": fresh, "catalog_sha": tip, "main_at_setup": at_setup, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    print(("✗ " + "。".join(bad) + "。 " + ROOT_CAUSE) if bad else f"✅ 土台の plugin {len(names)} 本が名簿の版 {tip[:12]} で入った")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
