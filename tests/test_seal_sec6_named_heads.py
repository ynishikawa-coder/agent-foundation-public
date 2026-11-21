"""spec-doc の seal.py が §6 の節を見出しの頭の番号か名で決め、別の節の見出しが決定照合を指すだけの物を数えないか（注入の試験）。"""
from test_dev_flow_spec_seal import HEAD, env, put15, seal  # noqa: F401  （env は fixture）


def test_別の節の見出しが決定照合を指すだけなら_6_の節に数えない(env):
    """前は「## 2. 決定照合の進め方」も §6 に数え、2 つ以上で止めた（名を挙げるだけの見出し）。今は §6 の節だけを照らす。"""
    repo, spec = env
    put15(spec, HEAD + "## 2. 決定照合の進め方\n\n- 作り物の手順: 関係なし\n\n"
                "## 6. 照合の結果\n\n| 決定 | 扱い |\n|---|---|\n| 作り物の決定 A | 未定 |\n")
    res = seal(repo, spec, "--match-only")
    assert res.returncode == 1 and "2 つ以上" not in res.stderr and "作り物の決定 A" in res.stderr
