"""Codex のための物を畳んだ（2026-11-19 のオーナーの決定「Codex はもう使わない」）約束の注入の試験。

前の物を戻すと赤になる形で書く:
- skill dev-flow:codex・codex_pack.py・その試験を戻すと赤
- 値の表の型の正本に dev-flow.codex の欄を戻す・畳んだ欄の印を外すと赤（使う側の表の古い欄が黙って効く・黙って捨てられる）
- 道具・文書・試験が codex の道具の名を呼ぶ・指すと赤（変更の記録の断片と、畳んだ印の行は外す）
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill-values"))

import skill_values as SV  # noqa: E402

NAMES = ("codex_pack", "dev-flow:codex", "skills/codex")


def test_codex_の_skill_と道具が無い():
    assert not (ROOT / "plugins" / "dev-flow" / "skills" / "codex").exists()
    assert not list((ROOT / "tests").glob("test_dev_flow_codex*"))


def test_値の表の_codex_の欄は畳んだ欄として名指される():
    schema = json.loads((ROOT / "skill-values" / "schema.json").read_text(encoding="utf-8"))
    assert "codex" not in schema["sections"]["dev-flow"]["skills"]
    assert "dev-flow.codex" in schema["retired"]
    probs = SV.check({"dev-flow": {"codex": {"self_allow": ["tools/**"]}}})
    assert any("dev-flow.codex は畳んだ欄" in p for p in probs), probs


def test_道具と文書が_codex_の道具を指さない():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    hits = []
    for rel in files:
        if rel.startswith("CHANGELOG.d/") or rel == "tests/test_codex_folded.py" or (ROOT / rel).is_symlink():
            continue   # symlink は正本（skill-values/ ほか）を読んだ所で照らす
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        for n, ln in enumerate(text.splitlines(), 1):
            if rel == "skill-values/schema.json" and '"dev-flow.codex":' in ln:
                continue   # 畳んだ印の行（使う側の古い欄を名指す訳の文）
            if any(w in ln for w in NAMES) or "Codex の DEFER" in ln:
                hits.append(f"{rel}:{n}")
    assert not hits, hits
