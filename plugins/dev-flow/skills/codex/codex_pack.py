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
   （Write/Edit の hook に頼らない＝Bash で回しても効く）。
3. 高エントロピーの塊（鍵らしい字・既定 32 字以上でエントロピー 4.0 以上）も既定で止める（オーナー同意 2026-11-19:
   前は件数を出して人の目に預けるだけで、鍵らしい字を含むパックが外へ出うった）。止めた文には塊の字を出さず、
   どの file の何行目か・長さ・指紋（sha256 の頭 12 字）だけを出す。誤って止まる塊（作り物の値・固定の検査値など）は
   値の表 `entropy_allow` で外す（PR とレビューを通る＝窓の一存で外れない）。止まるのは builder を回す AI だけ。
   形の推し量りは 32 字より短い鍵・字の種類の少ない鍵を通していたので、次の 3 段を足した（どれも止める・字は出さない）:
   a. 窓が持つ秘密の値そのもの: 名が鍵らしい環境変数（KEY・TOKEN・SECRET・PASS・CRED・AUTH・PRIVATE を含む）と
      repo の根の .env・.env.* の値（8 字以上）が、形を問わずそのまま在れば止める（形でなく値で照らす＝短い鍵も通らない）。
   b. 16 進の塊（20 字以上・数字と a-f の両方を含む）: その repo の git の物（commit などの印）でなければ止める
      （git の印と 16 進の鍵は形で見分けられない＝分かる物だけ通す）。
   c. 16〜31 字の塊: 英字と数字が混ざり、字の種類の入れ替わりが多く、字の散らばり（エントロピー）が長さの割に高く、
      識別子・path の語の並び（session_PARENT01・pdf/base_v2 の類）でない物は止める。
   残る穴（正直に書く）: 窓の外にしか無い鍵で、16 字未満か、英字だけ・語の並びの形の物は形で見分けられず通る。

値の表: config/skill-values.json の `dev-flow.codex`（在る時だけ。探し方と鍵の一覧は plugin の lib/skill_values.py
  ＝土台の skill-values/ の正本。知らない鍵・畳んだ鍵・型の違う値は名指しして中止＝黙って既定で動かない）。
  pack_dir（パックの置き場）・self_allow（[glob]・repo の根からの path の全体に当てる・* は / をまたがず dir をまたぐのは **）・clients（{名: {opt_in, no_training_tier, expires, paths}}）
  egress_log（送り出しの記録の jsonl の path。在る時だけ 1 行足す。本文・秘密は書かず、時刻・task・送り先・
  file の path・結果・件数・パックの sha256 だけ）
  entropy_allow（止めない高エントロピーの塊の並び。"sha256:<指紋 12 字以上>" は塊の sha256 の頭に当て、
  それ以外は塊の全体に当てる正規表現）

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

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
import skill_values  # noqa: E402  値の表の 1 本の口（plugin の lib/＝土台の skill-values/ への symlink）

import af_place  # noqa: E402  土台の在り処探しの 1 本の口（同じ lib/ の symlink）

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
GUARD_REL = os.path.join("public-guard", "guard.py")

# 書き込み前に止める秘密の形（block）は 2 つの和:
#   - 鍵・トークンの形: 土台の公開の検査 public-guard/guard.py の SECRET_PATTERNS を直に読む（token_forms・写さない）
#   - 鍵の形でない秘密（パックを外へ出す前だけ止める・公開の検査の範囲の外＝codex の足し）: EXTRA_FORMS
# 字はここで組み立てる（この file 自身が検査に当たらないため）。
EXTRA_FORMS = {
    "JWT": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}",
    "Bearer のトークン": r"\bBearer\s+[A-Za-z0-9._\-]{16,}",
    "合言葉のタグ": r"<password>.+?</password>",
    ".env 形の行": r"(?m)^[A-Z_]+_(?:KEY|TOKEN|SECRET|PASSWORD)=.+",
    "接続文字列の合言葉": r"[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@[^\s/]+",
    "DB の接続文字列": r"(?:postgres(?:ql)?|mongodb(?:\+srv)?)://[^\s\"'<>]+",
    "合言葉の代入": r"(?i)\b(?:password|passwd|secret|api_?key|token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]",
    # 引用符なしの値は、直後に . ( [ や識別子の字が続く時（式・参照）は当てない。
    "鍵の代入": (r"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*"
               r"(?:[\"'][A-Za-z0-9/+=_\-]{16,}|[A-Za-z0-9/+=_\-]{16,}(?![A-Za-z0-9/+=_\-$.(\[]))"),
}


def token_forms(environ=None) -> dict:
    """鍵・トークンの形の正本（土台の public-guard/guard.py の SECRET_PATTERNS）。見つからない・読めない・空なら Abort
    （照らせない物は外へ出さない＝既定で止める）。探す順: 環境変数 AF_PUBLIC_GUARD → 入った dev-flow と同じ版の土台。"""
    env = os.environ if environ is None else environ
    path = env.get("AF_PUBLIC_GUARD") or af_place.foundation_file(GUARD_REL, str(PLUGIN_ROOT))
    if not path or not os.path.isfile(path):
        raise Abort("鍵の形の正本（土台の public-guard/guard.py）が見つからず照らせない＝パックを作らない。"
                    "土台の plugin を市場から入れ直す（手元の置き場が違う時は AF_PUBLIC_GUARD に guard.py の path）")
    try:
        pats = getattr(af_place.load_module("af_public_guard_for_codex", path), "SECRET_PATTERNS", None)
        forms = {str(k): re.compile(v) for k, v in pats.items()} if isinstance(pats, dict) and pats else None
    except Exception as e:  # noqa: BLE001
        raise Abort(f"鍵の形の正本（{path}）が読めず照らせない＝パックを作らない: {e}")
    if not forms:
        raise Abort(f"鍵の形の正本（{path}）に SECRET_PATTERNS が無く照らせない＝パックを作らない")
    return forms


def block_forms(environ=None) -> dict:
    """止める形の全部（札→正規表現）。鍵の形は正本を読み、codex の足しを重ねる。"""
    return {**token_forms(environ), **{k: re.compile(v) for k, v in EXTRA_FORMS.items()}}


ADVISORY_MIN_LEN = 32
ADVISORY_MIN_ENTROPY = 4.0
SHORT_MIN_LEN = 16           # c. 短い塊の下限（ここより短い物は形で見分けない＝残る穴）
SHORT_MIN_SWITCHES = 6       # c. 字の種類（小文字・大文字・数字・記号）の入れ替わりの数の下限
SHORT_ENTROPY_SLACK = 0.8    # c. エントロピーが log2(長さ) − これ 以上なら散らばりが高い
HEX_MIN_LEN = 20             # b. 16 進の塊の下限
KNOWN_MIN_LEN = 8            # a. 照らす秘密の値の下限（これより短い値は他の字と取り違える）
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASS|CRED|AUTH|PRIVATE", re.I)
OUTPUT_CONTRACT = [
    "Status（Completed / Partially / Blocked）",
    "対象",
    "やったこと",
    "検証",
    "指摘・所見（1 件ずつ ID・重さ Blocker/Major/Minor/Nit・file:行・根拠）",
    "スコープ外",
    "要人間確認",
]


# 中止の時の最後の行（中身は細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: file を差し替えて出し直すだけで済ませず、意図（外へ渡す物に秘密と顧客の物が入らない）とのずれから入り、混じった原因（渡す物の選び方）を細目 §3「まず構造を疑う」で探して直す"

class Abort(Exception):
    pass


def repo_root(start: Path) -> Path:
    res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise Abort("git の repo の中で起動する（repo の根が分からない）")
    return Path(res.stdout.strip())


def load_values(root: Path, path: str | None) -> dict:
    try:
        return skill_values.section("dev-flow", "codex", explicit=path, starts=[str(root)])
    except skill_values.ValuesError as e:
        raise Abort(str(e))


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
    """path（repo の根から）が glob の並びのどれかの全体に当たるか。当て方の正本は値の表の口の glob_match
    （* と ? は / をまたがず、dir をまたぐのは **）。"""
    return any(skill_values.glob_match(g, rel) for g in (globs or []))


def old_only(rels, globs) -> list[str]:
    """前の読み方（fnmatch の * が / をまたぐ）でだけ当たる path（1 段目: 通して名指す。2 段目で畳む＝原因の台帳の行）。"""
    return [r for r in rels if not match_any(r, globs)
            and any(isinstance(g, str) and fnmatch.fnmatchcase(r, g) for g in (globs or []))]


def _note_old(key: str, olds: list[str]) -> None:
    if olds:
        sys.stderr.write(f"[codex_pack] 値の表の {key} の glob は前の読み方（* が / をまたぐ）でだけ当たる path を通した: {olds}。"
                         "今は通すが、下の dir まで許すなら dir/** に書き直す（* は / をまたがない読み方へ移る）\n")


def client_hit(rel: str, globs) -> bool:
    """顧客の物の path か。glob_match に加え、前の読み方（fnmatch の * が / をまたぐ）でも当たれば顧客の物と見る
    （1 段目: 顧客の物を見落とす側へ狭めない。前の形の値〔dir/* で下の dir 全部のつもり〕は ** に書き直す）。"""
    return match_any(rel, globs) or any(isinstance(g, str) and fnmatch.fnmatchcase(rel, g) for g in (globs or []))


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
    hits_client = {n for n, e in clients.items() for r in rels if client_hit(r, (e or {}).get("paths"))}
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
        olds = old_only(rels, allow)
        outside = [r for r in rels if not match_any(r, allow) and r not in olds]
        if outside:
            raise Abort(f"self_allow の外の path が混じる: {outside}（下の dir まで許すなら self_allow の行を dir/** で書く）")
        _note_old("self_allow", olds)
        return "self"
    if dest.startswith("client:") and dest[len("client:"):]:
        name = dest[len("client:"):]
        entry = clients.get(name) or {}
        why = client_ok(entry, today)
        if why:
            raise Abort(f"顧客 {name} へは出さない: {why}")
        olds = old_only(rels, entry.get("paths"))
        outside = [r for r in rels if not match_any(r, entry.get("paths")) and r not in olds]
        if outside:
            raise Abort(f"顧客 {name} の paths の外が混じる: {outside}（下の dir まで含めるなら paths の行を dir/** で書く）")
        _note_old(f"clients.{name}.paths", olds)
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


_CHUNK = re.compile(r"[A-Za-z0-9+/=_\-]{%d,}" % ADVISORY_MIN_LEN)
_SHORT = re.compile(r"(?<![A-Za-z0-9+/=_\-])[A-Za-z0-9+/=_\-]{%d,%d}(?![A-Za-z0-9+/=_\-])"
                    % (SHORT_MIN_LEN, ADVISORY_MIN_LEN - 1))
_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{%d,}(?![0-9A-Za-z])" % HEX_MIN_LEN)
# 識別子・path の語（小文字の語・大文字の語・頭だけ大文字の語＋数字 2 字まで・数字だけ）。塊が全部これで割れれば鍵とみない。
_WORD = re.compile(r"^(?:[a-z]+[0-9]{0,2}|[A-Z]+[0-9]{0,2}|[A-Z][a-z]+[0-9]{0,2}|[0-9]{1,4}|[a-z]?)$")


def _kind(c: str) -> str:
    return "l" if c.islower() else "u" if c.isupper() else "d" if c.isdigit() else "o"


def short_keylike(tok: str) -> bool:
    """c. 16〜31 字の塊が鍵らしいか（英字と数字が混ざる・入れ替わりが多い・散らばりが高い・語の並びでない）。"""
    if all(_WORD.match(p) for p in re.split(r"[/_=\-.+]", tok)):
        return False
    if not (re.search(r"[A-Za-z]", tok) and re.search(r"[0-9]", tok)) or re.fullmatch(r"[0-9a-fA-F]+", tok):
        return False
    switches = sum(1 for a, b in zip(tok, tok[1:]) if _kind(a) != _kind(b))
    return switches >= SHORT_MIN_SWITCHES and entropy(tok) >= math.log2(len(tok)) - SHORT_ENTROPY_SLACK


def git_objects(root: Path | None, toks) -> set[str]:
    """b. その repo の git の物（commit などの印・頭だけでも 1 つに決まる物）である塊の集まり。"""
    toks = sorted(set(toks))
    if not toks or root is None:
        return set()
    try:
        res = subprocess.run(["git", "cat-file", "--batch-check"], cwd=root, input="\n".join(toks) + "\n",
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return set()
    out = set()
    for tok, line in zip(toks, res.stdout.splitlines()):
        if not line.endswith((" missing", " ambiguous")):
            out.add(tok)
    return out


def known_secrets(root: Path | None, environ=None) -> list[tuple[str, str]]:
    """a. 窓が持つ秘密の値の (出所の名, 値) の並び。出所は環境変数の名か .env の file と鍵の名（値は外へ出さない）。"""
    env = os.environ if environ is None else environ
    out = [(f"環境変数 {k}", v) for k, v in env.items()
           if SECRET_NAME.search(k) and isinstance(v, str) and len(v.strip()) >= KNOWN_MIN_LEN]
    if root is not None:
        for f in sorted(root.glob(".env*")):
            if not f.is_file():
                continue
            for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", ln)
                if m:
                    v = m.group(2).strip().strip("'\"")
                    if len(v) >= KNOWN_MIN_LEN:
                        out.append((f"{f.name} の {m.group(1)}", v))
    return [(n, v.strip()) for n, v in out]


def allow_rules(values: dict):
    """値の表の entropy_allow を (指紋の頭の並び, 正規表現の並び) にする。読めない物は止める。"""
    fps, regs = [], []
    for item in values.get("entropy_allow") or []:
        if not isinstance(item, str) or not item:
            raise Abort("値の表の entropy_allow に字でない・空の物がある")
        if item.startswith("sha256:"):
            fp = item[len("sha256:"):].lower()
            if not re.fullmatch(r"[0-9a-f]{12,64}", fp):
                raise Abort(f"値の表の entropy_allow の指紋は 16 進 12 字以上: {item}")
            fps.append(fp)
        else:
            try:
                regs.append(re.compile(item))
            except re.error as e:
                raise Abort(f"値の表の entropy_allow に読めない正規表現（{e}）")
    return fps, regs


def entropy_hits(text: str, values: dict | None = None, rels=None, root: Path | None = None):
    """鍵らしい塊（高エントロピー・b の 16 進・c の短い塊）を (どこ, 行, 長さ, 指紋) の並びで返す。塊の字そのものは返さない。"""
    fps, regs = allow_rules(values or {})
    in_git = git_objects(root, _HEX.findall(text))
    hits, where, base = [], "（パックの見出し）", 0
    for no, ln in enumerate(text.splitlines(), 1):
        if ln.startswith("### ") and (rels is None or ln[4:] in rels):
            where, base = ln[4:], no + 1   # 次の行は ```` の囲み＝その次が file の 1 行目
            continue
        if ln == "````" and where != "（パックの見出し）" and no > base:
            where, base = "（パックの見出し）", 0   # file の囲みの閉じ＝その後は file の行でない
            continue
        cands = [t for t in _CHUNK.findall(ln) if entropy(t) >= ADVISORY_MIN_ENTROPY]
        cands += [t for t in _HEX.findall(ln)
                  if re.search(r"[0-9]", t) and re.search(r"[a-fA-F]", t) and t not in in_git]
        cands += [t for t in _SHORT.findall(ln) if short_keylike(t)]
        for tok in dict.fromkeys(cands):
            full = sha256_full(tok)
            fp = full[:12]
            if any(full.startswith(p) for p in fps) or any(r.fullmatch(tok) for r in regs):
                continue
            hits.append((where, no - base if where != "（パックの見出し）" else no, len(tok), fp))
    return hits


def sha256_full(tok: str) -> str:
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()


def scan(text: str, values: dict | None = None, rels=None, root: Path | None = None, environ=None):
    blocks = [label for label, rx in block_forms(environ).items() if rx.search(text)]
    fps, _ = allow_rules(values or {})
    for name, val in known_secrets(root, environ):
        if val in text and not any(sha256_full(val).startswith(p) for p in fps):
            blocks.append(f"窓が持つ秘密の値（{name}）")
    return blocks, entropy_hits(text, values, rels, root)


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
    ap.add_argument("--values", help="値の表の path（既定は SKILL_VALUES → repo の根の config/skill-values.json）")
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
        blocks, hits = scan(text, values, set(rels), root)
        meta = {"task": a.task, "dest": dest, "files": rels, "mode": a.mode,
                "entropy": len(hits), "dry_run": a.dry_run}
        if blocks:
            write_log(values, root, {**meta, "result": "中止", "block": blocks})
            raise Abort(f"秘密の形を検出（{', '.join(blocks)}）＝書き込まない")
        if hits:
            write_log(values, root, {**meta, "result": "中止", "block": ["高エントロピーの塊"],
                                     "fingerprints": [h[3] for h in hits]})
            unit = "差分の" if a.mode == "diff" else ""
            where = "\n".join(f"    - {w} の{unit} {n} 行目（{ln} 字・指紋 sha256:{fp}）" for w, n, ln, fp in hits)
            raise Abort(
                f"鍵らしい高エントロピーの塊が {len(hits)} 個＝書き込まない\n{where}\n"
                "  直し方: 鍵なら file から抜いて鍵を取り替える。載せなくてよい行なら --mode diff で変えた行だけにするか、"
                "その行の無い file に分けて載せる。\n"
                "  誤って止まった時（作り物の値・固定の検査値など秘密でないと確かめた塊）: repo の値の表 "
                "dev-flow.codex.entropy_allow に上の \"sha256:<指紋>\" を足す PR を出す（PR とレビューを通る）。")
        print(f"  dest       : {dest}")
        print(f"  files      : {len(rels)}")
        print("  secret     : block 0 / 高エントロピーの塊 0")
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
        print(ROOT_CAUSE, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
