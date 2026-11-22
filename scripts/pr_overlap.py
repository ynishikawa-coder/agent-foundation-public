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
読めない物を「無い」に畳まない: GitHub が patch を付けない file（バイナリ・大きすぎる差分・名の変更だけ）は、行が分からない＝
  file の全部を書き換えた物と見て名指す（空の差分と見て重ならないと言わない）。開いている PR の一覧と PR の file の一覧は
  頁を全部辿って読み（1 頁目だけで切らない）、GitHub が全部を返さない量（compare の 300 file 等）に届いたら見ていないと言う。

  python3 scripts/pr_overlap.py --repo <owner/name> --pr <番号>      # CI（GITHUB_TOKEN で読むだけ）
  python3 scripts/pr_overlap.py --self <patch の JSON> --others <JSON>  # 試験（{pr: {file: patch}} の形）
  python3 scripts/pr_overlap.py --repo <owner/name> --files <path> ...  # 並べる前・PR を出す前: 触ると宣言した file を
      開いている PR が書き換えているか（file の単位）。重なれば exit 1＝その窓は並べず、重なる PR が入るのを待つ列にする
      （振る舞いの既定「並走」）。開いている PR を読めない時は exit 3（重ならないと言わない）。

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

CONTEXT = 3
UNSEEN = 3  # 見ていない（緑に数えない）
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", re.M)
WHOLE = (1, 10**9)  # patch が無く行が分からない file の範囲＝file の全部
COMPARE_CAP = 300   # GitHub の compare が返す file の数の上限（届いたら全部を返していない）
PR_FILES_CAP = 3000  # GitHub の PR の file の一覧が返す数の上限
PAGES_CAP = 100


def ranges(patch: str | None) -> list[tuple[int, int]]:
    """patch の塊の main の側の行の範囲。patch が無い（None）時は行が分からない＝file の全部（WHOLE）。"""
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
    """分かれ目の行番号の範囲 span を、分かれ目→今の先端の差分 patch で今の先端の行番号へ写す。
    patch が "" ならそのまま。書き換えられた行に掛かる所は、書き換えた後の範囲の全部へ広げる。
    patch が None（先端の側で書き換えたが行が分からない）・span が全部なら、写せない＝file の全部。"""
    if patch is None or span == WHOLE:
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


def on_tip(files: dict[str, str | None], to_tip: dict[str, str | None]) -> dict[str, list[tuple[int, int]]]:
    """PR の {file: patch（分かれ目から）} を、今の先端の行番号の {file: [範囲]} へ写す
    （先端の側で触っていない file は "" ＝そのまま。触ったが patch が無い file は None＝全部）。"""
    return {f: [carry(r, to_tip.get(f, "")) for r in ranges(p)] for f, p in files.items()}


def blind(*sides: dict[str, list[tuple[int, int]]]) -> list[str]:
    """patch が無く行が分からない＝全部と見た file の名（知らせの中で名指す）。"""
    return sorted({f for side in sides for f, rs in side.items() if WHOLE in rs})


class Page(list):
    """一覧の 1 頁。next は次の頁の URL（GitHub の Link の rel="next"）か None＝この頁で終わり。"""
    next: str | None = None


def _get(url: str, token: str):
    """GitHub を読むのはここ 1 つ。一覧は Page（次の頁の URL つき）で返す。"""
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "Authorization": f"Bearer {token}", "User-Agent": "af-pr-overlap"})
    with urllib.request.urlopen(req, timeout=30) as r:
        m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link") or "")
        data = json.loads(r.read().decode("utf-8"))
    if isinstance(data, list):
        data = Page(data)
        data.next = m.group(1) if m else None
    return data


def _get_all(url: str, token: str, cap: int | None = None) -> list:
    """一覧の頁を Link の rel="next" で全部辿る（1 頁目だけで切らない）。辿り切れない・GitHub の上限 cap に届いた時は例外。"""
    out: list = []
    for _ in range(PAGES_CAP):
        data = _get(url, token)
        if not isinstance(data, list):
            raise OSError(f"一覧のはずが {type(data).__name__} が返った")
        out += data
        url = getattr(data, "next", None)
        if not url:
            if cap is not None and len(out) >= cap:
                raise OSError(f"{len(out)} 件＝GitHub が返す上限 {cap} に届き、全部を読めたか分からない")
            return out
    raise OSError(f"{PAGES_CAP} 頁を辿っても一覧が終わらない")


def _patch(r: dict) -> str | None:
    """compare の file の patch。GitHub が付けない（バイナリ・大きすぎる・名の変更だけ）時は None＝行が分からない。"""
    return r.get("patch") or None


def compare(repo: str, base: str, head: str, token: str) -> tuple[str, dict[str, str | None]]:
    """(分かれ目の commit, {file: patch（分かれ目から head まで）。patch が無い file は None})。"""
    c = _get(f"https://api.github.com/repos/{repo}/compare/{base}...{head}", token)
    files = c.get("files") or []
    if len(files) >= COMPARE_CAP:
        raise OSError(f"{base[:12]}...{head[:12]} の差分の file が {len(files)}＝compare の上限 {COMPARE_CAP} に届き、全部を読めない")
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


def open_files(repo: str, token: str) -> dict[str, list[str]]:
    """開いている PR ごとの触った file の名（PR の一覧も file の一覧も頁を全部辿る）。
    読めない・GitHub の上限に届いた時は例外（重ならないと言わない）。"""
    out = {}
    for p in open_prs(repo, token):
        try:
            files = _get_all(f"https://api.github.com/repos/{repo}/pulls/{p['number']}/files?per_page=100", token,
                             cap=PR_FILES_CAP)
        except OSError as e:
            raise OSError(f"#{p['number']} の file の一覧: {e}") from None
        out[f"#{p['number']} {p['head']['ref']}"] = [f["filename"] for f in files]
    return out


def open_prs(repo: str, token: str) -> list:
    """開いている PR の全部（頁を全部辿る。100 本を越えても黙って落とさない）。"""
    return _get_all(f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=100", token)


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
            opened = open_prs(a.repo, token)
            others_r = {f"#{p['number']}": on_base_tip(a.repo, tip, p["head"]["sha"], token, cache)
                        for p in opened if p["number"] != a.pr and (p.get("base") or {}).get("ref") == base}
    except Exception as e:  # noqa: BLE001  知らせる道具が壊れても PR は止めない（見ていない事を exit 3 で名指す）
        return unseen(f"他の PR を読めない（{e}）")
    if a.self_json:   # 試験の口: patch が null の file は行が分からない＝全部
        mine_r = {f: ranges(p) for f, p in mine.items()}
        others_r = {pr: {f: ranges(p) for f, p in fs.items()} for pr, fs in others.items()}
    hits = overlaps_ranges(mine_r, others_r)
    for pr, f, (s, e) in hits:
        where = "全部" if (s, e) == WHOLE else f"{s}〜{e} 行の辺り"
        print(f"⚠ {pr} も {f} の {where}を書き換えている（同じ節の本当の重なり）")
    unknown = blind(mine_r, *others_r.values())
    if unknown:
        print("pr_overlap: patch が無く行が分からない file は、全部を書き換えた物と見た（重ならないとは言わない）: "
              + "・".join(unknown))
    if hits:
        print("pr_overlap: 知らせ — 重なる PR の書いた窓と親の窓で、どちらを先に入れて後の方が取り込み直すかを今決める"
              "（合流の時に初めて衝突に気づかない）。止めはしない")
    else:
        print("pr_overlap: 重なる PR は無い")
    return 0


if __name__ == "__main__":
    sys.exit(main())
