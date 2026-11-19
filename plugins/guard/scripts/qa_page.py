"""PreToolUse — 問いのページ（確認ページ）を Artifact で出す前に、qa-html の検査（check.mjs）をかけ、赤なら止める。

なぜ在るか: 型（qa-html の template.html）と検査を通らない独自の確認ページが、前に答えた問い・調べれば分かる問い・
道具の都合をそのまま問いにした物をオーナーに出した。宛先がオーナーでも、ページで聞くなら同じ型と検査を当てる
（オーナー同意 2026-11-17）。

見る物: Artifact の publish（action が無いか "publish"・asset の上げは除く）で、file_path と files で足す file のうち .html か .json の物。
  （files の HTML は同じ Artifact の別のページとして開けるので、file_path と同じに見る）
問いのページの見分け（誤検知を少なくするため、どれか 1 つが要る）:
  HTML: ① 型の印（<body data-dest="send|copy|artifact">・CustomEvent('qa:submit')）
        ② 答えを入れる部品と、答えを外へ出す口の両方。どちらも字の並びで探さず類で読む:
           部品＝要素の木（html.parser）で HTML と ARIA が決める入れる部品の類（input〔hidden・button の類を除く〕・
           select・textarea・role=radio 等・contenteditable）と、script で組む部品（createElement・字の中の HTML）。
           口＝ページから外へ出る道の類（form・qa:submit・sendPrompt・sendBeacon・WebSocket・postMessage・clipboard・
           GET でない fetch／XMLHttpRequest・window.claude の読む動詞でない呼び出し・location に答えを載せる）。
           読むか書くかを字から決められない fetch（method や設定を変数で渡す）は口に数える（既定で数える）。
           （読むだけの fetch と、出す口の無いページの部品は数えない）
        ③ <script id="state"> などの JSON に、問いの並び（qs・questions）で、選択肢（options・choices）を持つ物
  JSON: 問いの並び（questions・qs）で、選択肢を持つ物（Artifact 型へ渡す問いのデータ）
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

PAGE_EXT = (".html", ".htm", ".json")
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
Q_KEYS = ("questions", "qs")
OPT_KEYS = ("options", "choices", "opts")



# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}

def _has_question_list(data, depth=0):
    """問いの並び（questions・qs）で、選択肢を持つ問いが 1 つでもあるか。入れ子は 3 段まで見る。"""
    if depth > 3:
        return False
    if isinstance(data, dict):
        for k in Q_KEYS:
            qs = data.get(k)
            if isinstance(qs, list) and any(isinstance(q, dict) and any(isinstance(q.get(o), list) and q.get(o) for o in OPT_KEYS) for q in qs):
                return True
        return any(_has_question_list(v, depth + 1) for v in data.values() if isinstance(v, (dict, list)))
    if isinstance(data, list):
        return any(_has_question_list(v, depth + 1) for v in data if isinstance(v, (dict, list)))
    return False


def why_question_page(path, raw):
    """問いのページなら見分けた理由（1 行）、違えば ""。"""
    if path.lower().endswith(".json"):
        try:
            return "問いのデータ（questions／qs に選択肢）" if _has_question_list(json.loads(raw)) else ""
        except ValueError:
            return ""
    if TYPE_MARK.search(raw):
        return "確認ページの型の印（data-dest・CustomEvent('qa:submit')）"
    for attrs, body in JSON_SCRIPT.findall(raw):
        if "json" in attrs.lower() or re.search(r"\bid\s*=\s*[\"']?state\b", attrs, re.I):
            try:
                if _has_question_list(json.loads(body.strip())):
                    return "ページに埋めた問いのデータ（<script> の JSON に questions／qs と選択肢）"
            except ValueError:
                pass
    control, exit_ = answer_control(raw), answer_exit(raw)
    if control and exit_:
        return "答えを入れる部品（%s）と答えを外へ出す口（%s）の両方" % (control, exit_)
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
        "問いのページ（確認ページ）が qa-html の検査を通っていないので、Artifact に出すのを止めました。\n"
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


def check(data, vals):
    """止めるなら理由、通すなら ""。file_path も files で足すページも同じに見る（files の HTML は別のページとして開ける）。"""
    if str(data.get("tool_name") or "") != "Artifact":
        return ""
    ti = data.get("tool_input")
    if not isinstance(ti, dict) or ti.get("asset"):
        return ""
    if str(ti.get("action") or "publish") != "publish":
        return ""
    for path in _sources(ti, data):
        why = check_page(path, vals)
        if why:
            return why
    return ""


def check_page(path, vals):
    if not path.lower().endswith(PAGE_EXT):
        return ""
    for pat in vals.get("qa_page_exempt") or []:
        if isinstance(pat, str) and pat and re.search(pat, path.replace(os.sep, "/")):
            return ""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return ""          # 読めない file は Artifact の道具の側が断る
    why = why_question_page(path, raw)
    if not why:
        return ""
    chk = find_check()
    node = shutil.which("node")
    if not chk:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return reason(path, why, ["  検査（docs-kit の qa-html の check.mjs）が guard と同じ版（%s）で見つからず、緑を確かめられない。"
                                  "別の版の検査では照らさない。plugin docs-kit を guard と同じ版で入れ直す（claude plugin install docs-kit@<市場>）" % os.path.basename(here)])
    if not node:
        return reason(path, why, ["  node が無く、検査（check.mjs）を走らせられない。node を入れる"], chk)
    try:
        p = subprocess.run([node, chk, path, "--json"], capture_output=True, text=True, timeout=TIMEOUT,
                           cwd=os.path.dirname(path))
    except (OSError, subprocess.SubprocessError) as e:
        return reason(path, why, ["  検査が走らなかった: %s" % e], chk)
    if p.returncode == 0:
        return ""
    try:
        res = json.loads(p.stdout)
        red = [str(r) for r in res.get("red") or []]
    except ValueError:
        red = []
    if p.returncode != 1 or not red:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-3:]
        return reason(path, why, ["  検査が壊れた（exit %d）: %s" % (p.returncode, " / ".join(tail))], chk)
    lines = ["  検査の赤 %d 件:" % len(red)]
    lines += ["    ✗ " + r for r in red[:RED_SHOWN]]
    if len(red) > RED_SHOWN:
        lines.append("    …ほか %d 件（全部は node %s %s で出る）" % (len(red) - RED_SHOWN, chk, path))
    return reason(path, why, lines, chk)
