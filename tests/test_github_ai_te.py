"""GitHub の手は AI が打つ（オーナーの指摘 2026-11-19: 合流や守りの設定がオーナーの手に回っていた）。"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_付いていないrepoはpushで付けて打ち_拒まれた時だけ原文を添えて人へ回す():
    t = _read("plugins/core/細目.md")
    assert "repo が付いていなければ `add_repo`（push）で付けて打ち" in t
    assert "打って拒まれた時だけ拒みの原文を添えて人へ回す。" in t


def test_守りの設定は正本のfileをPRで直しCIが書き戻す():
    t = _read("CONTRIBUTING.md")
    assert "正本は `.github/rulesets/main.json`。直す時は AI がこの file を PR で直し" in t
    assert "鍵 `RULESET_TOKEN` が無い時は書き戻しが赤で止まる" in t


def test_守りの正本の必須の検査は重複なく今の3つ():
    d = json.loads(_read(".github/rulesets/main.json"))
    checks = [c["context"] for r in d["rules"] if r["type"] == "required_status_checks"
              for c in r["parameters"]["required_status_checks"]]
    assert len(checks) == len(set(checks)), f"必須の検査が重なっている: {checks}"
    assert set(checks) == {"check", "public-guard", "plugin-smoke"}


def test_書き戻しは鍵が無いと止まりPRでは回らない():
    t = _read(".github/workflows/rulesets.yml")
    assert 'if [ -z "$GH_TOKEN" ]' in t and "exit 1" in t
    assert "pull_request" not in t


def test_AIの道具で打てる手は自分で打ち_人にしか打てない手だけ手の窓で頼む():
    t = _read("plugins/core/細目.md")
    assert "push・PR・合流・調べる・見張る・Notion や Drive への書き込み）は自分で打つ。" in t
    assert "人にしか打てない手（許し・アカウントと支払い・PC やスマホにしか無い物・社外への go・他社のオーナーへの連絡）だけ" in t
