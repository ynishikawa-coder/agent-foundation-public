"""同じ決まりを 2 か所で言い直さない（正本を指すだけ）: main へ入れる条件・値の表の鍵の既定と鍵の欄の形・
整地の雛形の依頼書に置く欄・後継へ渡す頼みと窓を立てる所（注入の試験＝言い直しを入れると赤）。"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
SCHEMA = json.loads((ROOT / "skill-values" / "schema.json").read_text(encoding="utf-8"))
SKILLS = sorted(PLUGINS.glob("*/skills/*/SKILL.md"))
CANON = {PLUGINS / "core" / "核.md", PLUGINS / "core" / "細目.md"}


# ── main へ入れる条件（核 §7・細目 §7 だけ）──
def restates_merge(text):
    """1 行に「レビュー」「緑」「絵」が揃う＝main へ入れる条件の並べ直し。"""
    return [ln for ln in text.splitlines() if "レビュー" in ln and "緑" in ln and "絵" in ln]


def merge_files():
    yield ROOT / "CONTRIBUTING.md"
    yield ROOT / ".github" / "pull_request_template.md"
    for p in PLUGINS.rglob("*.md"):
        if p not in CANON:
            yield p


def test_main_へ入れる条件を正本の外で並べ直さない():
    bad = {str(p.relative_to(ROOT)): restates_merge(p.read_text(encoding="utf-8")) for p in merge_files()}
    assert {k: v for k, v in bad.items() if v} == {}


def test_並べ直しを入れると赤():
    assert restates_merge("コードの完了は別窓レビュー green・試験が緑・実物を合意済みの全体の絵と照らすで決まる")


def test_verify_と_register_rule_は正本を指す():
    verify = (PLUGINS / "dev-flow" / "skills" / "verify" / "SKILL.md").read_text(encoding="utf-8")
    assert "- **コード（repo の中身）の完了と main へ入れる条件は核 §7・細目 §7「main へ入れる」だけが決める**（ここに条件を写さない＝別の目が決める）。" in verify
    assert "CI 緑＋別の窓のレビュー 1 回" not in verify


# ── 値の表: 鍵の既定は表の 1 か所・鍵の欄の形は 1 つ・common を読むと言うなら表に common の行 ──
def table_block(text):
    m = re.search(r"^## repo ごとの値[^\n]*\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M)
    return m.group(1) if m else ""


def key_cells(text):
    return [ln.strip().strip("|").split("|")[0].strip() for ln in table_block(text).splitlines()
            if ln.lstrip().startswith("| `")]


def table_problems(text):
    out = []
    block = table_block(text)
    keys = [k for cell in key_cells(text) for k in re.findall(r"`([^`]+)`", cell)]
    for k in keys:
        if k.split(".")[0] in SCHEMA["sections"] and not k.startswith("common."):
            out.append(f"鍵の欄 `{k}` が欄の名から書く形（短い鍵か common.<鍵> の 2 つの形にする）")
    for k in sorted(set(keys)):
        if [x for x in keys].count(k) > 1:
            out.append(f"鍵 `{k}` の行が 2 つ在る")
    outside = text.replace(block, "")
    for k in sorted(set(keys)):
        short = k.split(".")[-1]
        if re.search(r"`%s`（無ければ" % re.escape(k), outside) or re.search(r"`%s`（無ければ" % re.escape(short), outside):
            out.append(f"鍵 `{k}` の既定を表の外で言い直している（既定は表の 1 か所）")
    says_common = "`common.<鍵>`" in text
    has_common = any(k.startswith("common.") for k in keys)
    if says_common and block and not has_common:
        out.append("`common.<鍵>` から読むと書くのに、表に common の行が無い")
    return out


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: f"{p.parent.parent.parent.name}.{p.parent.name}")
def test_値の表の鍵は_1_つの形で既定は表の_1_か所(path):
    assert table_problems(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("bad", [
    "## repo ごとの値\n\n| 鍵 | 中身 | 既定 |\n|---|---|---|\n| `docs-kit.qa-html.limits` | x | y |\n\n## 次\n",
    "## repo ごとの値\n\n| 鍵 | 中身 | 既定 |\n|---|---|---|\n| `limits` | x | y |\n| `limits` | x | z |\n\n## 次\n",
    "## repo ごとの値\n\n| 鍵 | 中身 | 既定 |\n|---|---|---|\n| `record` | x | 聞く |\n\n## 次\n本文は `record`（無ければ各社の所）へ。\n",
    "`dev-flow.x.<鍵>` と `common.<鍵>` から読む。\n## repo ごとの値\n\n| 鍵 | 中身 | 既定 |\n|---|---|---|\n| `record` | x | y |\n\n## 次\n",
])
def test_値の表の崩れを入れると赤(bad):
    assert table_problems(bad)


def test_register_rule_は決定の記録の置き場を表の既定だけに置く():
    text = (PLUGINS / "dev-flow" / "skills" / "register-rule" / "SKILL.md").read_text(encoding="utf-8")
    assert "原文と経緯は `decision_record` へ（名指しが無い時の扱いは表の既定だけが決める）。" in text


def test_guard_rules_の例の整数は既定と同じ():
    """例の整数が既定と違うと、例を既定と読み違える（既定の正本は schema の 1 か所）。"""
    text = (PLUGINS / "guard" / "skills" / "guard-rules" / "SKILL.md").read_text(encoding="utf-8")
    example = json.loads(re.search(r"```json\n(.*?)```", text, re.S).group(1))["guard"]
    keys = SCHEMA["sections"]["guard"]["keys"]
    diff = {k: (example[k], v["default"]) for k, v in keys.items()
            if isinstance(v, dict) and v.get("type") == "int" and k in example and example[k] != v["default"]}
    assert diff == {}


# ── 整地の雛形: 依頼書に置く欄は frontmatter の鍵 ──
def test_整地の雛形は依頼書に置く欄を鍵で持つ():
    text = (PLUGINS / "dev-flow" / "skills" / "preimpl-cleanup" / "整地受領証.template.md").read_text(encoding="utf-8")
    front = text.split("---")[1]
    m = re.search(r"^依頼書に置く欄: (.+)$", front, re.M)
    assert m and [x.strip() for x in m.group(1).split(",")] == ["D", "E", "全件測り"]
    assert "依頼書の `## D.`" not in text, "置き場を注記の散文で言い直さない（鍵が正本）"


# ── 後継へ渡す頼み・窓を立てる所（細目 §8）と、文脈の知らせがそこを指す ──
def test_後継へ渡す頼みと窓を立てる所は細目_8_の_1_か所():
    text = (PLUGINS / "core" / "細目.md").read_text(encoding="utf-8")
    assert "- **文脈が重い時** — 区切りの良い所で後継へ移り、渡す頼みの文に ①目的 ②済んだ事 ③残り（並べ方は振る舞いの既定）④読む物 を書く。" in text
    assert "- **窓を立てる所** — 窓を立てる段には上限がある。" in text
    assert "後継は親（返し先）が立てる。" in text
    assert "判定の窓は書いた窓が立てて合流まで運ぶ（立てられなければ親へ PR と先端を添えて頼む）。" in text
    assert "後継の第一声" not in text and "**判定を頼む**" not in text


def test_文脈の知らせは細目_8_を指す():
    text = (PLUGINS / "guard" / "scripts" / "context_size.py").read_text(encoding="utf-8")
    assert text.count("細目 §8「文脈が重い時」") >= 3
    assert "細目 §8「文脈が重い時」「窓を立てる所」" in text


def test_畳んだ細目の文は_1_か所に残る():
    """止まる時の中身は 4 札の中身へ、根治の終わりの条件は核 §7 へ寄せた（細目を増やさない）。"""
    text = (PLUGINS / "core" / "細目.md").read_text(encoding="utf-8")
    assert '- **4 札の中身** — `⏳待ち` は誰を・いつまで、`🛑止まった` は何に当たったかと、誰が何をすれば続くかを書く。' in text
    assert '- **根治の終わり** — 終わったかは核 §7 の台帳の行で決める。' in text
    assert '「一部」には残りの行と直す窓の URL を書き、台帳を引いた結果（行の数と行き先ごとの数）を記録として報告に付ける。' in text
    assert "**止まる時**" not in text
