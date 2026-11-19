"""公開の検査（public-guard/guard.py）の出す前の文の口 `--text` が約束どおり効くかを見る。

守りの hook（guard の pr_text）が GitHub へ出す前の PR の題・本文・コメントをこの口で照らす。作り物の文で確かめる。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "public-guard" / "guard.py"
ENV_KEYS = ("AF_DENY_WORDS", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE", "GITHUB_ACTIONS", "GITHUB_EVENT_PATH")
MAIL = "someone" + "@" + "gmail.com"     # 形の照らしに当たる作り物（字のまま書くとこの file が公開の検査に当たる）


def _text_run(tmp_path, texts, words=None, env_extra=None):
    args = [sys.executable, str(GUARD)]
    for i, (where, body) in enumerate(texts):
        f = tmp_path / ("t%d.md" % i)
        f.write_text(body, encoding="utf-8")
        args += ["--text", "%s=%s" % (where, f)]
    if words is not None:
        wf = tmp_path / "deny.txt"
        wf.write_text("\n".join(words) + "\n", encoding="utf-8")
        args += ["--deny-words-file", str(wf)]
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env.update(env_extra or {})
    return subprocess.run(args, capture_output=True, text=True, env=env, cwd=tmp_path)


def test_出す前の文だけを照らし語を出力に出さない(tmp_path):
    p = _text_run(tmp_path, [("PR の題", "作り物ノ語 の直し"), ("PR の本文", "連絡は %s へ" % MAIL)], words=["作り物ノ語"],
                  env_extra={"AF_DENY_WORDS": "作り物ノ客"})
    assert p.returncode == 1
    assert "PR の題: 置かない語" in p.stdout and "PR の本文: メールアドレス" in p.stdout
    assert "作り物ノ語" not in p.stdout and "someone" not in p.stdout
    p = _text_run(tmp_path, [("コメント", "作り物ノ客 さんへの連絡")], env_extra={"AF_DENY_WORDS": "作り物ノ客"})
    assert p.returncode == 1 and "コメント: 顧客の語" in p.stdout and "作り物ノ客" not in p.stdout


def test_出す前の文はきれいなら緑で_CI_でも顧客の語が無いだけで止めない(tmp_path):
    p = _text_run(tmp_path, [("PR の本文", "作り物の確かめを足した")], words=["作り物ノ語"], env_extra={"GITHUB_ACTIONS": "true"})
    assert p.returncode == 0 and "出す前の文" in p.stdout


def test_出す前の文の指定の形が違えば使い方の誤り(tmp_path):
    p = subprocess.run([sys.executable, str(GUARD), "--text", "名だけ"], capture_output=True, text=True, cwd=tmp_path)
    assert p.returncode == 2
