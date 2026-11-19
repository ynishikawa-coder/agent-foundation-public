"""差し込みの後ろに節を足す（入れて起動する試験の注入の 1 つ）。

差し込む口の出す文の後ろに、節の切れ目で始まる正本に無い節を足す（入った口が checkout と違うと全体の比べを
飛ばしていた頃は緑だった）。
"""

ID = "差し込みの後ろに節を足す"
WANT = "kaku.py が正本の checkout と一字違わず同じでない"


def breaks(d):
    f = d / "plugins" / "core" / "scripts" / "kaku.py"
    text = f.read_text(encoding="utf-8")
    old = '"additionalContext": "\\n".join(parts)}'
    broken = text.replace(old, '"additionalContext": "\\n".join(parts) + "\\n## 足した節\\n- 正本に無い原則"}')
    assert broken != text, "kaku.py の inject() の形が変わった（この注入を合わせる）"
    f.write_text(broken, encoding="utf-8")
