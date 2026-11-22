"""起動の時の古い形の見張り（plugin core の SessionStart の inject）が、上限の秒に切られず・切られたら黙らない約束。

意図: 窓の起動で、使う側に残る土台の古い形を名指す見張りが最後まで照らし、照らせない時はそれを窓へ名指す。
課題: レビューの窓の起動で、見張りが 5 秒の上限で TimeoutError に切られた（古い形を照らし終えていない）。
原因: 照らしの重さ。行ごと（reads が commands の行が 4 つ）× main の木と checkout ごとに同じ .py を読み直し、
      .py の構文の読み（ast・tokenize）が 1 つの file に 8 回走っていた（この repo で 3.9 秒＝上限 5 秒の際）。
      読み口は (読み方, path, 中身) で決まるので、1 つの照らしの中で 1 回だけ作って分け合う。
"""
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "core" / "scripts" / "kaku.py"
spec = importlib.util.spec_from_file_location("kaku_one_parse", TOOL)
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)

PY = 'def f():\n    """説明"""\n    return 1  # 注釈\n'


def _git(*args):
    subprocess.run(["git", *map(str, args)], check=True, capture_output=True)


def _repo_with_origin(tmp_path, n_py):
    """main を持つ出所と、それを clone した作業の repo（main の木と checkout の中身が同じ）。"""
    src = tmp_path / "src"
    src.mkdir()
    for i in range(n_py):
        (src / f"m{i}.py").write_text(PY + f"X = {i}\n", encoding="utf-8")
    _git("init", "-q", "-b", "main", src)
    _git("-C", src, "add", "-A")
    _git("-C", src, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "x")
    work = tmp_path / "work"
    _git("clone", "-q", src, work)
    return work


def test_同じ中身の_py_は行と木をまたいで構文を1回だけ読む(tmp_path, monkeypatch):
    """注入: 行ごと・木ごとに読み口を作り直す形に戻す → py_code の回数が file の数を越えて赤。"""
    work = _repo_with_origin(tmp_path, 3)
    rows = [r for r in kaku.olds_table() if r.get("reads") == "commands"]
    assert len(rows) >= 2, "commands の行が 2 つ以上無いと、行をまたぐ読み直しを照らせない"
    calls = []
    real = kaku.py_code
    monkeypatch.setattr(kaku, "py_code", lambda text: calls.append(text) or real(text))
    scan = kaku.olds_scan(work, rows)
    assert scan["ref"] and scan["note"] is None, "main の木を読んでいない（checkout と木をまたぐ所を照らせていない）"
    assert len(calls) == 3, f"3 つの .py の構文を {len(calls)} 回読んだ（行×木ごとに読み直している）"


def test_読み口を分け合っても当たりは同じ(tmp_path):
    """読み口の分け合いで照らしの結果が変わらない（分け合わない old_hit と同じ）。"""
    rows = [r for r in kaku.olds_table() if r.get("reads") in ("commands", "prose")]
    texts = {"a.py": "x = 1\n", "b.md": "# 見出し\n本文\n"}
    for r in rows:
        texts[f"ex_{r['id']}.md"] = r["example"]
        texts[f"ex_{r['id']}.py"] = r["example"]
    views = {}
    for r in rows:
        for rel, text in texts.items():
            assert kaku.old_hit(r, rel, text, views) == kaku.old_hit(r, rel, text), (r["id"], rel)


def _inject(monkeypatch, tmp_path, project, bounded):
    """起動の hook（inject）を作り物の home で走らせ、差し込まれた文を返す。"""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    monkeypatch.setattr(kaku, "find_olds_bounded", bounded)
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert kaku.inject() == 0
    return json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]


def test_見張りが時間で切られたら窓へ名指し_手で照らす命令を添える(tmp_path, monkeypatch):
    """注入: わざと遅い見張り（上限 0.01 秒）→ 核は差し込み、古い形の見張りが動かなかった事と、古い形 0 と決まった
    のではない事と、上限なしで照らす命令を窓の文脈へ出す（黙って「古い形 0」にしない）。"""
    work = _repo_with_origin(tmp_path, 1)
    real = kaku.find_olds_bounded
    ctx = _inject(monkeypatch, tmp_path, work, lambda p: real(p, budget=0.01))
    assert "## 土台の見張り（古い形）が動かなかった" in ctx
    assert "TimeoutError" in ctx and "古い形 0 と決まったのではない" in ctx
    assert f"olds {work}" in ctx, "手で照らし直す命令が無い"


def test_古い形の表が壊れていたら窓へ名指し_黙らない(tmp_path, monkeypatch):
    """注入: 壊れた記録（古い形の表が JSON でない）→ 照らしを 0 と読まず、見張りが動かなかったと名指す。"""
    work = _repo_with_origin(tmp_path, 1)
    broken = tmp_path / "古い形.json"
    broken.write_text("{ 壊れた", encoding="utf-8")
    real = kaku.find_olds_bounded
    ctx = _inject(monkeypatch, tmp_path, work, lambda p: real(p, budget=60, table=broken))
    assert "## 土台の見張り（古い形）が動かなかった" in ctx
