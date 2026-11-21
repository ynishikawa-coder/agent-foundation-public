"""core の照らしと試験の読み口が「使う形」だけを見て、説明の文（地の文・引用・注釈・docstring・コードの囲みの例）で
名を挙げるだけの所を拾わないか。緩める向きの直しなので、使う形（命令のコード・欄・札・写しの文・本文の指し・
付けた印・呼ぶ形）が全部まだ拾われることを同じ file の注入の試験で示す。入力は全部作り物。"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from uses import py_calls, py_code, py_marks, sh_code, yaml_on, yaml_runs

ROOT = Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kaku = _load("kaku_uses_form", "plugins/core/scripts/kaku.py")
refs = _load("refs_uses_form", "plugins/core/scripts/refs.py")
ROWS = {r["id"]: r for r in kaku.olds_table()}
ADD = "claude plugin marketplace add ynishikawa-coder/agent-foundation-public --scope user"
ENTRY = "setup_plugins" + ".py"


# ── 古い形（reads: commands） ──
@pytest.mark.parametrize("rel,text", [
    ("README.md", "前の形は %s だけで入れていた。\n" % ADD),
    ("setup.sh", "# 前は %s だけだった\npython3 \"$af/scripts/%s\"\n" % (ADD, ENTRY)),
])
def test_古い形_入口を呼ばない_setup_は説明の文では名指さない(rel, text):
    assert not kaku.old_hit(ROWS["plugin-name-copy"], rel, text), text


@pytest.mark.parametrize("rel,text", [
    ("README.md", "入れ方:\n\n```bash\n%s\n```\n" % ADD),
    # 地の文の `…` は説明の例か使う命令かを構文で分けられない＝命令として読む（読む側に倒す）
    ("README.md", "土台は `%s` のように目録を足す。\n" % ADD),
    ("setup.sh", "%s\n# 入口 scripts/%s を呼ぶ（注釈の名は呼ぶことにならない）\n" % (ADD, ENTRY)),
    ("ci.yml", "run: |\n  %s  # %s\n" % (ADD, ENTRY)),
    ("x.py", '"""%s を呼ぶ"""\nimport os\nos.system("%s")\n' % (ENTRY, ADD)),
])
def test_古い形_入口を呼ばない命令は今も名指す(rel, text):
    assert kaku.old_hit(ROWS["plugin-name-copy"], rel, text), text


def test_古い形_入口を命令で呼ぶ_setup_は入口の側():
    text = "```bash\n%s\npython3 \"$af/scripts/%s\"\n```\n" % (ADD, ENTRY)
    assert not kaku.old_hit(ROWS["plugin-name-copy"], "docs.md", text)
    assert kaku.old_hit(ROWS["no-marketplace-update"], "docs.md", text)       # 入口を呼ぶ側の古い形は今も拾う


# ── 古い形（reads: prose） ──
@pytest.mark.parametrize("rid,text", [
    ("tasu-mado-heading", "前の欄「他の窓へ回す」は畳んで台帳にした\n"),
    ("tasu-mado-heading", "欄 `他の窓へ回す` は使わない\n"),
    ("tasu-mado-heading", "```md\n## 他の窓へ回す\n```\n"),
    ("tasu-mado-heading", "<!-- ## 他の窓へ回す は前の形 -->\n"),
    ("atonobin-tag", "札「[後の便｜…]」は [台帳へ｜…] に替えた\n"),
    ("atonobin-tag", "前の札 `〔後の便に回した事〕` は畳んだ\n"),
])
def test_古い形_引用と囲みで古い名を挙げるだけは名指さない(rid, text):
    assert not kaku.old_hit(ROWS[rid], "決まり.md", text), text


@pytest.mark.parametrize("rid,text", [
    ("tasu-mado-heading", "## 他の窓へ回す\n"),
    ("tasu-mado-heading", "**他の窓へ回す**\n"),
    ("tasu-mado-heading", "PR の本文は「## 他の窓へ回す」の欄に残りを書く\n"),
    ("tasu-mado-heading", "`## 他の窓へ回す` を書く\n"),
    ("atonobin-tag", "- [後の便｜整地] 〜\n"),
    ("atonobin-tag", "〔後の便に回した事〕\n"),
])
def test_古い形_欄と札は今も名指す(rid, text):
    assert kaku.old_hit(ROWS[rid], "決まり.md", text), text


def test_古い形_読み方の名が違えば一覧ごと読めない(tmp_path):
    bad = tmp_path / "古い形.json"
    bad.write_text('{"olds": [{"id": "x", "what": "w", "files": ["*.md"], "pattern": "a", "fix": "f", "example": "a",'
                   ' "reads": "なんでも"}]}', encoding="utf-8")
    with pytest.raises(ValueError):
        kaku.olds_table(bad)


# ── copies（引用と囲みは写しでない） ──
ORIGINAL = "戻せない操作の前に人に聞く — 強制 push・DB の削除・人の手が入った物や git に無い一点物の削除。"
COPIES = ROOT / "plugins" / "core" / "scripts" / "copies.py"


def _copies(tmp_path, text):
    f = tmp_path / "使う側の決まり.md"
    f.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, "-B", str(COPIES), str(f)], capture_output=True, text=True)


@pytest.mark.parametrize("text", [
    "# 決まり\n\n核の決まりはこう書いてある:\n\n> " + ORIGINAL + "\n",
    "# 決まり\n\n核の「" + ORIGINAL + "」を守る。\n",
    "# 決まり\n\n```text\n" + ORIGINAL + "\n```\n",
])
def test_copies_出所を示した引用と囲みは写しにしない(tmp_path, text):
    res = _copies(tmp_path, text)
    assert res.returncode == 0, res.stdout


def test_copies_自分の文として書いた写しは今も赤(tmp_path):
    res = _copies(tmp_path, "# 決まり\n\n- " + ORIGINAL + "\n")
    assert res.returncode == 1, res.stdout


# ── refs（コードの囲みの中は指しでない） ──
def test_refs_囲みの中の例の番号だけの指しは外れにしない_地の文は今も外れ():
    c = refs.contract()
    fenced = "例:\n\n```md\n細目 §3 を読む\n```\n"
    plain = "細目 §3 を読む\n"
    assert refs.check_text(c, fenced) == []
    assert refs.check_text(c, plain), "地の文の番号だけの指しが外れにならない"


# ── 試験の読み口（tests/uses.py） ──
def test_読み口_python_は注釈と_docstring_を除き_字の値と呼ぶ形は残す():
    src = '"""marketplaces を探さない"""\n# rev-parse は呼ばない\nX = "rev-parse"\nstart_cause(1)\n'
    code = py_code(src)
    assert "marketplaces" not in code and '"rev-parse"' in code
    assert "start_cause" in py_calls(src) and "start_cause" not in py_calls('"""start_cause(1) を呼ぶ"""\n')


def test_読み口_印は付けた物だけ():
    assert py_marks("import pytest\npytestmark = pytest.mark.real_claude\n") == {"real_claude"}
    assert py_marks("import pytest\n@pytest.mark.real_claude\ndef test_a():\n    pass\n") == {"real_claude"}
    assert py_marks('"""pytest.mark.real_claude を付ける"""\ndef test_a():\n    pass\n') == set()


def test_読み口_shell_は注釈を除き引用の中の_hash_は残す():
    assert sh_code("# conflict_markers.py を回す\ntrue\n").strip() == "true"
    assert "conflict_markers.py" in sh_code('python3 scripts/conflict_markers.py "#x"  # 注\n')


def test_読み口_workflow_は出来事と_run_だけ():
    yml = "# pull_request では回さない\non:\n  push:\n    branches: [main]\njobs:\n  a:\n    steps:\n      - name: workflow_dispatch\n        run: python3 x.py\n"
    assert yaml_on(yml) == {"push"}
    assert yaml_runs(yml) == ["python3 x.py"]
    assert "pull_request" in yaml_on("on: [push, pull_request]\n")


# ── 古い言い回しの残りの照らし（tests/test_core_plugin.py の old_words_left） ──
OLD = "他の窓へ" + "回す"


@pytest.mark.parametrize("rel,text", [
    ("x.py", "# 前の欄「## %s」は畳んだ\nX = 1\n" % OLD),
    ("x.py", '"""前は %s と書いていた。"""\nX = 1\n' % OLD),
    ("x.md", "前の欄「%s」は台帳に替えた\n" % OLD),
    ("x.md", "```md\n## %s\n```\n" % OLD),
    ("x.html", "<!-- %s は前の形 -->\n<p>今</p>\n" % OLD),
])
def test_古い言い回し_注釈と引用で挙げるだけは残りにしない(rel, text):
    from test_core_plugin import used_text
    assert OLD not in used_text(rel, text), text


@pytest.mark.parametrize("rel,text", [
    ("x.py", 'HEAD = "## %s"\n' % OLD),
    ("x.md", "## %s\n" % OLD),
    ("x.md", "本文は「## %s」の欄に書く\n" % OLD),
    ("x.json", '{"欄": "%s"}' % OLD),
])
def test_古い言い回し_使う所に在れば今も残り(rel, text):
    from test_core_plugin import used_text
    assert OLD in used_text(rel, text), text


# ── 読み口は 1 か所（kaku の「使う形の読み口」）。copies・refs・試験は呼ぶだけで、読み方を写さない ──
import inspect  # noqa: E402

copies = _load("copies_uses_form", "plugins/core/scripts/copies.py")
RULE = "戻せない操作の前に人に聞く"
NESTED = "````md\n```\n%s\n```\n````\n"          # 4 字の囲みの中に 3 字の囲み（3 字の行は閉じでない）


def test_読み口_囲みの見分けが_copies_refs_古い形_試験で揃う():
    """4 字の囲みの中の 3 字の行は閉じでない（CommonMark）。所ごとに読み方を写すと、どこかが 3 字の行で閉じて中を地の文に読む。"""
    from test_core_plugin import used_text
    assert refs.check_text(refs.contract(), NESTED % "細目 §3 を読む") == []
    assert RULE not in copies.own_text(NESTED % RULE)
    assert OLD not in used_text("x.md", NESTED % ("## " + OLD))
    assert not kaku.old_hit(ROWS["tasu-mado-heading"], "x.md", NESTED % ("## " + OLD))


def test_読み口_字の値の中の_slash_slash_は注釈でない():
    """.mjs の注釈の除き方が字の値の中の // を注釈として切ると、値の中の指し・古い名を見落とす。"""
    from test_core_plugin import used_text
    from test_skill_values_no_rule_copy import RULE_BUCKET, pointing
    src = 'const u = "https://x//common.rules"; // 注\n/* 注 */ const v = `a//b ' + OLD + '`;\n'
    assert RULE_BUCKET.search(pointing(".mjs", src))
    assert OLD in used_text("x.mjs", src) and "注" not in used_text("x.mjs", src)


def test_読み口_shell_の単引用の中の_backslash_は字のまま():
    assert kaku.sh_code("echo 'a\\' # 注\n") == "echo 'a\\' \n"
    assert "x.py" in kaku.sh_code('echo "a\\"" x.py # 注\n') and "注" not in kaku.sh_code('echo "a\\"" x.py # 注\n')


@pytest.mark.parametrize("rel,func", [
    ("plugins/core/scripts/copies.py", None),
    ("plugins/core/scripts/refs.py", None),
    ("tests/uses.py", None),
    ("tests/test_core_plugin.py", "used_text"),
    ("tests/test_skill_values_no_rule_copy.py", "pointing"),
])
def test_読み口_構造の読み方を写さない(rel, func):
    """囲み・注記・注釈の読み方（```・~~~・<!--・tokenize・// の除き）を自分で書かず、kaku の読み口を呼ぶ。"""
    if func:
        mod = _load("m_" + func, rel)
        src = inspect.getsource(getattr(mod, func))
    else:
        src = (ROOT / rel).read_text(encoding="utf-8")
    code = kaku.py_code(src)
    for w in ("```", "~~~", "<!--", "tokenize", "//[", "COMMENT", "startswith(\">\")"):
        assert w not in code, f"{rel} が構造の読み方 {w!r} を写している（kaku の読み口を呼ぶ）"


# ── 知らない形を黙って空にしない（reads: commands の .md） ──
@pytest.mark.parametrize("text", [
    "````bash\n%s\n````\n" % ADD,                       # 4 字の囲み
    "~~~~sh\n%s\n~~~~\n" % ADD,                         # 4 字の ~ の囲み
    "````bash\n```\n%s\n```\n````\n" % ADD,             # 囲みの中の 3 字の行
    "~~~\n%s\n~~~~~\n" % ADD,                           # 閉じは同じ字で数以上
    "入れ方:\n\n    %s\n" % ADD,                         # 4 字下げのコード
    "入れ方:\n\n\t%s\n" % ADD,                           # tab の字下げ
    "<pre>\n%s\n</pre>\n" % ADD,                        # <pre>
    "<PRE>%s</PRE>\n" % ADD,
    "```bash\n%s\n" % ADD,                              # 閉じの無い囲み（読めない形＝読む）
    "```bash\n%s\n``\n" % ADD,                          # 2 字の行は閉じでない
])
def test_古い形_知らない囲みの形も命令として読む(text):
    assert kaku.old_hit(ROWS["plugin-name-copy"], "README.md", text), text


def test_古い形_閉じの字が違えば閉じでない():
    """~~~ で開いた囲みは ``` の行で閉じない。中の命令の後の入口の呼び出しも同じ囲みの中（入口を呼ぶ側）。"""
    text = "~~~bash\n%s\n```\npython3 \"$af/scripts/%s\"\n~~~\n" % (ADD, ENTRY)
    assert not kaku.old_hit(ROWS["plugin-name-copy"], "x.md", text)
    assert kaku.old_hit(ROWS["no-marketplace-update"], "x.md", text)


def test_古い形_地の文の囲みに見える行は囲みでない():
    """` の囲みの開きの情報の欄に ` は入らない（```x``` は地の文の `…`）。"""
    assert kaku.md_blocks("```x``` は地の文\n")[0][0] == "text"


@pytest.mark.parametrize("text", [
    "```md\n## %s\n" % OLD,                             # 閉じの無い囲みは囲みと決められない＝地の文として読む
    "    ## %s\n" % OLD,                                # 字下げも地の文として読む
    "<pre>\n## %s\n</pre>\n" % OLD,
])
def test_古い形_読めない形の欄も今も名指す(text):
    assert kaku.old_hit(ROWS["tasu-mado-heading"], "決まり.md", text), text


# ── 古い形の行（reads: commands）の 4 行が、本物の照らし口で今も名指す ──
STALE = "claude plugin marketplace add ynishikawa-coder/agent-foundation-public --scope user || true\n" \
        "claude plugin marketplace update agent-foundation || true\n" \
        "python3 \"$af/scripts/%s\" || true\n" % ENTRY
SUBSTR = "af_old=\"$af_old\"';sys.exit(not(s.get(\"ref\") or a[2] not in json.dumps(s)))'\n" \
         "python3 \"$af/scripts/%s\"\n" % ENTRY


@pytest.mark.parametrize("rel,text", [
    ("setup.sh", STALE),
    ("setup.sh", STALE + "# claude plugin marketplace remove agent-foundation は前の形\n"),   # 注釈の remove は外すことにならない
    ("docs.md", "```bash\n%s```\n" % STALE),
    ("docs.md", "````bash\n%s````\n" % STALE),
    ("ci.yml", "run: |\n" + "".join("  " + ln + "\n" for ln in STALE.splitlines())),
])
def test_古い形_前の目録を外さない_setup_は今も名指す(rel, text):
    assert kaku.old_hit(ROWS["no-stale-catalog-remove"], rel, text), text


def test_古い形_前の目録を外さない_setup_を地の文で説明するだけは名指さない():
    text = "前は `%s` だけで、前の目録を外さなかった。\n" % STALE.splitlines()[0]
    assert not kaku.old_hit(ROWS["no-stale-catalog-remove"], "README.md", text)


@pytest.mark.parametrize("rel,text", [
    ("setup.sh", SUBSTR),
    ("docs.md", "```bash\n%s```\n" % SUBSTR),
    ("docs.md", "~~~~\n%s~~~~\n" % SUBSTR),
    ("x.py", 'import os\nos.system(%r)\n' % SUBSTR),
])
def test_古い形_出所を文字列の包含で見る_setup_は今も名指す(rel, text):
    assert kaku.old_hit(ROWS["stale-remove-substring"], rel, text), text


def test_古い形_出所を文字列の包含で見る形を注釈で挙げるだけは名指さない():
    text = "# 前は a[2] not in json.dumps(s) で見ていた\npython3 \"$af/scripts/%s\"\n" % ENTRY
    assert not kaku.old_hit(ROWS["stale-remove-substring"], "setup.sh", text)


def test_古い形_一覧の例の試験は本物の照らし口を通す():
    """一覧の例の試験（test_core_plugin）が行の読み方を通すこと: commands の行の例は .md の地の文に置けば当たらない。"""
    from test_core_plugin import example_files
    r = ROWS["no-stale-catalog-remove"]
    files = dict(example_files(r))
    assert files["x.md"].startswith("```") and not kaku.old_hit(r, "x.md", r["example"])
    assert all(kaku.old_hit(r, rel, text) for rel, text in files.items())


@pytest.mark.parametrize("text", [
    "~~~md\n## %s\n~~~~~\n" % OLD,                      # 閉じは同じ字で開きの数以上
    "````md\n## %s\n````\n" % OLD,                      # 4 字の囲み
    NESTED % ("## " + OLD),                             # 4 字の囲みの中の 3 字の行は閉じでない
])
def test_古い形_CommonMark_の囲みの中の欄は名指さない(text):
    assert not kaku.old_hit(ROWS["tasu-mado-heading"], "決まり.md", text), text


# ── common.rules の指し（test_skill_values_no_rule_copy.pointing）は禁じる語で説明と指示を分けない ──
def test_指し_禁じる語を添えて名を挙げても赤():
    from test_skill_values_no_rule_copy import RULE_BUCKET, pointing
    for line in ("`common.rules` は写さない。", "前の `common.rules.no_confirm` は畳んだ。"):
        assert RULE_BUCKET.search(pointing(".md", line)), line
    assert not RULE_BUCKET.search(pointing(".md", "<!-- common.rules -->")), "注記は指しでない"
