"""注入の試験: レビューは始めた時の決まり（決まりの版）で見る。

意図: PR のレビューの途中で main の見る点が増えても、初めの判定の版で見続け、後から足された点で red を返し合わない。
ただし安全の点（版によらず当てる点）は main の先端の名と値で必ず見る。
誤りの類をわざと入れて、道具（verdict_form）が拒む事を見る:
  後から足された点を要る扱いにする／安全の点を古い版で外す／初めの版と違う版で書く／初めの判定を古い版で書く／
  版が読めないのに形を通す。
1 段目の間は 3 行目の無い古い形と --first の無い古い呼び方を前の形で通す事も見る。
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import rules_git  # noqa: E402
from test_checker import GREEN, vf  # noqa: E402

V1 = rules_git.SKILL.read_text(encoding="utf-8")
ROW12 = next(l for l in V1.splitlines() if l.startswith("| 12 "))
LINE12 = "- 12 既定で止まる: pass/fail/N/A"
# v2: main に後から点 13 が足された版
V2 = V1.replace(ROW12, ROW12 + "\n| 13 作り物の新しい点 | 作り物 | 作り物 |").replace(LINE12, LINE12 + "\n- 13 作り物の新しい点: pass/fail")
WRITER = "session_WRITER01"


def verdict(ver, extra=""):
    text = GREEN.replace("決まりの版: 0123456789ab", "決まりの版: " + ver[:12])
    return text.replace("- 12 既定で止まる: N/A", "- 12 既定で止まる: N/A" + extra)


def run_main(tmp_path, text, first, monkeypatch, repo):
    monkeypatch.setenv("AF_RULES_GIT", str(repo))
    path = tmp_path / "v.md"
    path.write_text(text, encoding="utf-8")
    return vf.main(["verdict_form.py", str(path), "--writer", WRITER, "--head", "0123456789ab", "--first", first])


@pytest.fixture
def two(tmp_path):
    clone, v1 = rules_git.make(tmp_path / "g", V1)
    v2 = rules_git.push_version(clone, V2)
    return clone, v1, v2


def test_初めの版で見れば_後から足された点は要らない(two, tmp_path, monkeypatch):
    clone, v1, v2 = two
    rules, errs = vf.load_rules(v1[:12], v1[:12], clone)
    assert errs == [] and 13 not in rules.points and rules.tip == v2[:12]
    assert vf.check(verdict(v1), writer=WRITER, points=rules.points, values=rules.values, cards=rules.cards, rules=rules.ver) == []
    assert run_main(tmp_path, verdict(v1), v1[:12], monkeypatch, clone) == 0
    # 先端の版で見る判定には点 13 が要る（足された点は新しく始めた PR から効く）
    assert run_main(tmp_path, verdict(v2), "なし", monkeypatch, clone) == 1
    assert run_main(tmp_path, verdict(v2, "\n- 13 作り物の新しい点: pass"), "なし", monkeypatch, clone) == 0


def test_初めの版と違う版で書くと赤(two, tmp_path, monkeypatch):
    clone, v1, v2 = two
    rules, errs = vf.load_rules(v2[:12], v1[:12], clone)
    assert rules is None and any("初めの判定の版" in e for e in errs)
    assert run_main(tmp_path, verdict(v2, "\n- 13 作り物の新しい点: pass"), v1[:12], monkeypatch, clone) == 1


def test_初めの判定を古い版で書くと赤(two, tmp_path, monkeypatch):
    clone, v1, _ = two
    rules, errs = vf.load_rules(v1[:12], "なし", clone)
    assert rules is None and any("main の先端" in e for e in errs)
    assert run_main(tmp_path, verdict(v1), "なし", monkeypatch, clone) == 1


def test_1段目_決まりの版の行が無い古い形も前の形で通す(two, tmp_path, monkeypatch):
    # 壊れる変更の 1 段目（CONTRIBUTING.md §8）: 3 行目の無い判定・--first の無い呼び方・check を直に呼ぶ使う側の関所
    # （古い形.json の verdict-no-rules-line）は、前の形＝道具の入っている SKILL.md の点で照らして通す。形の崩れは今まで通り拒む
    clone, v1, _ = two
    old = verdict(v1).replace("決まりの版: %s\n" % v1[:12], "")
    assert "決まりの版" not in old
    assert run_main(tmp_path, old, v1[:12], monkeypatch, clone) == 0
    assert run_main(tmp_path, old, "なし", monkeypatch, clone) == 0
    assert vf.check(old, writer=WRITER, head="0123456789ab") == []
    assert vf.check_posted(old, None, writer=WRITER, head="0123456789ab") == []
    path = tmp_path / "o.md"
    path.write_text(old, encoding="utf-8")
    assert vf.main(["verdict_form.py", str(path), "--writer", WRITER, "--head", "0123456789ab"]) == 0
    broken = old.replace("- 5 秘密・顧客の物: pass\n", "")
    path.write_text(broken, encoding="utf-8")
    assert vf.main(["verdict_form.py", str(path), "--writer", WRITER, "--head", "0123456789ab"]) == 1
    assert vf.check(broken, writer=WRITER, head="0123456789ab") != []
    # 新しい形（3 行目在り）を --first 無しで出しても、古い呼び方として前の形で照らす（版の決まりは --first が在る時だけ）
    path.write_text(verdict(v1), encoding="utf-8")
    assert vf.main(["verdict_form.py", str(path), "--writer", WRITER, "--head", "0123456789ab"]) == 0


def test_安全の点は先端の名と値で必ず見る(tmp_path, monkeypatch):
    # 古い版は点 5 の名も値も違い「版によらず当てる点」の行も無い。先端は点 5 を改名し N/A を選べなくした
    old = V1.replace("| 5 秘密・顧客の物 |", "| 5 秘密 |").replace("- 5 秘密・顧客の物: pass/fail", "- 5 秘密: pass/fail/N/A")
    old = "\n".join(l for l in old.splitlines() if not l.startswith("- 版によらず当てる点:")) + "\n"
    tip = V1.replace("| 5 秘密・顧客の物 |", "| 5 秘密と顧客の物 |").replace("- 5 秘密・顧客の物: pass/fail", "- 5 秘密と顧客の物: pass/fail")
    clone, v1 = rules_git.make(tmp_path / "g", old)
    rules_git.push_version(clone, tip)
    rules, errs = vf.load_rules(v1[:12], v1[:12], clone)
    assert errs == [] and rules.points[5] == "秘密と顧客の物"
    text = verdict(v1)
    assert run_main(tmp_path, text, v1[:12], monkeypatch, clone) == 1   # 古い版の名（秘密・顧客の物）では赤
    assert run_main(tmp_path, text.replace("- 5 秘密・顧客の物: pass", "- 5 秘密: N/A"), v1[:12], monkeypatch, clone) == 1  # 古い版の名・値でも赤
    assert run_main(tmp_path, text.replace("- 5 秘密・顧客の物: pass", "- 5 秘密と顧客の物: pass"), v1[:12], monkeypatch, clone) == 0
    assert run_main(tmp_path, text.replace("- 5 秘密・顧客の物: pass", "- 5 秘密と顧客の物: N/A"), v1[:12], monkeypatch, clone) == 1


def test_先端に安全の点の行が無ければ止まる(tmp_path):
    tip = "\n".join(l for l in V1.splitlines() if not l.startswith("- 版によらず当てる点:")) + "\n"
    clone, v1 = rules_git.make(tmp_path / "g", V1)
    rules_git.push_version(clone, tip)
    with pytest.raises(ValueError):
        vf.load_rules(v1[:12], v1[:12], clone)


def test_版が読めない時は通さず_exit_2(two, tmp_path, monkeypatch):
    clone, v1, _ = two
    assert run_main(tmp_path, verdict("abcdefabcdef"), "abcdefabcdef", monkeypatch, clone) == 2    # 知らない版
    assert run_main(tmp_path, verdict(v1), v1[:12], monkeypatch, tmp_path / "無い") == 2           # 決まりの git が無い


def test_初めの判定は決まりの版を持つ物の初め():
    line1 = "レビューした窓: session_R1 判定: green"
    old = line1 + "\n見た先端: 0123456789ab\njob: x\n"
    a = line1 + "\n見た先端: 0123456789ab\n決まりの版: 111111111111\n"
    b = line1 + "\n見た先端: 0123456789ab\n決まりの版: 222222222222\n"
    assert vf.first_rules(["ただの話", old, a, b]) == "111111111111"
    assert vf.first_rules(["ただの話", old]) is None


def test_重なりの知らせは順と聞く時を言う(tmp_path):
    import json
    tool = ROOT / "scripts" / "pr_overlap.py"
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({"x.md": "@@ -1,2 +1,2 @@\n"}), encoding="utf-8")
    b.write_text(json.dumps({"#7": {"x.md": "@@ -1,1 +1,1 @@\n"}}), encoding="utf-8")
    res = subprocess.run([sys.executable, "-B", str(tool), "--self", str(a), "--others", str(b)], capture_output=True, text=True)
    assert res.returncode == 0 and "先に開いた PR が先に入り" in res.stdout and "逆向きの時だけ" in res.stdout
