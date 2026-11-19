"""main の守り（ruleset）を正本 .github/rulesets/main.json から GitHub へ書き戻す（CI の job `rulesets` が呼ぶ）。

書く前に、鍵の置き場の environment `rulesets` が main からしか使えないかを照らす。
environment は既定でどの枝からも使え、名を初めて指した時は枝の制限なしで自動で作られるので、
制限が main だけでない・読めない時は書かずに赤で止める（既定で止める）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULESET = ROOT / ".github/rulesets/main.json"
ENV = "rulesets"
FIX = "直し: 赤の訳を 1 つずつ潰さず、細目 §3「まず構造を疑う」で原因から直す"


def env_problem(env: dict, policies: dict | None) -> str | None:
    """environment の返りと枝の決まりの返りから、main だけに絞れていない訳を返す（絞れていれば None）。"""
    dbp = env.get("deployment_branch_policy")
    if not dbp:
        return "environment rulesets に枝の制限が無い（どの枝からも鍵が使える）"
    if dbp.get("protected_branches") or not dbp.get("custom_branch_policies"):
        return "枝の制限が「選んだ枝だけ」になっていない"
    names = sorted((p.get("type", "branch"), p.get("name")) for p in (policies or {}).get("branch_policies", []))
    if names != [("branch", "main")]:
        return f"使える枝が main だけでない: {names}"
    return None


def diff(want: dict, got: dict) -> list[str]:
    """正本の鍵ごとに、書き戻した後の返りと違う鍵の並び。"""
    return [k for k in want if got.get(k) != want[k]]


def gh(*args: str, stdin: str | None = None) -> dict:
    out = subprocess.run(["gh", "api", *args], input=stdin, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main() -> int:
    if not os.environ.get("GH_TOKEN"):
        print("✗ 鍵 RULESET_TOKEN が無い。守りは書き戻していない")
        print(FIX)
        return 1
    repo, rid = os.environ["GITHUB_REPOSITORY"], os.environ["RULESET_ID"]
    try:
        env = gh(f"repos/{repo}/environments/{ENV}")
        pol = gh(f"repos/{repo}/environments/{ENV}/deployment-branch-policies")
    except subprocess.CalledProcessError as e:
        print(f"✗ environment {ENV} の枝の制限が読めない: {e.stderr.strip()}")
        print(FIX)
        return 1
    why = env_problem(env, pol)
    if why:
        print(f"✗ {why}。守りは書き戻していない（CONTRIBUTING の「main の守りの設定」の手順で直す）")
        print(FIX)
        return 1
    want = json.loads(RULESET.read_text(encoding="utf-8"))
    got = gh("-X", "PUT", f"repos/{repo}/rulesets/{rid}", "--input", "-", stdin=json.dumps(want))
    bad = diff(want, got)
    if bad:
        print(f"✗ 書き戻した後の守りが正本と違う: {bad}")
        print(FIX)
        return 1
    print("✅ 守りは正本どおり")
    return 0


if __name__ == "__main__":
    sys.exit(main())
