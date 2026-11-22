"""PR の型と整地の雛形は、決まりが名で指す欄を節・欄として決まった順と置き場で持つ。

意図: 決まりの文が「PR 本文の「X」」と名で指す欄と、整地の解決の欄（足す物・畳む物・注入の試験・残る穴）が、
型の中で節・欄として在り、順と置き場が崩れたら赤にする（言い回しは照らさない）。
課題: 試験が型の字の有無だけを見ていたので、節を注記へ入れる・順を崩す・欄を外へ出しても緑だった。
原因: 試験が文書の構造を読む口を持たず、字で照らしていた（構造は tests/md_yomi.py で読む）。
"""
import re
from pathlib import Path

from md_yomi import 太字の欄, 節, 見出し

ROOT = Path(__file__).resolve().parent.parent


PR_TPL = ROOT / ".github" / "pull_request_template.md"
SEICHI_TPL = ROOT / "plugins" / "dev-flow" / "skills" / "preimpl-cleanup" / "整地受領証.template.md"
_PR_の欄を指す = re.compile(r"PR [^「」\n]{0,3}?本文の「([^」:：]+)」")


def _欄の名(head):
    return re.split(r"[（(]", head)[0].strip()


def PR_の型の外れ(tpl, rules):
    """PR の型（tpl）が、決まりの文（rules）が「PR 本文の「X」」と名で指す欄を全部 ## の節として持ち、
    「下の「X」」と指す節が指す所より下に在り、残りの節が型の最後の節で原因の台帳を指すかを照らす。
    節は注記・コードの囲いの外の見出しだけを数える（注記の中の字は節でない）。"""
    heads = 見出し(tpl, 2)
    names = [_欄の名(h) for h in heads]
    bad = [f"決まりが指す欄が PR の型の節に無い: {x}" for x in sorted(set(_PR_の欄を指す.findall(rules))) if x not in names]
    if len(set(names)) != len(names):
        bad.append(f"同じ名の節が 2 つ在る: {names}")
    if "残り" not in names:
        bad.append("残りの節が無い")
    else:
        if names[-1] != "残り":
            bad.append(f"残りの節が型の最後でない（他の節は片付かない物を下の残りへ送る）: {names}")
        if "原因の台帳" not in heads[names.index("残り")]:
            bad.append("残りの節が原因の台帳を指さない")
    lines = tpl.splitlines()
    at = {_欄の名(m.group(1)): n for n, l in enumerate(lines) if (m := re.match(r"^## (.+)$", l))}
    for n, l in enumerate(lines):
        for x in re.findall(r"下の「([^」]+)」", l):
            if at.get(x, -1) <= n:
                bad.append(f"下の「{x}」と指す節が、指す所より下に無い（{n + 1} 行目）")
    return bad


def _PR_の決まり():
    files = sorted((ROOT / "plugins").rglob("*.md")) + [ROOT / "CONTRIBUTING.md"]
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


def test_PR_の型は決まりが名で指す欄を節として持ち_残りは最後で台帳を指す():
    rules = _PR_の決まり()
    assert {"残り", "使う側の写しの残り"} <= set(_PR_の欄を指す.findall(rules)), "決まりが PR 本文の欄を名で指さなくなった"
    assert PR_の型の外れ(PR_TPL.read_text(encoding="utf-8"), rules) == []


def test_注入_PR_の型の節を注記に入れる_順を崩す_名を変えると赤():
    tpl, rules = PR_TPL.read_text(encoding="utf-8"), _PR_の決まり()
    in_comment = tpl.replace("## 使う側の写しの残り", "<!-- ## 使う側の写しの残り -->")
    assert "## 使う側の写しの残り" in in_comment   # 字は残る（字の有無の照らしなら緑だった）
    assert any("使う側の写しの残り" in x for x in PR_の型の外れ(in_comment, rules))
    a, b = tpl.index("## 使う側の写しの残り"), tpl.index("## 残り（原因の台帳の行）")
    swapped = tpl[:a] + tpl[b:] + "\n" + tpl[a:b]
    assert any("最後でない" in x for x in PR_の型の外れ(swapped, rules))
    assert any("下の「残り」" in x for x in PR_の型の外れ(swapped, rules))
    assert any("台帳を指さない" in x for x in PR_の型の外れ(tpl.replace("## 残り（原因の台帳の行）", "## 残り"), rules))
    assert any("節に無い" in x for x in PR_の型の外れ(tpl.replace("## 使う側の写しの残り", "## 写しのこと"), rules))
    # 型と決まりの名を一緒に言い換えれば緑（試験は名の字でなく、決まりが指す名と型の節が合うかを見る）
    assert PR_の型の外れ(tpl.replace("使う側の写しの残り", "写しの残り"), rules.replace("使う側の写しの残り", "写しの残り")) == []


def 整地の解決の外れ(tpl):
    """整地の雛形の解決の節が、見出しの（…）に並べた欄を太字の欄としてこの順で持ち、畳む物と残る穴が
    原因の台帳へ送る道を欄の中に持つかを照らす（欄の外・別の節の字は数えない）。"""
    head = next((h for h in 見出し(tpl, 2) if re.match(r"^\d+\. 解決（", h)), None)
    if head is None:
        return ["解決の節が無い"]
    want = re.split(r"・|と", re.search(r"（(.+)）", head).group(1))
    fields = 太字の欄(節(tpl, head) or "")
    names = [n for n, _ in fields]
    bad = [f"解決の欄が無い: {w}" for w in want if w not in names]
    got = [n for n in names if n in want]
    if not bad and got != want:
        bad.append(f"解決の欄の順が見出しと違う: {got} ／ 見出し: {want}")
    body = dict(fields)
    bad += [f"{w} の欄が原因の台帳へ送らない" for w in ("畳む物", "残る穴") if w in body and "原因の台帳" not in body[w]]
    bad += [f"{w} の欄が空" for w in want if w in body and not body[w].strip(" :：\n")]
    return bad


def test_整地の解決は足す物_畳む物_注入の試験_残る穴を欄としてこの順で持つ():
    assert 整地の解決の外れ(SEICHI_TPL.read_text(encoding="utf-8")) == []


def test_注入_整地の解決の欄を消す_順を崩す_台帳を欄の外へ出すと赤():
    tpl = SEICHI_TPL.read_text(encoding="utf-8")
    for name in ("足す物", "畳む物", "注入の試験", "残る穴"):
        broken = tpl.replace(f"**{name}**", name, 1)   # 欄を壊し字は残す
        assert any(f"欄が無い: {name}" in x for x in 整地の解決の外れ(broken)), name
    a, b = tpl.index("**足す物**"), tpl.index("**行き先**")
    c, d = tpl.index("**注入の試験**"), tpl.index("**残る穴**")
    swapped = tpl[:a] + tpl[c:d] + tpl[b:c] + tpl[a:b] + tpl[d:]
    assert any("順" in x for x in 整地の解決の外れ(swapped))
    moved = tpl.replace("原因の台帳の行にして直す窓を書く", "直す窓を書く").replace("原因の台帳の行にする", "書く")
    assert any("畳む物 の欄が原因の台帳" in x for x in 整地の解決の外れ(moved + "\n原因の台帳\n"))
    assert any("残る穴 の欄が原因の台帳" in x for x in 整地の解決の外れ(moved))
