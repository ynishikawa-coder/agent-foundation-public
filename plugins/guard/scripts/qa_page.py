"""PreToolUse — 問いのページ（確認ページ）を外へ出す前に、qa-html の検査（check.mjs）をかけ、赤なら止める。

なぜ在るか: 型（qa-html の template.html）と検査を通らない独自の確認ページが、前に答えた問い・調べれば分かる問い・
道具の都合をそのまま問いにした物をオーナーに出した。宛先がオーナーでも、ページで聞くなら同じ型と検査を当てる
（オーナー同意 2026-11-17）。

見る物（出口を道具の名 Artifact に限らない）:
  - Artifact の publish（action が無いか "publish"・asset の上げは除く）で、file_path と files で足す file。
    （files の HTML は同じ Artifact の別のページとして開けるので、file_path と同じに見る）
  - ほかの外へ出す道具（guard_common の読み手 read_call が「外へ出す」と読んだ MCP の道具＝送る・作る・付ける類の動詞。
    Drive の create_file・Notion の create-pages など）の入力の中身: 入力の字そのもの・base64 の字を解いた物・
    入力が指す手元の file。
  どの file・字も、拡張子や鍵の名でなく中身で読む（.xhtml・.svg・拡張子の無い file・鍵の名を替えた JSON も同じに見る）。
問いのページの見分け（誤検知を少なくするため、どれか 1 つが要る）:
  HTML: ① 型の印（<body data-dest="send|copy|artifact">・CustomEvent('qa:submit')）
        ② 答えを外へ出す口が在り、答えを入れる部品が在るか、部品を読めない形（button・role=button・onclick の要素や、
           script が要素を組む innerHTML・createElement・字を割って組む HTML）が在る。どちらも字の並びで探さず類で読む:
           部品＝要素の木（html.parser）で HTML と ARIA が決める入れる部品の類（input〔hidden・button の類を除く〕・
           select・textarea・role=radio 等・contenteditable）と、script で組む部品（createElement・字の中の HTML）。
           口＝ページから外へ出る道の類（form・qa:submit・sendPrompt・sendBeacon・WebSocket・postMessage・clipboard・
           GET でない fetch／XMLHttpRequest・window.claude の読む動詞でない呼び出し・location に答えを載せる）。
           読むか書くかを字から決められない fetch（method や設定を変数で渡す）は口に数える（既定で数える）。
           （読むだけの fetch と、出す口の無いページの部品は数えない）
        ③ <script> の JSON に、問いの形の構造（question_structure）が在る
  JSON（json として読める物）: 問いの形の構造が在る。鍵の名は見ない＝問いの形とは、dict の並びのうち、2 つ以上の選択肢
        （字の並びか、字を持つ dict の並び）と問いの文（qa-html の問いの終わり＝check.mjs の RULES.question_end を
        直に読む、で終わる字）を持つ物（表のデータ・グラフの系列のように問いの文の無い並びは数えない）。
検査が走らない（check.mjs が見つからない・node が無い・検査が壊れた）時も止める＝緑を確かめられない物は出さない。
  check.mjs の在り処は guard と同じ commit の docs-kit だけ: 同じ repo の plugins/docs-kit か、入れた plugin の
  cache/<市場>/docs-kit/<guard と同じ版>。別の版の docs-kit・path を渡す口（前の AF_QA_CHECK）は使わない＝型と検査の版が
  食い違ったまま判定しない（同じ版が無ければ止めて、docs-kit を同じ版で入れ直すよう名指しする）。
問いのページでないのに止まる時は、repo の値の表 guard.qa_page_exempt（file の path に当てる正規表現の並び）で外す
（値の表は PR とレビューを通るので、窓の中の一存では外れない）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser

import guard_common as G

TIMEOUT = 30
RED_SHOWN = 12

QA_SUBMIT = r"CustomEvent\s*\(\s*[\"']qa:submit[\"']"
TYPE_MARK = re.compile(r"<body\b[^>]*\bdata-dest\s*=\s*[\"']?(?:send|copy|artifact)\b|" + QA_SUBMIT, re.I)
# 答えを入れる部品＝HTML と ARIA が決める入れる部品の類（radio の字を探さない＝select・checkbox・role=radio・
# 手で書く欄も同じ類として数える）
INPUT_TYPES_SKIP = {"hidden", "submit", "button", "reset", "image", "file", "search"}
ANSWER_TAGS = {"select", "textarea"}
ANSWER_ROLES = {"radio", "radiogroup", "checkbox", "switch", "option", "listbox", "combobox", "textbox", "slider",
                "spinbutton", "menuitemradio", "menuitemcheckbox"}
JS_CONTROL = re.compile(
    r"createElement\s*\(\s*[\"'`](?:input|select|textarea)[\"'`]"
    r"|\.type\s*=\s*[\"'`](?:radio|checkbox|text|number|date|range)[\"'`]"
    r"|setAttribute\s*\(\s*[\"'`](?:role|type|contenteditable)[\"'`]\s*,\s*[\"'`](?:" + "|".join(sorted(ANSWER_ROLES)) +
    r"|true|text|number|date)[\"'`]"
    r"|\bcontentEditable\s*=", re.I)
JS_STRING = re.compile(r"`(?:[^`\\]|\\.)*`|\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'", re.S)
# 答えを外へ出す口＝ページから外へ出る道の類。読むだけの道（GET の fetch・window.claude の読む動詞）は数えず、
# 読むか書くかを字から決められない呼び出し（method を変数で渡す fetch など）は出す口に数える（既定で数える）
CLAUDE_READ = re.compile(r"^(?:get|load|read|list|fetch|query|search|view|whoami|me|user|on|subscribe|watch)", re.I)
SENDER = re.compile(
    r"<form\b|" + QA_SUBMIT + r"|\bsendPrompt\s*\(|navigator\.sendBeacon\s*\(|\bnew\s+WebSocket\s*\(|\.postMessage\s*\("
    r"|navigator\.clipboard\.write|\.(?:post|put|patch|delete)\s*\(|\$\.ajax\s*\(|\bnew\s+EventSource\s*\(",
    re.I)
JSON_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.I | re.S)
# 部品を読めない形（答えを出す口と組めば問いのページと見る＝既定で数える）: 押して選ぶ要素と、script が要素を組む形
OPAQUE_SCRIPT = re.compile(r"\.(?:inner|outer)HTML\s*\+?=|insertAdjacentHTML\s*\(|createElement\s*\(|document\.write\s*\("
                           r"|[\"'`]\s*<\w*[\"'`]?\s*\+|\+\s*[\"'`][^\"'`]*(?:type|role)\s*=", re.I)
CLICKABLE_ROLES = {"button", "link", "menuitem", "tab"}
MAX_READ = 2_000_000
QUESTION_END_FALLBACK = r"\S"     # 正本が読めない時は字の在る文を全部問いの文と見る（止める側＝検査が無ければどのみち止まる）



# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}

def question_end(chk=None):
    """問いの文の終わりの正規表現。正本は check.mjs の RULES.question_end（写さず直に読む）。読めなければ字の在る文の全部。"""
    chk = chk if chk is not None else find_check()
    try:
        with open(chk, encoding="utf-8") as f:
            m = re.search(r'"question_end"\s*:\s*("(?:[^"\\]|\\.)*")', f.read())
        return re.compile("(?:%s)\\s*[)）」』]?\\s*$" % json.loads(m.group(1)))
    except Exception:          # noqa: BLE001
        return re.compile("(?:%s)\\s*$" % QUESTION_END_FALLBACK)


def _choices(v):
    """2 つ以上の選択肢の並びか（字の並び＝"str"・字を持つ同じ形の dict の並び＝"obj"）。違えば ""。"""
    if not isinstance(v, list) or len(v) < 2:
        return ""
    if all(isinstance(x, str) and x.strip() for x in v):
        return "str"
    if all(isinstance(x, dict) and any(isinstance(y, str) and y.strip() for y in x.values()) for x in v):
        keys = {frozenset(x) for x in v}
        if frozenset.intersection(*keys):
            return "obj"
    return ""


def _is_question(d, qend):
    if not isinstance(d, dict):
        return False
    asks = any(isinstance(v, str) and qend.search(v.strip()) for v in d.values())
    return asks and any(_choices(v) for v in d.values())


def question_structure(data, depth=0, qend=None):
    """問いの形の構造（選択肢と問いの文を持つ dict の並び）が在るか。鍵の名は見ない。入れ子は 6 段まで見る。"""
    qend = qend or question_end()
    if depth > 6:
        return False
    if isinstance(data, list):
        if any(_is_question(x, qend) for x in data):
            return True
        return any(question_structure(v, depth + 1, qend) for v in data if isinstance(v, (dict, list)))
    if isinstance(data, dict):
        return any(question_structure(v, depth + 1, qend) for v in data.values() if isinstance(v, (dict, list)))
    return False


def _json_of(raw):
    t = (raw or "").strip()
    if not t or t[0] not in "[{":
        return None
    try:
        return json.loads(t)
    except ValueError:
        return None


def why_question_page(path, raw):
    """問いのページなら見分けた理由（1 行）、違えば ""。path は名指しに使うだけ（拡張子で読み方を変えない）。"""
    data = _json_of(raw)
    if data is not None:
        return "問いのデータ（JSON に問いの形の構造＝問いの文と選択肢の並び）" if question_structure(data) else ""
    if TYPE_MARK.search(raw):
        return "確認ページの型の印（data-dest・CustomEvent('qa:submit')）"
    for attrs, body in JSON_SCRIPT.findall(raw):
        got = _json_of(body)
        if got is not None and question_structure(got):
            return "ページに埋めた問いのデータ（<script> の JSON に問いの形の構造）"
    exit_ = answer_exit(raw)
    if not exit_:
        return ""
    control = answer_control(raw)
    if control:
        return "答えを入れる部品（%s）と答えを外へ出す口（%s）の両方" % (control, exit_)
    opaque = unreadable_control(raw)
    if opaque:
        return "答えを外へ出す口（%s）が在り、部品を読めない形（%s）が在る（既定で問いのページと見る）" % (exit_, opaque)
    return ""


class _Clickable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = ""

    def handle_starttag(self, tag, attrs):
        if self.found:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "button" or (tag == "input" and a.get("type", "").strip().lower() in ("button", "submit", "image")):
            self.found = tag
        elif a.get("role", "").strip().lower() in CLICKABLE_ROLES:
            self.found = "role=%s" % a["role"].strip()
        elif "onclick" in a:
            self.found = "onclick の %s" % tag


def unreadable_control(raw):
    """答えを入れる部品を読めない形が在れば何か、無ければ ""（押して選ぶ要素・script が要素を組む形）。"""
    p = _Clickable()
    try:
        p.feed(raw)
        p.close()
    except Exception:          # noqa: BLE001
        return "HTML として読めない"
    if p.found:
        return p.found
    for _attrs, body in JSON_SCRIPT.findall(raw):
        m = OPAQUE_SCRIPT.search(body)
        if m:
            return "script が要素を組む（%s）" % m.group(0).strip()[:30]
    return ""


class _Controls(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = ""

    def handle_starttag(self, tag, attrs):
        if self.found:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "input" and a.get("type", "text").strip().lower() not in INPUT_TYPES_SKIP:
            self.found = "input type=%s" % (a.get("type") or "text")
        elif tag in ANSWER_TAGS:
            self.found = tag
        elif a.get("role", "").strip().lower() in ANSWER_ROLES:
            self.found = "role=%s" % a["role"].strip()
        elif "contenteditable" in a and a["contenteditable"].strip().lower() != "false":
            self.found = "contenteditable"


def _html_controls(text):
    p = _Controls()
    try:
        p.feed(text)
        p.close()
    except Exception:
        return ""
    return p.found


def answer_control(raw):
    """答えを入れる部品が在れば何か（1 語）、無ければ ""。HTML の要素と、script の字の中に組む HTML・JS の組み立ても読む。"""
    found = _html_controls(raw)
    if found:
        return found
    for attrs, body in JSON_SCRIPT.findall(raw):
        m = JS_CONTROL.search(body)
        if m:
            return "script で組む部品（%s）" % m.group(0)[:40]
        for lit in JS_STRING.findall(body):
            if "<" in lit:
                found = _html_controls(lit[1:-1].replace("\\'", "'").replace('\\"', '"'))
                if found:
                    return "script の字の中の %s" % found
    return ""


def _call_args(raw, start):
    """raw[start] が ( の時、対の ) までの中身。"""
    depth, i = 0, start
    while i < len(raw):
        c = raw[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return raw[start + 1:i]
        i += 1
    return raw[start + 1:]


def answer_exit(raw):
    """答えを外へ出す口が在れば何か、無ければ ""。"""
    m = SENDER.search(raw)
    if m:
        return m.group(0)[:30]
    for m in re.finditer(r"\bfetch\s*\(", raw):
        args = _call_args(raw, m.end() - 1)
        meth = re.search(r"\bmethod\s*:\s*([\"'`])(\w+)\1", args)
        if meth:
            if meth.group(2).upper() not in ("GET", "HEAD"):
                return "fetch の method %s" % meth.group(2)
        elif re.search(r"\bmethod\b|\bbody\s*:", args) or re.search(r",\s*[A-Za-z_$][\w$]*\s*$", args.strip()):
            return "fetch（読むか書くかを字から決められない）"
    for m in re.finditer(r"\.open\s*\(\s*([\"'`])(\w+)\1", raw):
        if m.group(2).upper() not in ("GET", "HEAD"):
            return "XMLHttpRequest の %s" % m.group(2)
    for m in re.finditer(r"window\.claude\.((?:\w+\.)*)(\w+)\s*\(", raw):
        if not CLAUDE_READ.match(m.group(2)):
            return "window.claude.%s%s" % (m.group(1), m.group(2))
    if re.search(r"location(?:\.href)?\s*=\s*[^=;]*[?#]|window\.open\s*\([^)]*[?#]", raw):
        return "location に答えを載せる"
    return ""


def find_check(guard_root=None):
    """guard と同じ版の docs-kit の check.mjs の path か ""（別の版へは降りない・path を渡す口も持たない）。"""
    return G.sibling_plugin_file("docs-kit", os.path.join("skills", "qa-html", "check.mjs"), guard_root)


def _resolve(path, data):
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        base = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        path = os.path.join(base, path)
    return path


def reason(path, why, lines, chk=""):
    return (
        "問いのページ（確認ページ）が qa-html の検査を通っていないので、外へ出す（Artifact の publish・ほかの外へ出す道具）のを止めました。\n"
        "  出そうとした file: {}\n"
        "  問いのページと見た訳: {}\n"
        "{}\n"
        "直し方（skill guard:guard-rules の qa_page・docs-kit:qa-html）:\n"
        "  ① まず聞く前に引く: 決定の記録と問いの表を同じ言葉で引き、答え済み・資料で決まる・道具の都合の問いは消す（細目 §4）\n"
        "  ② オーナーへの問いなら選択肢の画面（AskUserQuestion）で聞く。ページで出すなら qa-html の型（template.html）を写して作り直す\n"
        "  ③ node {} {} が緑の物だけを publish する（赤の行を 1 つずつ潰すかは、止めた文の最後の行の入口から決める）"
    ).format(path, why, "\n".join(lines), chk or "<qa-html の check.mjs>", path)


def _sources(ti, data):
    """publish で出る file の path（file_path と files の元）。files は {公開の path: 元 | {from} | {artifact} | None} か [{path}]。"""
    out = []
    fp = ti.get("file_path")
    if isinstance(fp, str):
        out.append(_resolve(fp, data))
    files = ti.get("files")
    root = ti.get("root") if isinstance(ti.get("root"), str) else ""
    items = []
    if isinstance(files, dict):
        for pub, src in files.items():
            if isinstance(src, str):
                items.append(src)
            elif isinstance(src, dict) and isinstance(src.get("from"), str):
                items.append(src["from"])          # {artifact, path} は別の Artifact の物＝ここでは読めない
    elif isinstance(files, list):
        items = [f.get("path") for f in files if isinstance(f, dict) and isinstance(f.get("path"), str)]
    for src in items:
        if root and not os.path.isabs(os.path.expanduser(src)):
            src = os.path.join(root, src)
        out.append(_resolve(src, data))
    return out


def _inline(ti, data):
    """外へ出す道具の入力の中身: [(名指しの場所, 字 or None, 手元の path or None)]。"""
    import base64
    out = []
    for where, t in G.input_strings(ti):
        if not isinstance(t, str) or not t.strip():
            continue
        cand = t.strip()
        if "\n" not in cand and len(cand) < 4096:
            p = _resolve(cand, data)
            if os.path.isfile(p):
                out.append((where, None, p))
                continue
        if len(cand) >= 64 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", cand):
            try:
                dec = base64.b64decode(cand, validate=False).decode("utf-8")
            except Exception:  # noqa: BLE001
                dec = ""
            if dec.strip():
                out.append((where + "（base64 を解いた物）", dec, None))
                continue
        if "<" in cand or cand[:1] in "[{":
            out.append((where, cand, None))
    return out


def check(data, vals):
    """止めるなら理由、通すなら ""。file_path も files で足すページも同じに見る（files の HTML は別のページとして開ける）。
    Artifact 以外の外へ出す道具は、入力の字・base64・入力が指す file を中身で読む。"""
    name = str(data.get("tool_name") or "")
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return ""
    if name == "Artifact":
        if ti.get("asset") or str(ti.get("action") or "publish") != "publish":
            return ""
        for path in _sources(ti, data):
            why = check_page(path, vals)
            if why:
                return why
        return ""
    if not G.read_call(name, ti).out:
        return ""
    for where, text, path in _inline(ti, data):
        why = check_page(path, vals) if path else check_text("%s の %s" % (name, where), text, vals, data)
        if why:
            return why
    return ""


def check_text(label, raw, vals, data):
    """入力の字そのものを照らす（検査は file を読むので、一時の file に写して走らせる）。"""
    if any(isinstance(p, str) and p and re.search(p, label) for p in vals.get("qa_page_exempt") or []):
        return ""
    why = why_question_page(label, raw)
    if not why:
        return ""
    ext = ".json" if _json_of(raw) is not None else ".html"
    d = G.tmp_dir("qa_inline")
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, G.safe_id(label, 60) + ext)
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
    except OSError as e:
        return reason(label, why, ["  検査に渡す一時の file を書けなかった: %s" % e])
    return run_check(path, why, label)


def check_page(path, vals):
    for pat in vals.get("qa_page_exempt") or []:
        if isinstance(pat, str) and pat and re.search(pat, path.replace(os.sep, "/")):
            return ""
    try:
        if os.path.getsize(path) > MAX_READ:
            return ""
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except (OSError, UnicodeDecodeError):
        return ""          # 読めない file・字でない file（画像など）は問いのページでない／道具の側が断る
    why = why_question_page(path, raw)
    if not why:
        return ""
    return run_check(path, why)


def run_check(path, why, shown=None):
    """check.mjs を path に走らせる。緑なら ""、赤・走らないなら止める理由。shown は名指しに使う名（無ければ path）。"""
    shown = shown or path
    chk = find_check()
    node = shutil.which("node")
    if not chk:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return reason(shown, why, ["  検査（docs-kit の qa-html の check.mjs）が guard と同じ版（%s）で見つからず、緑を確かめられない。"
                                  "別の版の検査では照らさない。plugin docs-kit を guard と同じ版で入れ直す（claude plugin install docs-kit@<市場>）" % os.path.basename(here)])
    if not node:
        return reason(shown, why, ["  node が無く、検査（check.mjs）を走らせられない。node を入れる"], chk)
    try:
        p = subprocess.run([node, chk, path, "--json"], capture_output=True, text=True, timeout=TIMEOUT,
                           cwd=os.path.dirname(path))
    except (OSError, subprocess.SubprocessError) as e:
        return reason(shown, why, ["  検査が走らなかった: %s" % e], chk)
    if p.returncode == 0:
        return ""
    try:
        res = json.loads(p.stdout)
        red = [str(r) for r in res.get("red") or []]
    except ValueError:
        red = []
    if p.returncode != 1 or not red:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-3:]
        return reason(shown, why, ["  検査が壊れた（exit %d）: %s" % (p.returncode, " / ".join(tail))], chk)
    lines = ["  検査の赤 %d 件:" % len(red)]
    lines += ["    ✗ " + r for r in red[:RED_SHOWN]]
    if len(red) > RED_SHOWN:
        lines.append("    …ほか %d 件（全部は node %s %s で出る）" % (len(red) - RED_SHOWN, chk, path))
    return reason(shown, why, lines, chk)
