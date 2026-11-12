#!/usr/bin/env python3
"""finish_deck.py — NotebookLM 出力デッキの「仕上げ」だけを決定的に行う器（/make-deck 工程6）.

役割分担（設計の正本はrepo ごとの値の表 config/skill-values.json の docs-kit.make-deck.design_doc）:
  NotebookLM = 本文の体裁・図・短いコピー・情報圧縮（＝触らない・強みを活かす）
  この script = 会社のフォーマットの「固定できる所」だけ = 表紙 / 透かし除去 / 綴じ

なぜ NotebookLM 内でやらないか（実測 §3-6）: NotebookLM は背景色・配色・タイトル体裁の微調整が
弱く、再指定するとデッキ全体が振り直る（良いコピー/構成を失う）。∴ 見た目の固定は外（ここ）で。

やること:
  1. drop-first … NotebookLM 出力の先頭 title ページ（自前表紙・透かし付き）を綴じ前に落とす（任意）
  2. cover     … 本文と同じページサイズの表紙を先頭に挿入（会社名/タイトル/サブ/日付/任意ロゴ/アクセント色）
  3. watermark … 透かし領域を **塗る前に preflight**（背景白・本文非侵入・有色なし）で判定し、
                 安全なページだけ白塗り。over/背景不適合/判定不能は **無加工の report-only**。
  4. bind      … 表紙 + 本文を 1 本の PDF に綴じて出力

★透かし除去の芯:
  - **塗る前に対象領域を測る**（塗った後に測るのは tautology＝常に真っ白＝常に緑で嘘をつく）。
  - **二段階**: 全ページを preflight → 安全判定ページだけ描画。over/判定不能/背景不適合ページは
    無加工にし、1 枚でも危険なら **納品 --out を作らない**（診断は別名 *.preflight.pdf）。
    ＝「report-only」を制御フローで本当に成立させる（旧版は測った直後に無条件 draw_rect で
    flag があっても本文を消した PDF を保存していた）。
  - **主判定は単一 dark_ratio でない**: 背景の白さ・有色画素・暗content の bbox が
    guard band（wm_rect の左/上）へ侵入するか、の複合。白背景でないページは自動白塗りしない。

設計思想: **本文スライドは無加工で流用**（画質・レイアウトを保つ）。表紙は別ページとして足すだけ。
透かし除去は opt-in（--remove-watermark）。透かし位置は NotebookLM で固定（右下・実測 2026-08-23
で 1376x768 の透かしは右端から左 ~7.7%×下端から上 ~2.3%）＝既定 rect 右12%×下5.5% で覆う。**それより縮めない**
（: under-coverage を self-test で赤にできるまで既定を縮めない＝端クリップ見逃しを防ぐ）。

会社ごとの既定（--accent・--company・--logo を省いた時）: repo の根の config/skill-values.json の
  docs-kit.make-deck.{accent, cover_company, cover_logo}（読み口は同じ dir の skill_values.py）。
  表が無い・空なら中立の既定（DEFAULT_ACCENT・社名なし・ロゴなし）。

依存: PyMuPDF (import fitz)・numpy（透かし判定のラスタ解析）。日本語は MuPDF 内蔵 CJK "japan"。
      うまく出ない環境は --font <日本語TTF/TTC path> で差し替え。

使い方:
  python3 finish_deck.py finish --body deck.pdf --out final.pdf \
      --company "株式会社○○" --title "資料タイトル" --subtitle "サブタイトル" --date 2026-08-21 \
      [--logo logo.png] [--accent "#334155"] [--drop-first-page] \
      [--remove-watermark] [--wm-rect x0,y0,x1,y1]
  python3 finish_deck.py --self-test        # 実物同型ラスタ fixture + 画素不変 + mutation-killed
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skill_values  # noqa: E402  同じ dir の読み口（repo ごとの値の表）

DEFAULT_ACCENT = "#334155"   # 中立の既定（会社の色は config/skill-values.json の docs-kit.make-deck.accent）

try:
    import fitz  # PyMuPDF
except Exception as exc:  # pragma: no cover
    sys.stderr.write("PyMuPDF(fitz) が読めません: %s\npip install pymupdf\n" % exc)
    sys.exit(2)

try:
    import numpy as np
except Exception as exc:  # pragma: no cover
    sys.stderr.write("numpy が読めません: %s\npip install numpy\n" % exc)
    sys.exit(2)


# ── 判定の定数（実測較正・2026-08-23 に base.pdf/base_v2/control の実デッキ corpus で決めた） ──
# 実測: 既定 rect(右12%×下5.5%) 内でクリーンな透かしは white≈0.91 / dark≈0.02〜0.04 / colored=0 /
#       dark bbox x[0.36,0.93] y[0.55,0.72]（＝rect 左36%・上55% は空＝透かしは右下寄り）。
#       本文侵入ページ(base p5)は dark≈0.04（clean と同水準）だが bbox が x[0.04] y[0.00]＝guard へ侵入
#       ＝**単一 dark_ratio では区別不能・位置(bbox)で捉える**。
WHITE_THRESH = 235       # 全 channel これ超で「白」
DARK_THRESH = 120        # gray これ未満で「暗（透かし/本文）」
SAT_THRESH = 40          # RGB の max-min これ超で「有色」（透かしは無彩＝低い）
COLORED_FRAC_MAX = 0.02  # 有色画素がこれ超 → 背景/本文が白でない（白塗り不可）
WHITE_FRAC_MIN = 0.80    # 白画素がこれ未満（dark でない）→ 灰キャプション/濃色背景
DARK_FRAC_MIN = 0.005    # 暗がこれ未満 → 透かし不在/rズレ（塗る対象が無い。clean 透かし 0.02〜）
DARK_FRAC_MAX = 0.10     # 暗がこれ超 → 細い透かしでなく本文ブロック（over。clean 上限 0.04 に余裕）
GUARD_LEFT = 0.30        # 暗が wm_rect 左 30% へ入る → 本文侵入（透かし左端 0.36 に余裕）
GUARD_TOP = 0.45         # 暗が wm_rect 上 45% へ入る → 本文侵入（透かし上端 0.55 に余裕）
RASTER_SCALE = 2         # ラスタ化倍率


# ── 色ユーティリティ ────────────────────────────────────────────────
def hex_to_rgb01(h):
    """'#1F4E79' → (0.12, 0.30, 0.47)。不正なら中立の既定 DEFAULT_ACCENT。"""
    h = (h or "").strip().lstrip("#")
    try:
        if len(h) != 6:
            raise ValueError(h)
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        d = DEFAULT_ACCENT.lstrip("#")
        return tuple(int(d[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _is_cjk(text):
    return any(ord(c) > 0x2E00 for c in (text or ""))


def _register_font(page, font_path):
    """--font でTTF/TTCを渡された時だけ埋め込み、fontname を返す。無ければ None。"""
    if not font_path:
        return None
    if not os.path.isfile(font_path):
        sys.stderr.write("⚠ --font が見つからないので内蔵CJKにフォールバック: %s\n" % font_path)
        return None
    page.insert_font(fontname="F0", fontfile=font_path)
    return "F0"


def _font_for(text, embedded):
    """描画に使うフォント名。埋め込み優先→CJKは内蔵'japan'→ASCIIは'helv'。"""
    if embedded:
        return embedded
    return "japan" if _is_cjk(text) else "helv"


# ── 表紙 ────────────────────────────────────────────────────────────
def add_cover(doc, *, company, title, subtitle, date, logo, accent, font_path):
    """本文と同じページサイズの表紙を index 0 に挿入する（固定フォーマット）。"""
    if doc.page_count == 0:
        raise ValueError("本文PDFにページがありません")
    base = doc[0].rect
    w, h = base.width, base.height
    page = doc.new_page(pno=0, width=w, height=h)
    embedded = _register_font(page, font_path)
    ac = hex_to_rgb01(accent)
    ink = (0.13, 0.15, 0.18)   # ほぼ黒（真っ黒を避けた落ち着いた濃色）
    sub = (0.40, 0.44, 0.50)   # サブ・メタのグレー

    # 背景は白（透かし除去と一貫・playbook §6-4）。左に縦のアクセント帯を1本だけ（固定装飾）。
    page.draw_rect(fitz.Rect(0, 0, w, h), color=(1, 1, 1), fill=(1, 1, 1), width=0)
    # 左フル帯（“角”でなく読める帯に・実測FB #3 2026-08-22）。細すぎるとエッジ線に見えるため約4.5%幅。
    bar_w = max(10.0, w * 0.045)
    page.draw_rect(fitz.Rect(0, 0, bar_w, h), color=ac, fill=ac, width=0)
    # タイトル下に短いアクセント下線（1本）
    m = w * 0.11               # 左右マージン
    tline_y = h * 0.60
    page.draw_line(fitz.Point(m, tline_y), fitz.Point(m + w * 0.16, tline_y), color=ac, width=2.4)

    # 任意ロゴ（右上）
    if logo and os.path.isfile(logo):
        try:
            lw = w * 0.16
            lh = lw  # 正方枠に収める（アスペクトは keep_proportion）
            page.insert_image(fitz.Rect(w - m - lw, h * 0.10, w - m, h * 0.10 + lh),
                              filename=logo, keep_proportion=True)
        except Exception as exc:
            sys.stderr.write("⚠ ロゴ挿入に失敗（無視して続行）: %s\n" % exc)

    # 会社名／宛名（上部に寄せてページを上・中・下で締める・実測FB #4 2026-08-22）
    if company:
        page.insert_textbox(fitz.Rect(m, h * 0.16, w - m, h * 0.16 + h * 0.08),
                            company, fontsize=h * 0.026, fontname=_font_for(company, embedded),
                            color=sub, align=fitz.TEXT_ALIGN_LEFT)
    # タイトル（主役・大）
    page.insert_textbox(fitz.Rect(m, h * 0.40, w - m, tline_y),
                        title or "", fontsize=h * 0.066, fontname=_font_for(title, embedded),
                        color=ink, align=fitz.TEXT_ALIGN_LEFT)
    # サブタイトル（下線の下）
    if subtitle:
        page.insert_textbox(fitz.Rect(m, tline_y + h * 0.02, w - m, tline_y + h * 0.14),
                            subtitle, fontsize=h * 0.032, fontname=_font_for(subtitle, embedded),
                            color=sub, align=fitz.TEXT_ALIGN_LEFT)
    # 日付（最下）
    if date:
        page.insert_textbox(fitz.Rect(m, h * 0.88, w - m, h * 0.96),
                            date, fontsize=h * 0.022, fontname=_font_for(date, embedded),
                            color=sub, align=fitz.TEXT_ALIGN_LEFT)
    return page


# ── 透かし領域の解析（塗る前 preflight） ────────────────────
def _parse_rect(spec, page_rect):
    """--wm-rect 'x0,y0,x1,y1'（pt）を Rect に。None なら右下角（右12%×下5.5%）を既定。"""
    if spec:
        try:
            x0, y0, x1, y1 = (float(v) for v in spec.split(","))
            return fitz.Rect(x0, y0, x1, y1)
        except Exception:
            raise ValueError("--wm-rect は 'x0,y0,x1,y1'（pt・カンマ区切り）で指定")
    # NotebookLM/Gemini Notebook の透かしは右下角（実測 2026-08-23・1376x768 で dark bbox は
    # 右端から左 ~7.7%・下端から上 ~2.3% に収まる）。既定はそれを extremal+margin で覆う
    # **右12%×下5.5%**（旧 18%×7.5% は本文の右下侵入を拾い cry-wolf したため実測で締めた）。
    w, h = page_rect.width, page_rect.height
    return fitz.Rect(page_rect.x1 - w * 0.12, page_rect.y1 - h * 0.055, page_rect.x1, page_rect.y1)


def _rgb_array(page, rect):
    """rect を RGB ラスタ化して (H,W,3) uint8 配列に。描画不能なら None。"""
    try:
        pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(RASTER_SCALE, RASTER_SCALE),
                              colorspace=fitz.csRGB)
        if not pix.samples or pix.width == 0 or pix.height == 0:
            return None
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        return np.ascontiguousarray(arr[:, :, :3])
    except Exception:
        return None


# self-test の mutation-killed 用: 本番は None。finish→preflight→classify が直読する（global）。
_MUTATE = None


def classify_region(page, wm_rect, _mutate=None):
    """wm_rect を塗る前に測り verdict を返す（複合特徴・単一 dark_ratio でない）。

    返り値: (verdict, metrics)
      verdict ∈ 'paint_ok'（白背景＋透かしが右下小域に収まる＝白塗り安全）
              / 'no_watermark'（対象がほぼ無い＝rズレ/透かし不在）
              / 'over'（暗が多すぎ or guard band へ侵入＝本文侵入・塗ると本文を消す）
              / 'bg_unfit'（有色/非白背景＝白塗り不可・灰キャプション含む）
              / 'undetermined'（ラスタ化不能）
    判定順（過不足の切り分け）: ①有色→bg_unfit ②暗が多すぎ→over ③白率低い→bg_unfit
      ④暗ほぼ無い→no_watermark ⑤暗 bbox が guard へ侵入→over ⑥paint_ok。
      ②を③より先に置くのは、本文の濃いブロックも「白率低い」になるが over と呼ぶべきだから
      （灰キャプション＝暗でなく白でない は③、本文ブロック＝暗が多い は②）。
    _mutate/_MUTATE: 検査を無効化するキー（'over'/'bg'）。self-test の mutation-killed 専用。
    """
    mut = _mutate if _mutate is not None else _MUTATE
    arr = _rgb_array(page, wm_rect)
    if arr is None:
        return "undetermined", {}
    r = arr[:, :, 0].astype(np.int16)
    g = arr[:, :, 1].astype(np.int16)
    b = arr[:, :, 2].astype(np.int16)
    gray = (r + g + b) // 3
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    white = (r > WHITE_THRESH) & (g > WHITE_THRESH) & (b > WHITE_THRESH)
    dark = gray < DARK_THRESH
    colored = (mx - mn) > SAT_THRESH
    n = float(arr.shape[0] * arr.shape[1])
    white_frac = float(white.sum()) / n
    dark_frac = float(dark.sum()) / n
    colored_frac = float(colored.sum()) / n
    m = {"white_frac": round(white_frac, 4), "dark_frac": round(dark_frac, 4),
         "colored_frac": round(colored_frac, 4)}

    # ① 有色 → 背景/本文が白でない（白塗りで色を消す）＝
    if mut != "bg" and colored_frac > COLORED_FRAC_MAX:
        return "bg_unfit", m
    # ② 暗が多すぎ → 細い透かしでなく本文ブロック（over。白率チェックより先）
    if mut != "over" and dark_frac > DARK_FRAC_MAX:
        return "over", m
    # ③ 白背景率が低い（灰キャプション・濃色背景で暗は少ない）→ 白塗り不可＝
    if mut != "bg" and white_frac < WHITE_FRAC_MIN:
        return "bg_unfit", m
    # ④ 対象がほぼ無い → rズレ/透かし不在
    if dark_frac < DARK_FRAC_MIN:
        return "no_watermark", m
    # ⑤ 暗 bbox が guard band（左/上）へ侵入 → 本文侵入（over）＝
    ys, xs = np.where(dark)
    if len(xs):
        h, w = dark.shape
        if mut != "over" and (xs.min() < w * GUARD_LEFT or ys.min() < h * GUARD_TOP):
            m["bbox_min"] = (round(float(xs.min()) / w, 3), round(float(ys.min()) / h, 3))
            return "over", m
    return "paint_ok", m


def _residual_outside(page, wm_rect):
    """wm_rect の**すぐ外側**の細バンド（左/上）に透かし様の暗が残るか（under-coverage 検知）。

    ★端クリップ（透かしが rect からはみ出したまま「一部が rect 内なら緑」で合格）を塞ぐ。
    白背景上の暗が外側バンドに在れば透かしはみ出し＝rect が小さい。本文侵入と紛れないよう
    「外側バンドが概ね白 ∧ そこに暗クラスタ」の時だけ True（保守的）。
    """
    w, h = wm_rect.width, wm_rect.height
    band = max(4.0, min(w, h) * 0.12)
    left_band = fitz.Rect(max(0, wm_rect.x0 - band), wm_rect.y0, wm_rect.x0, wm_rect.y1)
    top_band = fitz.Rect(wm_rect.x0, max(0, wm_rect.y0 - band), wm_rect.x1, wm_rect.y0)
    for bnd in (left_band, top_band):
        if bnd.is_empty or bnd.width <= 0 or bnd.height <= 0:
            continue
        arr = _rgb_array(page, bnd)
        if arr is None:
            continue
        gray = (arr[:, :, 0].astype(np.int16) + arr[:, :, 1] + arr[:, :, 2]) // 3
        n = float(gray.size)
        dark_frac = float((gray < DARK_THRESH).sum()) / n
        white_frac = float((gray > WHITE_THRESH).sum()) / n
        if dark_frac > 0.01 and white_frac > 0.60:
            return True
    return False


def preflight_pages(doc, wm_spec, start, _mutate=None):
    """全 body ページを塗る前に判定（二段階の第1段）。返り値: {page_index: (verdict, metrics)}。"""
    verdicts = {}
    for i in range(start, doc.page_count):
        page = doc[i]
        wm = _parse_rect(wm_spec, page.rect)
        verdict, m = classify_region(page, wm, _mutate=_mutate)
        if verdict == "paint_ok" and _residual_outside(page, wm):
            verdict = "under"      # 透かしが rect からはみ出す（rが小さい）
        verdicts[i] = (verdict, m)
    return verdicts


def paint_safe_pages(doc, wm_spec, verdicts):
    """paint_ok と判定されたページだけ白塗りする（二段階の第2段）。返り値: 塗ったページ数。"""
    painted = 0
    for i, (verdict, _m) in verdicts.items():
        if verdict == "paint_ok":
            page = doc[i]
            wm = _parse_rect(wm_spec, page.rect)
            page.draw_rect(wm, color=(1, 1, 1), fill=(1, 1, 1), width=0)
            painted += 1
    return painted


_UNSAFE_REASON = {
    "no_watermark": "wm-rect に透かしが無い（領域ズレ/不在の可能性）",
    "over": "本文が透かし領域に侵入（塗ると本文を消す）",
    "bg_unfit": "背景が白でない/有色（白塗り不可）",
    "under": "透かしが領域外へはみ出す（wm-rect が小さい）",
    "undetermined": "ラスタ化できず判定不能",
}


# ── メイン工程 ──────────────────────────────────────────────────────
def cover_defaults(args):
    """--company/--accent/--logo を省いた時はrepo ごとの値の表 → 中立の既定の順で埋める。"""
    mk = ("docs-kit", "make-deck")
    company = args.company or skill_values.get(*mk, "cover_company", default="")
    accent = args.accent or skill_values.get(*mk, "accent", default=DEFAULT_ACCENT)
    logo = args.logo or skill_values.get(*mk, "cover_logo", default=None)
    if logo and not os.path.isabs(logo):
        root = skill_values._repo_root()
        if root and os.path.isfile(os.path.join(root, logo)):
            logo = os.path.join(root, logo)   # 表の path は repo の根から
    return company, accent, logo


def finish(args):
    if not os.path.isfile(args.body):
        sys.stderr.write("本文PDFがありません: %s\n" % args.body)
        return 2
    doc = fitz.open(args.body)

    dropped = False
    if getattr(args, "drop_first_page", False):
        if doc.page_count <= 1:
            sys.stderr.write("⚠ --drop-first-page: 本文が1枚以下なので落とさない\n")
        else:
            doc.delete_page(0)
            dropped = True
    n_body = doc.page_count

    # 透かし除去は表紙を足す前に body 全ページへ（cover offset を持ち込まない＝二段階を素直に）
    verdicts, painted, unsafe = {}, 0, []
    if args.remove_watermark:
        verdicts = preflight_pages(doc, args.wm_rect, 0)
        painted = paint_safe_pages(doc, args.wm_rect, verdicts)
        unsafe = [(i, v) for i, (v, _m) in sorted(verdicts.items()) if v != "paint_ok"]

    cover_added = False
    if not args.no_cover:
        company, accent, logo = cover_defaults(args)
        add_cover(doc, company=company, title=args.title, subtitle=args.subtitle,
                  date=args.date, logo=logo, accent=accent, font_path=args.font)
        cover_added = True

    out = args.out or (os.path.splitext(args.body)[0] + "_final.pdf")
    # ★二段階の契約: 1 枚でも unsafe なら **納品 --out を作らない**。診断は別名。
    deliver = not unsafe
    if deliver:
        doc.save(out, garbage=4, deflate=True)
        saved_path = out
    else:
        saved_path = getattr(args, "diagnostic_out", None) or (os.path.splitext(out)[0] + ".preflight.pdf")
        doc.save(saved_path, garbage=4, deflate=True)
    total = doc.page_count
    doc.close()

    # 出力は6項目のみ（多すぎる報告を出さない）
    def pno(i):   # verdict の index（body 0-based）→ 人間向けページ番号（表紙込み）
        return i + (1 if cover_added else 0) + 1
    print("対象: %s（本文 %d 枚%s）" % (args.body, n_body, "・先頭drop" if dropped else ""))
    print("表紙: %s" % ("付与（先頭に1枚）" if cover_added else "なし(--no-cover)"))
    if args.remove_watermark:
        print("透かし除去(塗る前preflight): 白塗り %d 枚 / 要確認 %d 枚" % (painted, len(unsafe)))
        for i, v in unsafe:
            print("  ⚠ p%d: %s" % (pno(i), _UNSAFE_REASON.get(v, v)))
    else:
        print("透かし除去: スキップ（--remove-watermark 未指定）")
    if deliver:
        print("出力: %s（全 %d 枚）" % (saved_path, total))
    else:
        print("出力: ❌ 納品ファイルは作っていない（unsafe %d 枚）／診断のみ: %s" % (len(unsafe), saved_path))
        print("  → --wm-rect で領域を当て直す / 該当ページを目視 / 有色背景は今回スコープ外")
    print("次の人間判断: 表紙の社名/タイトル/日付・要確認ページ・納品前チェックリスト（SKILL.md）")
    return 1 if unsafe else 0


# ── self-test（実物同型ラスタ fixture + 画素不変 + mutation-killed） ─────
def _fixture_page(doc, W, H, kind):
    """実物同型のラスタ想定ページを作る（実測: 透かしは既定 rect 内 x[0.36,0.93] y[0.55,0.72]）。"""
    p = doc.new_page(width=W, height=H)
    # 背景
    if kind == "colored_bg":
        p.draw_rect(p.rect, color=(0.2, 0.4, 0.8), fill=(0.2, 0.4, 0.8), width=0)
    elif kind == "gray_caption":
        p.draw_rect(p.rect, color=(1, 1, 1), fill=(1, 1, 1), width=0)
        p.draw_rect(fitz.Rect(0, H * 0.90, W, H), color=(0.6, 0.6, 0.6), fill=(0.6, 0.6, 0.6), width=0)
    else:
        p.draw_rect(p.rect, color=(1, 1, 1), fill=(1, 1, 1), width=0)
    # 本文見出し（左上・全 kind 共通＝画素不変の対象。wm_rect と重ならない）
    p.insert_textbox(fitz.Rect(60, 60, W * 0.6, 160), "本文見出し\nNotebookLM 出力の想定",
                     fontsize=30, fontname="japan", color=(0.1, 0.1, 0.1))
    # 透かし（右下・rect の右下寄り＝guard band を避ける実測位置）
    if kind not in ("no_watermark", "colored_bg", "gray_caption"):
        if kind == "rect_out":
            box = fitz.Rect(W * 0.02, H * 0.955, W * 0.20, H)   # 左下＝既定 rect(右12%) 外
        else:                                                   # normal / body_overlap
            box = fitz.Rect(W * 0.935, H * 0.975, W, H)         # 右下・rect内(右下寄り)
        p.insert_textbox(box, "Gemini Notebook", fontsize=8, fontname="helv", color=(0.1, 0.1, 0.1))
    # 本文侵入（over）: rect の左上へ濃い本文ブロック
    if kind == "body_overlap":
        p.draw_rect(fitz.Rect(W * 0.89, H * 0.95, W * 0.95, H * 0.99),
                    color=(0.1, 0.1, 0.1), fill=(0.1, 0.1, 0.1), width=0)
    return p


def _page_array(doc, idx, rect=None):
    page = doc[idx]
    r = rect or page.rect
    pix = page.get_pixmap(clip=r, matrix=fitz.Matrix(RASTER_SCALE, RASTER_SCALE), colorspace=fitz.csRGB)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return np.ascontiguousarray(a[:, :, :3])


def _run_case(kind, W, H, expect):
    """1 fixture を finish 相当（drop無・cover無・remove-wm）に通し、verdict と画素不変を検査。"""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="finish_deck_st_")
    src = os.path.join(tmp, "body.pdf")
    d = fitz.open()
    _fixture_page(d, W, H, kind)
    d.save(src)
    d.close()

    # 塗る前の全画素 & 本文領域（左上）
    d0 = fitz.open(src)
    before_full = _page_array(d0, 0)
    body_rect = fitz.Rect(0, 0, W * 0.6, H * 0.45)   # 本文見出しのある左上（wm_rect と重ならない）
    before_body = _page_array(d0, 0, body_rect)
    wm = _parse_rect(None, d0[0].rect)
    before_wm = _page_array(d0, 0, wm)
    verdict, _m = classify_region(d0[0], wm)
    if verdict == "paint_ok" and _residual_outside(d0[0], wm):
        verdict = "under"
    d0.close()

    # finish 実走（cover無・drop無・remove-wm）
    class A:
        body = src; out = os.path.join(tmp, "final.pdf"); no_cover = True
        company = ""; title = ""; subtitle = ""; date = ""
        logo = None; accent = "#1F4E79"; font = None
        remove_watermark = True; wm_rect = None; drop_first_page = False
        diagnostic_out = os.path.join(tmp, "diag.pdf")
    rc = finish(A)

    # 出力（deliver=A.out / 非deliver=diag.pdf）を読み、画素不変を検査
    out_path = A.out if os.path.isfile(A.out) else A.diagnostic_out
    d1 = fitz.open(out_path)
    after_full = _page_array(d1, 0)
    after_body = _page_array(d1, 0, body_rect)
    after_wm = _page_array(d1, 0, wm)
    d1.close()

    checks = []
    checks.append(("verdict==%s" % expect["verdict"], verdict == expect["verdict"]))
    # 本文領域は常に不変（塗って良い時も本文は触らない）
    checks.append(("本文領域 画素不変", np.array_equal(before_body, after_body)))
    if expect["verdict"] == "paint_ok":
        # 透かし領域が白へ（除去された）
        white_after = float((after_wm > WHITE_THRESH).all(axis=2).mean())
        checks.append(("透かし領域が除去(白化)", white_after > 0.98))
        # ★塗るのは wm_rect だけ＝それ以外は全画素不変（本文/図を一切触らない・reviewer 指摘の強化）。
        # 端の丸め/AA を避けるため wm より一回り大きい箱を除外して外側を比較する。
        Hp, Wp = after_full.shape[0], after_full.shape[1]
        wx0 = int(Wp * (1 - 0.13)); wy0 = int(Hp * (1 - 0.065))
        bo = before_full.copy(); ao = after_full.copy()
        bo[wy0:, wx0:] = 0; ao[wy0:, wx0:] = 0
        checks.append(("wm_rect 以外は全画素不変(本文非破壊)", np.array_equal(bo, ao)))
        checks.append(("納品 --out を生成", os.path.isfile(A.out)))
    else:
        # unsafe: ページ全体が画素不変（＝破壊していない）＋ 納品 --out を作らない
        checks.append(("unsafe時 全画素不変(非破壊)", np.array_equal(before_full, after_full)))
        checks.append(("unsafe時 納品 --out を作らない", not os.path.isfile(A.out)))
    checks.append(("rc の符号", (rc != 0) == (expect["verdict"] != "paint_ok")))
    return verdict, checks


_CASES = [
    ("normal", {"verdict": "paint_ok"}),
    ("rect_out", {"verdict": "no_watermark"}),
    ("body_overlap", {"verdict": "over"}),
    ("gray_caption", {"verdict": "bg_unfit"}),
    ("colored_bg", {"verdict": "bg_unfit"}),
    ("no_watermark", {"verdict": "no_watermark"}),
]


def _run_suite(W, H, verbose=False):
    """全 fixture を今の _MUTATE 設定で走らせ、[(kind, ok)] を返す。"""
    out = []
    for kind, expect in _CASES:
        verdict, checks = _run_case(kind, W, H, expect)
        ok = all(v for _n, v in checks)
        out.append((kind, ok))
        if verbose:
            print("  [%s] verdict=%s → %s" % (kind, verdict, "OK" if ok else "NG"))
            for name, v in checks:
                if not v:
                    print("      NG: %s" % name)
    return out


def _test_under_coverage(W, H):
    """: 既定 rect を縮めると透かしがはみ出し、必ず unsafe（paint_ok でない）になる。

    ＝端クリップ（透かしが rect からはみ出したまま「一部が rect 内なら緑」で合格）を塞ぐ実証。
    赤にできる＝既定 rect(右12%×下5.5%) は透かしを覆えている証拠（縮めない根拠）。
    """
    import tempfile
    tmp = tempfile.mkdtemp(prefix="finish_deck_uc_")
    src = os.path.join(tmp, "b.pdf")
    d = fitz.open(); _fixture_page(d, W, H, "normal"); d.save(src); d.close()
    d0 = fitz.open(src)
    full = _parse_rect(None, d0[0].rect)
    small = fitz.Rect(full.x0 + full.width * 0.5, full.y0 + full.height * 0.5, full.x1, full.y1)
    v, _m = classify_region(d0[0], small)
    resid = _residual_outside(d0[0], small)
    d0.close()
    unsafe = (v != "paint_ok") or resid
    print("    縮小 rect → verdict=%s / residual=%s / unsafe=%s" % (v, resid, unsafe))
    return unsafe


def _test_drop_first(W, H):
    """C13: --drop-first-page で本文が 1 枚減る（NotebookLM 自前表紙の二重化を防ぐ）。"""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="finish_deck_df_")
    src = os.path.join(tmp, "b.pdf")
    d = fitz.open()
    for _ in range(3):
        _fixture_page(d, W, H, "normal")
    d.save(src); d.close()

    class A:
        body = src; out = os.path.join(tmp, "final.pdf"); no_cover = True
        company = ""; title = ""; subtitle = ""; date = ""
        logo = None; accent = "#1F4E79"; font = None
        remove_watermark = False; wm_rect = None; drop_first_page = True
        diagnostic_out = None
    finish(A)
    d1 = fitz.open(A.out); n = d1.page_count; d1.close()
    ok = (n == 2)   # 3 枚 → drop で 2 枚（cover 無）
    print("    3枚を --drop-first-page → %d 枚（期待2）→ %s" % (n, "OK" if ok else "NG"))
    return ok


def self_test():
    """実物同型 fixture の verdict + 画素不変 + under-coverage + drop-first + mutation-killed。"""
    global _MUTATE
    print("[self-test] PyMuPDF:", fitz.VersionBind, "/ numpy:", np.__version__)
    W, H = 1376, 768

    print("[self-test] ① verdict + 画素不変 fixtures:")
    _MUTATE = None
    base = _run_suite(W, H, verbose=True)
    base_ok = all(ok for _k, ok in base)

    print("[self-test] ② under-coverage（縮小 rect で必ず unsafe）:")
    uc_ok = _test_under_coverage(W, H)

    print("[self-test] ③ --drop-first-page（C13）:")
    df_ok = _test_drop_first(W, H)

    # ④ mutation-killed: 検査を無効化すると **suite 全体が非0**（1 件以上 NG）になる
    #    ＝その検査を外すと本来 unsafe な case が verdict を保てない＝空検査でない証拠。
    print("[self-test] ④ mutation-killed（検査を殺すと suite が壊れる）:")
    mut_ok = True
    for mut in ("over", "bg"):
        _MUTATE = mut
        res = _run_suite(W, H, verbose=False)
        broke = [k for k, ok in res if not ok]
        killed = len(broke) > 0
        print("    _MUTATE=%s → 壊れた case=%s → %s"
              % (mut, ",".join(broke) or "なし", "OK(殺せた)" if killed else "NG(空検査の疑い)"))
        mut_ok = mut_ok and killed
    _MUTATE = None

    verdict_all = base_ok and uc_ok and df_ok and mut_ok
    print("[self-test] 判定:", "PASS ✅" if verdict_all else "FAIL ❌",
          "（verdict=%s / under=%s / drop=%s / mutation=%s）"
          % (base_ok, uc_ok, df_ok, mut_ok))
    return 0 if verdict_all else 1


def build_parser():
    p = argparse.ArgumentParser(description="NotebookLM デッキの仕上げ（表紙/透かし除去/綴じ）")
    p.add_argument("--self-test", action="store_true",
                   help="実物同型ラスタ fixture + 画素不変 + mutation-killed で器の健全性を確認")
    sub = p.add_subparsers(dest="cmd")
    f = sub.add_parser("finish", help="表紙付与 + 透かし除去(塗る前preflight) + 綴じ")
    f.add_argument("--body", required=True, help="NotebookLM 出力の本文PDF")
    f.add_argument("--out", help="出力PDF（既定: <body>_final.pdf）")
    f.add_argument("--company", default="", help="表紙の会社名")
    f.add_argument("--title", default="", help="表紙のタイトル（主役）")
    f.add_argument("--subtitle", default="", help="表紙のサブタイトル")
    f.add_argument("--date", default="", help="表紙の日付（例 2026-08-21）")
    f.add_argument("--logo", help="表紙ロゴ画像（png/jpg・任意）")
    f.add_argument("--accent", default=None,
                   help="アクセント色 hex（省けば config/skill-values.json の docs-kit.make-deck.accent・無ければ %s）" % DEFAULT_ACCENT)
    f.add_argument("--font", help="日本語TTF/TTC path（内蔵CJKで崩れる時に差し替え）")
    f.add_argument("--no-cover", action="store_true", help="表紙を付けない")
    f.add_argument("--drop-first-page", action="store_true",
                   help="NotebookLM 自前表紙（先頭ページ・透かし付き）を綴じ前に落とす（表紙二重化を防ぐ・推奨）")
    f.add_argument("--remove-watermark", action="store_true",
                   help="透かし領域を塗る前 preflight で判定し安全ページだけ白塗り")
    f.add_argument("--wm-rect", help="透かし領域 'x0,y0,x1,y1'（pt・既定は右下角 右12%%×下5.5%%）")
    f.add_argument("--diagnostic-out", help="unsafe 時の診断PDFの出力先（既定: <out>.preflight.pdf）")
    return p


def main():
    args = build_parser().parse_args()
    if args.self_test:
        sys.exit(self_test())
    if args.cmd == "finish":
        sys.exit(finish(args))
    build_parser().print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
