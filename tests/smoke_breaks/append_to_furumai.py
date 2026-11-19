"""差し込む材料に節を足す（入れて起動する試験の注入の 1 つ）。

差し込む口はそのままに、差し込む材料（振る舞い.md）の末尾に正本に無い節を足す。
"""

ID = "差し込む材料に節を足す"
WANT = "差し込まれた文が正本の差し込む口"


def breaks(d):
    f = d / "plugins" / "core" / "振る舞い.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n## 足した節\n- 正本に無い原則\n", encoding="utf-8")
