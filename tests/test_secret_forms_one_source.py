"""鍵の形の正本は public-guard/guard.py の SECRET_PATTERNS の 1 か所で、codex のパックの builder も写さず直に読む
（原因の台帳 束 F-secret の注入の試験）。

前の誤りを入れると赤になる形で書く:
- 正本から Stripe の本番の鍵・OpenAI の project の鍵・AWS の一時の鍵 ID・サービスアカウントの鍵の JSON の形を消すと赤
- codex_pack が鍵の形を自分の表に写して持つ（正本を読まない）へ戻すと、正本にだけ足した形を拾わず赤
- 正本が見つからない・読めない時に、codex_pack が黙って作らず通す（止めない）へ倒すと赤
- 2 つの在り処探し（guard の口と dev-flow の口）が別の写しに戻ると赤
作り物の鍵は字を組み立てて作る（この file に鍵の形を字で残さない・本物ではない）。
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "public-guard"))
sys.path.insert(0, str(ROOT / "plugins" / "dev-flow" / "skills" / "codex"))

import guard as PG  # noqa: E402
import codex_pack  # noqa: E402
from uses import py_code

# 作り物（形を確かめるだけ）。使う側の pixel-office の「土台へ足し待ち」の作り物と同じ形。
FAKE = {
    "Stripe の本番の鍵": "rk" + "_live_" + "Ab0" * 8,
    "Stripe の本番の鍵 (sk)": "s" + "k_live_" + "Ab0" * 8,
    "OpenAI の project の鍵": "sk-" + "proj-" + "Ab0_" * 9,
    "AWS の一時の鍵 ID": "AS" + "IA" + "AB0C" * 4,
    # サービスアカウントの鍵の JSON は値に PEM の頭の行を持つ＝「秘密鍵」の形が拾う（欄の名の形は足さない）
    "サービスアカウントの鍵の JSON": '{"type": "service_account", "private' + '_key": "-----BEGIN ' + 'PRIVATE KEY-----\\nMIIE"}',
}


@pytest.mark.parametrize("label", sorted(FAKE))
def test_正本が足りなかった形を拾う(label):
    assert PG.secret_labels("x = " + FAKE[label]), label


@pytest.mark.parametrize("text", [
    "rk_live の説明だけ",                       # 鍵の頭だけ
    "sk-proj- の形を説明する",
    "ASIA は地域の名",
    'd.get("private_key_id")',                  # 欄の名の一部
    '{"private' + '_key": os.environ["SA_KEY"]}',      # 鍵の無い欄の名（値は環境から）
    'The "private' + '_key": field holds the PEM.',    # 欄の名を説明する文
    '{"private' + '_key": ""}',
    "EASTASIAPACIFICSUMMIT2026",                 # 大文字の語の中の ASIA
    "XAKIAABCDEFGHIJKLMNOP",                     # 語の中の AKIA
])
def test_形の説明や似た字は拾わない(text):
    assert not PG.secret_labels(text), text


@pytest.mark.parametrize("label", sorted(FAKE))
def test_codex_のパックも同じ形で止まる(label):
    blocks, _ = codex_pack.scan("x = " + FAKE[label] + "\n", {}, set(), None, environ={})
    assert blocks, label


def test_codex_は鍵の形を写さず正本を読む(tmp_path):
    fake = tmp_path / "guard.py"
    fake.write_text('SECRET_PATTERNS = {"作り物の鍵": r"FAKEKEY-\\d{4}"}\n', encoding="utf-8")
    env = {"AF_PUBLIC_GUARD": str(fake)}
    blocks, _ = codex_pack.scan("x = FAKEKEY-1234\n", {}, set(), None, environ=env)
    assert "作り物の鍵" in blocks
    # 正本に無い鍵の形は codex の側に残らない（写しの表があれば正本を差し替えても拾い続けて赤）
    blocks, _ = codex_pack.scan("x = " + "gh" + "p_" + "Ab3d" * 9 + "\n", {}, set(), None, environ=env)
    assert not any("GitHub" in b for b in blocks), blocks
    assert not hasattr(codex_pack, "BLOCK_PATTERNS")


@pytest.mark.parametrize("body", ["X = 1\n", "SECRET_PATTERNS = {}\n", "raise RuntimeError('壊れた')\n",
                                  "SECRET_PATTERNS = {'x': '('}\n"])
def test_codex_は正本が読めなければ止める(tmp_path, body):
    fake = tmp_path / "guard.py"
    fake.write_text(body, encoding="utf-8")
    with pytest.raises(codex_pack.Abort) as e:
        codex_pack.scan("x = 1\n", {}, set(), None, environ={"AF_PUBLIC_GUARD": str(fake)})
    assert "照らせない" in str(e.value)
    with pytest.raises(codex_pack.Abort):
        codex_pack.scan("x = 1\n", {}, set(), None, environ={"AF_PUBLIC_GUARD": str(tmp_path / "無い.py")})


def test_codex_は入った版の土台を探して読む(tmp_path):
    """入れた形（cache/<市場>/dev-flow/<版> と marketplaces/<市場>）で、repo の根の guard.py を同じ口で見つける。"""
    import subprocess
    market = tmp_path / "marketplaces" / "m"
    (market / "public-guard").mkdir(parents=True)
    (market / "public-guard" / "guard.py").write_text('SECRET_PATTERNS = {"k": "K"}\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(market)], check=True)
    subprocess.run(["git", "-C", str(market), "-c", "user.email=noreply@anthropic.com", "-c", "user.name=t",
                    "commit", "-qm", "x", "--allow-empty"], check=True)
    subprocess.run(["git", "-C", str(market), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(market), "-c", "user.email=noreply@anthropic.com", "-c", "user.name=t",
                    "commit", "-qm", "y"], check=True)
    ver = subprocess.run(["git", "-C", str(market), "rev-parse", "--short=12", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    root = tmp_path / "cache" / "m" / "dev-flow" / ver
    root.mkdir(parents=True)
    assert codex_pack.af_place.foundation_file(os.path.join("public-guard", "guard.py"), str(root)) == \
        str(market / "public-guard" / "guard.py")


def test_在り処探しは_1_か所で_各_plugin_へ_symlink_で届く():
    src = ROOT / "skill-values" / "af_place.py"
    links = sorted((ROOT / "plugins").glob("*/lib/af_place.py"))   # どの plugin の lib に在っても写しでなく symlink
    assert {p.parent.parent.name for p in links} >= {"core", "guard", "dev-flow", "session-watch"}
    for link in links:
        assert link.is_symlink() and link.resolve() == src.resolve(), link
    common = (ROOT / "plugins" / "guard" / "scripts" / "guard_common.py").read_text(encoding="utf-8")
    common = py_code(common)                                            # 注釈・docstring の名は写しでない
    assert "_clone_git" not in common and "marketplaces" not in common   # 在り処探しの写しが guard の口に戻ると赤
    sw = (ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py").read_text(encoding="utf-8")
    sw = py_code(sw)
    assert '"marketplaces"' not in sw and "rev-parse" not in sw            # session-watch の写しに戻ると赤
