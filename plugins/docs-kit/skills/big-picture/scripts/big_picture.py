#!/usr/bin/env python3
"""全体の絵（big-picture/1 の JSON）の検査・描き直し・照らし・説明。

絵の正は JSON 1 つ。HTML はそこから描き直す写し（手で HTML を直さない）。

使い方:
    python3 big_picture.py check   <絵.json>
    python3 big_picture.py render  <絵.json> -o <出す.html>
    python3 big_picture.py compare <合意した絵.json> <実物の絵.json>
    python3 big_picture.py explain <絵.json> <起きた問題の id>
    python3 big_picture.py pick    <repo の根> <PR が触った file>...

check:   形の誤り（欄の欠け・知らない値・重なった id・行き先の無い矢印・無い箱を指す問題）は exit 1。
         合意の絵で意図が空の箱は「赤い点」として 1 行ずつ警告する（exit 0・止めない）。
render:  check を通った絵だけ HTML にする（誤りがあれば exit 1 で書かない）。
compare: 合意した版（kind 合意・agreed あり）と、レビューの窓がコードから描いた実物（kind 実物・drawn_from あり）を
         4 欄で照らす。差なし exit 0／差あり exit 1／照らせない（形の誤り・合意の印が無い・取り違え）exit 2。
explain: 起きた問題を、絵の箱の名を挙げたチャットの文にする。
pick:    PR が触った file から、照らす合意した絵を選ぶ。値の表 docs-kit.big-picture.agreed は
         文字列（repo 全体で 1 枚）か、[{name, path, covers: [path の頭…]}] の並び（1 repo に製品が複数）。
         無ければ docs/全体の絵.json 1 枚。選んだ絵を 1 行ずつ「絵 <名> <在り処>」と出す（exit 0）。
         どの絵も覆わない file が 1 つでもある・値の形が誤り・絵が無い 時は exit 2（照らせない＝黙って通さない）。

標準ライブラリだけ。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FORM = "big-picture/1"
TABS = {"ctx": "1. 全体の文脈", "flow": "2. ワークフロー", "arch": "3. 仕組みの構成"}
KINDS = {"owner": "人（オーナー）", "ai": "AI の窓", "part": "部品", "store": "置き場・記録", "ext": "外の物"}
SIDES = ("共通", "個別", "外")
ROLES = ("決める", "見る")
ORIGINS = ("構造", "単発")
VERSION = re.compile(r"^\d{4}-\d{2}-\d{2}\.\d+$")
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
TEMPLATE = Path(__file__).resolve().parent.parent / "references" / "template.html"
SLOT = "/*__BIG_PICTURE_DATA__*/null"
ROOT_CAUSE = "直し: 形の誤りを 1 つずつ潰して出し直すだけで済ませず、誤りが入った原因を細目 §3「まず構造を疑う」で探して直す"
ROOT_CAUSE_DIFF = "直し: 差は main へ入れずに止め、差を見せてオーナーに決めてもらう（実物を直す時は細目 §3「まず構造を疑う」で原因から）"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _text(v):
    return isinstance(v, str) and v.strip() != ""


def check(pic):
    """(誤り, 赤い点) を返す。誤りが 1 つでもあれば使えない絵。"""
    errs, reds = [], []
    if not isinstance(pic, dict):
        return ["絵が JSON の object でない"], []
    if not isinstance(pic.get("meta", {}), dict) or not isinstance(pic.get("tabs", {}), dict):
        return ["meta か tabs が object でない"], []
    for key in ("boxes", "arrows", "problems"):
        v = pic.get(key, [])
        if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
            return ["%s が object の並びでない" % key], []
    if pic.get("form") != FORM:
        errs.append("form が %s でない" % FORM)
    meta = pic.get("meta") or {}
    for k in ("title", "kind", "version", "problem", "goal"):
        if k == "version" and meta.get("kind") == "実物":
            continue                                 # 実物は版を持たない（どの先端から描いたかは drawn_from）
        if not _text(meta.get(k)):
            errs.append("meta.%s が無い（%s）" % (k, {"problem": "解決したい問題", "goal": "完成像"}.get(k, "欄")))
    kind = meta.get("kind")
    if kind not in ("合意", "実物"):
        errs.append("meta.kind が 合意／実物 のどちらでもない: %r" % kind)
    if _text(meta.get("version")) and not VERSION.match(meta["version"]):
        errs.append("meta.version が YYYY-MM-DD.n でない: %s" % meta["version"])
    if kind == "合意":
        ag = meta.get("agreed") or {}
        if ag.get("by") != "owner" or not _text(ag.get("date")) or not _text(ag.get("record")):
            errs.append("合意の絵に meta.agreed（by=owner・date・record）が無い＝合意した版と言えない")
    if kind == "実物" and (not _text(meta.get("drawn_from")) or not _text(meta.get("drawn_by"))):
        errs.append("実物の絵に meta.drawn_from（どの先端のコードから）と meta.drawn_by（描いた窓）が無い")

    tabs = pic.get("tabs") or {}
    for t in tabs:
        if t not in TABS:
            errs.append("知らないタブ: %s（%s だけ）" % (t, "・".join(TABS)))

    boxes, seen = pic.get("boxes") or [], {}
    if not boxes:
        errs.append("箱が 1 つも無い")
    for b in boxes:
        bid = b.get("id")
        if not isinstance(bid, str) or not ID.match(bid):
            errs.append("箱の id が無いか形が違う: %r" % bid)
            continue
        if bid in seen:
            errs.append("箱の id が重なる: %s" % bid)
        seen[bid] = b
        if b.get("tab") not in TABS:
            errs.append("%s: tab が %s のどれでもない" % (bid, "・".join(TABS)))
        if b.get("k") not in KINDS:
            errs.append("%s: k が %s のどれでもない" % (bid, "・".join(KINDS)))
        if b.get("side") not in SIDES:
            errs.append("%s: side（共通と個別の境）が %s のどれでもない" % (bid, "・".join(SIDES)))
        role = b.get("role", "")
        if role and role not in ROLES:
            errs.append("%s: role が %s のどれでもない" % (bid, "・".join(ROLES)))
        if b.get("k") == "owner" and role not in ROLES:
            errs.append("%s: 人の箱に role（決める／見る）が無い" % bid)
        for f in ("t", "what", "why"):
            if not _text(b.get(f)):
                errs.append("%s: %s が無い（%s）" % (bid, f, {"t": "名", "what": "何か", "why": "記録にある理由"}[f]))
        for f in ("x", "y", "w", "h"):
            if not isinstance(b.get(f), (int, float)):
                errs.append("%s: %s（置き場所）が数でない" % (bid, f))
        if "intent" not in b:
            errs.append("%s: intent の欄が無い（聞いていなければ null と書く）" % bid)
        elif kind == "合意" and not _text(b.get("intent")):
            reds.append("赤い点: %s ›「%s」— オーナーの意図をまだ聞いていない" % (TABS.get(b.get("tab"), "?"), b.get("t", bid)))

    pairs = set()
    for a in pic.get("arrows") or []:
        f, t = a.get("from"), a.get("to")
        if f not in seen or t not in seen:
            errs.append("矢印 %s → %s の端の箱が無い" % (f, t))
            continue
        if seen[f].get("tab") != seen[t].get("tab"):
            errs.append("矢印 %s → %s がタブをまたぐ" % (f, t))
        if (f, t) in pairs:
            errs.append("矢印 %s → %s が重なる" % (f, t))
        pairs.add((f, t))

    pids = set()
    for p in pic.get("problems") or []:
        pid = p.get("id")
        if not isinstance(pid, str) or not ID.match(pid) or pid in pids:
            errs.append("起きた問題の id が無いか重なる: %r" % pid)
            continue
        pids.add(pid)
        for f in ("title", "date", "why_here"):
            if not _text(p.get(f)):
                errs.append("問題 %s: %s が無い" % (pid, f))
        if p.get("origin") not in ORIGINS:
            errs.append("問題 %s: origin が 構造／単発 のどちらでもない（単発と言えるのは絵の上で構造に原因が無いと示せた時だけ）" % pid)
        if p.get("cause") not in seen:
            errs.append("問題 %s: 原因の箱 %r が絵に無い" % (pid, p.get("cause")))
        at = p.get("at") or []
        if not at:
            errs.append("問題 %s: 起きた所（at）が無い" % pid)
        for x in at + (p.get("via") or []):
            if x not in seen:
                errs.append("問題 %s: 箱 %s が絵に無い" % (pid, x))
    return errs, reds


# ── 照らし（4 欄） ────────────────────────────────────────────


def compare(agreed, actual):
    """(照らしの Markdown, 差の数)。照らせない時は ValueError。"""
    for name, pic, want in (("合意した絵", agreed, "合意"), ("実物の絵", actual, "実物")):
        errs, _ = check(pic)
        if errs:
            raise ValueError("%s の形の誤り: %s" % (name, " / ".join(errs[:5]) + (" ほか %d 件" % (len(errs) - 5) if len(errs) > 5 else "")))
        if pic["meta"]["kind"] != want:
            raise ValueError("%s の meta.kind が %s でない（取り違え・合意した絵どうしは照らさない）" % (name, want))
    am, xm = agreed["meta"], actual["meta"]
    out = ["# 全体の絵の照らし: %s" % am["title"],
           "- 合意した版: %s（%s %s・%s）" % (am["version"], am["agreed"]["by"], am["agreed"]["date"], am["agreed"]["record"]),
           "- 実物: %s から %s が描いた" % (xm["drawn_from"], xm["drawn_by"]), ""]
    diffs = 0

    def boxmap(p):
        return {b["id"]: b for b in p["boxes"]}

    A, X = boxmap(agreed), boxmap(actual)

    def name(i):
        b = A.get(i) or X.get(i)
        return "「%s」(%s)" % (b["t"], i)

    out.append("## 欄 1 解決したい問題と完成像（文なので並べて見せる・差に数えない）")
    out.append("- 問題: 合意＝%s ／ 実物＝%s" % (am["problem"], xm["problem"]))
    out.append("- 完成像: 合意＝%s ／ 実物＝%s" % (am["goal"], xm["goal"]))
    out.append("")

    out.append("## 欄 2 部品と流れ")
    lines = []
    for i in sorted(set(A) - set(X)):
        lines.append("- 合意に在って実物に無い箱: %s" % name(i))
    for i in sorted(set(X) - set(A)):
        lines.append("- 実物に在って合意に無い箱: %s" % name(i))
    for i in sorted(set(A) & set(X)):
        if A[i]["tab"] != X[i]["tab"]:
            lines.append("- 箱のタブが違う: %s 合意＝%s 実物＝%s" % (name(i), TABS[A[i]["tab"]], TABS[X[i]["tab"]]))
        if A[i]["k"] != X[i]["k"]:
            lines.append("- 箱の種類が違う: %s 合意＝%s 実物＝%s" % (name(i), KINDS[A[i]["k"]], KINDS[X[i]["k"]]))
    ae = {(a["from"], a["to"]) for a in agreed.get("arrows") or []}
    xe = {(a["from"], a["to"]) for a in actual.get("arrows") or []}
    for f, t in sorted(ae - xe):
        lines.append("- 合意に在って実物に無い流れ: %s → %s" % (name(f), name(t)))
    for f, t in sorted(xe - ae):
        lines.append("- 実物に在って合意に無い流れ: %s → %s" % (name(f), name(t)))
    diffs += len(lines)
    out += lines or ["- 差なし"]
    out.append("")

    out.append("## 欄 3 共通と個別の境")
    lines = ["- %s 合意＝%s 実物＝%s" % (name(i), A[i]["side"], X[i]["side"])
             for i in sorted(set(A) & set(X)) if A[i]["side"] != X[i]["side"]]
    diffs += len(lines)
    out += lines or ["- 差なし"]
    out.append("")

    out.append("## 欄 4 人が見る所・決める所")
    ar = {i: b.get("role", "") for i, b in A.items() if b.get("role")}
    xr = {i: b.get("role", "") for i, b in X.items() if b.get("role")}
    lines = []
    for i in sorted(set(ar) | set(xr)):
        if ar.get(i) != xr.get(i):
            lines.append("- %s 合意＝%s 実物＝%s" % (name(i), ar.get(i) or "人の手なし", xr.get(i) or "人の手なし"))
    diffs += len(lines)
    out += lines or ["- 差なし"]
    out.append("")
    out.append("差: %d 件 → %s" % (diffs, "差なし（green）" if not diffs else "差あり（red・main へ入れずに止め、差を見せてオーナーに決めてもらう）"))
    return "\n".join(out), diffs


# ── 説明（チャットの文） ──────────────────────────────────────


def explain(pic, pid):
    errs, _ = check(pic)
    if errs:
        raise ValueError("絵の形の誤り: " + " / ".join(errs[:5]))
    B = {b["id"]: b for b in pic["boxes"]}
    p = next((x for x in pic.get("problems") or [] if x["id"] == pid), None)
    if p is None:
        raise ValueError("起きた問題 %s が絵に無い（先に problems へ足す）" % pid)

    def nm(i):
        return "【%s】（%s）" % (B[i]["t"], TABS[B[i]["tab"]])

    c = B[p["cause"]]
    same = [x for x in pic.get("problems") or [] if x["cause"] == p["cause"]]
    path = [p["cause"]] + [v for v in (p.get("via") or []) if v != p["cause"]]
    lines = [
        "「%s」（%s）" % (p["title"], p["date"]),
        "- 起きた所: " + "・".join(nm(i) for i in p["at"]),
        "- 原因の箱: %s — %s" % (nm(p["cause"]), "構造から来る" if p["origin"] == "構造" else "単発（絵の上で構造に原因が無いと示せた）"),
        "- 流れ: " + " → ".join(nm(i) for i in path + [a for a in p["at"] if a not in path]),
        "- この箱の意図: " + (c.get("intent") or "まだ聞いていない（赤い点）"),
        "- なぜここから起きたか: " + p["why_here"],
        "- この箱で起きた問題: %d 件" % len(same),
    ]
    return "\n".join(lines)


def render(pic):
    errs, _ = check(pic)
    if errs:
        raise ValueError("絵の形の誤り（描かない）: " + " / ".join(errs[:5]))
    tpl = TEMPLATE.read_text(encoding="utf-8")
    if tpl.count(SLOT) != 1:
        raise ValueError("型（%s）に差し込み口が 1 つでない" % TEMPLATE)
    data = json.dumps(pic, ensure_ascii=False).replace("</", "<\\/")
    title = pic["meta"]["title"].replace("&", "&amp;").replace("<", "&lt;")
    return tpl.replace(SLOT, data).replace("<title>全体の絵</title>", "<title>%s</title>" % title)


VALUES = Path("config") / "skill-values.json"
DEFAULT_AGREED = "docs/全体の絵.json"


def _agreed_value(root):
    vp = Path(root) / VALUES
    if not vp.exists():
        return None
    table = json.loads(vp.read_text(encoding="utf-8"))
    values = (table.get("docs-kit") or {}).get("big-picture") or {}
    return values.get("agreed")


def pick(root, files):
    """PR が触った file から照らす絵を選ぶ。返り値 (選んだ [(名, 在り処, [file])], 誤り [文])。"""
    if not files:
        return [], ["PR が触った file が渡されていない"]
    value = _agreed_value(root)
    errs = []
    if value in (None, ""):
        value = DEFAULT_AGREED
    if isinstance(value, str):
        if not value.strip():
            return [], ["値の表の docs-kit.big-picture.agreed が空"]
        local = Path(root) / value
        if value.endswith(".json") and not local.exists():
            return [], ["合意した絵が無い（%s）＝先に絵を描いてオーナーの OK を取る" % value]
        return [("全体", value, list(files))], []
    if not isinstance(value, list) or not value:
        return [], ["値の表の docs-kit.big-picture.agreed は文字列か {name, path, covers} の並び"]
    pics, names = [], set()
    for i, ent in enumerate(value):
        if not isinstance(ent, dict):
            errs.append("agreed[%d] が {name, path, covers} でない" % i)
            continue
        name, path, covers = ent.get("name"), ent.get("path"), ent.get("covers")
        if not isinstance(name, str) or not name.strip() or " " in name or "／" in name:
            errs.append("agreed[%d] の name が無いか、空白・／を含む" % i)
            continue
        if name in names:
            errs.append("agreed の name「%s」が重なる" % name)
        names.add(name)
        if not isinstance(path, str) or not path.strip():
            errs.append("絵「%s」の path が無い" % name)
        elif path.endswith(".json") and not (Path(root) / path).exists():
            errs.append("絵「%s」の合意した絵が無い（%s）" % (name, path))
        if not isinstance(covers, list) or not covers or not all(isinstance(c, str) and c for c in covers):
            errs.append("絵「%s」の covers（覆う path の頭の並び・全体は \"/\"）が無い" % name)
            continue
        pics.append((name, path, covers))
    if errs:
        return [], errs

    def hit(f, c):
        return c == "/" or f == c.rstrip("/") or f.startswith(c.rstrip("/") + "/")

    chosen = []
    for name, path, covers in pics:
        mine = [f for f in files if any(hit(f, c) for c in covers)]
        if mine:
            chosen.append((name, path, mine))
    loose = [f for f in files if not any(hit(f, c) for _, _, cs in pics for c in cs)]
    for f in loose:
        errs.append("どの絵も覆わない file: %s（その製品の絵を描いて OK を取るか、covers に足す）" % f)
    return ([] if errs else chosen), errs


def main(argv):
    if len(argv) >= 3 and argv[1] == "pick":
        try:
            chosen, errs = pick(argv[2], argv[3:])
        except (ValueError, OSError, json.JSONDecodeError) as e:
            chosen, errs = [], ["値の表が読めない: %s" % e]
        for e in errs:
            print("照らせない: " + e)
        if errs:
            print(ROOT_CAUSE)
        for name, path, mine in chosen:
            print("絵 %s %s（触った file %d）" % (name, path, len(mine)))
        return 2 if errs else 0
    if len(argv) < 3 or argv[1] not in ("check", "render", "compare", "explain"):
        sys.stderr.write(__doc__)
        return 2
    cmd = argv[1]
    try:
        if cmd == "check":
            if len(argv) != 3:
                sys.stderr.write(__doc__)
                return 2
            errs, reds = check(load(argv[2]))
            for e in errs:
                print("誤り: " + e)
            for r in reds:
                print(r)
            print("CHECK %s 誤り %d・赤い点 %d" % ("NG" if errs else "OK", len(errs), len(reds)))
            if errs:
                print(ROOT_CAUSE)
            return 1 if errs else 0
        if cmd == "render":
            if len(argv) != 5 or argv[3] != "-o":
                sys.stderr.write(__doc__)
                return 2
            Path(argv[4]).write_text(render(load(argv[2])), encoding="utf-8")
            print("RENDER OK %s" % argv[4])
            return 0
        if cmd == "compare":
            if len(argv) != 4:
                sys.stderr.write(__doc__)
                return 2
            text, diffs = compare(load(argv[2]), load(argv[3]))
            print(text)
            if diffs:
                print(ROOT_CAUSE_DIFF)
            return 1 if diffs else 0
        if len(argv) != 4:
            sys.stderr.write(__doc__)
            return 2
        print(explain(load(argv[2]), argv[3]))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print("照らせない: %s" % e if cmd == "compare" else "誤り: %s" % e)
        print(ROOT_CAUSE)
        return 2 if cmd == "compare" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
