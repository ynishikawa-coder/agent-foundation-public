"""check_all が照らしていない検査・回らない検査・CI と手元の差を緑の側へ数えないか（注入の試験）。

原因の台帳 束 F1 の行:
- scripts/checks の 1 段の *.sh だけを拾い、.py の検査や下の dir の検査は黙って回らない → 置けば赤
- 終わり方 3 が「照らしていない」専用でない（exec した道具が別の訳で 3 を返しても照らしていないに入る）
  → 検査が AF_CHECK_UNCHECKED に訳（対象外: / 照らせない:）を書いた時だけ数える。訳なしの 3 は赤
- 照らしていない検査が在っても全体は緑（CI でも） → CI の「照らせない」は赤。「対象外」は名指すだけ
- 最後の行が CI と手元の差を名指さない → 「場 CI」「場 手元（…）」を必ず書く
- kaku_growth は main の先端（main への push・手元の main）では分かれ目が先端自身で必ず緑 → 先端の 1 つ前と比べる
- pr_writer は本文が渡っても PR の外では照らさない → PR_BODY が在れば照らす
"""
import subprocess
from pathlib import Path

import pytest
from entry_box import box_env, copy_entry

ROOT = Path(__file__).resolve().parent.parent
LIB = '. "$(dirname "$0")/../af_unchecked.sh"\n'


def box(tmp_path, checks):
    root = copy_entry(tmp_path / "box")
    (root / "tests").mkdir()
    (root / "tests" / "test_ok.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    (root / "scripts" / "checks").mkdir(parents=True)
    for name, body in checks.items():
        (root / "scripts" / "checks" / name).parent.mkdir(parents=True, exist_ok=True)
        (root / "scripts" / "checks" / name).write_text(body, encoding="utf-8")
    return root


def run(root, ci=False):
    r = subprocess.run(["bash", "scripts/check_all.sh"], cwd=root, capture_output=True, text=True,
                       env=box_env(ci=ci), timeout=300)
    return r.returncode, r.stdout.strip().splitlines()[-1], r.stdout + r.stderr


@pytest.mark.parametrize("name", ["x.py", "sub/y.sh", "z.bash"])
def test_注入_回らない形の検査を置くと赤(tmp_path, name):
    code, last, out = run(box(tmp_path, {name: "exit 1\n"}))
    assert code == 1 and f"scripts/checks/{name}" in last, out


def test_注入_訳の無い終わり方_3_は赤(tmp_path):
    """exec した道具が別の訳で 3 を返した形（前の形は「照らしていない」に数えて全体は緑）。"""
    code, last, out = run(box(tmp_path, {"t.sh": "exec python3 -c 'raise SystemExit(3)'\n"}))
    assert code == 1 and "訳の無い終わり方 3" in last, out


def test_注入_緑と照らしていないを両方言うと赤(tmp_path):
    code, last, out = run(box(tmp_path, {"t.sh": 'printf "照らせない: x\\n" > "$AF_CHECK_UNCHECKED"\nexit 0\n'}))
    assert code == 1 and "両方言った" in last, out


def test_照らせない検査は手元では名指し_CI_では赤(tmp_path):
    root = box(tmp_path, {"t.sh": LIB + "af_unchecked 照らせない 作り物の値が無い\n"})
    code, last, out = run(root)
    assert code == 0 and "照らしていない 1 本: t.sh" in last and "場 手元" in last, out
    code, last, out = run(root, ci=True)
    assert code == 1 and "CI で照らせない" in last and "場 CI" in last, out


def test_対象外の検査は_CI_でも名指して緑(tmp_path):
    code, last, out = run(box(tmp_path, {"t.sh": LIB + "af_unchecked 対象外 作り物の訳\n"}), ci=True)
    assert code == 0 and "対象外 1 本: t.sh（作り物の訳）" in last and "場 CI" in last, out


def test_最後の行は手元で_CI_との差を名指す(tmp_path):
    code, last, out = run(box(tmp_path, {}))
    assert code == 0 and "場 手元（CI と違い、飛ばし 0 本と照らしていない 0 本を赤にしていない）" in last, out


# ---- kaku_growth と pr_writer -----------------------------------------------------------------------

def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path, check, stub):
    """出所（bare）と、main を push した手元。check を写し、本体（stub の path）は渡された引数を出す作り物にする。"""
    work = tmp_path / "work"
    (work / "scripts" / "checks").mkdir(parents=True)
    for rel in ("scripts/checks/" + check, "scripts/pr_shape.py", "scripts/af_unchecked.sh"):
        (work / rel).write_bytes((ROOT / rel).read_bytes())
    (work / stub).parent.mkdir(parents=True, exist_ok=True)
    (work / stub).write_text("import sys\nprint('本体に来た', *sys.argv[1:])\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", "出所.git")
    _git(work, "init", "-q", "-b", "main")
    _git(work, "remote", "add", "origin", str(tmp_path / "出所.git"))
    for i in (1, 2):
        (work / "f.txt").write_text(str(i), encoding="utf-8")
        _git(work, "add", "-A")
        _git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", f"c{i}")
    _git(work, "push", "-q", "origin", "main")
    return work


def test_注入_kaku_growth_は_main_の先端で先端の_1_つ前と比べる(tmp_path):
    work = _repo(tmp_path, "kaku_growth.sh", "plugins/core/scripts/kaku.py")
    r = subprocess.run(["bash", "scripts/checks/kaku_growth.sh"], cwd=work, capture_output=True, text=True,
                       env=box_env(GITHUB_EVENT_NAME="push"))
    parent = _git(work, "rev-parse", "HEAD^1")
    assert f"本体に来た grow --base {parent}" in r.stdout, r.stdout + r.stderr


def test_注入_pr_writer_は本文が渡れば_PR_の外でも照らす(tmp_path):
    work = _repo(tmp_path, "pr_writer.sh", "plugins/checker/scripts/pr_writer.py")
    _git(work, "checkout", "-q", "-b", "claude/20261120-sakuramono")
    r = subprocess.run(["bash", "scripts/checks/pr_writer.sh"], cwd=work, capture_output=True, text=True,
                       env=box_env(PR_BODY="書いた窓: 作り物"))
    assert "本体に来た --branch claude/20261120-sakuramono" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("env,kind", [({"GITHUB_EVENT_NAME": "push"}, "対象外"), ({}, "照らせない")])
def test_pr_writer_は本文が無い訳を書いて_3(tmp_path, env, kind):
    work = _repo(tmp_path, "pr_writer.sh", "plugins/checker/scripts/pr_writer.py")
    why = tmp_path / "why"
    r = subprocess.run(["bash", "scripts/checks/pr_writer.sh"], cwd=work, capture_output=True, text=True,
                       env=box_env(AF_CHECK_UNCHECKED=str(why), **env))
    assert r.returncode == 3 and why.read_text(encoding="utf-8").startswith(kind + ":"), r.stdout + r.stderr
