"""レビューの判定の形の正本が 1 つ（checker の verdict_form.py）で、決まりの文（review-pr の SKILL.md）と守りの hook（guard の
pr_text）が同じ物を直に読むかを見る。

なぜ在るか（原因の台帳の同じ原因の 1 行・2026-11-19）: 判定の決まりが SKILL.md と verdict_form.py の 2 か所に在り、
①止める札が無く点に fail が在る判定を、文は green・コードは red とした ②書いた窓と同じ窓の判定を、SKILL の立ち位置は
「判定しない」・点の表は「red」とした ③判定のコメントかの見分けの正規表現が pr_text.py と verdict_form.py に別々に在った
④返しの 1 行を照らす・組むコードが無かった。
注入の試験: 決まりの文を正本と違える・pr_text に見分けの写しを戻す・返しの行を手で組む形を SKILL に戻すと赤。入力は全部作り物。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / "plugins" / "checker" / "scripts" / "verdict_form.py"
SKILL = ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md"
PR_TEXT = ROOT / "plugins" / "guard" / "scripts" / "pr_text.py"

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("verdict_form_one_source", FORM)
vf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vf)

WRITER = "session_01WRITER0100000000"
REVIEWER = "session_01REVIEW0100000000"
HEAD = "0123456789ab" + "0" * 28


def comment(verdict="green", fail_point=None, stop=False):
    points = vf.load_points()
    lines = ["レビューした窓: %s 判定: %s" % (REVIEWER, verdict), "見た先端: %s" % HEAD[:12], "job: 作り物", "",
             "## verdict", verdict]
    if verdict == "red":
        lines.append(vf.ROOT_CAUSE)
    lines += ["", "## 点"]
    for no, name in sorted(points.items()):
        val = "書いた窓 %s ≠ この窓" % WRITER if no == 3 else ("fail（作り物）" if no == fail_point else "pass")
        lines.append("- %d %s: %s" % (no, name, val))
    lines += ["", "## 所見", "- [%s｜実装] 作り物の所見" % ("止める" if stop else "台帳へ")]
    return "\n".join(lines) + "\n"


# ── 決まりの文は正本の文そのまま ──
def test_判定の決まりの文は正本と同じ():
    text = SKILL.read_text(encoding="utf-8")
    assert "- " + vf.JUDGE_RULE in text


def test_同じ窓の判定の決まりは立ち位置と点の表で同じ文():
    text = SKILL.read_text(encoding="utf-8")
    assert text.count(vf.SAME_EYE_RULE) == 2, "立ち位置と点の表の 3 の行の両方に同じ文を載せる"
    row3 = [ln for ln in text.splitlines() if ln.startswith("| 3 別の目 |")]
    assert row3 and row3[0].rstrip().endswith("| " + vf.SAME_EYE_RULE + " |")


def test_止める札が無くても点に_fail_が在れば_red():
    """注入: 点の fail を数えない判定（文の古い形）を green で出すと誤り。"""
    errs = vf.check(comment("green", fail_point=4), writer=WRITER, head=HEAD)
    assert any("判定は red" in e for e in errs), errs
    assert vf.check(comment("red", fail_point=4), writer=WRITER, head=HEAD) == []
    assert vf.check(comment("green"), writer=WRITER, head=HEAD) == []


# ── 判定のコメントかの見分けは verdict_form 1 つ ──
def test_pr_text_は判定の見分けを写さず_verdict_form_を呼ぶ():
    src = PR_TEXT.read_text(encoding="utf-8")
    assert "レビューした窓" not in src.split("def check_verdict")[0], "pr_text に判定の見分けの写しが在る"
    assert '"--looks"' in src


def run_form(*args):
    return subprocess.run([sys.executable, str(FORM), *args], capture_output=True, text=True)


def test_looks_は判定とふつうのコメントを分ける(tmp_path):
    f = tmp_path / "c.md"
    f.write_text(comment(), encoding="utf-8")
    assert run_form("--looks", str(f)).stdout.strip() == "verdict"
    f.write_text("作り物の話。判定: green と書いたふつうの文\n", encoding="utf-8")
    assert run_form("--looks", str(f)).stdout.strip() == "other"


# ── 返しの 1 行は道具が組む ──
def test_返しの行は形の通った判定からだけ組む(tmp_path):
    good = tmp_path / "g.md"
    good.write_text(comment("red", stop=True), encoding="utf-8")
    p = run_form(str(good), "--writer", WRITER, "--head", HEAD, "--return-line", "--pr", "7", "--branch", "claude/x",
                 "--ruler", "check_all: 緑 (5 本)")
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.strip() == ("判定 7 claude/x@%s verdict=red レビューした窓=%s 物差し=check_all: 緑 (5 本)"
                                " 直し=細目 §3「まず構造を疑う」" % (HEAD[:12], REVIEWER))
    bad = tmp_path / "b.md"
    bad.write_text(comment("green", stop=True), encoding="utf-8")   # 止める札が在るのに green＝形の誤り
    p = run_form(str(bad), "--writer", WRITER, "--head", HEAD, "--return-line", "--pr", "7", "--branch", "claude/x",
                 "--ruler", "x")
    assert p.returncode == 1 and "判定 7" not in p.stdout
    assert run_form(str(good), "--writer", WRITER, "--head", HEAD, "--return-line").returncode == 2


def test_SKILL_は返しの行を手で組む形を書かない():
    text = SKILL.read_text(encoding="utf-8")
    assert "--return-line" in text
    assert "`判定 <PR> <枝>@<SHA12>" not in text
