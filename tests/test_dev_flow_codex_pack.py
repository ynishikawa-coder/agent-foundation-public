"""codex_pack.py（Codex へ渡すパックの builder）の守りが効くかを、作り物の repo で見る。"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

BUILDER = (Path(__file__).resolve().parent.parent
           / "plugins" / "dev-flow" / "skills" / "codex" / "codex_pack.py")
TODAY = "2026-11-11"


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "tools").mkdir(parents=True)
    (r / "cases" / "acme").mkdir(parents=True)
    (r / "config").mkdir()
    (r / "tools" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (r / "cases" / "acme" / "flow.py").write_text("STEP = 1\n", encoding="utf-8")
    values = {"dev-flow": {"codex": {
        "self_allow": ["tools/*"],
        "clients": {"acme": {"opt_in": True, "no_training_tier": True,
                             "expires": "2026-12-31", "paths": ["cases/acme/*"]}},
    }}}
    (r / "config" / "skill-values.json").write_text(json.dumps(values), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                    "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=r, check=True)
    return r


def run(repo, out, *args):
    cmd = [sys.executable, str(BUILDER), "--task", "t1", "--purpose", "見る", "--scope", "全部",
           "--done", "指摘が 0", "--out-dir", str(out), "--today", TODAY, *args]
    return subprocess.run(cmd, cwd=repo, capture_output=True, text=True)


def test_self_の作り物はパックになり印と錨が付く(repo, tmp_path):
    out = tmp_path / "out"
    res = run(repo, out, "--file", "tools/calc.py")
    assert res.returncode == 0, res.stderr
    pack = (out / "t1" / "pack.md").read_text(encoding="utf-8")
    assert pack.startswith("<!-- codex-egress-dest: self -->")
    assert "def add" in pack
    assert (out / "t1" / "goal.txt").read_text(encoding="utf-8").strip() == "指摘が 0"


def test_秘密が混じると書かずに止まる(repo, tmp_path):
    fake = "gh" + "p_" + "A1b2" * 10  # 作り物のトークンの形（file に字で残さない）
    (repo / "tools" / "leak.py").write_text(f"T = '{fake}'\n", encoding="utf-8")
    out = tmp_path / "out"
    res = run(repo, out, "--file", "tools/leak.py")
    assert res.returncode == 1
    assert "秘密の形を検出" in res.stderr
    assert "細目 §3「まず構造を疑う」" in res.stderr.strip().splitlines()[-1], "中止の理由だけを返す古い形に戻った"
    assert fake not in res.stdout + res.stderr
    assert not (out / "t1").exists()


def test_self_allow_の外と値の表が無い時は既定_deny(repo, tmp_path):
    (repo / "notes.md").write_text("メモ\n", encoding="utf-8")
    res = run(repo, tmp_path / "o1", "--file", "notes.md")
    assert res.returncode == 1 and "self_allow の外" in res.stderr
    (repo / "config" / "skill-values.json").unlink()
    res = run(repo, tmp_path / "o2", "--file", "tools/calc.py")
    assert res.returncode == 1 and "既定 deny" in res.stderr


def test_顧客の物は自動で決めず_self_を騙れない(repo, tmp_path):
    res = run(repo, tmp_path / "o1", "--file", "cases/acme/flow.py")
    assert res.returncode == 1 and "自動では決めない" in res.stderr
    res = run(repo, tmp_path / "o2", "--dest", "self", "--file", "cases/acme/flow.py")
    assert res.returncode == 1 and "顧客の物の path が混じる" in res.stderr


def test_顧客の物は許しと期限の内だけ(repo, tmp_path):
    res = run(repo, tmp_path / "o1", "--dest", "client:acme", "--file", "cases/acme/flow.py")
    assert res.returncode == 0, res.stderr
    res = run(repo, tmp_path / "o2", "--dest", "client:acme", "--file", "cases/acme/flow.py",
              "--today", "2027-01-01")
    assert res.returncode == 1 and "期限切れ" in res.stderr
    res = run(repo, tmp_path / "o3", "--dest", "client:other", "--file", "cases/acme/flow.py")
    assert res.returncode == 1 and "既定 deny" in res.stderr


def test_dry_run_は書かない(repo, tmp_path):
    out = tmp_path / "out"
    res = run(repo, out, "--file", "tools/calc.py", "--dry-run")
    assert res.returncode == 0 and "dry-run" in res.stdout
    assert not out.exists()


def load_builder():
    # プラグインの dir に __pycache__ を作らない（写しの目録が正本とずれる）。
    spec = importlib.util.spec_from_file_location("codex_pack", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


# 作り物の秘密の形（字を組み立てて作る＝この file に秘密の形を字で残さない）。
X = "Ab3d" * 10
FAKE_SECRETS = {
    "JWT": "e" + "yJ" + X[:20] + "." + X[:20] + "." + X[:12],
    "Bearer": "Authorization: Bear" + "er " + X[:24],
    ".env 形の行": "AWS_SECRET_ACCESS" + "_KEY=" + X[:20],
    ".env 形の行 (TOKEN)": "API" + "_TOKEN=" + X[:20],
    "Google の API 鍵": "AI" + "za" + X[:35],
    "sk- 20〜39 字": "s" + "k-" + X[:24],
    "引用符なしの api_key": "api" + "_key: " + X[:24],
    "GitHub 20 字": "gh" + "p_" + X[:24],
    "DB の接続文字列": "postgre" + "sql://db.example.invalid/app",
    "合言葉のタグ": "<pass" + "word>hunter22</password>",
}


@pytest.mark.parametrize("label", sorted(FAKE_SECRETS))
def test_写す元の秘密の形は_1_つずつ止まる(label):
    blocks, _ = load_builder().scan(f"x = 1\n{FAKE_SECRETS[label]}\n")
    assert blocks, f"{label} が block 0"


def test_式や参照は止めない():
    blocks, _ = load_builder().scan("key = obj.client_secret\napi_key = settings.api_key_value_from_env\n")
    assert not blocks, blocks


def test_送り出しの記録は値の表が在る時だけ本文なしで書く(repo, tmp_path):
    out = tmp_path / "out"
    assert run(repo, out, "--file", "tools/calc.py").returncode == 0
    assert not (repo / "logs").exists()
    vals = json.loads((repo / "config" / "skill-values.json").read_text(encoding="utf-8"))
    vals["dev-flow"]["codex"]["egress_log"] = "logs/egress.jsonl"
    (repo / "config" / "skill-values.json").write_text(json.dumps(vals), encoding="utf-8")
    assert run(repo, tmp_path / "o2", "--file", "tools/calc.py").returncode == 0
    lines = (repo / "logs" / "egress.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[-1])
    assert rec["result"] == "作った" and rec["files"] == ["tools/calc.py"] and len(rec["sha256"]) == 64
    assert "def add" not in lines[-1]


# ── 高エントロピーの塊（鍵らしい字）は既定で止める（オーナー同意 2026-11-19）──
def fake_chunk(seed: str) -> str:
    """作り物の高エントロピーの塊（この file に字で残さない＝実行時に組む）。"""
    import base64
    import hashlib
    return base64.b64encode(hashlib.sha512(seed.encode()).digest()).decode().rstrip("=")


def put_chunk(repo, seed="作り物"):
    tok = fake_chunk(seed)
    (repo / "tools" / "blob.py").write_text(f"x = 1\nBLOB = '{tok}'\n", encoding="utf-8")
    return tok


def set_values(repo, **kw):
    p = repo / "config" / "skill-values.json"
    vals = json.loads(p.read_text(encoding="utf-8"))
    vals["dev-flow"]["codex"].update(kw)
    p.write_text(json.dumps(vals), encoding="utf-8")


def test_高エントロピーの塊が混じると書かずに止まり_字を出さず場所と指紋を出す(repo, tmp_path):
    tok = put_chunk(repo)
    out = tmp_path / "out"
    res = run(repo, out, "--file", "tools/blob.py")
    assert res.returncode == 1
    assert "高エントロピーの塊" in res.stderr
    assert "tools/blob.py の 2 行目" in res.stderr
    assert "sha256:" in res.stderr and "entropy_allow" in res.stderr   # 直し方と外し方を出す
    assert tok not in res.stdout + res.stderr
    assert not (out / "t1").exists()


def test_高エントロピーの塊は_dry_run_でも止まる(repo, tmp_path):
    put_chunk(repo)
    res = run(repo, tmp_path / "out", "--file", "tools/blob.py", "--dry-run")
    assert res.returncode == 1 and "高エントロピーの塊" in res.stderr


def test_ふつうのコードと低いエントロピーの長い字は止めない(repo, tmp_path):
    (repo / "tools" / "plain.py").write_text(
        "def very_long_function_name_for_testing_purposes_only():\n"
        "    return 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
        "COMMIT = '0123456789abcdef0123456789abcdef01234567'\n", encoding="utf-8")
    res = run(repo, tmp_path / "out", "--file", "tools/plain.py")
    assert res.returncode == 0, res.stderr


def test_誤って止まる塊は値の表の指紋か正規表現で外せる(repo, tmp_path):
    import hashlib
    tok = put_chunk(repo)
    fp = hashlib.sha256(tok.encode()).hexdigest()[:12]
    set_values(repo, entropy_allow=[f"sha256:{fp}"])
    assert run(repo, tmp_path / "o1", "--file", "tools/blob.py").returncode == 0
    set_values(repo, entropy_allow=[r"[A-Za-z0-9+/]{86}"])
    assert run(repo, tmp_path / "o2", "--file", "tools/blob.py").returncode == 0
    # 別の塊は外れない（外すのは名指した物だけ）
    set_values(repo, entropy_allow=[f"sha256:{fp}"])
    put_chunk(repo, "別の作り物")
    assert run(repo, tmp_path / "o3", "--file", "tools/blob.py").returncode == 1


def test_値の表の外し方が読めない時は止める(repo, tmp_path):
    put_chunk(repo)
    for bad in (["sha256:xyz"], ["("], [""]):
        set_values(repo, entropy_allow=bad)
        res = run(repo, tmp_path / "o", "--file", "tools/blob.py")
        assert res.returncode == 1 and "entropy_allow" in res.stderr, bad


def test_止めた時の送り出しの記録に塊の字を書かない(repo, tmp_path):
    tok = put_chunk(repo)
    set_values(repo, egress_log="logs/egress.jsonl")
    assert run(repo, tmp_path / "o", "--file", "tools/blob.py").returncode == 1
    line = (repo / "logs" / "egress.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    rec = json.loads(line)
    assert rec["result"] == "中止" and rec["block"] == ["高エントロピーの塊"]
    assert tok not in line


@pytest.mark.parametrize("raw", ['["並び"]', '{"dev-flow": ""}', '{"dev-flow": [1]}', '{"dev-flow": {"codex": "字"}}'])
def test_値の表の形が違えば黙って空にせず止める(repo, tmp_path, raw):
    (repo / "config" / "skill-values.json").write_text(raw, encoding="utf-8")
    res = run(repo, tmp_path / "o", "--file", "tools/calc.py")
    assert res.returncode == 1 and "Traceback" not in res.stderr and "値の表" in res.stderr, raw


def test_渡した値の表が無い時は止める(repo, tmp_path):
    res = run(repo, tmp_path / "o", "--file", "tools/calc.py", "--values", str(tmp_path / "無い.json"))
    assert res.returncode == 1 and "値の表が無い" in res.stderr
