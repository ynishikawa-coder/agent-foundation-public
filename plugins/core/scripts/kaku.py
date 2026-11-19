#!/usr/bin/env python3
"""核を窓の起動時に差し込む口と、常に読まれる量の上限を照らす口（plugin core の道具はこの 1 本）。

使い方:
  python3 kaku.py inject              SessionStart の hook が呼ぶ。核（同じ plugin の 核.md）と振る舞いの既定
                                      （振る舞い.md）を窓の文脈へいつも差し込み、形の細目（細目.md）の在り処を知らせる。使う側に残った写し・古い形は名指しで知らせる:
                                      開いた repo の古い形（古い形.json の一覧・核の写しの枠など）／CLAUDE.md の量の上限越え／
                                      古い形の setup script（土台の入口 scripts/setup_plugins.py を通っていない）／入っていない plugin。
                                      あわせて、窓の最初の 1 回だけ、入った土台が main の先端と同じかを見て窓ごとに覚える。古ければ、
                                      setup の時の main の先端の記録（setup.json の main_at_setup）と比べて、setup が古い物を入れた
                                      （setup script を直す）か setup の後に main が進んだ（引き継ぐ）かを分ける（記録が無ければ分からないと名指す）。
  python3 kaku.py fresh               UserPromptSubmit の hook が呼ぶ。起動の後に main の先端の plugin が変わったら、
                                      この窓を新しい窓へ引き継いで閉じるよう AI に知らせる（人の作業は止めない）。
  python3 kaku.py check [--claude P]  核と振る舞いの既定が在り、上限の内かを照らす。--claude を渡すと、その CLAUDE.md が各社固有の上限の内で
                                      核の写しの枠を持たないかも照らす。
  python3 kaku.py grow --base REF     増やさない物（guarded() の一覧＝毎回差し込む物と形の細目）が git の REF の時より
                                      増えていないかを照らす。足すなら同じ変更で同じだけ畳む（上限の内で足し続けて満杯にしない）。
  python3 kaku.py olds DIR...         使う側の repo の main（origin の既定の枝）の中身に古い形.json の古い形が残っていないかを照らす
                                      （main を持たない dir は checkout を読む）
                                      （「壊れる（2 段目）」の前に、使う側が移ったのを記録で確かめる口）。
exit: inject と fresh は何が起きても 0（窓の起動も人の作業も止めない）。check・grow・olds は 0=緑 / 1=外れ・増えた / 2=読めない。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
KAKU = PLUGIN / "核.md"
FURUMAI = PLUGIN / "振る舞い.md"
SAIMOKU = PLUGIN / "細目.md"
OLDS = PLUGIN / "古い形.json"
FRAME_BEGIN = "<!-- AF-CORE:BEGIN"
# 越えた時の最後の行（中身は細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: 文を移して量を合わせるだけで済ませず、決まりが増えた原因を細目 §3「まず構造を疑う」で探して畳む"
# 常に読まれる量の上限（バイト・UTF-8）。数はここの 1 か所だけに置く。
LIMITS = {"核": 4800, "振る舞い": 2400, "各社固有": 3000}
MARKET = "agent-foundation"
# 土台の出所（GitHub の repo）。目録 agent-foundation がこの repo から入った時だけ、main の先端と比べ入れ方を照らす
# （同じ名で fork が登録された箱で、fork の main を正と取り違えない）。docs/核の届け方.md の setup script の
# `marketplace add` と同じ（試験が照らす）。
UPSTREAM = "ynishikawa-coder/agent-foundation-public"
# 土台の振る舞いを運ぶ path。ここが変わった時だけ「古い土台」と見る（文書・試験・CI だけの変更では窓を替えない）。
CARRIERS = ("plugins", ".claude-plugin")
FRESH_INTERVAL = 900  # 起動の後に main の先端を見に行く間（秒）。毎回の問いごとに外へ出ない。
# 起動の時の古い形の見張りに使ってよい時間（秒）。越えたら打ち切って名指しする（hook の上限に当たって核の差し込みごと落ちない）。
WATCH_BUDGET = 5


# 読めない時の類（無い・権限・UTF-8 でない中身）を 1 か所で受ける。どの読みもこれで受け、欠けを名指しする。
UNREADABLE = (OSError, UnicodeDecodeError)


def size(text: str) -> int:
    return len(text.encode("utf-8"))


# ── 使う側に残った古い形（写し）を名指しする ──

def olds_table(path: Path = OLDS) -> list[dict]:
    """古い形の一覧。形が違えば ValueError（黙って一部だけ見ない）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("olds") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{path.name} に olds の並びが無い")
    keys = {"id", "what", "files", "pattern", "fix", "example"}
    for r in rows:
        if not isinstance(r, dict) or set(r) != keys or not isinstance(r["files"], list) or not r["files"]:
            raise ValueError(f"{path.name} の行の欄が {sorted(keys)} でない: {r!r}")
        r["re"] = re.compile(r["pattern"])
    return rows


def _tracked(project: Path, specs: list[str]) -> list[Path]:
    """照らす file の全部。数で切らない（切ると残りを照らさず緑を返す）。時間の上限は find_olds_bounded が
    process の外から掛け、越えたら打ち切ったと名指す。"""
    out = _git(str(project), "ls-files", "-z", "--", *specs, timeout=10)
    if out is not None:
        return [project / n for n in out.split("\0") if n]
    return [project / s for s in specs if "*" not in s]  # git でない dir は、名で書いた file だけ見る


def _local_main(project: Path) -> str | None:
    for ref in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master"):
        sha = _git(str(project), "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", timeout=10)
        if sha:
            return sha
    return None


def main_ref(project: Path) -> tuple[str | None, str | None]:
    """開いた repo の main（出所 origin の既定の枝）の今の commit と、それを確かめられなかった時の名指し。
    正本は出所の今の main（手元の refs/remotes/origin/* は fetch しなければ古い・origin/HEAD は既定の枝と限らない）:
    出所へ既定の枝と先端を聞き（ls-remote --symref）、手元に無ければその枝だけを取って来る。
    (sha, None)＝出所の今の main を読んだ / (sha, 名指し)＝出所に出られない・取れず手元の origin の main を読んだ
    （同じかは分からない）/ (None, None)＝git でない・origin が無い（checkout を読む）。"""
    if _git(str(project), "remote", "get-url", "origin", timeout=5) is None:
        return None, None
    local = _local_main(project)
    out = _git(str(project), "ls-remote", "--symref", "origin", "HEAD", timeout=3)
    branch = tip = None
    for line in (out or "").splitlines():
        m = re.fullmatch(r"ref: refs/heads/(\S+)\tHEAD", line)
        if m:
            branch = m.group(1)
        elif line.endswith("\tHEAD") and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", line.split("\t")[0]):
            tip = line.split("\t")[0]
    if not tip:
        note = "出所（origin）に出られず、出所の今の main を確かめられない"
        return local, (f"{note}。読んだのは手元の origin の main {local[:12]}（出所の今の main と同じかは分からない）"
                       if local else note)
    have = lambda: _git(str(project), "cat-file", "-e", f"{tip}^{{commit}}", timeout=5) is not None  # noqa: E731
    if not have() and branch:
        _git(str(project), "fetch", "--quiet", "--no-tags", "origin",
             f"+refs/heads/{branch}:refs/remotes/origin/{branch}", timeout=3)
    if have():
        return tip, None
    note = f"出所の今の main {tip[:12]} を取って来られなかった"
    return local, (f"{note}。読んだのは手元の origin の main {local[:12]}（出所より古い）" if local else note)


def _hits(rows: list[dict], texts) -> list[tuple[dict, str]]:
    """(相対 path, 中身) の並びに古い形の行を当てる（照らし方はこの 1 か所）。"""
    found = []
    for r in rows:
        for rel, text in texts(r):
            if r["re"].search(text):
                found.append((r, rel))
    return found


def _checkout_texts(project: Path):
    def texts(r):
        for f in _tracked(project, r["files"]):
            try:
                if f.is_file() and f.stat().st_size <= 1_000_000:
                    yield str(f.relative_to(project)), f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    return texts


def _tree_texts(project: Path, ref: str, only: set[tuple[str, str]] | None = None):
    """ref の木の中身（checkout でなく git の物を読む）。path の選び方は checkout と同じ pathspec（git が解く）。
    only を渡すと、その (行の id, path) だけを読む。"""
    empty = _git(str(project), "hash-object", "-t", "tree", "/dev/null", timeout=10)

    def texts(r):
        out = _git(str(project), "diff", "--name-only", "-z", "--no-renames", "--diff-filter=A", empty or "", ref,
                   "--", *r["files"], timeout=10)
        if empty is None or out is None:
            raise OSError(f"main（{ref[:12]}）の木を読めない")
        names = [n for n in out.split("\0") if n and "\n" not in n and (only is None or (r["id"], n) in only)]
        if not names:
            return
        try:
            p = subprocess.run(["git", "-C", str(project), "cat-file", "--batch"], capture_output=True, timeout=20,
                               input="".join(f"{ref}:{n}\n" for n in names).encode("utf-8"))
        except (OSError, subprocess.SubprocessError) as e:
            raise OSError(f"main（{ref[:12]}）の中身を読めない: {e}") from None
        buf, i = p.stdout, 0
        for n in names:
            head_end = buf.find(b"\n", i)
            if p.returncode != 0 or head_end < 0:
                raise OSError(f"main（{ref[:12]}）の中身を読めない（{n}）")
            head = buf[i:head_end].split()
            i = head_end + 1
            if len(head) != 3 or not head[2].isdigit():
                continue                       # missing など（中身が続かない）
            n_bytes = int(head[2])
            body = buf[i:i + n_bytes]
            i += n_bytes + 1
            if head[1] == b"blob" and n_bytes <= 1_000_000:
                yield n, body.decode("utf-8", errors="replace")
    return texts


SCAN_KEYS = ("found", "fixed_here", "behind", "added", "unknown")


def olds_scan(project: Path, rows: list[dict] | None = None) -> dict:
    """古い形を照らす。正本は main の中身（窓の作業の枝の checkout は main より古いことがある＝main で直った形を
    「この仕事で消す」と言い切らない）。main を持たない repo（git でない・origin の main が無い）は checkout を読む。
    checkout にだけ残る物は、枝と main の分かれ目の中身で分ける（中身で決める）: 分かれ目に在った＝main で直った
    （behind・枝が main より古い）／無かった＝この枝で足した（added・この仕事で消す）。
    {"ref": main の commit か None, "found": main に残る (行, path), "behind": [...], "added": [...]}。"""
    rows = rows if rows is not None else olds_table()
    ref, note = main_ref(project)
    checkout = _hits(rows, _checkout_texts(project))
    if note:  # 読んだ main が出所の今の main と確かめられない: どれも消す・直ったと言い切らない（分からないと名指す）
        found = _hits(rows, _tree_texts(project, ref)) if ref else []
        seen = {(r["id"], f) for r, f in found}
        return {"ref": ref, "note": note, "found": [], "fixed_here": [], "behind": [], "added": [],
                "unknown": found + [(r, f) for r, f in checkout if (r["id"], f) not in seen]}
    if not ref:
        return {"ref": None, "note": None, "found": checkout, "fixed_here": [], "behind": [], "added": [], "unknown": []}
    found = _hits(rows, _tree_texts(project, ref))
    seen = {(r["id"], f) for r, f in found}
    only = {(r["id"], f) for r, f in checkout} - seen
    base = _git(str(project), "merge-base", "HEAD", ref, timeout=10) if only else None
    was = {(r["id"], f) for r, f in _hits(rows, _tree_texts(project, base, only))} if base else set()
    rest = [(r, f) for r, f in checkout if (r["id"], f) in only]
    if not base:  # 分かれ目が読めない（浅い clone 等）: main で直ったともこの枝で足したとも言い切らない
        return {"ref": ref, "note": None, "found": found, "fixed_here": [(r, f) for r, f in found if (r["id"], f) not in
                                                                         {(x["id"], y) for x, y in checkout}],
                "behind": [], "added": [], "unknown": rest}
    return {"ref": ref, "note": None, "found": found, "fixed_here": [(r, f) for r, f in found if (r["id"], f) not in
                                                       {(x["id"], y) for x, y in checkout}],
            "behind": [x for x in rest if (x[0]["id"], x[1]) in was],
            "added": [x for x in rest if (x[0]["id"], x[1]) not in was], "unknown": []}


def find_olds(project: Path, rows: list[dict] | None = None) -> list[tuple[dict, str]]:
    """開いた repo に残る古い形の (行, 当たった file の相対 path)。読むのは main の中身（無ければ checkout）。"""
    return olds_scan(project, rows)["found"]


def find_olds_bounded(project: Path, budget: float = WATCH_BUDGET, table: Path = OLDS) -> dict:
    """olds_scan を別の process で走らせ、budget 秒で殺す。1 つの file の正規表現の照らしは途中で止められないので、
    時間の上限は file の合間でなく process の外から掛ける。越えたら TimeoutError（黙って一部だけにしない）。"""
    cmd = [sys.executable, str(Path(__file__).resolve()), "olds", "--json", "--table", str(table), str(project)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=budget)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"{budget} 秒で見終わらず打ち切った（古い形の照らしの途中）") from None
    if p.returncode not in (0, 1):
        raise ValueError((p.stdout + p.stderr).strip() or f"olds が {p.returncode} で抜けた")
    rows = {r["id"]: r for r in olds_table(table)}
    got = json.loads(p.stdout)
    return {"ref": got["ref"], "note": got.get("note"), **{k: [(rows[i], f) for i, f in got.get(k) or []] for k in SCAN_KEYS}}


def olds_text(scan: dict, project: Path) -> str | None:
    ref = scan["ref"]
    fixed = {(r["id"], f) for r, f in scan.get("fixed_here") or []}
    remove = [(r, f, "（この枝では消えている＝枝を main へ入れれば済む）" if (r["id"], f) in fixed else "")
              for r, f in scan["found"]] + [(r, f, "（この枝で足した）") for r, f in scan.get("added") or []]
    lines = []
    if remove:
        src = f"main（{ref[:12]}）の中身" if ref else "checkout"
        lines += [f"## この repo（{project.name}）に土台の古い形（写し）が残っている — この仕事で消す\n",
                  f"読んだ物: {src}。写しは土台が変わっても古いまま残り、誰も止めない。土台を直した同じ仕事で使う側も直す決まり（オーナー決定 2026-11-19）なので、"
                  "この repo の手順（CONTRIBUTING・CLAUDE.md）で 1 枝 1 PR を出して消す。頼みの仕事が別なら、その仕事を止めずに並べて出す:\n"]
        lines += [f"- {f}: {r['what']} → {r['fix']}{note}\n" for r, f, note in remove]
    if scan.get("behind"):
        lines += [f"## この repo（{project.name}）の作業の枝は main より古い — 古い形は main では直っている\n",
                  f"次は checkout には残るが main（{ref[:12]}）で直った（消す仕事は要らない。枝を main に追いつかせれば消える）: "
                  + "・".join(f"{f}（{r['id']}）" for r, f in scan["behind"]) + "\n"]
    if scan.get("note") and scan.get("unknown"):
        lines += [f"## この repo（{project.name}）の古い形が今の main に残るかが分からない — 照らした main を出所の今の main と確かめられない\n",
                  f"{scan['note']}。次は手元の main か checkout に在る。消すか（main に残る）・直った（main で消えた）かを言い切れないので、"
                  "`git fetch origin` の後に土台の kaku.py olds でこの repo を照らし直して決める: "
                  + "・".join(f"{f}（{r['id']}）" for r, f in scan["unknown"]) + "\n"]
    elif scan.get("unknown"):
        lines += [f"## この repo（{project.name}）の作業の枝にだけ古い形が在る — main で直ったか、この枝で足したかが分からない\n",
                  f"次は checkout には在るが main（{ref[:12]}）には無い。枝と main の分かれ目が読めない（浅い clone など）ので、"
                  "main で直った物（枝を main に追いつかせれば消える）か、この枝で足した物（この仕事で消す）かを言い切れない。"
                  "`git fetch --unshallow`（または `--deepen`）で分かれ目を取ってから見分ける: "
                  + "・".join(f"{f}（{r['id']}）" for r, f in scan["unknown"]) + "\n"]
    return "".join(lines) or None


def claude_md_text(project: Path) -> str | None:
    """開いた repo の根の CLAUDE.md が各社固有の上限を越えていれば知らせる文。"""
    try:
        n = size((project / "CLAUDE.md").read_text(encoding="utf-8"))
    except UNREADABLE:
        return None
    if n <= LIMITS["各社固有"]:
        return None
    return (f"## この repo の CLAUDE.md が常に読まれる量の上限を越えている\n"
            f"{n} > {LIMITS['各社固有']} バイト（数は土台の plugin core の LIMITS の 1 か所・写さない）。"
            "その repo に固有の決まりだけを残し、細かい手順はその repo の文書へ移して指す 1 行にする。\n")


LOCAL_SOURCES = ("directory", "file")  # 手元の dir・file から入れた試し・CI（使う側の setup script を持たず main と比べない）


def source_ref(m: dict) -> str:
    """目録が追う出所の枝（known_marketplaces の source の ref＝`marketplace add <repo>#<枝>`。無ければ main）。
    枝で入れた窓（plugin-smoke の試し）は、その枝の先端と比べる（いつも main と比べて「setup が古い物を入れた」と取り違えない）。"""
    src = m.get("source") if isinstance(m.get("source"), dict) else {}
    ref = str(src.get("ref") or "").strip()
    return ref or "main"


def source_tip(loc: str, ref: str) -> str | None:
    """出所（origin）の枝 ref の今の先端を出所へ直に聞く（共用の FETCH_HEAD や手元の ref を読まない）。
    枝が無い（版の tag で止めた目録など）時は出所の main と比べる（止めた版を「古くない」と見ない）。聞けなければ None。"""
    for name in dict.fromkeys((ref, "main")):
        out = _git(loc, "ls-remote", "--quiet", "origin", f"refs/heads/{name}") or ""
        sha = out.split()[0] if out.split() else ""
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
            return sha
    return None


def catalog_source() -> tuple[dict, str | None]:
    """目録 agent-foundation の登録（known_marketplaces.json の行）と、土台の出所でない時の名指し。
    ({}, None)＝目録が無い・手元から入れた（照らさない）/ (行, None)＝土台の repo の GitHub から入った /
    ({}, 名指し)＝別の出所（fork・別の git）から入った＝その main を正と見ない。"""
    m = (_read_json(_home() / "plugins" / "known_marketplaces.json") or {}).get(MARKET) or {}
    src = m.get("source") if isinstance(m.get("source"), dict) else {}
    if not m.get("installLocation") or src.get("source") in LOCAL_SOURCES or not src:
        return {}, None
    where = src.get("repo") or src.get("url") or src.get("source")
    if src.get("source") != "github" or str(src.get("repo") or "").lower() != UPSTREAM.lower():
        return {}, (f"- 土台の目録 {MARKET} が土台の repo {UPSTREAM} でない出所（{where}）から入っている（同じ名の fork・別の git）。"
                    "その出所の main を正として古さ・入れ損ねを照らさない＝この窓の核と守りが土台の今の物か分からない。"
                    "最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形（土台の repo を足す）に直す。\n")
    return m, None


def _when(text) -> float | None:
    """ISO 8601 の時（Z・+0900 の形）を秒に。読めなければ None。"""
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def user_rows(table: dict | None = None, market: str = MARKET) -> dict[str, list[dict]]:
    """{plugin の名: 入った台帳の user scope の行の並び}（目録 market の物だけ）。scope の欄が user と書かれた行だけを
    数える（欄の無い行を user と見ない）。台帳を読む所（新しさ・入れ方・写しの見張り・plugin-smoke）はこの 1 つを通す。"""
    if table is None:
        table = _read_json(_home() / "plugins" / "installed_plugins.json") or {}
    plugins = table.get("plugins") if isinstance(table, dict) else None
    out = {}
    for key, rows in plugins.items() if isinstance(plugins, dict) else []:
        name, at, m = str(key).rpartition("@")
        user = [r for r in rows if isinstance(r, dict) and r.get("scope") == "user"] if isinstance(rows, list) else []
        if at and m == market and user:
            out[name] = user
    return out


def current_row(rows: list[dict]) -> dict | None:
    """user scope の行が複数の時に、今読まれる 1 つ: dir が在る行のうち最後に入れた（lastUpdated の新しい）行。
    最初の行・dir の無い行（消えた前の版）を取らない。在る行が無ければ None（＝分からない）。"""
    live = [r for r in rows if r.get("installPath") and Path(str(r["installPath"])).is_dir()]
    return max(live, key=lambda r: _when(r.get("lastUpdated")) or 0.0, default=None)


def _foundation_rows() -> dict[str, dict]:
    """{plugin の名: 入った台帳の今読まれる user scope の行}（土台の目録の物だけ・current_row で 1 つに決めた物）。"""
    out = {}
    for name, rows in user_rows().items():
        row = current_row(rows)
        if row is not None:
            out[name] = row
    return out


def setup_record() -> tuple[dict | None, str | None]:
    """今の土台を入れた setup が入口 scripts/setup_plugins.py で書いた記録（setup.json）と、そう確かめられない訳。
    file が在るだけでは今回の記録と見ない: 記録の名簿の版（catalog_sha）が入った plugin core の commit と同じで、
    記録の時（at）が土台の plugin を入れ直した時（台帳の lastUpdated）より前でない時だけ今回の物（前の setup の記録が
    残った容器で、入口を通らない古い形の setup script が入れ直したのを見逃さない）。"""
    state = _read_json(_home() / "af-foundation" / "setup.json")
    if not isinstance(state, dict):
        return None, "入口の記録（~/.claude/af-foundation/setup.json）が無い"
    have = installed_sha()
    if not have or state.get("catalog_sha") != have:
        return None, (f"入口の記録の名簿の版 {str(state.get('catalog_sha'))[:12]} が入った土台 {str(have)[:12]} と違う"
                      "（前の setup の記録が残っている）")
    at = _when(state.get("at"))
    # 入れ直した時は user scope の全部の行で見る（古い行の lastUpdated で、記録の後の入れ直しを見逃さない）
    later = [t for rows in user_rows().values() for t in (_when(r.get("lastUpdated")) for r in rows) if t is not None]
    if at is None or (later and max(later) > at + 2):
        return None, "入口の記録の時が土台の plugin を入れ直した時より前（記録の後に入口を通らずに入れ直した）"
    return state, None


def _enabled() -> set[str]:
    """user scope で enabled の plugin（~/.claude/settings.json の enabledPlugins。入口の listed() と同じ見方）。"""
    on = (_read_json(_home() / "settings.json") or {}).get("enabledPlugins") or {}
    return {k for k, v in on.items() if v is True} if isinstance(on, dict) else set()


def setup_text() -> str | None:
    """GitHub から土台を入れた窓で、古い形の setup script（入口を通っていない）・入っていない plugin・土台でない出所を知らせる文。"""
    m, other = catalog_source()
    if other:
        return "## 土台の入れ方が古い・欠けている\n" + other
    if not m:
        return None
    parts = []
    if installed_sha() is None:  # 別の dir の行の版で古さを決めない＝分からない事をそのまま名指す
        parts.append(f"- この窓に入った plugin core の版が分からない（入った台帳 installed_plugins.json に installPath が"
                     f"この plugin の dir {PLUGIN} と同じ行が無い）。土台の古さを照らしていない＝核と守りが土台の今の物か分からない。"
                     "最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形に直す。\n")
    state, why = setup_record()
    if state is None:
        parts.append(f"- 環境の setup script が古い形（今の土台を入れた setup が土台の入口 scripts/setup_plugins.py を通っていない: {why}）。"
                     "土台が plugin を足しても入らず、入れ損ねの見張りにも入らない。土台の docs/核の届け方.md の形に貼り替える"
                     "（Javis の環境は get_environment → update_environment。直せない環境は親の窓・連絡板へ頼み、オーナーへ 1 行知らせる）。\n")
    # 名簿は setup が入れた版（入った core の commit）の物を読む（目録の clone の今の作業の木は setup の後に進みうる）
    want = catalog_at(m["installLocation"], installed_sha())
    have, on = set(_foundation_rows()), _enabled()
    lack = [p.get("name") for p in (want or {}).get("plugins") or []
            if isinstance(p, dict) and (p.get("name") not in have or f"{p.get('name')}@{MARKET}" not in on)]
    if want is None:
        parts.append("- 入った版の土台の名簿（.claude-plugin/marketplace.json）が目録の clone から読めず、入っていない plugin を照らしていない。"
                     "最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形に直す。\n")
    if lack:
        parts.append(f"- 土台の plugin が user scope で入って enabled になっていない: {' '.join(map(str, lack))}。その plugin の決まりと守りの hook がこの窓で効いていない。"
                     "最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形に直す。\n")
    state = state or {}
    if state.get("refreshed") is False or state.get("stale"):
        parts.append(f"- 土台の目録を先端へ取り直せず、または名簿の版に揃わずに入った（揃わない plugin: {' '.join(map(str, state.get('stale') or [])) or 'なし'}）。"
                     "古い決まりと守りの hook で動いている。最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形に直す。\n")
    return ("## 土台の入れ方が古い・欠けている\n" + "".join(parts)) if parts else None


def catalog_at(loc: str, sha: str | None) -> dict | None:
    """目録の clone の、commit sha の時の名簿（.claude-plugin/marketplace.json）。読めなければ None。"""
    if not sha:
        return None
    text = _git(loc, "show", f"{sha}:.claude-plugin/marketplace.json")
    try:
        data = json.loads(text) if text else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def injected() -> tuple[Path, ...]:
    """毎回差し込む物の一覧（差し込む inject と増え方を照らす grow が同じこの 1 つを読む）。頭の核は欠けたら差し込まない。"""
    return (KAKU, FURUMAI)


def guarded() -> tuple[Path, ...]:
    """増やさない物の一覧＝毎回差し込む物と、核から押し出した物の行き先の細目（細目だけ照らさないと押し出した物がそこで膨らむ）。"""
    return (*injected(), SAIMOKU)


def inject_text() -> str:
    head, *rest = injected()
    parts = [head.read_text(encoding="utf-8").rstrip("\n")]
    for path in rest:
        try:
            parts.append(path.read_text(encoding="utf-8").rstrip("\n"))
        except UNREADABLE as e:
            # 欠けたまま黙って核だけにしない: 窓の起動は止めず、欠けた事を文脈に名指しで出す
            print(f"plugin core: {path.name} が読めない（{e}）", file=sys.stderr)
            parts.append(f"（毎回差し込む {path} が読めず、差し込まれていない。最初にオーナーへ知らせる）")
    return ("\n\n".join(parts) + "\n\n"
            + "（この核と振る舞いの既定は土台の plugin core が起動時に差し込んだ。"
            + f"返事・問い・手の窓などの形の細目は {SAIMOKU} の同じ番号の節。その形を書く時に Read する）\n")


# ── 土台の新しさ（入っている物と main の先端を比べる） ──

def _home() -> Path:
    return Path(os.environ.get("HOME") or "~").expanduser() / ".claude"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _git(loc: str, *args: str, timeout: int = 20) -> str | None:
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=off", "-C", loc, *args], capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))  # 鍵を問う画面で止まらない
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def installed_sha() -> str | None:
    """この窓に入った plugin core の commit（入れた時に Claude Code が書く台帳から）。

    読むのは installPath がこの plugin の dir（今動いている kaku.py の在り処）と同じ行だけ。合う行が無ければ None
    （＝分からない）。行が 1 つでも別の dir（project scope で入った・前に別の所へ入った）の行の版で古さを決めない。"""
    table = _read_json(_home() / "plugins" / "installed_plugins.json") or {}
    rows = (table.get("plugins") or {}).get(f"core@{MARKET}") or []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("installPath") and Path(row["installPath"]).resolve() == PLUGIN:
            return row.get("gitCommitSha") or None
    return None


def _carrier_names(names: str) -> set[str]:
    return {n.split("/")[1] if n.startswith("plugins/") and n.count("/") >= 2 else n.split("/")[0]
            for n in names.splitlines() if n}


def freshness() -> dict | None:
    """{installed, main, ref, shas, plugins}（plugins が空でなければ古い）。比べられない時は None。

    GitHub から入れた時だけ見る（手元の dir から入れた試し・CI は main の先端と比べる物が無い）。
    先端は、目録が追う枝（source_ref・ふつうは main）の今の先端を出所へ直に聞き（共用の FETCH_HEAD を読まない）、
    その commit を入れた時の marketplace の clone へ取って来て比べる（鍵は要らない・public）。
    古さは plugin ごとに、その plugin の入った版と先端を比べる（core の版 1 つで全部の plugin の古さを決めない
    ＝core だけ先端に揃い guard の入れ直しが失敗した窓を「古くない」と見ない）。core の版からは
    plugins/・.claude-plugin/ の全部を見る（足された・消えた plugin も拾う）。"""
    m, _ = catalog_source()  # 土台の repo の GitHub から入った時だけ（fork の main を正と見ない）
    loc = m.get("installLocation")
    if not loc:
        return None
    have = installed_sha()
    ref = source_ref(m)
    tip = source_tip(loc, ref) if have else None
    if not tip:
        return None
    if _git(loc, "cat-file", "-e", f"{tip}^{{commit}}") is None:
        _git(loc, "fetch", "--quiet", "--depth=1", "origin", tip)
        if _git(loc, "cat-file", "-e", f"{tip}^{{commit}}") is None:
            return None
    shas = {name: str(row.get("gitCommitSha") or "") or None for name, row in _foundation_rows().items()}
    shas["core"] = have  # core は今動いている dir の行（installed_sha）の版
    plugins: set[str] = set()
    for name, sha in sorted(shas.items()):
        if sha == tip:
            continue
        if not sha:
            plugins.add(name)  # 版が分からない plugin は古い側に数える（既定で知らせる側）
            continue
        paths = CARRIERS if name == "core" else (f"plugins/{name}", ".claude-plugin")
        names = _git(loc, "diff", "--name-only", sha, tip, "--", *paths)
        if names is None:  # 入った commit が clone に無い＝比べられないが先端とは違う。古いと見る（既定で知らせる側）
            plugins.add("（どれか分からない）" if name == "core" else name)
        elif name == "core":
            plugins |= _carrier_names(names)
        elif names:
            plugins.add(name)
    return {"installed": have, "main": tip, "ref": ref, "shas": shas, "plugins": sorted(plugins)}


def _state_path(session: str) -> Path:
    safe = "".join(c for c in session if c.isalnum() or c in "-_") or "unknown"
    return _home() / "af-foundation" / f"{safe}.json"


def _save_state(session: str, state: dict) -> None:
    try:
        path = _state_path(session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _hook_input() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _short(f: dict) -> str:
    ref = f.get("ref") or "main"
    return f"入った土台 {f['installed'][:12]}・{ref} の先端 {f['main'][:12]}・変わった plugin: {'・'.join(f['plugins'])}"


def start_cause(f: dict | None) -> str | None:
    """起動の時に入った土台が古い訳。比べる正本は setup の時の main の先端（入口 scripts/setup_plugins.py が
    setup.json の main_at_setup に書く記録）で、hook の時の main ではない（setup の後に main が進んだだけの窓を
    「setup script を直せ」と取り違えない）。
    None＝古くない・比べられない / "setup"＝setup が main の先端と違う物を入れた / "after"＝setup は main の先端を
    入れ、その後に main が進んだ / "unknown"＝setup の時の main の記録が無く見分けられない。"""
    if not f or not f["plugins"]:
        return None
    rec = (setup_record()[0] or {}).get("main_at_setup")  # 今回の setup の記録だけを読む（前の記録の残りを読まない）
    if not isinstance(rec, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", rec):
        return "unknown"
    # 全部の plugin が setup の時の先端で入っていれば、その後に先端が進んだだけ（1 つでも違えば setup が古い物を入れた）
    shas = f.get("shas") or {"core": f["installed"]}
    return "after" if all(sha == rec for sha in shas.values()) else "setup"


def stale_at_start_text(f: dict) -> str:
    rec = (setup_record()[0] or {}).get("main_at_setup") or ""
    return ("## 土台が古いまま立った窓 — setup script を直してから引き継いで閉じる\n"
            f"この窓は main の先端より古い土台で立った（{_short(f)}）。setup の時の main の先端は {rec[:12]} で、setup はそれと違う物を入れた。"
            "setup script が版（tag）を指している・目録を取り直さない古い形（marketplace update の行が無い）・入れ損ねている"
            "ので、直さずに立て直しても同じ物が入る。この返事では頼みに手を付けず次をする（人の作業は新しい窓で止まらず続く・🙋 の窓も同じ）:\n"
            "1. 環境の setup script を土台の docs/核の届け方.md の形（main の先端を入れる）に直す: "
            "claude-code-remote の get_environment → update_environment（直せる環境の時）。\n"
            "2. 直せた時は、手の中の変更を push し、create_session で同じ repo・同じ環境に新しい窓を立てて引き継ぎ文"
            "（元の頼み・済んだ事・枝と PR・未決・次の 1 手・窓の題と「古い土台の窓からの引き継ぎ」の 1 行）を渡し、"
            "人と親の窓へ新しい窓の URL を返し、archive_session で自分の窓を閉じる。\n"
            "3. 直せない時（他のアカウントの環境・道具が無い・この窓自身が「古い土台の窓からの引き継ぎ」で立った）は引き継がず、"
            "UTC の環境なら連絡板の issue で setup script の直しを頼み、オーナーへ「核と守りが古い形で動いている」と 1 行知らせてから頼みを続ける。\n")


def unknown_at_start_text(f: dict) -> str:
    return ("## 土台が古いまま立った窓 — 起動の時から古いか、setup の後に main が進んだかが分からない\n"
            f"この窓は main の先端より古い土台で立った（{_short(f)}）。setup の時に入れた main の先端の記録"
            "（土台の入口 scripts/setup_plugins.py が ~/.claude/af-foundation/setup.json の main_at_setup に書く）が無いので、"
            "setup script が古い物を入れたのか、setup の後に main が進んだだけなのかを見分けられない"
            "（記録が無いのは、setup script が入口を通らない古い形か、入口が記録を書く前の版で入れた時）。この返事では頼みに手を付けず次をする:\n"
            "1. claude-code-remote の get_environment で setup script を読み、土台の docs/核の届け方.md の形（目録の取り直しと入口）と照らす。"
            "違えば update_environment で直す（直せない環境は親の窓・連絡板へ頼み、オーナーへ 1 行知らせて頼みを続ける）。\n"
            "2. 形が正しかった・直せた時は、手の中の変更を push し、create_session で同じ repo・同じ環境に新しい窓を立てて引き継ぎ文"
            "（元の頼み・済んだ事・枝と PR・未決・次の 1 手・窓の題と「古い土台の窓からの引き継ぎ」の 1 行）を渡し、"
            "人と親の窓へ新しい窓の URL を返し、archive_session で自分の窓を閉じる。"
            "この窓自身が「古い土台の窓からの引き継ぎ」で立った時は引き継がず、オーナーへ 1 行知らせて頼みを続ける。\n")


def handover_text(f: dict) -> str:
    return ("## 土台が新しくなった — この窓を引き継いで閉じる\n"
            f"この窓が立った後に、土台の main の先端で窓の振る舞いが変わった（{_short(f)}）。"
            "この窓は古い核と守りで動いているので、この返事では頼みに手を付けず次をする（人の作業は新しい窓で止まらず続く・🙋 の窓も同じ）:\n"
            "1. 手の中の変更を枝へ commit・push する。\n"
            "2. claude-code-remote の create_session で、同じ repo・同じ環境に新しい窓を立てる。prompt は引き継ぎ文: "
            "元の頼み（オーナーの原文）・ここまでに済んだ事・枝と PR・未決の問い・次の 1 手・窓の題と、「古い土台の窓からの引き継ぎ」の 1 行。\n"
            "3. 人へ 1 行で新しい窓の URL を返す。親の窓がある時は親へも send_message で URL を知らせる。\n"
            "4. archive_session で自分の窓を閉じる。\n"
            "窓を立てる道具が無い時（手元の CLI 等）は、人へ「土台が新しくなった・新しい窓で続けてほしい」と 1 行知らせてから頼みを続ける。\n")


def inject() -> int:
    data = _hook_input()
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    parts = []
    try:  # 核はいつも正本を差し込む（使う側の写しの枠が在っても、写しでなく正本が効く）
        parts.append(inject_text())
    except UNREADABLE as e:
        print(f"plugin core: 核.md が読めない（{e}）＝核は差し込まれていない", file=sys.stderr)
    for name, make in (("古い形", lambda: olds_text(find_olds_bounded(project), project)),
                       ("CLAUDE.md の量", lambda: claude_md_text(project)), ("入れ方", setup_text)):
        try:
            t = make()
        except Exception as e:  # noqa: BLE001  見張りが壊れても核の差し込みは止めない。壊れた事は名指しする
            t = f"## 土台の見張り（{name}）が動かなかった\n{type(e).__name__}: {e}。土台の plugin core の不具合として親の窓へ知らせる。\n"
        if t:
            parts.append(t)
    session = data.get("session_id")
    state = _read_json(_state_path(session)) if session else None
    if isinstance(state, dict):
        # 同じ窓の 2 回目（文脈の圧縮・/clear・resume）: 起動の時の記録を書き直さない（途中で古くなった窓を
        # 「起動の時から古い」と取り違えて引き継ぎを消さない）。外へも見に行かない。
        f = state.get("start") if state.get("stale_at_start") else None
        cause = state.get("cause") or "setup"
    else:
        try:
            f = freshness()
            cause = start_cause(f)
        except Exception:  # noqa: BLE001  新しさの見張りが壊れても核の差し込みは止めない
            f, cause = None, None
        if session:
            # setup の後に main が進んだだけ（after）は「起動の時から古い」でなく、起動の後に古くなった窓と同じ
            # 引き継ぎ（fresh が問いのたびに知らせる）。setup script を直させない。
            state = {"checked": time.time(), "stale_at_start": cause in ("setup", "unknown"), "cause": cause,
                     "comparable": f is not None, "start": f}
            if cause == "after":
                state["seen"] = f
            _save_state(session, state)
    if f and f["plugins"] and cause in ("setup", "unknown"):
        parts.append(stale_at_start_text(f) if cause == "setup" else unknown_at_start_text(f))
    if parts:
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(parts)}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


def fresh() -> int:
    """起動の後に土台が新しくなったかを見る。新しくなっていれば、引き継いで閉じる手順を AI に知らせる。

    起動の時から古かった窓（setup script が古い物を入れた）はここでは扱わない（inject の知らせが setup script を直してから引き継がせる）。"""
    data = _hook_input()
    session = data.get("session_id")
    if not session:
        return 0
    path = _state_path(session)
    state = _read_json(path)
    if not isinstance(state, dict) or state.get("stale_at_start") or not state.get("comparable"):
        return 0
    f = state.get("seen")
    if not f:
        interval = float(os.environ.get("AF_FRESH_INTERVAL") or FRESH_INTERVAL)
        if time.time() - float(state.get("checked") or 0) < interval:
            return 0
        try:
            got = freshness()
        except Exception:  # noqa: BLE001
            got = None
        state["checked"] = time.time()
        if got and got["plugins"]:
            state["seen"] = f = got
        _save_state(session, state)
    if f:  # 一度見つけたら、引き継ぐまで問いのたびに知らせる（外へは出ない）
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": handover_text(f)}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


def check(claude: Path | None) -> int:
    bad = []
    try:
        n = size(KAKU.read_text(encoding="utf-8"))
    except UNREADABLE as e:
        print(f"✗ 核.md が読めない: {e}")
        return 2
    if n > LIMITS["核"]:
        bad.append(f"核（{KAKU.name}）が上限を越えた: {n} > {LIMITS['核']} バイト（細目へ移す）")
    try:
        f = size(FURUMAI.read_text(encoding="utf-8"))
    except UNREADABLE as e:
        print(f"✗ 振る舞い.md が読めない: {e}")
        return 2
    if f > LIMITS["振る舞い"]:
        bad.append(f"振る舞いの既定（{FURUMAI.name}）が上限を越えた: {f} > {LIMITS['振る舞い']} バイト（癖と逆を求めない物を細目へ移す）")
    if claude is not None:
        try:
            text = claude.read_text(encoding="utf-8")
        except UNREADABLE as e:
            print(f"✗ {claude} が読めない: {e}")
            return 2
        m = size(text)
        if FRAME_BEGIN in text:
            bad.append(f"{claude} に核の写しの枠が残っている（枠を中身ごと消す・核は plugin core が差し込む）")
        if m > LIMITS["各社固有"]:
            bad.append(f"各社固有（{claude}）が上限を越えた: {m} > {LIMITS['各社固有']} バイト（その repo の文書へ移す）")
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(ROOT_CAUSE)
        return 1
    print("✅ 量の上限 緑")
    return 0


# 増やさない物（guarded＝毎回差し込む物と細目）。足す時は同じ変更で同じだけ畳む（上限の内でも純増は赤）。
GROW_FIX = "直し: 足すなら同じ変更で同じだけ畳む（重複を細目・skill の正本へ寄せる）。量を合わせるだけで済ませず、細目 §3「まず構造を疑う」で増えた原因から畳む"


def base_text(ref: str, path: Path) -> str:
    """git の ref の時の中身。読めない（ref が無い・その時に file が無い）時は OSError で止める。"""
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path.parent, capture_output=True, text=True)
    if top.returncode != 0:
        raise OSError(f"git の外: {top.stderr.strip()}")
    rel = path.resolve().relative_to(Path(top.stdout.strip()).resolve()).as_posix()
    r = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=path.parent, capture_output=True)
    if r.returncode != 0:
        raise OSError(f"{ref}:{rel} が読めない: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout.decode("utf-8")


def grow(ref: str) -> int:
    bad = []
    for path in guarded():
        try:
            now = size(path.read_text(encoding="utf-8"))
            before = size(base_text(ref, path))
        except UNREADABLE as e:
            # 比べる元が無い時に黙って緑にしない（既定で止める）
            print(f"✗ {path.name} の増え方を照らせない: {e}")
            return 2
        if now > before:
            bad.append(f"{path.name} が {ref} より増えた: {before} → {now} バイト（+{now - before}）")
        else:
            print(f"・{path.name}: {before} → {now} バイト")
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(GROW_FIX)
        return 1
    print("✅ 毎回差し込む物と細目は増えていない")
    return 0


def olds(dirs: list[Path], table: Path = OLDS, as_json: bool = False) -> int:
    try:
        rows = olds_table(table)
    except (OSError, ValueError) as e:
        print(f"✗ {table.name} が読めない: {e}")
        return 2
    bad = 0
    for d in (x.resolve() for x in dirs):
        if not d.is_dir():
            print(f"✗ {d} が無い")
            return 2
        try:
            scan = olds_scan(d, rows)
        except OSError as e:
            print(f"✗ {d.name}: {e}")
            return 2
        found = scan["found"]
        if as_json:
            print(json.dumps({"ref": scan["ref"], "note": scan.get("note"), **{k: [[r["id"], f] for r, f in scan[k]] for k in SCAN_KEYS}},
                             ensure_ascii=False))
            bad += len(found)
            continue
        src = f"main {scan['ref'][:12]} の中身" if scan["ref"] else "checkout"
        if scan.get("note"):  # 出所の今の main を読めていない: 0 とも言い切らない（照らせない）
            held = "・".join(f"{f}（{r['id']}）" for r, f in scan["unknown"])
            print(f"✗ {d.name}: 照らせない — {scan['note']}（手元の main か checkout に在る形: "
                  f"{held or 'なし'}）")
            return 2
        for r, f in found:
            print(f"✗ {d.name}/{f}: {r['id']}（{r['what']}・読んだ物: {src}）")
        if not found:
            print(f"✅ {d.name}: 古い形 0（読んだ物: {src}・見た形: {'・'.join(r['id'] for r in rows)}）")
        bad += len(found)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="核の差し込みと量の上限の照らし")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inject", help="SessionStart の hook から呼ぶ")
    sub.add_parser("fresh", help="UserPromptSubmit の hook から呼ぶ")
    c = sub.add_parser("check", help="量の上限を照らす")
    c.add_argument("--claude", type=Path, help="照らす repo の根の CLAUDE.md")
    g = sub.add_parser("grow", help="毎回差し込む物と細目が REF より増えていないかを照らす")
    g.add_argument("--base", required=True, help="比べる元の git の ref（例: main との分かれ目）")
    o = sub.add_parser("olds", help="使う側の checkout に古い形が残っていないかを照らす")
    o.add_argument("dirs", type=Path, nargs="+")
    o.add_argument("--table", type=Path, default=OLDS, help="古い形の一覧（既定は plugin の 古い形.json）")
    o.add_argument("--json", action="store_true", help="当たりを [[id, path], …] で出す（起動の hook が別の process で呼ぶ）")
    a = ap.parse_args(argv)
    if a.cmd == "inject":
        return inject()
    if a.cmd == "grow":
        return grow(a.base)
    if a.cmd == "fresh":
        return fresh()
    if a.cmd == "olds":
        return olds(a.dirs, a.table, a.json)
    return check(a.claude)


if __name__ == "__main__":
    sys.exit(main())
