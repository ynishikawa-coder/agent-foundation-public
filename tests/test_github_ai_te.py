"""GitHub の手は AI が打つ（オーナーの指摘 2026-11-19: 合流や守りの設定がオーナーの手に回っていた）。"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _細目():
    return (ROOT / "plugins/core/細目.md").read_text(encoding="utf-8")


def test_合流とPRはAIが打ち_付いていないrepoはpushで付ける():
    t = _細目()
    assert "**GitHub の手は AI が打つ**" in t
    assert "`add_repo`（access: push）で付けてから打つ" in t


def test_守りの設定は正本のfileをPRで直す():
    t = _細目()
    assert "`.github/rulesets/main.json` を PR で直す" in t
    assert "鍵が無い時は書き戻しが赤で止まる" in t


def test_人の手へ回すのは拒まれた時だけで原文を添える():
    t = _細目()
    assert "人の手へ回すのは、道具を実際に打って拒まれた時だけにし、拒みの原文を添える" in t
    assert "頼みの文に「AI は打たない」と書かない" in t


def test_守りの正本は今の必須の検査を全部持つ():
    d = json.loads((ROOT / ".github/rulesets/main.json").read_text(encoding="utf-8"))
    checks = {c["context"] for r in d["rules"] if r["type"] == "required_status_checks"
              for c in r["parameters"]["required_status_checks"]}
    assert {"check", "public-guard", "plugin-smoke"} <= checks


def test_書き戻しは鍵が無いと止まりPRでは回らない():
    t = (ROOT / ".github/workflows/rulesets.yml").read_text(encoding="utf-8")
    assert "exit 1" in t and "RULESET_TOKEN" in t
    assert "pull_request" not in t
