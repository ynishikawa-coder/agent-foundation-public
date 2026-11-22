"""鍵の形の正本は public-guard/guard.py の SECRET_PATTERNS の 1 か所（原因の台帳 束 F-secret の注入の試験）。

前の誤りを入れると赤になる形で書く:
- 正本から Stripe の本番の鍵・OpenAI の project の鍵・AWS の一時の鍵 ID・サービスアカウントの鍵の JSON の形を消すと赤
- 在り処探し（guard の口と session-watch の口）が別の写しに戻ると赤
作り物の鍵は字を組み立てて作る（この file に鍵の形を字で残さない・本物ではない）。
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "public-guard"))

import guard as PG  # noqa: E402

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


def test_在り処探しは_1_か所で_各_plugin_へ_symlink_で届く():
    src = ROOT / "skill-values" / "af_place.py"
    for plugin in ("guard", "session-watch"):
        link = ROOT / "plugins" / plugin / "lib" / "af_place.py"
        assert link.is_symlink() and link.resolve() == src.resolve(), link
    common = (ROOT / "plugins" / "guard" / "scripts" / "guard_common.py").read_text(encoding="utf-8")
    assert "_clone_git(" not in common and "marketplaces" not in common   # 在り処探しの写しが guard の口に戻ると赤
    sw = (ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py").read_text(encoding="utf-8")
    assert '"marketplaces"' not in sw and "rev-parse" not in sw            # session-watch の写しに戻ると赤
