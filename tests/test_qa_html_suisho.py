"""docs-kit の qa-html: 推奨の印（細目 §4「推奨の印」と同じ決め方）の注入の試験。

オーナー宛て（copy・artifact）の作り方の分かれ道の問い（judge）だけ・1 問に 1 つ・1 つ目の選択肢だけ・「分からない」に付けない・
理由つき。お客さん宛て（send）と事実を聞く問いは印なし。ブラウザと検査で読みが分かれる書き方で判定を隠させない（入口で赤）。
"""
import json
import re

import pytest

from test_docs_kit import DATA, filled_template, needs_node, run_check


# 推奨の印（細目 §4と同じ決め方）: オーナー宛て（copy・artifact）の作り方の分かれ道の問い（judge）だけ・1 問に 1 つ・
# 1 つ目の選択肢だけ・「分からない」に付けない・理由つき。お客さん宛て（send）と事実を聞く問いは印なし（見込みは .estimate の別枠）
REC = '<small class="rec">貸した物の手入れは今も貸した側がしている</small>'


def _rec_page(tmp_path, dest, mutate):
    """型を埋めたページの q3（作り方の分かれ道の問い・judge）の選択肢に印を付けて検査する。"""
    html = filled_template(dest)
    head, rest = html.split('data-qkey="q3"', 1)
    rest = mutate(rest)
    page = tmp_path / "確認.html"
    page.write_text(head + 'data-qkey="q3"' + rest, encoding="utf-8")
    return run_check(page)["red"]


def _mark(nth):
    """q3 の nth 番目（0 から）の選択肢の変わる事の後に印を付ける。"""
    def m(rest):
        parts = rest.split("</small></span></label>")
        parts[nth] = parts[nth] + "</small>" + REC[:-len("</small>")]
        return "</small></span></label>".join(parts)
    return m


@needs_node
@pytest.mark.parametrize("dest", ["copy", "artifact"])
def test_オーナー宛ての分かれ道の問いの_1_つ目に_1_つの印は緑(tmp_path, dest):
    assert _rec_page(tmp_path, dest, _mark(0)) == []


REC_HTML_RED = [
    ("オーナー宛てで 2 つ目に印", "copy", _mark(1), "問い q3: 選択肢「借りた日から 14 日」の推奨の印: 印は 1 つ目の選択肢だけ"),
    ("1 問に 2 つ", "copy", lambda r: _mark(1)(_mark(0)(r)), "問い q3: 推奨の印は 1 問に 1 つ（今 2）"),
    ("「分からない」に印", "copy",
     lambda r: r.replace("<b>分からない・確かめてから答える</b>", "<b>分からない・確かめてから答える</b>" + REC, 1),
     "問い q3: 選択肢「分からない・確かめてから答える」の推奨の印: 「分からない」には付けない"),
    ("お客さん宛て（send）に印", "send", _mark(0), "問い q3: 推奨の印（small.rec）はオーナー宛て（copy・artifact）のページだけ"),
    # 検査とブラウザで読みが分かれる書き方は入口で赤（印がすり抜けない）
    ("引用符の無い印を send に", "send", lambda r: _mark(0)(r).replace('<small class="rec">', "<small class=rec>", 1),
     "属性は空白で区切り、値は引用符"),
    ("/ で区切った印を send に", "send", lambda r: _mark(0)(r).replace('<small class="rec">', '<small/class="rec">', 1),
     "属性は空白で区切り、値は引用符"),
    ("文字参照の印を send に", "send", lambda r: _mark(0)(r).replace('<small class="rec">', '<small class="&#114;ec">', 1),
     "属性「class」の値に文字参照"),
    ("タブの文字参照の印を send に", "send", lambda r: _mark(0)(r).replace('<small class="rec">', '<small class="x&#9;rec">', 1),
     "属性「class」の値に文字参照"),
    ("値の中の偽の class", "send", lambda r: _mark(0)(r).replace('<small class="rec">', """<small title=" class='x'" class="rec">""", 1),
     "属性「title」の値の中に「名=」"),
    ("理由が空", "copy", lambda r: _mark(0)(r).replace(REC, '<small class="rec"></small>', 1), "問い q3: 選択肢「借りた日から 7 日」の推奨の印に理由が無い"),
]


@needs_node
@pytest.mark.parametrize("name, dest, mutate, expect", REC_HTML_RED, ids=[m[0] for m in REC_HTML_RED])
def test_推奨の印の付け方が崩れると赤(tmp_path, name, dest, mutate, expect):
    red = _rec_page(tmp_path, dest, mutate)
    # 入口の止め（書き方の赤）は 1 つの書き方に幾つか重なってよい。印の付け方の赤は、その 1 つだけ
    hits = [r for r in red if r.startswith(expect)]
    assert hits and (len(red) == 1 or all(not r.startswith("問い ") for r in red)), (name, red)


@needs_node
@pytest.mark.parametrize("dest, mutate", [
    # 値の中に偽の data-kind（検査が judge と読み、事実を聞く問いの印を通す形）
    ("copy", lambda r: _mark(0)(r).replace('data-kind="judge"', 'title=" data-kind=\'judge\'" data-kind="choose"', 1)),
    # body の値の中に偽の data-dest（検査が copy と読み、send のページの印を通す形）
    ("send", lambda r: _mark(0)(r)),
], ids=["偽の data-kind", "偽の data-dest"])
def test_値の中の偽の属性で印の判定をすり抜けない(tmp_path, dest, mutate):
    html = filled_template(dest)
    if dest == "send":
        html = html.replace('data-dest="send"', 'title=" data-dest=\'copy\'" data-dest="send"', 1)
    head, rest = html.split('data-qkey="q3"', 1)
    page = tmp_path / "確認.html"
    page.write_text(head + 'data-qkey="q3"' + mutate(rest), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and red[0].startswith("属性「title」の値の中に「名=」"), red   # 偽の値を読ませる書き方は入口で赤＝印は通らない


# ブラウザと検査で「どこが生きた中身か」の読みが分かれる書き方は入口で赤（印を検査から隠して send のページに出させない）
REC_HIDE = [
    ("textarea の中のコメントの始め", lambda r: _mark(0)(r).replace(REC, '<textarea hidden><!--</textarea>' + REC + '<textarea hidden>--></textarea>', 1),
     "<textarea> の中に < を書かない"),
    ("<? で始めた崩れたコメント", lambda r: _mark(0)(r).replace(REC, '<?x <!-- ?>' + REC + '<!-- -->', 1), "検査が読めない < の書き方"),
    ("<! で始めた崩れたコメント", lambda r: _mark(0)(r).replace(REC, '<!x <!-- >' + REC + '<!-- -->', 1), "検査が読めない < の書き方"),
    ("small の中の small に印", lambda r: _mark(0)(r).replace(REC, "", 1).replace('</small></span></label>', REC + '</small></span></label>', 1),
     "<small> の中に <small> を入れない"),
    ("label の中の label の後に印", lambda r: _mark(0)(r).replace(REC, "<label></label>" + REC, 1), "<label> の中に <label> を入れない"),
    ("値の中の </label> と > で印を隠す", lambda r: _mark(0)(r).replace(REC, '<span data-x="</label>"></span><small title=">" class="rec">理由</small>', 1),
     "属性「data-x」の値に < > を書かない"),
    ("class の NBSP の区切り", lambda r: _mark(0)(r).replace('<small class="rec">', '<small class="x\u00a0rec">', 1),
     "class の値は半角英数字"),
    ("閉じ忘れた印が次の選択肢に写る", lambda r: _mark(0)(r).replace(REC, '<small class="rec">貸した物の手入れは今も貸した側がしている', 1), "閉じタグ </span> が開いた順と合わない"),
    ("表の中から印を外へ移させる", lambda r: _mark(0)(r).replace(REC, "<table>" + REC + "</table>", 1), "<table> の中にじかに <small> を置かない"),
    ("select の中で閉じタグを消させる", lambda r: _mark(0)(r).replace(REC, "<select></label></select>" + REC, 1), "選択肢の枠（label.opt）の中の欄は radio か checkbox 1 つだけ"),
    ("p の中の div で p を閉じさせる", lambda r: _mark(0)(r).replace(REC, '<p><div></div></p>' + REC, 1), "<p> の中に <div> を置かない"),
    ("label.opt の外の radio で 1 つ目をずらす（label）", lambda r: _mark(0)(r).replace('<label class="opt">', '<label><input type="radio" name="q3" value="d3"></label><label class="opt">', 1),
     "選択（radio・checkbox）が問いの選択肢（label.opt）の外"),
    ("label.opt の外の radio で 1 つ目をずらす（div）", lambda r: _mark(0)(r).replace('<label class="opt">', '<div><input type="radio" name="q3" value="d3"></div><label class="opt">', 1),
     "選択（radio・checkbox）が問いの選択肢（label.opt）の外"),
    ("p の奥の div で label を閉じさせる", lambda r: _mark(0)(r).replace(REC, "<span><div></div></span>" + REC, 1).replace('<label class="opt">', '<p><label class="opt">', 1).replace("</label>", "</label></p>", 1),
     "<p> の中に <div> を置かない"),
    ("select の中の input", lambda r: _mark(0)(r).replace(REC, '<select><input type="hidden" name="x" value="1"></select>' + REC, 1), "選択肢の枠（label.opt）の中の欄は radio か checkbox 1 つだけ"),
    ("li の中の li", lambda r: _mark(0)(r).replace(REC, "<ul><li>a<li>b</li></li></ul>" + REC, 1), "<li> の中に <li> を開かない"),
    ("label.opt の外の select で 1 つ目をずらす", lambda r: _mark(0)(r).replace('<label class="opt">', '<select name="q3"><option value="d3">借りた日から 3 日</option></select><label class="opt">', 1),
     "問い q3: 推奨の印の付いた問いは、答えの欄"),
    ("label で包んだ select で 1 つ目をずらす", lambda r: _mark(0)(r).replace('<label class="opt">', '<label><select name="q3"><option value="d3">3 日</option></select></label><label class="opt">', 1),
     "問い q3: 推奨の印の付いた問いは、答えの欄"),
    ("字の欄で 1 つ目をずらす", lambda r: _mark(0)(r).replace('<label class="opt">', '<label><input type="text" name="q3" value="3 日"></label><label class="opt">', 1),
     "問い q3: 推奨の印の付いた問いは、答えの欄"),
    ("問いの外の hidden で答えを足す", lambda r: _mark(0)(r).replace("</fieldset>", '</fieldset><input type="hidden" name="q3" value="d3">', 1),
     "問い q3: 推奨の印の付いた問いは、答えの欄"),
    ("option の name で答えを足す", lambda r: _mark(0)(r).replace('<label class="opt">', '<select name="pick"><option name="q3" value="d3">3 日</option></select><label class="opt">', 1),
     "<option> に name を付けない"),
    ("label.opt の for で 2 つ目を選ばせる", lambda r: _mark(0)(r).replace('<label class="opt">', '<label class="opt" for="x14">', 1).replace('value="d14"', 'value="d14" id="x14"', 1),
     "選択肢の枠（label.opt）に for を付けない"),
    ("label.opt の for で別の問いを選ばせる", lambda r: _mark(0)(r).replace('<label class="opt">', '<label class="opt" for="zz">', 1), "選択肢の枠（label.opt）に for を付けない"),
    ("radio の id", lambda r: _mark(0)(r).replace('value="d14"', 'value="d14" id="x14"', 1), "選択（radio・checkbox）に id を付けない"),
    ("印の選択肢を初めから選ぶ", lambda r: _mark(0)(r).replace('value="d7" required', 'value="d7" required checked', 1), "問い q3: 推奨の印の付いた問いの選択肢に checked"),
    ("印の選択肢を隠す", lambda r: _mark(0)(r).replace('<label class="opt">', '<label class="opt" hidden>', 1), "hidden の属性を付けない"),
    ("label.opt に for=supp_ を付ける", lambda r: _mark(0)(r).replace('<label class="opt">', '<label class="opt" for="supp_q3">', 1), "選択肢の枠（label.opt）に for を付けない"),
    ("選択肢の中の textarea", lambda r: _mark(0)(r).replace('<label class="opt"><input', '<label class="opt"><textarea></textarea><input', 1), "選択肢の枠（label.opt）の中の欄は radio か checkbox 1 つだけ"),
    ("選択肢の中の select", lambda r: _mark(0)(r).replace('<label class="opt"><input', '<label class="opt"><select><option>x</option></select><input', 1), "選択肢の枠（label.opt）の中の欄は radio か checkbox 1 つだけ"),
    ("印の選択肢を div hidden で包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<div hidden><label class="opt">', 1).replace("</label>", "</label></div>", 1), "hidden の属性を付けない"),
    ("印の選択肢を閉じた details で包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<details><label class="opt">', 1).replace("</label>", "</label></details>", 1), "選択肢の枠（label.opt）を <details> の中に置かない"),
    ("印の選択肢を fieldset disabled で包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<fieldset disabled><label class="opt">', 1).replace("</label>", "</label></fieldset>", 1), "<fieldset> の中に <fieldset> を置かない"),
    ("問いの fieldset に disabled", lambda r: _mark(0)(r).replace('data-kind="judge"', 'data-kind="judge" disabled', 1), "disabled の属性を付けない"),
    ("印の選択肢をリンクで包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<a href="#x"><label class="opt">', 1).replace("</label>", "</label></a>", 1), "選択肢の枠（label.opt）を <a>・<summary>・<figure> の中に置かない"),
    ("印の選択肢の中のリンク", lambda r: _mark(0)(r).replace(REC, '<a href="#x">x</a>' + REC, 1), "選択肢の枠（label.opt）の中に <a> を置かない"),
    ("印の選択肢に step の class", lambda r: _mark(0)(r).replace('<label class="opt">', '<label class="opt step">', 1), "型の外に class「step」を付けない"),
    ("印の選択肢を div.step で包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<div class="step"><label class="opt">', 1).replace("</label>", "</label></div>", 1), "型の外に class「step」を付けない"),
    ("印の選択肢を div.err で包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<div class="err"><label class="opt">', 1).replace("</label>", "</label></div>", 1), "型の外に class「err」を付けない"),
    ("印の選択肢の中の span.err", lambda r: _mark(0)(r).replace('<label class="opt"><input type="radio" name="q3" value="d7" required><span>', '<label class="opt"><input type="radio" name="q3" value="d7" required><span class="err">', 1), "型の外に class「err」を付けない"),
    ("印の選択肢を id で隠す", lambda r: _mark(0)(r).replace('<label class="opt">', '<div id="qa-print"><label class="opt">', 1).replace("</label>", "</label></div>", 1), "型の外の id はひとことの欄"),
    ("印の選択肢を空の鍵の問いの箱で包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<fieldset class="q" data-qkey=""><label class="opt">', 1).replace("</label>", "</label></fieldset>", 1), "<fieldset> の中に <fieldset> を置かない"),
    ("印の選択肢を自由記入の箱で包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<fieldset class="q" data-qkey="__自由記入__"><label class="opt">', 1).replace("</label>", "</label></fieldset>", 1), "<fieldset> の中に <fieldset> を置かない"),
    ("印の選択肢を開いた details で包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<details open><label class="opt">', 1).replace("</label>", "</label></details>", 1), "選択肢の枠（label.opt）を <details> の中に置かない"),
    ("印の選択肢を切り抜きの figure で包む", lambda r: _mark(0)(r).replace('<label class="opt">', '<figure class="clip"><label class="opt">', 1).replace("</label>", "</label></figure>", 1), "選択肢の枠（label.opt）を <a>・<summary>・<figure> の中に置かない"),
    ("閉じタグの中の空白で選択肢の切り方をずらす", lambda r: _mark(1)(r).replace("</label>", "</label >", 1), "検査が読めない < の書き方"),
    ("</ と空白の崩れたタグ", lambda r: _mark(0)(r).replace(REC, '</ x <!-- >' + REC + '<!-- -->', 1), "検査が読めない < の書き方"),
]


@needs_node
@pytest.mark.parametrize("name, mutate, expect", REC_HIDE, ids=[m[0] for m in REC_HIDE])
def test_印を検査から隠す書き方は赤(tmp_path, name, mutate, expect):
    red = _rec_page(tmp_path, "send", mutate)
    assert red and red[0].startswith(expect), (name, red)


@needs_node
def test_問いの外の印は赤(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template("send").replace('<input type="hidden" name="__受付番号__" value="">',
                    '<input type="hidden" name="__受付番号__" value=""><label class="opt"><span><b>x</b>' + REC + '</span></label>', 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert any(r.startswith("推奨の印（class=\"rec\"）が問いの選択肢") for r in red), red


@needs_node
def test_title_の中の偽の宛先と_doctype_の無いページは赤(tmp_path):
    html = filled_template("send")
    page = tmp_path / "確認.html"
    page.write_text(re.sub(r"<title>", '<title><body data-dest="copy">', html, count=1), encoding="utf-8")
    red = run_check(page)["red"]
    assert any(r.startswith("<title> の中に < を書かない") for r in red), red
    page.write_text(html.replace("<!doctype html>", "", 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and red[0].startswith("先頭に <!doctype html> が要る"), red


@needs_node
def test_値の中の日本語の名と等号は緑(tmp_path):
    """値の中の「名=」の赤は、検査が読む属性の名（半角）の形だけ。「単価=100」のような字は赤にしない。"""
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace('data-where="2 枚目・送料の行"', 'data-where="2 枚目・送料 単価=100 の行"', 1), encoding="utf-8")
    assert run_check(page)["red"] == []


@needs_node
def test_事実を聞く問いの推奨の印は赤(tmp_path):
    """オーナー宛てでも、事実を聞く問い（ここは q1＝choose）には印を付けない。見込みは .estimate の別枠。"""
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace('<small class="chg">10 月の請求が合計 1,200 円</small>',
                                              '<small class="chg">10 月の請求が合計 1,200 円</small>' + REC, 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and red[0].startswith("問い q1: 推奨の印（small.rec）は作り方の分かれ道の問い（judge）だけ"), red


@needs_node
def test_推奨の字をページに書くのと古い印の形は赤(tmp_path):
    """印の字は型の CSS が出す＝ページの文に「推奨」「おすすめ」を書けば赤。字を書く古い印（tag-rec）も赤。"""
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace("<b>切り捨てる</b>", '<b>切り捨てる<span class="tag-rec">おすすめ</span></b>', 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert any(r.startswith("推奨の印の古い形（tag-rec）は使わない") for r in red), red
    assert any(r.startswith("「おすすめ」は書かない") for r in red), red


REC_JSON = [
    ("good の印（オーナー宛て・judge・1 つ目に理由つき）は緑", lambda d: None, None),
    ("2 つ目に印", lambda d: d["questions"][2]["options"][1].update(recommended="借りた側が使う物のため"),
     "問い q3: 推奨の印は 1 問に 1 つ（今 2）"),
    ("1 つ目を外して 2 つ目にだけ印", lambda d: (d["questions"][2]["options"][0].pop("recommended"),
                                         d["questions"][2]["options"][1].update(recommended="借りた側が使う物のため")),
     "問い q3: 選択肢「借りた側が直す」の推奨の印: 印は 1 つ目の選択肢だけ"),
    ("「分からない」に印", lambda d: d["questions"][2]["options"].append({"value": "__unknown__", "label": "分からない", "recommended": "x"}),
     "問い q3: 「分からない」に推奨の印"),
    ("send に印", lambda d: d.update(dest="send"), "問い q3: 推奨の印（\"recommended\"）はオーナー宛て"),
    ("事実を聞く問いに印", lambda d: d["questions"][1]["options"][0].update(recommended="控えの日付のため"),
     "問い q2: 推奨の印（\"recommended\"）は作り方の分かれ道の問い（judge）だけ"),
    ("理由が文字でない", lambda d: d["questions"][2]["options"][0].update(recommended=True),
     "問い q3: 選択肢「貸した側が直す」の推奨の印: \"recommended\" は理由の文字"),
]


@needs_node
@pytest.mark.parametrize("name, mutate, expect", REC_JSON, ids=[m[0] for m in REC_JSON])
def test_問いのデータの推奨の印(tmp_path, name, mutate, expect):
    data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
    mutate(data)
    q = tmp_path / "q.json"
    q.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    red = run_check(q)["red"]
    if expect is None:
        assert red == [], red
        return
    assert len(red) == 1 and red[0].startswith(expect), (name, red)
