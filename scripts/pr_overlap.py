#!/usr/bin/env python3
"""開いている他の PR と、同じ file の同じ行の辺りを書き換えていないかを知らせる（止めない・見た時は exit 0）。

意図: 並ぶ PR が同じ節を同時に直す食い違いを、PR を出した時に名指しし、書いた窓どうし（と親の窓）が先に順を決められるようにする。
課題: 並ぶ PR が 細目.md・核.md・CONTRIBUTING.md・各 SKILL.md の同じ節を書き換えると（追記でなく本当の重なり）、
後に入る方が合流の時に初めて衝突に気づき、見直しをやり直していた。
原因: 同じ節を同時に直すのは中身の食い違いなので構造で消せる物でなく、早く知る仕組みが無かった。
重なり: 同じ file で、main の側の行の範囲（差分の塊の @@ -a,b の範囲）が CONTEXT 行の内で触れ合う物。
物差し: PR ごとの差分の行番号は、その PR の分かれ目（merge base）の main の行番号で、違う時期に切った PR どうしでは
  物差しが違う。なので各 PR の範囲を、分かれ目から base の枝の今の先端までの差分で今の先端の行番号へ写してから比べる
  （写す所が書き換えられた行は、書き換えた後の範囲の全部へ広げる＝見落とす側に倒さない）。比べる PR は同じ base の枝の物だけ。
取れない物は「無い」と読まない: 開いた PR・PR の file は頁を全部取る。GitHub が patch を返さない file（バイナリ・大きすぎる差分）は
  file の全部の行を書き換えたと読む（空の差分と読んで重なりを見落とさない）。compare の file が上限 300 に当たった・PR の file が
  上限 3000 に当たった時は、全部を見ていないので exit 3（見ていない）で名指す。

  python3 scripts/pr_overlap.py --repo <owner/name> --pr <番号>      # CI（GITHUB_TOKEN で読むだけ）
  python3 scripts/pr_overlap.py --self <patch の JSON> --others <JSON>  # 試験（{pr: {file: patch}} の形）
  python3 scripts/pr_overlap.py --repo <owner/name> --files <path> ...  # 並べる前・PR を出す前: 触ると宣言した file を
      開いている PR が書き換えているか（file の単位）。重なれば exit 1＝その窓は並べず、重なる PR が入るのを待つ列にする
      （振る舞いの既定「並走」）。開いている PR を読めない時は exit 3（重ならないと言わない）。

今いっしょに進む PR だけと照らす: 開いた PR のうち、STALE_DAYS 日より長く動いていない（updated_at が古い）物は照らさず、
  番号を 1 行で名指すだけにする（閉じ忘れの古い PR が知らせを埋め、本当にぶつかる相手が見えなくなるのを防ぐ。
  黙って捨てない）。updated_at の無い PR は動いていると読む（知らせを落とす側に倒さない）。

exit（--files の外）: 0=見た（重なりの有無は文で知らせる・止めない）/ 3=見ていない（材料が無い・他の PR を読めない）。
  見ていない時を 0 で終えると、知らせを出せなかった job が「重なりは無い」と同じ緑の印に見える。なので 3 で終え、
  GitHub の上では ::warning:: の注記も出す（job は止めない＝ci.yml の job overlap は step を continue-on-error で回す）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

CONTEXT = 3
UNSEEN = 3  # 見ていない（緑に数えない）
WHOLE = (1, 10**9)  # patch の無い file の範囲（全部の行）
COMPARE_FILES_CAP = 300   # compare の応答に載る file の上限（越える分は黙って欠ける）
PR_FILES_CAP = 3000       # PR の file の一覧の上限
PER_PAGE = 100
STALE_DAYS = 14           # これより長く動いていない開いた PR は、今いっしょに進む相手に数えない
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", re.M)


def ranges(patch: str | None) -> list[tuple[int, int]]:
    """差分の塊の古い側の範囲。patch が None（GitHub が返さなかった）は file の全部の行（WHOLE）。"""
    if patch is None:
        return [WHOLE]
    out = []
    for m in HUNK.finditer(patch or ""):
        start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        out.append((start, start + max(n, 1) - 1))
    return out


def _hunks(patch: str) -> list[tuple[int, int, int, int]]:
    """[(古い側の始め, 行数, 新しい側の始め, 行数)]。行数 0 の塊（足しただけ・消しただけ）の始めは、その次の行に直す。"""
    out = []
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", patch or "", re.M):
        os_, ol = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        ns, nl = int(m.group(3)), int(m.group(4) if m.group(4) is not None else 1)
        out.append((os_ if ol else os_ + 1, ol, ns if nl else ns + 1, nl))
    return out


def carry(span: tuple[int, int], patch: str | None) -> tuple[int, int]:
    """分かれ目の行番号の範囲 span を、分かれ目→今の先端の差分 patch で今の先端の行番号へ写す（patch が無ければそのまま）。
    書き換えられた行に掛かる所は、書き換えた後の範囲の全部へ広げる。patch が None（返らなかった）は全部の行へ広げる。"""
    if patch is None:
        return WHOLE
    if not patch:
        return span
    hunks = _hunks(patch)

    def one(x: int) -> tuple[int, int]:
        delta = 0
        for os_, ol, ns, nl in hunks:
            if x < os_:
                break
            if x < os_ + ol:
                return ns, ns + max(nl, 1) - 1
            delta = (ns + nl) - (os_ + ol)
        return x + delta, x + delta

    a, b = one(span[0]), one(span[1])
    return min(a[0], b[0]), max(a[1], b[1])


def overlaps_ranges(mine: dict[str, list[tuple[int, int]]],
                    others: dict[str, dict[str, list[tuple[int, int]]]]) -> list[tuple[str, str, tuple[int, int]]]:
    """同じ物差しの行の範囲どうしで [(他の PR, file, 自分の行の範囲)]。"""
    hits = []
    for pr, files in sorted(others.items()):
        for f, theirs in files.items():
            if f not in mine:
                continue
            for a, b in mine[f]:
                if any(a - CONTEXT <= d and c - CONTEXT <= b for c, d in theirs):
                    hits.append((pr, f, (a, b)))
                    break
    return hits


def overlaps(mine: dict[str, str], others: dict[str, dict[str, str]]) -> list[tuple[str, str, tuple[int, int]]]:
    """同じ分かれ目から切った PR どうし（{file: patch}）で [(他の PR, file, 自分の行の範囲)]（試験の口）。"""
    return overlaps_ranges({f: ranges(p) for f, p in mine.items()},
                           {pr: {f: ranges(p) for f, p in fs.items()} for pr, fs in others.items()})


def on_tip(files: dict[str, str], to_tip: dict[str, str]) -> dict[str, list[tuple[int, int]]]:
    """PR の {file: patch（分かれ目から）} を、今の先端の行番号の {file: [範囲]} へ写す。"""
    return {f: [carry(r, to_tip.get(f, "")) for r in ranges(p)] for f, p in files.items()}


def _get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "Authorization": f"Bearer {token}", "User-Agent": "af-pr-overlap"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_all(url: str, token: str, cap: int | None = None) -> list:
    """一覧の頁を全部取る（per_page=100 で、満ちた頁の次を取り続ける）。cap 件に届いた時は全部を取れていないので OSError。"""
    out: list = []
    page = 1
    sep = "&" if "?" in url else "?"
    while True:
        more = f"&page={page}" if page > 1 else ""      # 1 頁目は頁の印なし（GitHub の既定が 1 頁目）
        got = _get(f"{url}{sep}per_page={PER_PAGE}{more}", token)
        if not isinstance(got, list):
            raise OSError(f"一覧の形でない応答（{url}）")
        out.extend(got)
        if cap is not None and len(out) >= cap:
            raise OSError(f"一覧が上限 {cap} 件に当たり、全部を読めない（{url}）")
        if len(got) < PER_PAGE:
            return out
        page += 1


def _patch(r: dict) -> str | None:
    """file の patch。返らない時、行の変更が 0（中身の変わらない名の付け替え）なら空、そうでなければ None（全部の行）。"""
    p = r.get("patch")
    if p:
        return p
    return "" if not r.get("changes") else None


def compare(repo: str, base: str, head: str, token: str) -> tuple[str, dict[str, str | None]]:
    """(分かれ目の commit, {file: patch（分かれ目から head まで）})。file が上限 300 に当たれば OSError（欠けを見ない）。"""
    c = _get(f"https://api.github.com/repos/{repo}/compare/{base}...{head}", token)
    files = c.get("files") or []
    if len(files) >= COMPARE_FILES_CAP:
        raise OSError(f"{base[:12]}...{head[:12]} の file が上限 {COMPARE_FILES_CAP} に当たり、全部の差分を読めない")
    return c["merge_base_commit"]["sha"], {r["filename"]: _patch(r) for r in files}


def on_base_tip(repo: str, base_tip: str, head: str, token: str, cache: dict) -> dict[str, list[tuple[int, int]]]:
    """PR（先端 head）の範囲を、base の枝の今の先端 base_tip の行番号で。"""
    mb, files = compare(repo, base_tip, head, token)
    if mb != base_tip and mb not in cache:
        cache[mb] = compare(repo, mb, base_tip, token)[1]
    return on_tip(files, cache.get(mb) or {})


def claimed(declared: list[str], others: dict[str, list[str]]) -> list[tuple[str, str]]:
    """触ると宣言した file と、開いている PR の {PR: [file]} が重なる [(PR, file)]（試験の口）。"""
    want = {f.strip().lstrip("./") for f in declared if f.strip()}
    return [(pr, f) for pr, fs in sorted(others.items()) for f in fs if f in want]


def moving(opened: list, now: datetime | None = None) -> tuple[list, list]:
    """(今いっしょに進む PR, STALE_DAYS 日より長く動いていない PR)。updated_at の無い・読めない PR は進む側に入れる。"""
    edge = (now or datetime.now(timezone.utc)) - timedelta(days=STALE_DAYS)
    live, stale = [], []
    for p in opened:
        try:
            when = datetime.fromisoformat((p.get("updated_at") or "").replace("Z", "+00:00"))
        except ValueError:
            when = None
        (stale if when is not None and when < edge else live).append(p)
    return live, stale


def say_stale(stale: list) -> None:
    if stale:
        print(f"pr_overlap: {STALE_DAYS} 日より長く動いていない開いた PR {len(stale)} 本は照らさない（"
              + "・".join(f"#{p['number']}" for p in stale) + "）。閉じ忘れなら閉じる")


def open_files(repo: str, token: str) -> dict[str, list[str]]:
    """今いっしょに進む開いた PR ごとの触った file の名。読めない・多すぎる時は例外（重ならないと言わない）。"""
    out = {}
    live, stale = moving(_get_all(f"https://api.github.com/repos/{repo}/pulls?state=open", token))
    say_stale(stale)
    for p in live:
        files = _get_all(f"https://api.github.com/repos/{repo}/pulls/{p['number']}/files", token, cap=PR_FILES_CAP)
        out[f"#{p['number']} {p['head']['ref']}"] = [f["filename"] for f in files]
    return out


# 重なった時の順（オーナーの答え 2026-11-23「AI が決め、ぶつかる時だけ聞く」）: 順は AI が決め、聞くのはぶつかる時だけ
ORDER = ("順: 先に開いた PR が先に入り、後の PR は入った main を取り込んでから続ける（AI が決める・聞かない）。"
         "オーナーに聞くのは、片方がもう片方の通る条件（試験・レビューの見る点）を変える時と、2 つの意図が逆向きの時だけ")


def main_files(repo: str, declared: list[str]) -> int:
    try:
        others = open_files(repo, os.environ.get("GITHUB_TOKEN") or "")
    except Exception as e:  # noqa: BLE001  読めない時は重ならないと言わない（exit 3）
        return unseen(f"開いている PR を読めない（{e}）")
    hits = claimed(declared, others)
    for pr, f in hits:
        print(f"✗ {pr} が {f} を書き換えている")
    if hits:
        print("pr_overlap: 重なる — 同じ file を取る窓は並べず列にする（重なる PR が入ってから main を取り込んで始める）")
        print(ORDER)
        print("直し: 1 つの file を多くの窓が取り合うなら、意図（窓どうしが互いに待たずに進む）とのずれから入り、分け方の原因を細目 §3「まず構造を疑う」で探す")
        return 1
    print(f"pr_overlap: 重ならない — 宣言した {len(declared)} file を開いている PR {len(others)} 本のどれも書き換えていない")
    return 0


def unseen(why: str) -> int:
    """見ていない事を名指して exit 3（緑の印にしない）。GitHub の上では注記 ::warning:: も出す。"""
    print(f"pr_overlap: 見ていない — {why}（重なる PR が無いとは言えない）")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=pr_overlap 見ていない::{why}（重なる PR が無いとは言えない）")
    return UNSEEN


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--self", dest="self_json")
    ap.add_argument("--others")
    ap.add_argument("--files", nargs="+", help="並べる前に触ると宣言する file（--repo と一緒に）")
    a = ap.parse_args(argv)
    if a.files:
        if not a.repo:
            return unseen("--files は --repo <owner/name> と一緒に渡す")
        return main_files(a.repo, a.files)
    try:
        if a.self_json:
            mine = json.loads(open(a.self_json, encoding="utf-8").read())
            others = json.loads(open(a.others, encoding="utf-8").read())
        else:
            token = os.environ.get("GITHUB_TOKEN") or ""
            if not (a.repo and a.pr and token):
                return unseen("照らす材料（--repo・--pr・GITHUB_TOKEN）が無い")
            me = _get(f"https://api.github.com/repos/{a.repo}/pulls/{a.pr}", token)
            base = me["base"]["ref"]
            tip = _get(f"https://api.github.com/repos/{a.repo}/branches/{base}", token)["commit"]["sha"]
            cache: dict = {}
            mine_r = on_base_tip(a.repo, tip, me["head"]["sha"], token, cache)
            opened, stale = moving(_get_all(f"https://api.github.com/repos/{a.repo}/pulls?state=open", token))
            say_stale(stale)
            others_r = {f"#{p['number']}": on_base_tip(a.repo, tip, p["head"]["sha"], token, cache)
                        for p in opened if p["number"] != a.pr and (p.get("base") or {}).get("ref") == base}
    except Exception as e:  # noqa: BLE001  知らせる道具が壊れても PR は止めない（見ていない事を exit 3 で名指す）
        return unseen(f"他の PR を読めない（{e}）")
    hits = overlaps(mine, others) if a.self_json else overlaps_ranges(mine_r, others_r)
    for pr, f, (s, e) in hits:
        print(f"⚠ {pr} も {f} の {s}〜{e} 行の辺りを書き換えている（同じ節の本当の重なり）")
    if hits:
        print("pr_overlap: 知らせ — 重なる PR の書いた窓へ今知らせる（合流の時に初めて衝突に気づかない）。止めはしない")
        print(ORDER)
    else:
        print("pr_overlap: 重なる PR は無い")
    return 0


if __name__ == "__main__":
    sys.exit(main())
