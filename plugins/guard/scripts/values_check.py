"""SessionStart — 値の表（config/skill-values.json）の土台の欄を鍵の一覧（lib/schema.json）で照らし、
知らない鍵・畳んだ鍵・型の違う値を名指しで知らせる（止めない＝窓の起動を妨げない）。

道具（check.mjs・codex_pack.py・make-deck の scripts）は、自分の欄に同じ問題があればその場で止まる。
守りの hook（guard）は、問題の鍵だけ既定で動く。どちらも黙って捨てないよう、起動の時に表全体を 1 度言う。
"""
import guard_common as G

HOOKS = {"start": "check"}


def check(payload, vals):
    path, problems = G.values_problems(payload)
    if not problems:
        return ""
    return (
        "[guard: 値の表] %s に、土台の道具に効かない・止まる値がある。表を直す（鍵の一覧の正本は土台の "
        "skill-values/schema.json・確かめる命令は python3 \"${CLAUDE_PLUGIN_ROOT}/lib/skill_values.py\" check）:\n%s"
        % (path, "\n".join("  - " + p for p in problems))
    )
