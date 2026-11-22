#!/usr/bin/env python3
"""workflow の読み手（正本）。「どの workflow の・どの job の・どの step が・どの起こり方で土台の action public-guard を呼ぶか」を
1 か所で読む。見回り（public-guard/patrol.py）・守りの hook（plugins/guard/scripts/pr_text.py）・手元の公開の検査
（scripts/checks/public_guard.sh）は皆ここを通して読む（file の text を正規表現で拾う別の読み方を持たない）。

意図: workflow の見分けを 1 つにし、見回り・守りの hook・手元の検査が同じ読み方をする。
課題: 前は見回りが file 全体の text から `uses:` を拾い（コメントの行・job の外・起こり方を見ない）、守りの hook は
名の順で最初の workflow だけを見て（起こり方・job の if: を見ず、2 つ目の workflow の語の表を落とし）、手元の検査は
ci.yml の値を手で写していた。それぞれ違う外れ方をしていた。
原因: 同じ見分けが 3 通りに分かれていた。

数える呼び口: workflow が PR か push で走り（on: に pull_request・pull_request_target・push・merge_group）、
job の if: と step の if: が字どおりの false でない step。workflow_dispatch・schedule だけで走る workflow や
`if: false` の job の呼び口は、PR の検査として走らないので数えない（見つけはするが counts=False）。

標準の Python だけで動く（見回りは他の道具を入れない Actions の python3 で、守りの hook は使う側の窓で動く）。
YAML は workflow に要る範囲（字下げの写像・並び・流れの形 [..] {..}・引用・| と > の塊）だけを読む。anchor 等は読まない。

使い方（手元の検査が CI と同じ値で guard.py を呼ぶため）:
  python3 workflow_reader.py guard-args <workflow の file> [--check public-guard]
  → 必須の検査の名（job の name か id）が --check の job の、数える呼び口の with: から guard.py の引数を 1 行 1 つで出す。
  exit: 0=出した / 2=呼び口が 1 つに決まらない・読めない
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import namedtuple

FOUNDATION = "ynishikawa-coder/agent-foundation-public"   # 土台の repo の名（正本。見回りと守りの hook はここを読む）
LOCAL_ACTION = "./public-guard"
# PR か push で走る起こり方（必須の検査として走る）。ここに無い起こり方だけの workflow の呼び口は数えない。
RUNS_ON_CHANGE = ("pull_request", "pull_request_target", "push", "merge_group")
CHECK = "public-guard"


# ── YAML（workflow に要る範囲） ──
class _Line:
    __slots__ = ("indent", "text", "raw")

    def __init__(self, raw):
        self.raw = raw
        self.indent = len(raw) - len(raw.lstrip(" "))
        self.text = _strip_comment(raw.strip())


def _strip_comment(s):
    """引用の外の `#`（行頭か空白の後）から後を外す。"""
    q = None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in "'\"" and (i == 0 or s[i - 1] in " \t:[{,-"):
            q = ch
        elif ch == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s[1:-1])
    return s


def _split_key(text):
    """`key: value` の (key, value)。写像の行でなければ None。"""
    if text[:1] in "'\"":
        q = text[0]
        end = text.find(q, 1)
        while q == "'" and end != -1 and text[end + 1:end + 2] == "'":
            end = text.find(q, end + 2)
        if end == -1 or text[end + 1:end + 2] != ":":
            return None
        rest = text[end + 2:]
        if rest and rest[0] not in " \t":
            return None
        return _unquote(text[:end + 1]), rest.strip()
    m = re.match(r"^([^\s\[\]{},#'\"][^:#]*?|[^\s\[\]{},#'\"])\s*:(?:\s+|$)(.*)$", text)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def _flow(s, i=0):
    """流れの形（[..] {..} と素の値）を読む。(値, 次の位置)。"""
    while i < len(s) and s[i] in " \t":
        i += 1
    if i < len(s) and s[i] in "[{":
        close = "]" if s[i] == "[" else "}"
        out = [] if s[i] == "[" else {}
        i += 1
        while True:
            while i < len(s) and s[i] in " \t,":
                i += 1
            if i >= len(s) or s[i] == close:
                return out, i + 1
            if s[i] in "]}":          # 閉じの字が合わない（崩れた形）。読める所までで止める
                return out, len(s)
            if isinstance(out, list):
                v, i = _flow(s, i)
                out.append(v)
            else:
                k, i = _flow_scalar(s, i, key=True)
                while i < len(s) and s[i] in " \t":
                    i += 1
                if i < len(s) and s[i] == ":":
                    v, i = _flow(s, i + 1)
                else:
                    v = ""
                out[k] = v
    return _flow_scalar(s, i)


def _flow_scalar(s, i, key=False):
    while i < len(s) and s[i] in " \t":
        i += 1
    if i < len(s) and s[i] in "'\"":
        q = s[i]
        j = i + 1
        while j < len(s):
            if s[j] == q:
                if q == "'" and s[j + 1:j + 2] == "'":
                    j += 2
                    continue
                break
            j += 2 if (q == '"' and s[j] == "\\") else 1
        return _unquote(s[i:j + 1]), j + 1
    j = i
    stops = ",]}" + (":" if key else "")
    while j < len(s) and s[j] not in stops:
        if key and s[j] == ":":
            break
        j += 1
    return s[i:j].strip(), j


def _scalar(text):
    if text[:1] in "[{":
        return _flow(text)[0]
    return _unquote(text)


def _parse_block(lines, i, indent):
    """lines[i] から字下げ indent の塊を読む。(値, 次の i)。"""
    if i >= len(lines):
        return "", i
    if lines[i].text == "-" or lines[i].text.startswith("- "):
        return _parse_seq(lines, i, indent)
    return _parse_map(lines, i, indent)


def _value_after(lines, i, indent, value):
    """`key:`/`- ` の後の値。空なら下の塊、| > なら塊の字、そうでなければ素の値（続きの行も繋ぐ）。"""
    if value == "":
        while i < len(lines) and not lines[i].text:
            i += 1
        if i < len(lines) and (lines[i].indent > indent or
                               (lines[i].indent == indent and (lines[i].text == "-" or lines[i].text.startswith("- ")))):
            return _parse_block(lines, i, lines[i].indent)
        return "", i
    if re.match(r"^[|>][-+0-9]*$", value):
        body = []
        while i < len(lines) and (lines[i].indent > indent or not lines[i].raw.strip()):
            body.append(lines[i].raw)
            i += 1
        while body and not body[-1].strip():
            body.pop()
        cut = min((len(b) - len(b.lstrip(" ")) for b in body if b.strip()), default=0)
        sep = "\n" if value[0] == "|" else " "
        return sep.join(b[cut:] for b in body), i
    parts = [value]
    while i < len(lines) and lines[i].text and lines[i].indent > indent:   # 素の値の続きの行
        parts.append(lines[i].text)
        i += 1
    return _scalar(" ".join(parts)), i


def _parse_map(lines, i, indent):
    out = {}
    while i < len(lines):
        ln = lines[i]
        if not ln.text:
            i += 1
            continue
        if ln.indent != indent or ln.text.startswith("- ") or ln.text == "-":
            break
        kv = _split_key(ln.text)
        if kv is None:
            i += 1
            continue
        key, value = kv
        out[key], i = _value_after(lines, i + 1, indent, value)
    return out, i


def _parse_seq(lines, i, indent):
    out = []
    while i < len(lines):
        ln = lines[i]
        if not ln.text:
            i += 1
            continue
        if ln.indent != indent or not (ln.text == "-" or ln.text.startswith("- ")):
            break
        rest = ln.text[1:].lstrip(" ")
        after = ln.raw[indent + 1:]
        col = indent + 1 + len(after) - len(after.lstrip(" "))
        if rest == "":
            v, i = _value_after(lines, i + 1, indent, "")
        elif _split_key(rest) is not None and rest[:1] not in "[{":
            # `- key: v` は字下げ col の写像の 1 行目（後の行は同じ字下げで続く）
            lines[i] = _Line(" " * col + rest)
            v, i = _parse_map(lines, i, col)
        else:
            v, i = _value_after(lines, i + 1, indent, rest)
        out.append(v)
    return out, i


def load(text):
    """workflow の text を dict に（読めない形は空の dict）。値はみな文字か dict・list（true/false も字のまま）。"""
    # コメントだけの行は字が空の行として残す（構造では飛ばし、| > の塊の中では字のまま）
    lines = [_Line(r) for r in text.replace("\t", "  ").splitlines() if r.strip() not in ("---", "...")]
    while lines and not lines[0].text:
        lines.pop(0)
    if not lines:
        return {}
    v, _ = _parse_block(lines, 0, lines[0].indent)
    return v if isinstance(v, dict) else {}


# ── 呼び口の見分け（正本） ──
def calls_action(uses, foundation):
    """step の `uses:` の値が土台の action public-guard か。@ の前の道を、土台の `<owner>/<repo>/public-guard`（大小を問わない）か
    `./public-guard`（土台そのもの）と全体で比べる。版の印は問わない。似た名の action・fork・名を道に含む別の出所は呼び口でない。
    土台の名が読めない時（foundation が空）だけ、道の最後が public-guard の呼び口を数える（照らさないより多く照らす）。"""
    path = str(uses or "").strip().partition("@")[0]
    if path == LOCAL_ACTION:
        return True
    if foundation:
        return path.lower() == (foundation + "/public-guard").lower()
    return "/" in path and path.rsplit("/", 1)[-1] == "public-guard"


def triggers(wf):
    """workflow の on: の起こり方の名の集まり（字・並び・写像のどれでも）。"""
    on = wf.get("on", wf.get("true", ""))   # YAML 1.1 では on が真偽に読まれる事がある（ここは字で読む）
    if isinstance(on, dict):
        return {str(k) for k in on}
    if isinstance(on, list):
        return {str(k) for k in on}
    return {str(on)} if str(on).strip() else set()


def literal_false(cond):
    """if: の値が字どおりの false か（`false`・`${{ false }}`）。式は評価しない（字どおりでなければ走り得る）。"""
    s = str(cond).strip() if isinstance(cond, str) else ""
    m = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", s)
    return (m.group(1) if m else s).strip().lower() == "false"


# 土台の action public-guard を呼ぶ 1 つの step。job=job の id・check=必須の検査として出る名（job の name、無ければ id）・
# uses=uses: の値・ref=@ の後（無ければ ""）・local=./public-guard（土台そのもの）・inputs=with: の写像・
# counts=PR・push の検査として走るか・why_not=数えない訳。
# （dataclass は使わない: 守りの hook は sys.modules に載せずに読み込むので、dataclass の型の解決が落ちる）
Call = namedtuple("Call", "job check uses ref local inputs counts why_not")


def calls(text, foundation):
    """workflow の text の、job の steps の中で土台の action public-guard を呼ぶ step の並び（数えない物も counts=False で）。
    job の外・コメントの行・run: の塊の中の字・job の名だけは呼び口でない。"""
    wf = load(text)
    jobs = wf.get("jobs")
    if not isinstance(jobs, dict):
        return []
    runs = bool(triggers(wf) & set(RUNS_ON_CHANGE))
    out = []
    for job_id, job in jobs.items():
        if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
            continue
        name = job.get("name")
        check = name if isinstance(name, str) and name.strip() else job_id
        for step in job["steps"]:
            if not isinstance(step, dict) or not isinstance(step.get("uses"), str):
                continue
            if not calls_action(step["uses"], foundation):
                continue
            why = ("PR・push で走らない（on: %s）" % "・".join(sorted(triggers(wf))) if not runs else
                   "job %s の if: が false" % job_id if literal_false(job.get("if")) else
                   "step の if: が false" if literal_false(step.get("if")) else "")
            uses = step["uses"].strip()
            out.append(Call(job=str(job_id), check=str(check), uses=uses, ref=uses.partition("@")[2],
                            local=uses.partition("@")[0] == LOCAL_ACTION,
                            inputs=step["with"] if isinstance(step.get("with"), dict) else {},
                            counts=not why, why_not=why))
    return out


def counted(text, foundation):
    """数える呼び口だけ（PR・push で走り、job と step の if: が字どおりの false でない）。"""
    return [c for c in calls(text, foundation) if c.counts]


def deny_words_files(text, foundation):
    """数える呼び口の with: の deny-words-file の値の並び（重なりを除く・空は除く）。"""
    out = []
    for c in counted(text, foundation):
        v = c.inputs.get("deny-words-file")
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
    return out


def guard_args(call):
    """呼び口の with: から guard.py の引数（action.yml の run と同じ組み方）。式（${{ }}）の値は手元で決まらないので ValueError。"""
    args = []
    words = str(call.inputs.get("deny-words-file") or "").strip()
    skip = str(call.inputs.get("pattern-skip") or "").strip()
    for v in (words, skip):
        if "${{" in v:
            raise ValueError("with: の値が式で、手元では決まらない: %s" % v)
    if words:
        args += ["--deny-words-file", words]
    if skip:
        args += ["--pattern-skip"] + skip.split()
    return args


def main(argv=None):
    ap = argparse.ArgumentParser(description="workflow の public-guard の呼び口を読む")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("guard-args", help="必須の検査の job の呼び口の with: から guard.py の引数を 1 行 1 つで出す")
    g.add_argument("workflow")
    g.add_argument("--check", default=CHECK)
    a = ap.parse_args(argv)
    try:
        with open(a.workflow, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print("✗ workflow を読めない: %s" % e, file=sys.stderr)
        return 2
    # 土台の名は問わない（手元の検査は土台そのものの workflow を読む＝呼び口は ./public-guard）
    found = [c for c in counted(text, "") if c.check == a.check]
    if len(found) != 1:
        print("✗ %s の job %s に数える public-guard の呼び口が %d 個（1 つに決まらない）" % (a.workflow, a.check, len(found)),
              file=sys.stderr)
        return 2
    try:
        args = guard_args(found[0])
    except ValueError as e:
        print("✗ %s" % e, file=sys.stderr)
        return 2
    print("\n".join(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
