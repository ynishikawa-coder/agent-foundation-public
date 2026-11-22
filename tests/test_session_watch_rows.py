"""session-watch が会話ログの行を読む所の根治の試験（誤りの類をわざと入れて、拒む・名指すかを見る）。

- 画像だけを貼った人の頼みも人の行（番の切れ目・最初の頼み）に数える（正本は guard_common.is_owner_row）。
- 1 行 1 件の JSON は改行（\\n）だけで割る（U+2028・\\r を文に含む行を割らない）。書きかけの最後の行は壊れ行にしない。
- 壊れた行は黙って捨てず unread の札で行の番号を名指す（止めない）。
- 知らせの行・縮めた後の要約の行は番を切らない（人の行でない）。
- 隣の guard_common が無い時、記録でない first_seeded で窓の種類を決めない（remind_title が先に guard_gap を見る）。
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py"
GUARD = ROOT / "plugins" / "guard" / "scripts" / "guard_common.py"

sys.dont_write_bytecode = True


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sw = _load("session_watch_rows", SCRIPT)
G = _load("guard_common_rows", GUARD)


@pytest.fixture(params=["隣あり", "隣なし"])
def side(request, monkeypatch):
    """隣の guard_common が在る時（正本を読む）と無い時（控えで読む）の両方で同じ結果になるか。"""
    monkeypatch.setattr(sw, "_loaded", {"guard_common": G if request.param == "隣あり" else None,
                                        "ask_shape": None, "public_guard": None})
    return request.param


def human(text=None, image=False, **extra):
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    if image:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}})
    row = {"type": "user", "message": {"role": "user", "content": content}, "origin": {"kind": "human"}}
    row.update(extra)
    return row


def write(tmp_path, raw):
    p = tmp_path / "log.jsonl"
    p.write_bytes(raw)
    return p


def dump(row):
    return json.dumps(row, ensure_ascii=False).encode("utf-8")


# ── 画像だけの頼み ──
def test_画像だけの頼みも人の行に数える(side):
    img = human(image=True)
    assert G.is_owner_row(img) and G.is_human_row(img)
    assert sw.is_owner_text(img) and sw.starts_turn(img)
    log = sw.Log([human("はじめ"), img])
    assert [k for k, _ in log.events] == ["owner", "owner"]   # 画像だけの頼みで番が切れる


def test_画像だけの最初の頼みで最初の頼みが決まる(side):
    log = sw.Log([human(image=True), human("返し先=オーナー")])
    assert log.first_prompt == ""        # 最初の頼みは画像の行＝後の行の文で上書きしない


def test_道具の返りと差し戻しは画像があっても人の行でない(side):
    tool = human(image=True)
    tool["toolUseResult"] = {"x": 1}
    meta = human(image=True, isMeta=True)
    assert not sw.is_owner_text(tool) and not sw.is_owner_text(meta)
    assert not G.is_owner_row(tool) and not G.is_owner_row(meta)


def test_空の頼みは人の行でない(side):
    assert not sw.is_owner_text(human("   "))
    assert not G.is_owner_row(human("   "))


# ── 改行だけで割る ──
@pytest.mark.parametrize("sep", [" ", " ", "\r", "\x85", "\x0c"])
def test_改行でない区切りの字を含む行を割らない(side, tmp_path, sep):
    rows = [human("前%s後" % sep), human("次")]
    p = write(tmp_path, b"\n".join(dump(r) for r in rows) + b"\n")
    got = sw.read_rows(p)
    assert len(got) == 2 and sw.UNREADABLE not in got[0]
    assert sw.text_of(got[0]) == "前%s後" % sep


def test_壊れた行は捨てずに行の番号で名指す_止めない(side, tmp_path):
    p = write(tmp_path, dump(human("一")) + b"\n{broken\n" + dump(human("三")) + b"\n[1]\n")
    got = sw.read_rows(p)
    log = sw.Log(got)
    assert sorted(log.unreadable) == [2, 4]
    found = sw.check(log)
    msg = [m for c, m in found if c == "unread"]
    assert msg and "2・4 行目" in msg[0]
    assert sw.watch(str(p)) == found    # 例外で落ちず、拾った物として返す


def test_書きかけの最後の行は壊れ行にしない(side, tmp_path):
    p = write(tmp_path, dump(human("一")) + b"\n" + b'{"type": "user", "mess')
    log = sw.Log(sw.read_rows(p))
    assert log.unreadable == []


def test_読めない_utf8_は置き換えて読む(side, tmp_path):
    p = write(tmp_path, dump(human("一")) + b"\n\xff\xfe\n")
    log = sw.Log(sw.read_rows(p))
    assert log.unreadable == [2]


# ── 知らせ・要約は人の行でない ──
def test_知らせの行と要約の行は番を切らない(monkeypatch):
    monkeypatch.setattr(sw, "_loaded", {"guard_common": G, "ask_shape": None, "public_guard": None})
    notice = human("別の窓から", origin={"kind": "peer"})
    summary = human("前の話の要約", isCompactSummary=True)
    interrupt = human("[Request interrupted by user]")
    log = sw.Log([human("はじめ"), notice, summary, interrupt])
    assert [k for k, _ in log.events] == ["owner", "notice", "notice", "notice"]
    assert log.first_prompt == "はじめ"


def test_要約の行は最初の頼みにしない(monkeypatch):
    monkeypatch.setattr(sw, "_loaded", {"guard_common": G, "ask_shape": None, "public_guard": None})
    log = sw.Log([human("要約", isCompactSummary=True), human("本当の頼み（返し先=オーナー）")])
    assert log.first_prompt == "本当の頼み（返し先=オーナー）"


# ── 照らしの故障は止めずに名指す ──
def test_照らしの故障は止めずに名指す(tmp_path, monkeypatch):
    import io
    import os

    def boom(*a, **k):
        raise RuntimeError("作り物の故障")
    monkeypatch.setattr(sw, "stop", boom)
    monkeypatch.setattr(os, "environ", dict(os.environ, AF_SESSION_WATCH_TMP=str(tmp_path / "sw")))
    assert sw.hook_stop(io.StringIO('{"session_id": "s9"}')) == 0
    note = sw.take_note(os.environ, "s9")
    assert note and "見張りの --stop が壊れて" in note and "RuntimeError" in note


# ── 窓の種類: 記録の正本が無い時は first_seeded で決めない ──
def test_隣が無い時は記録でない印で子の窓と決めずサーバの記録を読ませる(monkeypatch):
    monkeypatch.setattr(sw, "_loaded", {"guard_common": None, "ask_shape": None, "public_guard": None})
    log = sw.Log([human("作り物を調べて（返し先=session_Y）")])
    log.first_seeded = True     # 隣が無い時に何かの拍子で立った印（記録でない）
    got = sw.remind_title(log, {})
    assert got.startswith(sw.REMIND_PARENT) and "記録を読めない訳" in got


def test_隣がある時は記録で子の窓と決める(monkeypatch):
    monkeypatch.setattr(sw, "_loaded", {"guard_common": G, "ask_shape": None, "public_guard": None})
    log = sw.Log([human("作り物を調べて（返し先=session_Y）", origin={"kind": "peer"})])
    assert log.first_seeded
    assert sw.remind_title(log, {}) == sw.REMIND_CHILD
