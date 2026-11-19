"""守り irreversible・paid_upstream・values_keys が字の並びでなく読み手の語・決まりの正本で照らす約束（原因の台帳 rui82 の H1 の行）。

注入の試験: 台帳の行に挙がった「言い換えると通った形」を 1 つずつ入れ、今は拒む（止める・拾う・知らせる）ことを見る。
あわせて、前から通していた正しい形は通すことを見る。入力は全部作り物。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins" / "guard" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import cmd_read  # noqa: E402
import guard_common  # noqa: E402
import irreversible  # noqa: E402
import paid_upstream  # noqa: E402
import values_keys  # noqa: E402

KEY = "OPENAI" + "_API_KEY"          # この file を書く窓の守りに当たらないよう字を割る


def _git_repo(path):
    g = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    g.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})
    path.mkdir(parents=True, exist_ok=True)
    (path / "kept.txt").write_text("記録済み", encoding="utf-8")
    for c in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(path), *c], check=True, env=g, capture_output=True)
    return path


@pytest.fixture
def outside_scratch(monkeypatch, tmp_path):
    """tmp_path を一時の置き場でない所として見させる（一時の置き場の中は消しても戻せる扱いで通るため）。"""
    other = tmp_path / "別の一時の置き場"
    other.mkdir()
    monkeypatch.setattr(irreversible.tempfile, "gettempdir", lambda: str(other))
    return tmp_path


# ── irreversible 行 …8121-937f-cf0423cb51c4: 再帰の削除を rm と -r の字で見分けた ／ 段の頭の位置で形を見分けた（PR #81 の red）──
STOP = [
    # 台帳の行の形
    "python3 -c \"import shutil; shutil.rmtree('/home/x/data')\"",
    "git clean -fdx",
    "rsync -a --delete src/ /home/x/backup/",
    # PR #81 のレビューが red にした形（段の頭が読み手の表に無い・包みの option・中に包む・git の前の option）
    "if true; then dropdb prod; fi",
    "! dropdb prod",
    "timeout -s KILL 5 dropdb prod",
    "nice -n 5 dropdb prod",
    "env -u X dropdb prod",
    "echo dropdb prod | sh",
    "git -C . reset --hard",
    "git -c x=y reset --hard",
    "gh -R o/r repo delete --yes",
    "dd if=/dev/zero of=disk.img",
    "unlink f.txt",
    "aws s3 rb s3://b",
    "redis-cli FLUSHALL",
    "helm uninstall r",
    "git push --force origin x",
    'bash -c "rm -rf /home/x"',
]


@pytest.mark.parametrize("cmd", STOP)
def test_irreversible_は語の網で読めない形の削除も止める(cmd, outside_scratch):
    """直す前は rm と -r の字・段の頭（words[0]）の表で見たので、これらは素通りした。"""
    assert irreversible.bash_verbs(cmd, str(outside_scratch)), cmd


def test_irreversible_は_branch_D_を止める(outside_scratch):
    """直す前は git branch -D を「戻せる」として通した（試験も通す側に置いていた）。"""
    assert irreversible.match("Bash", {"command": "git branch -D old"}, str(outside_scratch), {})


def test_irreversible_は上書きのリダイレクトで戻せない_file_を消す形を止める(outside_scratch):
    repo = _git_repo(outside_scratch / "repo")
    (repo / "未記録.txt").write_text("消えると戻せない", encoding="utf-8")
    assert irreversible.bash_verbs(": > 未記録.txt", str(repo))
    assert not irreversible.bash_verbs(": > kept.txt", str(repo))          # git に記録済み＝戻せる
    assert not irreversible.bash_verbs(": > まだ無い.txt", str(repo))     # 在らない＝失う物が無い


@pytest.mark.parametrize("cmd", [
    "ls -la", "git status", "git log --grep=delete", "grep -rn rmtree src/", "gh release create v9",
    "vercel deploy --prod", "echo $(date)", "ruby x.rb", "git reset --soft HEAD~1", "cat a | grep b",
])
def test_irreversible_は読むだけと戻せる命令を通す(cmd, outside_scratch):
    assert not irreversible.bash_verbs(cmd, str(outside_scratch)), cmd


def test_irreversible_は綺麗な作業の木の_git_の捨てると記録済みの_rm_を通す(outside_scratch):
    repo = _git_repo(outside_scratch / "repo")
    assert not irreversible.bash_verbs("git reset --hard", str(repo))
    assert not irreversible.bash_verbs("rm -f kept.txt", str(repo))
    (repo / "未記録.txt").write_text("x", encoding="utf-8")
    assert irreversible.bash_verbs("git reset --hard", str(repo))
    assert irreversible.bash_verbs("rm -f 未記録.txt", str(repo))


@pytest.mark.parametrize("name, ti", [
    ("mcp__x__batch", {"batch": [{"op": "update"}, {"op": "delete", "id": "p1"}]}),
    ("mcp__x__notion-update-page", {"page_id": "p", "command": "replace_content", "new_str": "x"}),
    ("mcp__drive__update_file", {"fileId": "f", "trashed": True}),
    ("mcp__github__issue_write", {"method": "update", "issue_number": 1, "state": "closed"}),
    ("mcp__mail-x__sendEmail", {}),
])
def test_irreversible_は道具の入力の入れ子と引数で消す形を止める(name, ti):
    """直す前は入力の頂の action・method しか見ず、入れ子と state・trashed・command の値は素通りした。"""
    assert irreversible.tool_verbs(name, ti), name


@pytest.mark.parametrize("name, ti", [
    ("mcp__x__notion-update-page", {"page_id": "p", "command": "update_properties"}),
    ("mcp__github__issue_write", {"method": "update", "state": "open"}),
    ("mcp__x__notion-search", {"query": "delete"}),                     # 読むだけの道具の問いの字は見ない
    ("mcp__claude-code-remote__send_message", {"message": "古い枝を delete してよいか"}),
])
def test_irreversible_は戻せる道具の入力を通す(name, ti):
    assert not irreversible.tool_verbs(name, ti), name


# ── paid_upstream 行 …810e-971c-fb2bcef076a8: 試験の置き場を dir 名と file 名の形の列挙で見た ──
def test_paid_upstream_試験の_file_は試験の道具の集め方の決まりで読む(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    (repo / "conftest.py").write_text("from fixtures.llm_client import make_client\n", encoding="utf-8")
    (repo / "fixtures").mkdir()
    (repo / "fixtures" / "llm_client.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    assert paid_upstream.is_test_file(str(repo / "app" / "tests.py"))                # unittest・Django の既定 test*.py
    assert paid_upstream.is_test_file(str(repo / "conftest.py"))                     # 根の conftest.py
    assert paid_upstream.is_test_file(str(repo / "fixtures" / "llm_client.py"))      # conftest が取り込む fixtures
    assert not paid_upstream.is_test_file(str(repo / "src" / "client.py"))
    assert not paid_upstream.is_test_file(str(repo / "tests") + "/")                 # dir は file でない


def test_paid_upstream_pytest_の設定の_testpaths_と_python_files_を読む(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    (repo / "pytest.ini").write_text("[pytest]\ntestpaths = checks\npython_files = check_*.py\n", encoding="utf-8")
    assert paid_upstream.is_test_file(str(repo / "checks" / "helpers.py"))
    assert paid_upstream.is_test_file(str(repo / "pkg" / "check_api.py"))
    assert not paid_upstream.is_test_file(str(repo / "pkg" / "api.py"))


@pytest.mark.parametrize("path", ["app/tests.py", "conftest.py"])
def test_paid_upstream_Write_で決まりの試験の_file_へ鍵の名を書くと止める(tmp_path, path):
    """直す前は TEST_PATH_RE が app/tests.py・根の conftest.py を試験と見ず通した。"""
    repo = _git_repo(tmp_path / "repo")
    data = {"tool_name": "Write", "cwd": str(repo), "tool_input": {"file_path": str(repo / path),
                                                                    "content": "os.environ['%s']" % KEY}}
    assert paid_upstream.check(data, {})


def test_paid_upstream_道具の名でなく入力の形で見る(tmp_path):
    """直す前は Write・Edit・MultiEdit・NotebookEdit の名だけを見て、MCP の file 書き込みは素通りした。"""
    data = {"tool_name": "mcp__fs__write_file", "tool_input": {"path": str(tmp_path / "tests" / "test_a.py"),
                                                               "content": "KEY = '%s'" % KEY}}
    assert paid_upstream.check(data, {})
    grep = {"tool_name": "Grep", "tool_input": {"path": str(tmp_path / "tests" / "test_a.py"), "pattern": KEY}}
    assert not paid_upstream.check(grep, {})


# ── paid_upstream 行 …81b1-8156-e791a2d093fd: 書く道を > tee sed -i perl -i の字に限った ──
def test_paid_upstream_Bash_の知らない書き手で試験の_file_へ書くと止める(tmp_path):
    """直す前は cp・python -c の open・dd of= で試験の file へ書く形が見えなかった。"""
    repo = _git_repo(tmp_path / "repo")
    (repo / "src").mkdir()
    (repo / "src" / "real.py").write_text("KEY = '%s'\n" % KEY, encoding="utf-8")
    for cmd in ("cp src/real.py tests/test_llm.py",
                "dd if=src/real.py of=tests/test_llm.py",
                "python3 -c \"open('tests/test_llm.py','w').write('%s')\"" % KEY):
        data = {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": cmd}}
        assert "有料の上流" in paid_upstream.check(data, {}), cmd


@pytest.mark.parametrize("cmd", [
    "grep -rn %s tests/" % KEY,
    "pytest tests/ 2>&1 > /tmp/out.txt && echo %s" % KEY,
    "cp src/real.py src/copy.py",
])
def test_paid_upstream_Bash_の読みと試験の外への書き込みは通す(tmp_path, cmd):
    repo = _git_repo(tmp_path / "repo")
    (repo / "src").mkdir()
    (repo / "src" / "real.py").write_text("KEY = '%s'\n" % KEY, encoding="utf-8")
    assert not paid_upstream.check({"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": cmd}}, {})


# ── values_keys ──
BAD = {"guard": {"作り物の知らない鍵": 1}}


@pytest.fixture
def proj(tmp_path, monkeypatch):
    p = _git_repo(tmp_path / "proj")
    monkeypatch.delenv("SKILL_VALUES", raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(p))
    (p / "config").mkdir()
    (p / "config" / "skill-values.json").write_text("{}", encoding="utf-8")
    return p


def test_values_keys_Bash_で値の表へ書く形を止める(proj):
    """行 …8174-97d7-e06b8295f0e0: 直す前は Write・Edit・MultiEdit の 3 つしか見ず、jq … > 値の表 は止まらなかった。"""
    for cmd in ("jq '.x=1' a.json > config/skill-values.json", "sed -i 's/a/b/' config/skill-values.json",
                "cat > config/skill-values.json <<'EOF'\n{}\nEOF"):
        data = {"tool_name": "Bash", "cwd": str(proj), "tool_input": {"command": cmd}}
        assert "Write か Edit で書く" in values_keys.check(data, {}), cmd
    read = {"tool_name": "Bash", "cwd": str(proj), "tool_input": {"command": "jq . config/skill-values.json > /tmp/x.json"}}
    assert not values_keys.check(read, {})


def test_values_keys_SKILL_VALUES_が指す別の_path_への書き込みも照らす(proj, tmp_path, monkeypatch):
    """行 …8174: 直す前は path の末尾が config/skill-values.json の時だけ値の表と見た。"""
    other = tmp_path / "別の置き場" / "values.json"
    other.parent.mkdir()
    other.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(other))
    data = {"tool_name": "Write", "cwd": str(proj),
            "tool_input": {"file_path": str(other), "content": json.dumps(BAD, ensure_ascii=False)}}
    assert "作り物の知らない鍵" in values_keys.check(data, {})


def test_values_keys_書いた後に値の表へ知らない鍵が残れば知らせる(proj):
    """Bash の知らない書き手（python -c の open）は書く前に中身を読めないので、書いた後に表を照らして知らせる。"""
    (proj / "config" / "skill-values.json").write_text(json.dumps(BAD, ensure_ascii=False), encoding="utf-8")
    cmd = "python3 -c \"import json; json.dump({}, open('config/skill-values.json', 'w'))\""
    data = {"tool_name": "Bash", "cwd": str(proj), "tool_input": {"command": cmd}}
    assert "作り物の知らない鍵" in values_keys.after_bash(data, {})
    data["tool_input"]["command"] = "cat config/skill-values.json"
    assert not values_keys.after_bash(data, {})                         # 読むだけは照らさない


def test_values_keys_手で回す口は_SKILL_VALUES_と_CLAUDE_PROJECT_DIR_から表を引く(tmp_path):
    """行 …811a-91aa-f82b5726059c: 直す前は引数が無いと今の dir の相対 config/skill-values.json だけを読んだ。"""
    t = tmp_path / "表.json"
    t.write_text(json.dumps(BAD, ensure_ascii=False), encoding="utf-8")
    elsewhere = tmp_path / "よそ"
    elsewhere.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("SKILL_VALUES", "CLAUDE_PROJECT_DIR")}
    run = lambda e: subprocess.run([sys.executable, str(SCRIPTS / "values_keys.py")], cwd=str(elsewhere),  # noqa: E731
                                   capture_output=True, text=True, env=e)
    r = run(dict(env, SKILL_VALUES=str(t)))
    assert r.returncode == 1 and "作り物の知らない鍵" in r.stdout
    p = _git_repo(tmp_path / "proj")
    (p / "config").mkdir()
    (p / "config" / "skill-values.json").write_text(json.dumps(BAD, ensure_ascii=False), encoding="utf-8")
    r = run(dict(env, CLAUDE_PROJECT_DIR=str(p)))
    assert r.returncode == 1 and str(p / "config" / "skill-values.json") in r.stdout


def test_values_keys_起動の知らせは_guard_common_の読み口を通る(monkeypatch):
    """行 …81e3-9361-cb8fcc6cc02c: 直す前は resurface が表の path を自分で組み、guard_common の読む順と別に動いた。"""
    monkeypatch.setattr(guard_common, "values_problems", lambda data=None: ("/作り物/表.json", ["作り物の問題"]))
    out = values_keys.resurface({}, {})
    assert "/作り物/表.json" in out and "作り物の問題" in out


def test_values_keys_照らす_plugin_は手の列挙でなく鍵の一覧の正本の_sections(monkeypatch):
    """行 …8120-972e-d8b2ec162709: 手の列挙（FOUNDATION）だと、新しい土台の plugin の頭の鍵は照らされなかった。"""
    sv = values_keys.SV
    real = sv.schema()
    fake = dict(real, sections=dict(real["sections"], **{"作り物の新しい plugin": {"keys": {"今の鍵": {"type": "str"}}}}))
    monkeypatch.setattr(sv, "schema", lambda: fake)
    got = values_keys.unknown({"作り物の新しい plugin": {"今の鍵": "x", "知らない鍵": 1}})
    assert len(got) == 1 and got[0].startswith("作り物の新しい plugin.知らない鍵 ")
    assert not hasattr(values_keys, "FOUNDATION")
