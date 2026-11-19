"""codex_pack.py: 32 字より短い鍵・字の種類の少ない鍵を通さないか（注入の試験）。

形の推し量り（32 字以上・エントロピー 4.0 以上）だけでは短い鍵・16 進の鍵が素通りしていた。
窓が持つ秘密の値そのもの（環境変数・.env）・その repo の git の物でない 16 進の塊・鍵らしい短い塊を、わざと入れて止まるかを見る。
"""
import os
import subprocess
import sys

import pytest

from test_dev_flow_codex_pack import BUILDER, TODAY, repo  # noqa: F401  （repo は fixture）


def run_env(repo, out, extra_env, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("AF_FAKE")}
    env.update(extra_env)
    cmd = [sys.executable, str(BUILDER), "--task", "t1", "--purpose", "見る", "--scope", "全部",
           "--done", "指摘が 0", "--out-dir", str(out), "--today", TODAY, *args]
    return subprocess.run(cmd, cwd=repo, capture_output=True, text=True, env=env)


def put(repo, line):
    (repo / "tools" / "leak.py").write_text(f"x = 1\n{line}\n", encoding="utf-8")


def short_value():
    # 作り物の短い値（この file に字で残さない＝実行時に組む）。英字だけ・9 字＝形では見分けられない鍵の類。
    return "".join(chr(ord("a") + (i * 7) % 26) for i in range(9))


def test_窓の環境変数の秘密の値はどんな形でも止め_名だけを出す(repo, tmp_path):
    val = short_value()
    put(repo, f"WORD = '{val}'")
    res = run_env(repo, tmp_path / "o", {"AF_FAKE_SERVICE_TOKEN": val}, "--file", "tools/leak.py")
    assert res.returncode == 1, res.stdout
    assert "窓が持つ秘密の値（環境変数 AF_FAKE_SERVICE_TOKEN）" in res.stderr
    assert val not in res.stdout + res.stderr
    assert not (tmp_path / "o" / "t1").exists()


def test_repo_の_env_の値も止める(repo, tmp_path):
    val = short_value()
    (repo / ".env.local").write_text(f"FAKE_DB_PASSWORD={val}\n", encoding="utf-8")
    put(repo, f"WORD = '{val}'")
    res = run_env(repo, tmp_path / "o", {}, "--file", "tools/leak.py")
    assert res.returncode == 1 and ".env.local の FAKE_DB_PASSWORD" in res.stderr


def test_秘密の名でない環境変数と値の無いパックは止めない(repo, tmp_path):
    val = short_value()
    put(repo, f"WORD = '{val}'")
    assert run_env(repo, tmp_path / "o1", {"AF_FAKE_LANGUAGE": val}, "--file", "tools/leak.py").returncode == 0
    assert run_env(repo, tmp_path / "o2", {"AF_FAKE_SERVICE_TOKEN": val}, "--file", "tools/calc.py").returncode == 0


def fake_hex(n):
    import hashlib
    return hashlib.sha256(b"fake-hex-key").hexdigest()[:n]


def fake_short(alphabet, n):
    import hashlib
    d = hashlib.sha256(alphabet.encode()).digest()
    return "".join(alphabet[b % len(alphabet)] for b in d[:n])


@pytest.mark.parametrize("label,tok", [
    ("git に無い 16 進の 32 字の鍵", fake_hex(32)),
    ("git に無い 16 進の 20 字の鍵", fake_hex(20)),
    ("英字と数字の 20 字の鍵", fake_short("abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789", 20)),
    ("小文字と数字の 24 字の鍵", fake_short("abcdefghijkmnopqrstuvwxyz0123456789", 24)),
])
def test_短い鍵と字の種類の少ない鍵を止め_字を出さない(repo, tmp_path, label, tok):
    put(repo, f"KEY = '{tok}'")
    res = run_env(repo, tmp_path / "o", {}, "--file", "tools/leak.py")
    assert res.returncode == 1, (label, res.stdout)
    assert "tools/leak.py の 2 行目" in res.stderr, label
    assert tok not in res.stdout + res.stderr, label


def test_止めた秘密の値は値の表の指紋で外せる(repo, tmp_path):
    import hashlib
    import json
    val = short_value()
    put(repo, f"WORD = '{val}'")
    p = repo / "config" / "skill-values.json"
    vals = json.loads(p.read_text(encoding="utf-8"))
    vals["dev-flow"]["codex"]["entropy_allow"] = ["sha256:" + hashlib.sha256(val.encode()).hexdigest()[:12]]
    p.write_text(json.dumps(vals), encoding="utf-8")
    assert run_env(repo, tmp_path / "o", {"AF_FAKE_SERVICE_TOKEN": val}, "--file", "tools/leak.py").returncode == 0
