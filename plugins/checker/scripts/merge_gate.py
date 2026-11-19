#!/usr/bin/env python3
"""合流の関所を機械で照らす（目で読まない）。main へ入れてよい PR かを、PR の本文・commit・コメントだけから決める。

入れてよい（exit 0）のは次が全部そろう時だけ:
  1. 書いた窓が分かる: PR 本文の `書いた窓: <id>` が在る。merge でない commit の `Claude-Session:` の窓も書いた窓に数える。
  2. 今の先端に、書いた窓のどれとも別の窓の green が在る: 判定のコメントが verdict_form.py の形を通り
     （--writer に書いた窓・--head に今の先端）、1 行目の窓が書いた窓のどれでもない。
  3. 頼み直しを照らした: その green より前に red の判定が在れば、最後の red を前回として verdict_form.py の
     --previous と同じ照らし（前回の止めるを全部 `前回の N 番` で照らし、見た先端が動いた）を通る。
材料が欠けた・読めない時は入れない（exit 1・照らせない事を名指す）。

使い方:
  python3 merge_gate.py --json <PR の材料の JSON>      （{"body": str, "head": sha, "commits": [{"message": str, "parents": int}], "comments": [str]}）
  python3 merge_gate.py --github <owner/repo> --pr <番号> [--status]
      GitHub から材料を取る（環境の GITHUB_TOKEN）。--status は結果を今の先端の commit の状態 `merge-gate` に書く（CI 用）。
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verdict_form as VF  # noqa: E402  判定の形の正本（形をここに写さない）

WRITER = re.compile(r"^書いた窓:\s*(%s)\s*$" % VF.WINDOW, re.M)
TRAILER = re.compile(r"^Claude-Session:\s*\S*?(session_[A-Za-z0-9]+)\s*$", re.M)
CONTEXT = "merge-gate"


def writers_of(body, commits):
    """(PR 本文の書いた窓, 書いた窓の集まり〔揃えた形〕, 誤り)。PR 本文の名乗りが無ければ誤り（照らせない）。"""
    errs, ws, named = [], set(), None
    m = WRITER.search(body or "")
    if not m:
        errs.append("PR 本文に `書いた窓: <id>` が無い（別の目かを照らせない）")
    else:
        named = VF.norm(m.group(1))
        ws.add(named)
    for c in commits or []:
        if int(c.get("parents", 1)) > 1:
            continue    # main を取り込む merge の commit は書いた窓の名乗りに数えない
        for s in TRAILER.findall(c.get("message", "")):
            ws.add(VF.norm(s))
    return named, ws, errs


def judge(data, extra=None):
    """(入れてよいか, 理由の並び)。"""
    head = (data.get("head") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        return False, ["今の先端の SHA が分からない（照らせない）"]
    writer, writers, errs = writers_of(data.get("body", ""), data.get("commits", []))
    if errs:
        return False, errs
    verdicts = []
    for text in data.get("comments", []):
        first = (text or "").splitlines()[0].strip() if (text or "").strip() else ""
        m = VF.LINE1.match(first)
        if m:
            verdicts.append((VF.norm(m.group(1)), m.group(2), text))
    if not verdicts:
        return False, ["判定のコメントが 1 つも無い（別の窓のレビューを頼む）"]
    why = []
    last_red = None
    ok = False
    for reviewer, judged, text in verdicts:
        if judged == "red":
            last_red = text
            continue
        if reviewer in writers:
            why.append("green の窓 %s は書いた窓（自分の PR に green を付けない）" % reviewer)
            continue
        if VF.seen_head(text) != head[:12]:
            continue    # 見た後に push があった green は数えない（今の先端で見直す）
        e = VF.check(text, writer=writer, head=head, previous=last_red, extra=extra)
        if e:
            why.append("窓 %s の green が形を通らない: %s" % (reviewer, " / ".join(e)))
            continue
        ok = True
    if ok:
        return True, ["今の先端 %s に書いた窓（%s）と別の窓の green が在る" % (head[:12], "・".join(sorted(writers)))]
    if not why:
        why.append("今の先端 %s を見た別の窓の green が無い（最後の判定の後に push があったら見直しを頼む）" % head[:12])
    return False, why


def _get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _pages(url, token):
    out, page = [], 1
    while True:
        got = _get("%s%sper_page=100&page=%d" % (url, "&" if "?" in url else "?", page), token)
        out.extend(got)
        if len(got) < 100:
            return out
        page += 1


def from_github(repo, pr, token):
    api = "https://api.github.com/repos/%s" % repo
    p = _get("%s/pulls/%d" % (api, pr), token)
    commits = [{"message": c["commit"]["message"], "parents": len(c.get("parents", []))}
               for c in _pages("%s/pulls/%d/commits" % (api, pr), token)]
    comments = [c.get("body") or "" for c in _pages("%s/issues/%d/comments" % (api, pr), token)]
    return {"body": p.get("body") or "", "head": p["head"]["sha"], "commits": commits, "comments": comments}


def post_status(repo, sha, ok, text, token):
    body = json.dumps({"state": "success" if ok else "failure", "context": CONTEXT,
                       "description": text[:139]}).encode("utf-8")
    req = urllib.request.Request("https://api.github.com/repos/%s/statuses/%s" % (repo, sha), data=body, method="POST",
                                 headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"})
    urllib.request.urlopen(req, timeout=30).close()


def main(argv):
    args = argv[1:]
    opts = {}
    i = 0
    while i < len(args):
        if args[i] == "--status":
            opts["--status"] = True
            i += 1
            continue
        if args[i] in ("--json", "--github", "--pr", "--extra-points") and i + 1 < len(args) and args[i] not in opts:
            opts[args[i]] = args[i + 1]
            i += 2
            continue
        sys.stderr.write("知らない印か値の欠け・2 度書き: %s\n%s" % (args[i], __doc__))
        return 2
    try:
        extra = json.loads(opts["--extra-points"]) if "--extra-points" in opts else VF.load_extra()
        if "--json" in opts:
            data = json.loads(Path(opts["--json"]).read_text(encoding="utf-8"))
        elif "--github" in opts and "--pr" in opts:
            token = os.environ.get("GITHUB_TOKEN", "")
            if not token:
                raise ValueError("GITHUB_TOKEN が無い")
            data = from_github(opts["--github"], int(opts["--pr"]), token)
        else:
            sys.stderr.write(__doc__)
            return 2
    except Exception as e:  # noqa: BLE001  材料が読めない時は入れない（照らさずに通さない）
        print("merge-gate: 入れない（材料が読めない: %s）" % e)
        return 1
    ok, why = judge(data, extra=extra)
    print("merge-gate: %s" % ("入れてよい" if ok else "入れない"))
    for w in why:
        print("- " + w)
    if opts.get("--status"):
        # 関所は先端の commit の状態 `merge-gate` が持つ（コメントで回る時も同じ先端に付く）。書けたら job は緑で終える
        post_status(opts["--github"], data["head"], ok, why[0], os.environ["GITHUB_TOKEN"])
        return 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
