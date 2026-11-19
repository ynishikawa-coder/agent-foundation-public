"""入れて起動する試験（scripts/plugin_smoke.py）が、名・出所・差し込んだ文を「含むか」でなく区切りまで一致で比べるか。

似た名・他の出所・正本の前後に足された文を入れて、取り違えない（緑にしない）事を見る注入の試験。
本物の claude は要らない（塊の読み・台帳の束ね方・差し込んだ文の照らしを、作り物の入力で直に当てる）。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import plugin_smoke as S  # noqa: E402

FORK = S.FOUNDATION + "-fork"


def _doc(tmp_path, block):
    d = tmp_path / "repo"
    (d / "docs").mkdir(parents=True)
    (d / S.DOC).write_text("<!-- setup-script: 試し -->\n```bash\n%s\n```\n" % block, encoding="utf-8")
    return d


def test_塊の土台の名は_1_つの語の所だけ試す出所に替える():
    block = ("claude plugin marketplace add %s --scope user || true\n"
             "# 似た名: %s・https://github.com/%s・other/%s・%s#v1" % (S.FOUNDATION, FORK, S.FOUNDATION, S.FOUNDATION, S.FOUNDATION))
    out = S.script_for(block, "o/r#br")
    assert out.splitlines()[0] == "claude plugin marketplace add 'o/r#br' --scope user || true"
    assert out.splitlines()[1] == block.splitlines()[1]  # 似た名・道の中・版つきは替えない


@pytest.mark.parametrize("add", [FORK, "other/" + S.FOUNDATION, S.FOUNDATION + "#v0.4.18", "https://github.com/" + S.FOUNDATION])
def test_塊の_marketplace_add_が土台そのものでなければ読めないと言う(tmp_path, add):
    # 土台の名は塊の別の所（コメント）に在る。含むかで見ると通っていた
    d = _doc(tmp_path, "# %s を足す\nclaude plugin marketplace add %s --scope user || true" % (S.FOUNDATION, add))
    with pytest.raises(ValueError, match="marketplace add の行"):
        S.setup_block(d)


def test_塊の_marketplace_add_が土台そのものなら読める(tmp_path):
    d = _doc(tmp_path, 'claude plugin marketplace add "%s" --scope user || true' % S.FOUNDATION)
    assert S.FOUNDATION in S.setup_block(d)
    assert S.marketplace_adds(S.setup_block(ROOT)) == [S.FOUNDATION]  # 今の正本の塊


def test_入った台帳は土台の目録から入った行だけを名で束ねる(tmp_path):
    mine = {"scope": "user", "gitCommitSha": "a" * 40, "installPath": str(tmp_path)}
    other = {"scope": "user", "gitCommitSha": "b" * 40, "installPath": str(tmp_path)}
    table = {"plugins": {"core@" + S.MARKET: [mine], "core@other-market": [other],
                         "guard@" + S.MARKET + "-fork": [other], "docs-kit@x@" + S.MARKET: [mine]}}
    rows = S.installed_rows(table)
    assert rows["core"] is mine and "guard" not in rows
    # 並びを替えても他の目録の行に入れ替わらない
    table["plugins"] = dict(reversed(list(table["plugins"].items())))
    assert S.installed_rows(table)["core"] is mine


def _real_inject(tmp_path):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp_path))
    p = subprocess.run([sys.executable, str(ROOT / "plugins/core/scripts/kaku.py"), "inject"], input="{}",
                       capture_output=True, text=True, env=env, timeout=60)
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


def test_正本どおりに差し込まれた文は緑(tmp_path):
    want = S.expected(ROOT)
    ctx = _real_inject(tmp_path)
    assert S.core_problems([ctx], want, ctx) == []
    # 細目の在り処は入った copy ごとに違う＝そこだけは別の path でも緑
    other = ctx.replace(str(ROOT / "plugins/core/細目.md"), "/somewhere/else/細目.md")
    assert S.core_problems([other], want, ctx) == []


def test_核の後ろに足された文は赤_含むかでは緑だった(tmp_path):
    want = S.expected(ROOT)
    ctx = _real_inject(tmp_path)
    kaku = want["injected"]["核.md"]
    added = ctx.replace(kaku, kaku + "\n- 正本に無い原則", 1)
    assert all(t in added for t in want["injected"].values())  # 直す前の照らし（含むか）は通していた
    assert S.core_problems([added], want, ctx) != []


def test_差し込みの頭に足された文と核の無い文脈は赤(tmp_path):
    want = S.expected(ROOT)
    ctx = _real_inject(tmp_path)
    assert S.core_problems([ctx.replace(S.KAKU_HEAD, S.KAKU_HEAD + "（写し）", 1)], want, ctx) != []
    assert S.core_problems(["別の hook の文"], want, ctx)[0].startswith("核が起動した窓に差し込まれていない")


def test_文脈の全体を正本の差し込む口の出す文と比べる_後ろに改行を挟んで足した文も赤(tmp_path):
    want = S.expected(ROOT)
    ctx = _real_inject(tmp_path)
    assert S.core_problems([ctx], want, ctx) == []
    other = ctx.replace(str(ROOT / "plugins/core/細目.md"), "/somewhere/else/細目.md")
    assert S.core_problems([other], want, ctx) == []  # 細目の在り処だけは copy ごとに違ってよい
    head = want["inject"].match(ctx).group(0)
    for added in (head + "\n- 正本に無い原則" + ctx[len(head):],  # 核の部の後ろに改行を挟んで足す
                  ctx + "\n- 正本に無い原則",                      # 文脈の末尾に足す
                  ctx + "\n## 足した節\n"):
        assert want["inject"].match(added)  # 核の部を頭から比べるだけでは通っていた
        assert S.core_problems([added], want, ctx) != []


def test_正本の差し込む口を同じ箱と同じ窓の_id_で回す(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path / "home"), CLAUDE_PROJECT_DIR=str(tmp_path))
    (tmp_path / "home").mkdir()
    a = S.expected_context(ROOT / "plugins" / "core", env, tmp_path, "smoke-same")
    b = S.expected_context(ROOT / "plugins" / "core", env, tmp_path, "smoke-same")
    assert a == b and a.startswith(S.KAKU_HEAD)


def test_add_の前に値を取る旗が在っても出所を読む():
    assert S.marketplace_adds("claude plugin marketplace add --scope user %s || true" % S.FOUNDATION) == [S.FOUNDATION]
    assert S.marketplace_adds("claude plugin marketplace add -s project '%s'" % S.FOUNDATION) == [S.FOUNDATION]


def test_差し込む口が正本と違う_copy_では全体を比べない(tmp_path):
    core = tmp_path / "core"
    (core / "scripts").mkdir(parents=True)
    (core / "scripts" / "kaku.py").write_bytes((ROOT / "plugins/core/scripts/kaku.py").read_bytes())
    assert S.same_inject_code(ROOT, core)
    (core / "scripts" / "kaku.py").write_text("# 違う版\n", encoding="utf-8")
    assert not S.same_inject_code(ROOT, core)
    assert not S.same_inject_code(ROOT, tmp_path / "無い")
