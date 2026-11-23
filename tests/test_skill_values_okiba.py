"""SKILL の鍵の照らし（tests/test_skill_values.py の 2 つ）を、SKILL の全体の字でなく「repo ごとの値」の節の表の鍵の升で照らす。

意図: 鍵の一覧（skill-values/schema.json）の鍵が、SKILL の値の表（決めた置き場）の鍵の升に在る事を守り、本文の言い回しは縛らない。
課題: 試験が鍵を SKILL の全体から探していたので、鍵を表から本文・注記・コードの囲いへ移しても緑だった
  （common の鍵も全 SKILL を繋いだ字から探していた）。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、file の全体を字で探していた。
"""
import json
import re
from pathlib import Path

from md_yomi import 地の行, 表の行, 節

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
SCHEMA = json.loads((ROOT / "skill-values" / "schema.json").read_text(encoding="utf-8"))
_HEAD2 = re.compile(r"^##[ \t]+(.+?)[ \t]*$")


def _値の表の見出し(name: str) -> bool:
    return name.startswith("repo ごとの値") or name == "値の表"


def 値の表の鍵(text: str) -> set[str] | None:
    """「repo ごとの値…」か「値の表」の 2 段の見出しの節の、頭が「鍵」の表の 1 つ目の升の `…` の字の集まり。
    節が無い・2 つ在る時は None（注記・囲いの中の見出しは数えない）。"""
    names = [m.group(1) for l in 地の行(text) if (m := _HEAD2.match(l)) and _値の表の見出し(m.group(1))]
    if len(names) != 1:
        return None
    body = 節(text, names[0])
    if body is None:
        return None
    out = set()
    for row in 表の行(body, "鍵"):
        out |= set(re.findall(r"`([A-Za-z0-9_.\-*]+)`", row[0]))
    return out


def 鍵の外れ(text: str, plugin: str, skill: str, keys) -> list[str]:
    """鍵の一覧の鍵が値の表の鍵の升に在り、升の鍵が鍵の一覧に在るか。"""
    toks = 値の表の鍵(text)
    if toks is None:
        return [f"{plugin}.{skill}: 値の表の節が 1 つでない"] if keys else []   # 鍵の無い skill は表を持たなくてよい
    out = []
    for tok in sorted(toks):
        parts = tok.rstrip(".*").split(".")
        if parts[0] == "common":
            if parts[1] not in SCHEMA["sections"]["common"]["keys"]:
                out.append(f"{plugin}.{skill}: {tok} が鍵の一覧に無い")
            continue
        if parts[:2] == [plugin, skill]:
            parts = parts[2:]
        if parts[0] not in keys:
            out.append(f"{plugin}.{skill}: 値の表の鍵 {tok} が鍵の一覧（skill-values/schema.json）に無い")
    def pat(k):
        return re.compile(r"^(?:[\w.\-]+\.)?%s(?:\.\*)?$" % re.escape(k))
    out += [f"{plugin}.{skill}: 鍵の一覧の {k} が値の表の鍵の升に無い" for k in keys if not any(pat(k).match(t) for t in toks)]
    return out


def common_の外れ(texts: list[str]) -> list[str]:
    """common の鍵が、どれかの SKILL の値の表の鍵の升に在るか。"""
    toks = set().union(*[(v or set()) for v in map(値の表の鍵, texts)])
    return [f"common.{k} を値の表に持つ skill が無い" for k in SCHEMA["sections"]["common"]["keys"]
            if not any(t.rstrip(".*") == f"common.{k}" for t in toks)]


def skill_specs():
    for plugin, sec in SCHEMA["sections"].items():
        for skill, sk in sec.get("skills", {}).items():
            yield plugin, skill, sk.get("keys", {})


def _keys(plugin, skill):
    return {(p, s): k for p, s, k in skill_specs()}[(plugin, skill)]


def _skill(plugin, skill):
    return (PLUGINS / plugin / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")


def _all_skills():
    return [p.read_text(encoding="utf-8") for p in sorted(PLUGINS.glob("*/skills/*/SKILL.md"))]


def test_今は揃う():
    for plugin, skill, keys in skill_specs():
        assert 鍵の外れ(_skill(plugin, skill), plugin, skill, keys) == []
    assert common_の外れ(_all_skills()) == []


def test_注入_鍵の行を注記へ_囲いへ_本文へ移すと赤_説明を言い換えても緑():
    t, keys = _skill("docs-kit", "qa-html"), _keys("docs-kit", "qa-html")
    line = next(l for l in t.splitlines() if l.startswith("| `docs-kit.qa-html.limits`"))
    assert 鍵の外れ(t, "docs-kit", "qa-html", keys) == []
    for wrap in (lambda s: f"<!-- {s} -->", lambda s: f"```\n{s}\n```"):
        hidden = t.replace(line, wrap(line), 1)
        assert "`docs-kit.qa-html.limits`" in hidden
        assert any("limits" in x for x in 鍵の外れ(hidden, "docs-kit", "qa-html", keys))
    # 表の行を消し、同じ鍵を本文の文へ移す（全文に字は残る）
    prose = t.replace(line + "\n", "", 1) + "\n鍵 `docs-kit.qa-html.limits` で上限を上書きする。\n"
    assert any("limits" in x for x in 鍵の外れ(prose, "docs-kit", "qa-html", keys))
    cells = line.split("|")
    reworded = t.replace(line, "|".join(cells[:2] + [" 長さと問いの数の上限を替える "] + cells[3:]), 1)
    assert 鍵の外れ(reworded, "docs-kit", "qa-html", keys) == []


def test_注入_見出しを変えると赤_知らない鍵を表に足すと赤():
    t, keys = _skill("dev-flow", "codex"), _keys("dev-flow", "codex")
    head = next(l for l in t.splitlines() if l.startswith("## repo ごとの値"))
    assert 鍵の外れ(t.replace(head, "## 設定", 1), "dev-flow", "codex", keys) == ["dev-flow.codex: 値の表の節が 1 つでない"]
    row = next(l for l in t.splitlines() if l.startswith("| `"))
    added = t.replace(row, row + "\n| `dev-flow.codex.nai_kagi` | x | y |", 1)
    assert any("nai_kagi" in x for x in 鍵の外れ(added, "dev-flow", "codex", keys))


def test_注入_common_の鍵を表から本文へ移すと赤():
    k = next(iter(SCHEMA["sections"]["common"]["keys"]))
    tok = re.compile(r"`common\.%s(?:\.\*)?`" % re.escape(k))

    def 外す(s):
        lines = [tok.sub("`x`", l) if l.startswith("| `") else l for l in s.splitlines()]
        return "\n".join(lines) + f"\n\n本文で `common.{k}` を読む。\n"

    moved = [外す(s) for s in _all_skills()]
    assert all(f"common.{k}" in s for s in moved)
    assert common_の外れ(moved) == [f"common.{k} を値の表に持つ skill が無い"]
