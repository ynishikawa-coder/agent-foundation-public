"""guard の qa_page は guard と同じ版の docs-kit の検査だけで照らす（別の版・path を渡す口へ降りない）。"""
from __future__ import annotations

from test_guard import (_qa_page_mod, denied, deny_reason, env, filled_qa_page, needs_node, publish,  # noqa: F401  （env は fixture）
                        without_check)
from test_guard import ROOT


def test_qa_page_path_を渡す口では別の検査に替えられない(tmp_path, monkeypatch):
    qa_page = _qa_page_mod()
    fake = tmp_path / "写した" / "check.mjs"
    fake.parent.mkdir()
    fake.write_text("process.exit(0)", encoding="utf-8")       # 何でも緑にする写し
    monkeypatch.setenv("AF_QA_CHECK", str(fake))
    assert qa_page.find_check() == str(ROOT / "plugins" / "docs-kit" / "skills" / "qa-html" / "check.mjs")


@needs_node
def test_qa_page_別の版の_docs_kit_しか無ければ止まる(env, tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_qa_page("artifact"), encoding="utf-8")
    env = without_check(env, tmp_path, ver="v1", docs_kit_ver="v0")   # 別の版の docs-kit だけ（型と検査が食い違いうる）
    why = deny_reason(env, publish(page))
    assert "同じ版（v1）で見つからず" in why and "別の版の検査では照らさない" in why
    env = without_check(env, tmp_path, ver="v1", docs_kit_ver="v1")   # 同じ版を入れれば通る
    assert not denied(env, publish(page))
