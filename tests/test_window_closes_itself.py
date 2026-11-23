"""窓を閉じるのは窓自身（細目 §5「閉じる窓」）の文が残っているか。

意図: AI が立てた窓は報告を返したら自分で閉じ、開いた窓が積み上がらない。オーナーが立てた窓だけをオーナーの判断に残す。
課題: 2026-11-23 に開いた窓が 139 個残っていた（済んだ窓・親が閉じた後の子・知らせの来ない物を待つ窓）。
原因: 閉じる役（親か子か）が決まっておらず、除外の鍵が題の 🙋 で、知らせの来ない物を窓で待っていた。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _s5():
    # 文を消して回す試験（test_rule_holes）が read_text を差し替えて回すので、読むのは試験の中で
    return (ROOT / "plugins/core/細目/05-返事の形.md").read_text(encoding="utf-8")


def test_AI_が立てた窓は記録の親で決め_報告したら子と自分を閉じる():
    assert "- **閉じる窓** — AI が立てた窓（`parent_session_id` 在り）は報告したら子と自分を閉じる。" in _s5()


def test_知らせの来ない物は窓で待たず預ける():
    assert "知らせの来ない物は待たず台帳か PR に預ける。" in _s5()


def test_閉じない除外は記録の親の無い窓で_題の印によらない():
    assert "親の無い窓（オーナーが立てた窓）は閉じない。" in _s5()
    assert "オーナーの窓は閉じない" not in _s5()


def test_核は題の印でなく_AI_が立てた窓を閉じる():
    assert "- AI が立てた窓は済んだら自分で閉じる。" in (ROOT / "plugins/core/核.md").read_text(encoding="utf-8")
    assert "🤖 の窓は済んだら閉じる" not in (ROOT / "plugins/core/核.md").read_text(encoding="utf-8")
