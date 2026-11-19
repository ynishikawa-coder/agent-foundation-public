#!/usr/bin/env python3
"""合流の関所を機械で照らす（目で読まない）。main へ入れてよい PR かを、PR の本文・commit・コメント・出来事だけから決める。

入れてよい（exit 0）のは次が全部そろう時だけ（どれかを照らせない時も入れない＝既定で止める）:
  1. main へ向いた PR: base が main（既定の枝）で、本文に `積んだ基点:` が無い。base を後から main へ向け直した PR は、
     向け直した後に付いた判定だけを数える（積んだ差分だけを見た green で下の PR の commit を通さない）。
  2. 書いた窓が 1 つに決まる: PR 本文の `書いた窓: <id>` が在り、merge でない commit が全部 `Claude-Session:` で
     同じ窓を名乗る（id の 3 つの形 session_・cse_・UUID を揃えて比べる）。名乗りの無い commit・違う窓の commit は入れない。
  3. 判定は repo の持ち主・仲間（author_association が OWNER・MEMBER・COLLABORATOR）のコメントだけを数える。
  4. 今の先端を見た判定のうち最後の物が、書いた窓と別の窓の green で、verdict_form.py の形を通る
     （--writer に書いた窓・--head に今の先端）。green の後に red が付けば、その red が勝つ。
  5. 頼み直しを照らした: その green より前に red の判定が在れば、最後の red を前回として verdict_form.py の
     --previous と同じ照らし（前回の止めるを全部 `前回の N 番` で照らし、見た先端が動いた）を通る。
材料が欠けた・読めない時は入れない（exit 1・照らせない事を名指す）。

使い方:
  python3 merge_gate.py --json <PR の材料の JSON>
      {"body": str, "head": sha, "base": "main", "default_branch": "main", "base_changed_at": ISO 時刻か null,
       "commits": [{"message": str, "parents": int}],
       "comments": [{"body": str, "author_association": str, "created_at": ISO 時刻}]}
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
STACKED = re.compile(r"^積んだ基点:", re.M)
TRAILER = re.compile(r"^Claude-Session:\s*\S*?(%s)\s*$" % VF.WINDOW, re.M)
TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")   # 判定を数えるコメントの書き手（公開の repo の誰でも書けるコメントは数えない）
CONTEXT = "merge-gate"


def writer_of(body, commits):
    """(書いた窓〔揃えた形〕, 誤り)。本文の名乗りが無い・commit の名乗りが欠ける／違う時は誤り（照らせない）。"""
    m = WRITER.search(body or "")
    if not m:
        return None, ["PR 本文に `書いた窓: <id>` が無い（別の目かを照らせない）"]
    named, errs = VF.norm(m.group(1)), []
    for c in commits or []:
        if int(c.get("parents", 1)) > 1:
            continue    # main を取り込む merge の commit は名乗りを照らさない
        title = (c.get("message") or "").splitlines()[0][:30] if (c.get("message") or "").strip() else "(空)"
        got = {VF.norm(s) for s in TRAILER.findall(c.get("message") or "")}
        if not got:
            errs.append("commit「%s」に `Claude-Session:` の名乗りが無い（誰が書いたか照らせない）" % title)
        elif got != {named}:
            errs.append("commit「%s」の名乗り %s が本文の書いた窓 %s と違う（別の窓の commit が混ざる・積んだ PR の下の commit）"
                        % (title, "・".join(sorted(got)), named))
    return named, errs


def _comment(c):
    return c if isinstance(c, dict) else {"body": c}    # 字だけの材料は書き手が分からない＝数えない


def judge(data, extra=None):
    """(入れてよいか, 理由の並び)。"""
    head = (data.get("head") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        return False, ["今の先端の SHA が分からない（照らせない）"]
    base, default = data.get("base"), data.get("default_branch") or "main"
    if base != default:
        return False, ["PR の base が %s でない（%s）。積んだ PR は下の PR が入ってから main へ向け直し、頼み直す" % (default, base)]
    if STACKED.search(data.get("body") or ""):
        return False, ["本文に `積んだ基点:` が残る（積んだ差分だけを見た判定で main へ入れない。向け直したら本文から消して頼み直す）"]
    writer, errs = writer_of(data.get("body", ""), data.get("commits", []))
    if errs:
        return False, errs
    since = data.get("base_changed_at") or ""
    verdicts = []
    for c in map(_comment, data.get("comments", [])):
        text = c.get("body") or ""
        first = text.splitlines()[0].strip() if text.strip() else ""
        m = VF.LINE1.match(first)
        if not m:
            continue
        if c.get("author_association") not in TRUSTED:
            continue    # 持ち主・仲間でない人の判定は数えない
        if since and (c.get("created_at") or "") <= since:
            continue    # base を main へ向け直す前の判定（積んだ差分だけを見た物）は数えない
        verdicts.append((VF.norm(m.group(1)), m.group(2), text))
    if not verdicts:
        return False, ["数えられる判定のコメントが 1 つも無い（持ち主・仲間が書いた別の窓のレビューを頼む）"]
    at_head = [v for v in verdicts if VF.seen_head(v[2]) == head[:12]]
    if not at_head:
        return False, ["今の先端 %s を見た判定が無い（最後の判定の後に push があったら見直しを頼む）" % head[:12]]
    reviewer, judged, text = at_head[-1]
    if judged == "red":
        return False, ["今の先端の最後の判定が red（窓 %s）。直して頼み直す" % reviewer]
    if reviewer == writer:
        return False, ["green の窓 %s は書いた窓（自分の PR に green を付けない）" % reviewer]
    idx = verdicts.index(at_head[-1])
    reds = [t for _, j, t in verdicts[:idx] if j == "red"]
    e = VF.check(text, writer=writer, head=head, previous=reds[-1] if reds else None, extra=extra)
    if e:
        return False, ["窓 %s の green が形を通らない: %s" % (reviewer, " / ".join(e))]
    return True, ["今の先端 %s の最後の判定が書いた窓（%s）と別の窓 %s の green" % (head[:12], writer, reviewer)]


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
    comments = [{"body": c.get("body") or "", "author_association": c.get("author_association"),
                 "created_at": c.get("created_at") or ""}
                for c in _pages("%s/issues/%d/comments" % (api, pr), token)]
    moved = [e.get("created_at") or "" for e in _pages("%s/issues/%d/events" % (api, pr), token)
             if e.get("event") == "base_ref_changed"]
    return {"body": p.get("body") or "", "head": p["head"]["sha"], "base": p["base"]["ref"],
            "default_branch": p["base"]["repo"]["default_branch"], "base_changed_at": max(moved) if moved else None,
            "commits": commits, "comments": comments}


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
    if not ok:
        print("直し: 判定を足し直すだけで済ませず、なぜ関所を通らない PR になったかを細目 §3「まず構造を疑う」で原因から直す")
    if opts.get("--status"):
        # 関所は先端の commit の状態 `merge-gate` が持つ（コメントで回る時も同じ先端に付く）。書けたら job は緑で終える
        post_status(opts["--github"], data["head"], ok, why[0], os.environ["GITHUB_TOKEN"])
        return 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
