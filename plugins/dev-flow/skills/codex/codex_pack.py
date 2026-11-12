#!/usr/bin/env python3
"""codex_pack: Codex（外部のレビュアー）へ渡すパックを安全に組む builder（/codex §往き の機構）。

守り（落とさない歯）:
1. 送り先の印: すべてのパックに `codex-egress-dest: self | client:<名>` を付ける。
   - self（顧客の物でない仕組み）: 載せる file が全部、値の表の `self_allow`（glob の並び）に入ること。
     表に無ければ既定 deny＝何も載せない。`clients.<名>.paths` に当たる file が 1 つでも混じれば中止。
   - client:<名>（顧客の物）: 値の表の `clients.<名>` が opt_in ∧ no_training_tier ∧ 期限（expires）内の
     時だけ。既定 deny。載せる file は全部 `clients.<名>.paths` の中であること。
   - `--dest` を省くと self だけを機械が決める（全部が self_allow の中で、顧客の path に当たらない時）。
     顧客の物へ自動で決めることは一切しない。
2. 秘密の最終関所: パックの完成全文を、書き込む **前** に再検査し、block 1 件でも出たら書かずに中止
   （Write/Edit の hook に頼らない＝Bash で回しても効く）。高エントロピーの塊は advisory として要約に出す。

値の表: repo の根の config/skill-values.json の `dev-flow.codex`（在る時だけ）。
  pack_dir（パックの置き場）・self_allow（[glob]）・clients（{名: {opt_in, no_training_tier, expires, paths}}）
  egress_log（送り出しの記録の jsonl の path。在る時だけ 1 行足す。本文・秘密は書かず、時刻・task・送り先・
  file の path・結果・件数・パックの sha256 だけ）

exit: 0=パックを作った（--dry-run は判定だけ）／1=中止（秘密・送り先の不許可・入力の不正）。
"""
from __future__ import annotations

import argparse
import hashlib
import datetime as dt
import fnmatch
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

# 書き込み前に止める秘密の形（block）。字はここで組み立てる（この file 自身が検査に当たらないため）。
BLOCK_PATTERNS = {
    "GitHub のトークン": r"gh[pousr]_[A-Za-z0-9]{20,}",
    "Anthropic の鍵": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "OpenAI 形の鍵": r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}",
    "AWS の鍵 ID": r"AKIA[0-9A-Z]{16}",
    "Slack のトークン": r"xox[abpors]-[A-Za-z0-9-]{10,}",
    "Google の API 鍵": r"AIza[0-9A-Za-z_\-]{30,}",
    "文書サービスのトークン": r"\b(?:secret_|ntn_)[A-Za-z0-9]{16,}",
    "JWT": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}",
    "Bearer のトークン": r"\bBearer\s+[A-Za-z0-9._\-]{16,}",
    "秘密鍵": "-----BEGIN " + r"[A-Z ]*" + "PRIVATE KEY-----",
    "合言葉のタグ": r"<password>.+?</password>",
    ".env 形の行": r"(?m)^[A-Z_]+_(?:KEY|TOKEN|SECRET|PASSWORD)=.+",
    "接続文字列の合言葉": r"[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@[^\s/]+",
    "DB の接続文字列": r"(?:postgres(?:ql)?|mongodb(?:\+srv)?)://[^\s\"'<>]+",
    "合言葉の代入": r"(?i)\b(?:password|passwd|secret|api_?key|token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]",
    # 引用符なしの値は、直後に . ( [ や識別子の字が続く時（式・参照）は当てない。
    "鍵の代入": (r"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*"
               r"(?:[\"'][A-Za-z0-9/+=_\-]{16,}|[A-Za-z0-9/+=_\-]{16,}(?![A-Za-z0-9/+=_\-$.(\[]))"),
}
ADVISORY_MIN_LEN = 32
ADVISORY_MIN_ENTROPY = 4.0
OUTPUT_CONTRACT = [
    "Status（Completed / Partially / Blocked）",
    "対象",
    "やったこと",
    "検証",
    "指摘・所見（1 件ずつ ID・重さ Blocker/Major/Minor/Nit・file:行・根拠）",
    "スコープ外",
    "要人間確認",
]


class Abort(Exception):
    pass


def repo_root(start: Path) -> Path:
    res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise Abort("git の repo の中で起動する（repo の根が分からない）")
    return Path(res.stdout.strip())


def load_values(root: Path, path: str | None) -> dict:
    p = Path(path) if path else root / "config" / "skill-values.json"
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Abort(f"値の表が読めない（{p.name}: {e}）")
    return (data.get("dev-flow") or {}).get("codex") or {}


def rel_of(root: Path, f: str) -> str:
    p = (root / f).resolve() if not os.path.isabs(f) else Path(f).resolve()
    try:
        rel = p.relative_to(root.resolve()).as_posix()
    except ValueError:
        raise Abort(f"repo の外の file は載せない: {f}")
    if not p.is_file():
        raise Abort(f"file が無い: {rel}")
    return rel


def match_any(rel: str, globs) -> bool:
    return any(fnmatch.fnmatchcase(rel, g) for g in (globs or []))


def client_ok(entry: dict, today: dt.date) -> str | None:
    """顧客の物を出してよいか。だめなら理由を返す。"""
    if not entry:
        return "値の表に、この顧客の許しが無い（既定 deny）"
    if entry.get("opt_in") is not True:
        return "opt_in が無い"
    if entry.get("no_training_tier") is not True:
        return "学習に使わない契約（no_training_tier）が無い"
    try:
        exp = dt.date.fromisoformat(str(entry.get("expires", "")))
    except ValueError:
        return "期限（expires: YYYY-MM-DD）が無い・読めない"
    if exp < today:
        return f"許しの期限切れ（{exp.isoformat()}）"
    return None


def resolve_dest(dest: str | None, rels: list[str], values: dict, today: dt.date) -> str:
    clients = values.get("clients") or {}
    hits_client = {n for n, e in clients.items() for r in rels if match_any(r, (e or {}).get("paths"))}
    if dest is None:
        if hits_client:
            raise Abort("顧客の物の path が混じる＝送り先を自動では決めない（--dest client:<名> を明示）")
        dest = "self"
    if dest == "self":
        if hits_client:
            raise Abort(f"self を名乗るのに顧客の物の path が混じる: {sorted(hits_client)}")
        allow = values.get("self_allow") or []
        if not allow:
            raise Abort("値の表に self_allow が無い（既定 deny＝何も載せない）")
        outside = [r for r in rels if not match_any(r, allow)]
        if outside:
            raise Abort(f"self_allow の外の path が混じる: {outside}")
        return "self"
    if dest.startswith("client:") and dest[len("client:"):]:
        name = dest[len("client:"):]
        entry = clients.get(name) or {}
        why = client_ok(entry, today)
        if why:
            raise Abort(f"顧客 {name} へは出さない: {why}")
        outside = [r for r in rels if not match_any(r, entry.get("paths"))]
        if outside:
            raise Abort(f"顧客 {name} の paths の外が混じる: {outside}")
        return dest
    raise Abort("--dest は self か client:<名>")


def body_of(root: Path, rel: str, mode: str) -> str:
    if mode == "diff":
        res = subprocess.run(["git", "diff", "HEAD", "--", rel], cwd=root,
                             capture_output=True, text=True)
        return res.stdout or "（差分なし）\n"
    return (root / rel).read_text(encoding="utf-8", errors="replace")


def build_pack(a, rels: list[str], dest: str, root: Path) -> str:
    head = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip() or "不明"
    out = [
        f"<!-- codex-egress-dest: {dest} -->",
        f"# Codex レビューのパック: {a.task}",
        "",
        "## 1. 固定起点ゴール（このレビューの終わり・ぶらさない錨）",
        a.done,
        "",
        "## 2. このパックの読み方",
        "- あなた（Codex）はレビューだけをする。コードを書き換えない・実装しない。",
        "- 範囲の外は直さず「スコープ外」に挙げるだけ。",
        "",
        "## 3. 目的", a.purpose, "",
        "## 4. 範囲", a.scope, "",
        "## 5. 変更禁止", a.forbid or "（指定なし）", "",
        "## 6. 実測とコードの時点",
        f"- コードの HEAD: {head}",
        f"- 実測の時点: {a.measured_at}" if a.measured_at
        else "- 実測の時点: 未指定＝所見は仮説扱い（再測してから採否）",
        "",
        "## 7. 出力の契約（この 7 欄で返す・起点ゴールの達成を可否で明記）",
        *[f"- {c}" for c in OUTPUT_CONTRACT],
        "",
        f"## 8. 対象（mode={a.mode}）",
    ]
    for r in rels:
        out += ["", f"### {r}", "````", body_of(root, r, a.mode).rstrip("\n"), "````"]
    return "\n".join(out) + "\n"


def entropy(s: str) -> float:
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in (s.count(ch) for ch in set(s)))


def scan(text: str):
    blocks = [label for label, pat in BLOCK_PATTERNS.items() if re.search(pat, text)]
    advis = [t for t in re.findall(r"[A-Za-z0-9+/=_\-]{%d,}" % ADVISORY_MIN_LEN, text)
             if entropy(t) >= ADVISORY_MIN_ENTROPY]
    return blocks, len(advis)


def write_log(values: dict, root: Path, rec: dict) -> None:
    path = values.get("egress_log")
    if not path:
        return
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = root / p
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds"), **rec}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Codex へ渡すパックを安全に組む")
    ap.add_argument("--task", required=True)
    ap.add_argument("--dest", help="self | client:<名>（省くと self だけ自動）")
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--scope", required=True)
    ap.add_argument("--done", required=True, help="起点ゴール（何が起きたら終わりか）")
    ap.add_argument("--forbid")
    ap.add_argument("--file", action="append", required=True)
    ap.add_argument("--mode", choices=["full", "diff"], default="full")
    ap.add_argument("--measured-at")
    ap.add_argument("--out-dir", help="パックの置き場（値の表の pack_dir より先）")
    ap.add_argument("--values", help="値の表の path（既定は repo の根の config/skill-values.json）")
    ap.add_argument("--today", help=argparse.SUPPRESS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", a.task):
            raise Abort("--task は英数字と . _ - だけ")
        root = repo_root(Path.cwd())
        values = load_values(root, a.values)
        today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
        rels = [rel_of(root, f) for f in a.file]
        dest = resolve_dest(a.dest, rels, values, today)
        text = build_pack(a, rels, dest, root)
        blocks, advis = scan(text)
        meta = {"task": a.task, "dest": dest, "files": rels, "mode": a.mode,
                "advisory": advis, "dry_run": a.dry_run}
        if blocks:
            write_log(values, root, {**meta, "result": "中止", "block": blocks})
            raise Abort(f"秘密の形を検出（{', '.join(blocks)}）＝書き込まない")
        print(f"  dest       : {dest}")
        print(f"  files      : {len(rels)}")
        print(f"  secret     : block 0 / advisory {advis}" + ("（送る前に人の目で差分を見る）" if advis else ""))
        if a.dry_run:
            print("codex_pack: dry-run（書かない）")
            return 0
        base = a.out_dir or values.get("pack_dir") or os.path.join(
            os.environ.get("TMPDIR", "/tmp"), "codex")
        out = Path(base).expanduser() / a.task
        out.mkdir(parents=True, exist_ok=True)
        (out / "pack.md").write_text(text, encoding="utf-8")
        (out / "goal.txt").write_text(a.done + "\n", encoding="utf-8")
        write_log(values, root, {**meta, "result": "作った", "block": [],
                                 "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
        print(f"codex_pack: 作った {out / 'pack.md'}")
        return 0
    except Abort as e:
        print(f"codex_pack: 中止 — {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
