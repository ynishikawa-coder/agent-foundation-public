#!/usr/bin/env node
// qa-html の確認ページの検査（外部依存ゼロ・node だけで動く）。決まりの表はこのファイルの頭の RULES の 1 か所。
//   repo ごとに足す語・上限は repo の根の config/skill-values.json の docs-kit.qa-html.internal_words・limits。
// 赤にする物（形の約束は SKILL.md §型の約束）:
//   型: 宛先の印（data-dest＝send・copy・artifact）が無い／qa:css・qa:js が型（references/template.html）と違う／
//     型の外に style・script を書いた／暗い色の設定／会社の色（--brand）が body の style の外・白地で読めない濃さ／
//     差出人・宛名・連絡先が無い／版（__版__）が無い／送る前の確認と受付の部品が無い
//   問い: 問いの形（data-kind）が 4 つ以外／並び（data-group）が 会社の決まり→人ごとの事実→今回だけの事 でない／
//     内部の言葉／番号で過去の問いを指す／数を書かせる問い／長さ・問いの数の上限超え／選択肢が 1 つだけ／
//     選択肢に A・B などの記号／選択肢の鍵（value）の形・重なり／「分からない」（__unknown__）が無い・最後でない／
//     答えずに送れる（required が無い）／1 問に 2 つ以上／「合っていますか」を食い違いの外で使う／
//     資料の外の事実に「当てはまらない」が無い／ひとこと（supp_鍵）が無い／この答えで決まる事（data-decides）が無い／鍵の重なり
// 読める物は 2 つで、問いの決まりは同じ 1 か所（checkPage）が見る:
//   ① 1 枚の HTML（型を写した物・<body data-dest="send|copy|artifact">・確認のページ（Artifact）も同じ HTML）
//   ② 問いのデータ（JSON・Artifact 型に中身をデータで渡す時。形は SKILL.md §問いのデータ）
// 使い方: node check.mjs <file.html|file.json> [--json] [--values <skill-values.json>]
//   別の検査（配る口の検査など）からは import { checkQa, checkQaJson, checkFile } で呼ぶ。
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// ── 問いの決まりの表（1 か所）。会社ごとに足す語は config/skill-values.json の docs-kit.qa-html.internal_words
//    （文字列か {語, 正規表現, 言い換え}）、上限は docs-kit.qa-html.limits で上書きする。
export const RULES = {
  "limits": {
    "question_chars": 40,
    "known_lines": 2,
    "known_chars": 120,
    "known_table_rows": 5,
    "decides_chars": 40,
    "option_chars": 30,
    "option_detail_chars": 40,
    "questions_per_page": 12
  },
  "kinds": {
    "choose": "どちらが正しいですか＝こちらが計算した候補を並べる（候補 2 つ以上）",
    "mismatch": "資料どうしが食い違う＝「合っていますか」を使ってよいのはここだけ（候補 2 つ以上）",
    "fact": "資料の外にしか無い事実（「当てはまらない」を必ず置く）",
    "judge": "読んでも決まりが分からない時の判断（候補 2 つ以上）"
  },
  "groups": {
    "rule": "会社の決まり（全員に効く）",
    "person": "人ごとの事実",
    "once": "今回だけの事"
  },
  "unknown": { "value": "__unknown__", "label": "分からない・社内で確かめてから答える" },
  "fact_must_have": [
    "当てはまらない"
  ],
  "brand_min_contrast": 4.5,
  "internal_words": [
    {
      "語": "型",
      "正規表現": "(?<![大小新原典定類体血模髪])型(?:に|の|で|を|から)|(?:の|へ)型(?![紙枠録])",
      "言い換え": "決まり・やり方"
    },
    {
      "語": "読む順",
      "正規表現": "読む順",
      "言い換え": "どの資料を先に見るか"
    },
    {
      "語": "立ち上げ",
      "正規表現": "立ち上げ",
      "言い換え": "始める時の設定"
    },
    {
      "語": "仮",
      "正規表現": "仮の(?:値|額|答え|所|印)|仮で(?:計算|進め)|（仮）",
      "言い換え": "今の見込み"
    },
    {
      "語": "式",
      "正規表現": "式の(?:語|一覧|選び方|名)",
      "言い換え": "計算のしかた"
    },
    {
      "語": "部品",
      "正規表現": "部品",
      "言い換え": "（書かない）"
    },
    {
      "語": "道具",
      "正規表現": "道具",
      "言い換え": "（書かない）"
    },
    {
      "語": "照合",
      "正規表現": "照合|照らし合わせ",
      "言い換え": "確かめ"
    },
    {
      "語": "答え（照らす元）",
      "正規表現": "答え(?:と|との|から)(?:一致|照ら|合わ|逆算)",
      "言い換え": "（書かない）"
    },
    {
      "語": "逆算",
      "正規表現": "逆算|検算",
      "言い換え": "（作り方は書かない）"
    },
    {
      "語": "Q-ID の語",
      "正規表現": "Q-?ID|設問番号",
      "言い換え": "問いの中身を言葉で"
    },
    {
      "語": "窓",
      "正規表現": "(?<![一-龥])窓(?!口)",
      "言い換え": "（書かない）"
    },
    {
      "語": "job・PR",
      "正規表現": "\\bjob\\b|\\bPR\\b|scratchpad",
      "言い換え": "（書かない）"
    },
    {
      "語": "md の名",
      "正規表現": "\\.md\\b",
      "言い換え": "決まりの中身を言葉で"
    }
  ],
  "past_question_id": "Q\\d{2,4}[.\\-]\\d{1,2}-\\d+|(?<![A-Za-z0-9])Q-?\\d{1,4}(?![0-9])",
  "number_ask": "(?:額|金額|数|日数|時間|時給|単価|回数|人数)\\s*(?:を|は)?\\s*(?:教えて|書いて|ご記入|記入|入力|ご入力|打ち込|お知らせ)|何(?:日|時間|円|回|人)(?:ですか|でしたか|ありますか|働)",
  "confirm": "合っていますか|こう読みました|こう理解しています|よろしいですか",
  "two_in_one": "、また|また、|および|及び|あわせて|併せて|それぞれ[^。]*(?:と|、)|[^、。・\\s]{2,}と[^、。・\\s]{2,}(?:を|は)(?:教えて|お知らせ|ご確認|確認|決め|選)",
  "question_end": "ですか|ますか|でしょうか|ください|[？?]",
  "option_symbol": "^\\s*(?:案\\s*[A-Za-zＡ-Ｚ0-9０-９]|[A-Za-zＡ-Ｚａ-ｚ](?:\\s*[.．:：、)）]|\\s+)|[0-9０-９]{1,2}\\s*[.．:：、)）](?![0-9０-９])|[①-⑳])|^\\s*[(（](?:[A-Za-zＡ-Ｚ]|[0-9]{1,2})[)）]",
  "symbol_ref": "(?<![A-Za-z0-9])(?:案\\s*)?[A-DＡ-Ｄ]\\s*(?:なら|の場合|案|を選)"
};
const KINDS = Object.keys(RULES.kinds);
const GROUPS = Object.keys(RULES.groups);
const FREE = "__自由記入__";
const UNKNOWN = RULES.unknown.value;
const TEMPLATE = fileURLToPath(new URL("./references/template.html", import.meta.url));

// 会社の表（config/skill-values.json）を、渡した path か、ファイルの dir と今の dir から上へ探す。
export function findValues(...starts) {
  for (const s of starts.filter(Boolean)) {
    let d = resolve(s);
    for (;;) {
      const p = join(d, "config", "skill-values.json");
      if (existsSync(p)) return p;
      const up = dirname(d);
      if (up === d) break;
      d = up;
    }
  }
  return null;
}

function loadCompany(valuesPath) {
  if (!valuesPath) return {};
  try {
    return JSON.parse(readFileSync(valuesPath, "utf8"))?.["docs-kit"]?.["qa-html"] ?? {};
  } catch {
    return {};
  }
}

const mask = (s) => s.replace(/<!--[\s\S]*?(-->|$)/g, (m) => " ".repeat(m.length));
const dropCode = (s) => s.replace(/<(script|style)\b[\s\S]*?<\/\1\s*>/gi, (m) => " ".repeat(m.length));
const decode = (s) =>
  s.replace(/&nbsp;/g, " ").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
// 見える字（行は <br>・塊の終わりで区切る）
function textLines(html) {
  const t = html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(li|p|div|tr|h\d|legend|summary|label|dt|dd)\s*>/gi, "\n")
    .replace(/<[^>]+>/g, " ");
  return decode(t)
    .split("\n")
    .map((x) => x.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}
const text = (html) => textLines(html).join(" ");
const len = (s) => [...String(s).replace(/\s+/g, "")].length;
const attr = (tag, name) => {
  const m = new RegExp(`\\s${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`, "i").exec(tag);
  return m ? decode(m[1] ?? m[2]) : null;
};
const hasAttr = (tag, name) => new RegExp(`\\s${name}(?:\\s*=|[\\s>/])`, "i").test(tag);

// 開きタグの位置から、同じ名のタグの入れ子を数えて閉じまでの [始め, 終わり) を返す。
function elementAt(html, at) {
  const open = /^<([a-z][a-z0-9]*)\b[^>]*>/i.exec(html.slice(at));
  if (!open) return null;
  const tag = open[1];
  const tok = new RegExp(`<(/?)${tag}\\b[^>]*>`, "gi");
  tok.lastIndex = at + open[0].length;
  let depth = 1;
  for (let m; (m = tok.exec(html)); ) {
    depth += m[1] ? -1 : 1;
    if (!depth) return { start: at, end: m.index + m[0].length, inner: html.slice(at + open[0].length, m.index), tag: open[0] };
  }
  return { start: at, end: html.length, inner: html.slice(at + open[0].length), tag: open[0] };
}
function byClass(html, cls) {
  const out = [];
  const re = new RegExp(`<[a-z][a-z0-9]*\\b[^>]*\\bclass\\s*=\\s*["'][^"']*\\b${cls}\\b[^"']*["'][^>]*>`, "gi");
  for (const m of html.matchAll(re)) out.push(elementAt(html, m.index));
  return out.filter(Boolean);
}
const byId = (html, id) => {
  const m = new RegExp(`<[a-z][a-z0-9]*\\b[^>]*\\bid\\s*=\\s*["']${id}["'][^>]*>`, "i").exec(html);
  return m ? elementAt(html, m.index) : null;
};

// 宛先: send＝素のフォームで配る口へ・copy＝答えを写して貼り戻す・artifact＝確認のページ（Artifact）が答えを受ける
export const DESTS = ["send", "copy", "artifact"];

function compileWords(company) {
  return [...RULES.internal_words, ...(company.internal_words ?? [])].map((w) =>
    typeof w === "string" ? { 語: w, re: new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "u") } : { ...w, re: new RegExp(w.正規表現 ?? w.語, "u") },
  );
}

// 型の動かない所（qa:css・qa:js）の中身。空白の違いは見ない。
const region = (raw, name) => {
  const m = new RegExp(`<!--${name}-->([\\s\\S]*?)<!--/${name}-->`).exec(raw);
  return m ? m[1].replace(/\s+/g, " ").trim() : null;
};
let templateCache = null;
const templateRegions = () =>
  (templateCache ??= (() => {
    const t = readFileSync(TEMPLATE, "utf8");
    return { "qa:css": region(t, "qa:css"), "qa:js": region(t, "qa:js") };
  })());

// 白地に対する色の濃さ（WCAG の比）
function contrastOnWhite(hex) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const L = 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  return 1.05 / (L + 0.05);
}
function checkBrand(color, red) {
  if (color == null) return;
  if (!/^#[0-9a-fA-F]{6}$/.test(color)) {
    red.push(`会社の色は #rrggbb の 1 色だけ（今 ${color}）`);
    return;
  }
  const c = contrastOnWhite(color);
  if (c < RULES.brand_min_contrast) red.push(`会社の色 ${color} は白地で読みにくい（濃さの比 ${c.toFixed(1)}・${RULES.brand_min_contrast} 以上）`);
}

// ── 読み取り 1: HTML（型を写した 1 枚） → 問いの形と、型の約束の赤
export function readHtml(raw) {
  const html = dropCode(mask(raw));
  const holes = [...new Set(mask(raw).match(/\{\{[^}]*\}\}/g) ?? [])];
  const shape = [];

  const body = /<body\b[^>]*>/i.exec(html)?.[0] ?? "";
  const dest = attr(body, "data-dest");

  // 型の動かない所
  const tpl = templateRegions();
  for (const name of ["qa:css", "qa:js"]) {
    const got = region(raw, name);
    if (got == null) shape.push(`型の ${name} の印が無い（型を丸ごと写す）`);
    else if (got !== tpl[name]) shape.push(`${name} の中身が型と違う（宛先で変えてよいのは 差出人・宛名・連絡先・会社の色 だけ）`);
  }
  const outside = mask(raw.replace(/<!--qa:(css|js)-->[\s\S]*?<!--\/qa:\1-->/g, " "));
  if (/<style\b/i.test(outside)) shape.push("型の外に <style> がある（見た目は型の 1 つだけ）");
  if (/<script\b/i.test(outside)) shape.push("型の外に <script> がある（動きは型の 1 つだけ・送信の JS も書かない）");
  if (/<link\b[^>]*rel\s*=\s*["']?stylesheet/i.test(outside)) shape.push("外の見た目（link stylesheet）を読んでいる");
  if (/prefers-color-scheme\s*:\s*dark|color-scheme\s*:\s*[^;"'}]*dark|name\s*=\s*["']color-scheme["'][^>]*content\s*=\s*["'][^"']*dark/i.test(raw))
    shape.push("暗い色の設定がある（明るい色で固定）");
  for (const m of html.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\sstyle\s*=\s*(?:"[^"]*"|'[^']*')[^>]*>/gi)) {
    if (m[1].toLowerCase() !== "body") shape.push(`<${m[1]}> に style がある（色や形は変えない・会社の色は body の --brand だけ）`);
  }
  const bodyStyle = attr(body, "style");
  let brand = null;
  if (bodyStyle != null) {
    const b = /^\s*--brand\s*:\s*([^;]+?)\s*;?\s*$/.exec(bodyStyle);
    if (!b) shape.push(`body の style に置けるのは --brand の 1 色だけ（今 ${bodyStyle}）`);
    else brand = b[1];
  }

  // 差出人・宛名・連絡先・版・送る前の確認と受付
  const header = /<header\b[^>]*>[\s\S]*?<\/header\s*>/i.exec(html)?.[0] ?? "";
  for (const [cls, name] of [["to", "宛名"], ["from", "差出人"], ["contact", "連絡先"]]) {
    const el = byClass(header, cls)[0];
    if (!el || !text(el.inner)) shape.push(`${name}（header の .${cls}）が無い`);
  }
  const forms = html.match(/<form\b/gi) ?? [];
  if (forms.length !== 1) shape.push(`form は 1 つ（今 ${forms.length}）`);
  const formTag = /<form\b[^>]*>/i.exec(html)?.[0] ?? "";
  if (/\s(method|action)\s*=/i.test(formTag)) shape.push("form に method・action を書かない（配る口が書き込む）");
  const ver = /<input\b[^>]*\bname\s*=\s*["']__版__["'][^>]*>/i.exec(html);
  const version = ver ? attr(ver[0], "value") ?? "" : null;
  if (version == null) shape.push('版（<input type="hidden" name="__版__">）が無い');
  else if (!/^[0-9A-Za-z._-]+$/.test(version) && !/^\{\{/.test(version)) shape.push(`版は半角英数字と . _ - だけ（今 ${version}）`);
  if (!/<input\b[^>]*\bname\s*=\s*["']__受付番号__["']/i.test(html)) shape.push('受付番号の欄（<input type="hidden" name="__受付番号__">）が無い');
  for (const [id, name] of [["qa-review", "送る前の確認"], ["qa-sum", "答えの一覧"], ["qa-done", "受付"], ["qa-rno", "受付番号"], ["copybtn", "写すボタン"], ["out", "答えの控え"]]) {
    if (!byId(html, id)) shape.push(`${name}（id=${id}）が無い`);
  }
  const send = /<button\b[^>]*\bid\s*=\s*["']sendbtn["'][^>]*>/i.exec(html);
  if (!send || !/\stype\s*=\s*["']submit["']/i.test(send[0])) shape.push('送るボタン（<button type="submit" id="sendbtn">）が無い');
  const next = byClass(html, "next")[0];
  if (!next || !text(next.inner)) shape.push("受付の「この後のこと」（.next）が無い");

  const visible = textLines(html.replace(/<(head)\b[\s\S]*?<\/head\s*>/i, (m) => (/<title>([\s\S]*?)<\/title>/i.exec(m)?.[1] ?? "")));
  const attrTexts = [...html.matchAll(/\bdata-(?:qlabel|decides|glabel)\s*=\s*(?:"([^"]*)"|'([^']*)')/gi)].map((m) => decode(m[1] ?? m[2]));

  const questions = [];
  for (const m of html.matchAll(/<[a-z][a-z0-9]*\b[^>]*\bdata-qkey\s*=\s*["']([^"']+)["'][^>]*>/gi)) {
    if (m[1] === FREE) continue;
    const q = elementAt(html, m.index);
    if (!q) continue;
    const legend = /<legend\b[^>]*>([\s\S]*?)<\/legend\s*>/i.exec(q.inner);
    const known = byClass(q.inner, "known")[0];
    const knownTables = known ? [...known.inner.matchAll(/<table\b[\s\S]*?<\/table\s*>/gi)] : [];
    const inputs = [...q.inner.matchAll(/<input\b[^>]*\btype\s*=\s*["']?(radio|checkbox)\b[^>]*>/gi)].map((i) => i[0]);
    const sel = [...q.inner.matchAll(/<option\b[^>]*>([\s\S]*?)<\/option>/gi)].filter((o) => attr(o[0], "value") !== "" && text(o[1]));
    const opts = [...q.inner.matchAll(/<label\b[^>]*\bclass\s*=\s*["'][^"']*\bopt\b[^"']*["'][^>]*>([\s\S]*?)<\/label>/gi)].map((o) => {
      const inp = /<input\b[^>]*>/i.exec(o[1])?.[0] ?? "";
      const b = /<b\b[^>]*>([\s\S]*?)<\/b>/i.exec(o[1]);
      const small = /<small\b[^>]*>([\s\S]*?)<\/small>/i.exec(o[1]);
      return {
        value: attr(inp, "value"),
        all: text(o[1]),
        head: text((b ? b[1] : o[1]).replace(/<span\b[^>]*class\s*=\s*["'][^"']*tag-rec[\s\S]*?<\/span>/gi, "")),
        detail: small ? text(small[1]) : "",
        rec: /tag-rec/.test(o[1]),
      };
    });
    const freeInputs = [...q.inner.matchAll(/<input\b[^>]*\btype\s*=\s*["']?(text|date|month|number)\b[^>]*>|<select\b[^>]*>|<textarea\b[^>]*\bname\s*=\s*["'](?!supp_)[^>]*>/gi)].map((i) => i[0]);
    questions.push({
      key: m[1],
      kind: attr(q.tag, "data-kind"),
      group: attr(q.tag, "data-group"),
      question: legend ? text(legend[1]) : "",
      multiline: !!legend && /<br\b/i.test(legend[1]),
      known: known ? textLines(known.inner.replace(/<table\b[\s\S]*?<\/table\s*>/gi, "")) : [],
      tableRows: knownTables.reduce((n, t) => n + (t[0].match(/<tr\b/gi) ?? []).length, 0),
      decides: attr(q.tag, "data-decides") ?? "",
      options: opts,
      choices: inputs.length || sel.length,
      oneChoice: (inputs.length > 0 && inputs.length < 2) || (!inputs.length && sel.length === 1),
      freeInput: freeInputs.length > 0,
      required: [...inputs, ...freeInputs].some((t) => hasAttr(t, "required")),
      unknownLast: opts.length > 0 && opts[opts.length - 1].value === UNKNOWN,
      supp: new RegExp(`\\bname\\s*=\\s*["']supp_${m[1]}["']`).test(q.inner),
    });
  }
  return { format: "html", dest, holes, shape, brand, texts: [...visible, ...attrTexts], questions };
}

// ── 読み取り 2: 問いのデータ（JSON）。確認のページを Artifact 型で作り、問いをデータで渡す時の形（SKILL.md §問いのデータ）。
//   「分からない」と「ほかに伝えたい事」は型の側が足す＝データに書かない。
const lines = (v) => (Array.isArray(v) ? v : typeof v === "string" ? v.split("\n") : []).map((x) => String(x).trim()).filter(Boolean);
export function readJson(data) {
  const shape = [];
  const qsIn = Array.isArray(data?.questions) ? data.questions : [];
  for (const [k, name] of [["to", "宛名"], ["from", "差出人"], ["contact", "連絡先"], ["title", "件名"], ["next", "この後のこと"]]) {
    if (!String(data?.[k] ?? "").trim()) shape.push(`${name}（"${k}"）が無い`);
  }
  const version = data?.version;
  if (version == null || !String(version).trim()) shape.push('版（"version"）が無い');
  else if (!/^[0-9A-Za-z._-]+$/.test(String(version))) shape.push(`版は半角英数字と . _ - だけ（今 ${version}）`);
  const questions = qsIn
    .filter((q) => q?.key !== FREE)
    .map((q) => {
      const raw = Array.isArray(q.options) ? q.options : [];
      if (raw.some((o) => typeof o === "string")) shape.push(`問い ${q.key}: 選択肢は {"value","label"} の形で書く（文字だけでは機械で戻せない）`);
      const options = raw
        .filter((o) => o && typeof o === "object" ? o.value !== UNKNOWN : true)
        .map((o) =>
          typeof o === "string"
            ? { value: null, head: o, all: o, detail: "" }
            : { value: o?.value ?? null, head: String(o?.label ?? ""), detail: String(o?.detail ?? ""), all: [o?.label, o?.detail].filter(Boolean).join(" "), rec: !!o?.recommended },
        );
      const table = Array.isArray(q.table) ? q.table : [];
      return {
        key: String(q.key ?? ""),
        kind: q.kind ?? null,
        group: q.group ?? null,
        question: String(q.question ?? "").trim(),
        multiline: /\n/.test(String(q.question ?? "").trim()),
        known: lines(q.known),
        tableRows: table.length,
        decides: String(q.decides ?? "").trim(),
        options,
        choices: options.length,
        oneChoice: options.length === 1,
        freeInput: ["text", "date", "month", "number"].includes(q.input),
        required: true, // 型の側が付ける
        unknownLast: true, // 型の側が足す
        supp: q.supp !== false,
      };
    });
  const texts = [data?.to, data?.from, data?.contact, data?.title, data?.lead, data?.due, data?.next, ...qsIn.flatMap((q) => [q?.label, q?.glabel, q?.question, ...lines(q?.known), q?.more, q?.decides,
    ...(Array.isArray(q?.table) ? q.table.flat().map(String) : []),
    ...(Array.isArray(q?.options) ? q.options.flatMap((o) => (typeof o === "string" ? [o] : [o?.label, o?.detail])) : [])])]
    .flatMap((x) => lines(x));
  const holes = [...new Set(JSON.stringify(data ?? {}).match(/\{\{[^}]*\}\}/g) ?? [])];
  return { format: "json", dest: data?.dest ?? null, holes, shape, brand: data?.brand ?? null, texts, questions };
}

// ── 決まり: 問いの形（HTML でも JSON でも同じ物）を 1 か所で見る
export function checkPage(page, { valuesPath = null } = {}) {
  const company = loadCompany(valuesPath);
  const limits = { ...RULES.limits, ...(company.limits ?? {}) };
  const words = compileWords(company);
  const rx = (k) => new RegExp(RULES[k], "u");
  const red = [...page.shape];
  const warn = [];
  const { dest, holes, questions: qs } = page;

  if (holes.length) red.push(`型の差し込みが残っている: ${holes.slice(0, 3).join("、")}${holes.length > 3 ? ` ほか ${holes.length - 3} 個` : ""}`);
  if (!DESTS.includes(dest)) red.push(`宛先の印が無い: data-dest="send|copy|artifact"（HTML は <body data-dest>・データは "dest"）`);
  checkBrand(page.brand, red);

  for (const line of page.texts) {
    for (const w of words) {
      const m = w.re.exec(line);
      if (m) red.push(`内部の言葉「${m[0]}」（${w.語}→${w.言い換え ?? "先方の言葉で"}）: ${line.slice(0, 60)}`);
    }
    const q = rx("past_question_id").exec(line);
    if (q) red.push(`番号「${q[0]}」で過去の問いを指している（言葉で書き直し、元の問いへのリンクを付ける）: ${line.slice(0, 60)}`);
  }

  if (!qs.length) red.push("問い（data-qkey を持つ箱・データの questions）が 1 つも無い");
  if (qs.length > limits.questions_per_page) red.push(`問いが ${qs.length} 個（1 枚 ${limits.questions_per_page} 問まで＝要らない問いを外すか 2 枚に分ける）`);
  const keys = qs.map((q) => q.key);
  for (const k of new Set(keys.filter((k, i) => keys.indexOf(k) !== i))) red.push(`問いの鍵「${k}」が重なっている（鍵は 1 問に 1 つ）`);

  let lastGroup = -1;
  for (const q of qs) {
    const id = `問い ${q.key || "(鍵なし)"}`;
    if (!/^[A-Za-z0-9_]+$/.test(q.key)) red.push(`${id}: 鍵は半角英数字と _ だけ`);
    if (!KINDS.includes(q.kind)) red.push(`${id}: 問いの形 data-kind が ${KINDS.join("・")} のどれでもない（今 ${q.kind ?? "無し"}）`);
    const gi = GROUPS.indexOf(q.group);
    if (gi < 0) red.push(`${id}: まとまり data-group が ${GROUPS.join("・")} のどれでもない（今 ${q.group ?? "無し"}）`);
    else if (gi < lastGroup) red.push(`${id}: 並びが逆（${GROUPS.map((g) => RULES.groups[g]).join(" → ")} の順に並べる）`);
    else lastGroup = gi;

    const qtext = q.question;
    if (!qtext) red.push(`${id}: 問いの 1 行（legend）が無い`);
    if (q.multiline) red.push(`${id}: 問いが 2 行以上（1 行にする）`);
    if (len(qtext) > limits.question_chars) red.push(`${id}: 問いが ${len(qtext)} 字（${limits.question_chars} 字まで）: ${qtext}`);
    const ends = qtext.match(new RegExp(RULES.question_end, "gu")) ?? [];
    if (ends.length > 1 || rx("two_in_one").test(qtext)) red.push(`${id}: 1 問に 2 つ以上を聞いている（1 問 1 つに分ける）: ${qtext}`);
    if (/^\s*(?:[A-Za-z]?-?\d+[.．]|問\s*\d+)/.test(qtext)) red.push(`${id}: 問いの頭に番号を付けない（進み具合は型が出す）: ${qtext}`);

    if (q.known.length > limits.known_lines) red.push(`${id}: 分かっている事が ${q.known.length} 行（${limits.known_lines} 行まで・数字は表に・残りは「くわしく」へ）`);
    if (len(q.known.join("")) > limits.known_chars) red.push(`${id}: 分かっている事が ${len(q.known.join(""))} 字（${limits.known_chars} 字まで）`);
    if (q.tableRows > limits.known_table_rows) red.push(`${id}: 数字の表が ${q.tableRows} 行（見出しを入れて ${limits.known_table_rows} 行まで）`);
    const asked = [qtext, ...q.known].join(" ");
    const num = rx("number_ask").exec(asked);
    if (num) red.push(`${id}: 数を書かせる問い「${num[0]}」（こちらで計算した候補を並べて「どちらが正しいですか」にする）`);
    const conf = rx("confirm").exec(asked);
    if (conf && q.kind !== "mismatch") red.push(`${id}: 「${conf[0]}」は資料どうしが食い違う時だけ（data-kind="mismatch"）`);
    const sym = rx("symbol_ref").exec(asked);
    if (sym) red.push(`${id}: 記号「${sym[0]}」で選択肢を指している（中身の言葉で書く）`);

    if (!q.decides) red.push(`${id}: この答えで決まる事（data-decides）が無い`);
    else if (len(q.decides) > limits.decides_chars) red.push(`${id}: この答えで決まる事が ${len(q.decides)} 字（${limits.decides_chars} 字まで）`);

    if (q.oneChoice) red.push(`${id}: 選択肢が 1 つだけ（「分からない」の外に 2 つ以上）`);
    if (!q.choices && !q.freeInput) red.push(`${id}: 答える欄が無い`);
    if (!q.required) red.push(`${id}: 答えずに送れる（最初の選択肢か入力の欄に required を付ける）`);
    const real = q.options.filter((o) => o.value !== UNKNOWN);
    if (real.filter((o) => o.rec).length > 1) red.push(`${id}: おすすめは 1 つまで`);
    const vals = [];
    for (const o of real) {
      if (len(o.head) > limits.option_chars) red.push(`${id}: 選択肢の見出しが ${len(o.head)} 字（${limits.option_chars} 字まで・中身は結果の 1 行へ）: ${o.head.slice(0, 30)}…`);
      if (len(o.detail) > limits.option_detail_chars) red.push(`${id}: 選択肢の結果の 1 行が ${len(o.detail)} 字（${limits.option_detail_chars} 字まで）: ${o.detail.slice(0, 30)}…`);
      if (rx("option_symbol").test(o.head)) red.push(`${id}: 選択肢に記号を付けない（中身の見出しで書く）: ${o.head.slice(0, 30)}`);
      if (o.value == null || !/^[A-Za-z0-9_]+$/.test(o.value) || o.value.startsWith("__")) red.push(`${id}: 選択肢の鍵（value）は半角英数字と _ だけ（__ で始めない）: ${o.head.slice(0, 20)}（今 ${o.value ?? "無し"}）`);
      vals.push(o.value);
    }
    for (const v of new Set(vals.filter((v, i) => v != null && vals.indexOf(v) !== i))) red.push(`${id}: 選択肢の鍵「${v}」が重なっている`);
    if (q.choices) {
      const unk = q.options.find((o) => o.value === UNKNOWN);
      if (page.format === "html") {
        if (!unk) red.push(`${id}: 「${RULES.unknown.label}」（value="${UNKNOWN}"）が無い`);
        else if (unk.head !== RULES.unknown.label) red.push(`${id}: 「分からない」の文は「${RULES.unknown.label}」のまま`);
        else if (!q.unknownLast) red.push(`${id}: 「分からない」は選択肢の最後に置く`);
      }
    }
    if (q.kind === "fact") {
      for (const must of RULES.fact_must_have) if (!q.options.some((o) => o.all.includes(must))) red.push(`${id}: 資料の外の事実の問いに「${must}」の選択肢が無い`);
    }
    if (!q.supp) red.push(`${id}: ひとことの欄（name="supp_${q.key}"）が無い`);
  }
  return { ok: red.length === 0, format: page.format, dest, questions: keys, red: [...new Set(red)], warn };
}

// 入口（ほかの検査は import して呼ぶ）
export const checkQa = (raw, opts) => checkPage(readHtml(raw), opts);
export const checkQaJson = (data, opts) => checkPage(readJson(typeof data === "string" ? JSON.parse(data) : data), opts);
export function checkFile(path, opts) {
  const raw = readFileSync(path, "utf8");
  if (/\.json$/i.test(path) || /^\s*\{/.test(raw)) {
    let data;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      return { ok: false, format: "json", dest: null, questions: [], red: [`JSON として読めない: ${e.message}`], warn: [] };
    }
    return checkQaJson(data, opts);
  }
  return checkQa(raw, opts);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const file = args.find((a, i) => !a.startsWith("--") && args[i - 1] !== "--values");
  if (!file) {
    console.error("使い方: check.mjs <file.html|file.json> [--json] [--values <skill-values.json>]");
    process.exit(2);
  }
  const vi = args.indexOf("--values");
  const valuesPath = vi >= 0 ? args[vi + 1] : findValues(dirname(resolve(file)), process.cwd());
  const res = checkFile(file, { valuesPath });
  if (args.includes("--json")) console.log(JSON.stringify({ file: resolve(file), ...res }, null, 2));
  else {
    console.log(`${res.ok ? "🟢 緑" : "🔴 赤"}  ${resolve(file)}（${res.format}・問い ${res.questions.length}・宛先 ${res.dest ?? "?"}）`);
    for (const r of res.red) console.log(`  ✗ ${r}`);
  }
  process.exit(res.ok ? 0 : 1);
}
