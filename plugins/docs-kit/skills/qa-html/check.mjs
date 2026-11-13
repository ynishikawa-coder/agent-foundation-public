#!/usr/bin/env node
// qa-html の確認ページの検査（外部依存ゼロ・node だけで動く）。決まりの表はこのファイルの頭の RULES の 1 か所。
//   repo ごとに足す語・上限は repo の根の config/skill-values.json の docs-kit.qa-html.internal_words・limits。
// 赤にする物（形の約束は SKILL.md §型の約束）:
//   型: 宛先の印（data-dest＝send・copy・artifact）が無い／qa:css・qa:js・qa:foot が型（references/template.html）と違う
//     （qa:foot は「この後のこと」だけ差してよい）／型の外に許す物の表（ALLOW）に無い要素・属性・URL を書いた
//     （script・style・iframe・on… の属性・javascript:・外のリソースなど）／暗い色の設定／会社の色（--brand）が body の style の外・白地で読めない濃さ／
//     差出人・宛名・連絡先が無い／版（__版__）が無い／送る前の確認と受付の部品が無い
//   前提（3 段）: 読んだ資料の一覧（.docs の li[data-doc]）・答えるまでの扱い（.hold）が無い／まとまりの 1 行（.glead）が
//     各まとまりの最初の問いに 1 つでない／1 問の 4 欄（何について .about・見つけた事 .known と data-docs・なぜ聞くか .why・
//     くわしく details.more）のどれかが空・上限超え・見つけた事が一覧に無い資料を指す／なぜ聞くかが決まった 4 文でない／
//     切り抜き（figure.clip）が 3 枚以上・一覧に無い資料・問いの人の外の名が写る／選択肢にこの答えで変わる事（small.chg）が無い
//   問い: 問いの形（data-kind）が 4 つ以外／並び（data-group）が 会社の決まり→人ごとの事実→今回だけの事 でない／
//     内部の言葉／番号で過去の問いを指す／数を書かせる問い／長さ・問いの数の上限超え／選択肢が 1 つだけ／
//     選択肢に A・B などの記号／選択肢の鍵（value）の形・重なり／「分からない」（__unknown__）が無い・最後でない／
//     答えずに送れる（required が無い）／1 問に 2 つ以上／「合っていますか」を食い違いの外で使う／
//     資料の外の事実に「当てはまらない」が無い／ひとこと（supp_鍵）が無い／鍵の重なり
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
    "known_line_chars": 60,
    "known_table_rows": 5,
    "glead_chars": 40,
    "about_tags": 3,
    "more_lines": 3,
    "clips": 2,
    "option_chars": 30,
    "option_detail_chars": 40,
    "change_chars": 40,
    "questions_per_page": 12
  },
  // なぜ聞くか（決まった 4 文）。会社の表の docs-kit.qa-html.why で文だけ替えられる（例 once を「この月だけの事を確かめます」）
  "why": {
    "mismatch": "資料どうしで食い違っています",
    "missing": "資料に書いてありません",
    "law": "今の決まりが法律の決まりと合っていません",
    "once": "今回だけの事を確かめます"
  },
  // この答えで変わる事を書かなくてよい選択肢＝ひとことに書かせる逃げ道だけ（鍵と見出しの両方が合う時）
  "free_options": { "other": ["ほかの答え", "別の決め方"], "none": ["当てはまらない"] },
  // ひとことに書かせる選択肢の字（見出し・添え書き・変わる事のどれか）。当たる選択肢には data-supp="need"（JSON は "supp": "need"）が要る
  "supp_ask": /ひとこと|補足に書/,
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
const WHYS = Object.keys(RULES.why);
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

// 宛先: send＝素のフォームで配る口へ・copy＝答えを写して貼り戻す・artifact＝確認のページ（Artifact）が答えを受ける
export const DESTS = ["send", "copy", "artifact"];

function compileWords(company) {
  return [...RULES.internal_words, ...(company.internal_words ?? [])].map((w) =>
    typeof w === "string" ? { 語: w, re: new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "u") } : { ...w, re: new RegExp(w.正規表現 ?? w.語, "u") },
  );
}

// 型の動かない所（qa:css・qa:js・qa:foot）の中身。空白の違いは見ない。qa:foot は「この後のこと」（.next）の中身だけ差してよい。
const region = (raw, name) => {
  const m = new RegExp(`<!--${name}-->([\\s\\S]*?)<!--/${name}-->`).exec(raw);
  if (!m) return null;
  let t = m[1];
  if (name === "qa:foot") t = t.replace(/(<p\b[^>]*\bclass\s*=\s*["']next["'][^>]*>)[\s\S]*?(<\/p\s*>)/i, "$1…$2");
  return t.replace(/\s+/g, " ").trim();
};
const FIXED = ["qa:css", "qa:js", "qa:foot"];
let templateCache = null;
const templateRegions = () =>
  (templateCache ??= (() => {
    const t = readFileSync(TEMPLATE, "utf8");
    return Object.fromEntries(FIXED.map((n) => [n, region(t, n)]));
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

// 型の外（突き合わせた 3 か所の外）に書いてよい物の表。表に無い物は全部赤＝悪い物の名前を探すのでなく、許す物だけを通す。
export const ALLOW = {
  elements: ["html", "head", "meta", "title", "body", "div", "header", "section", "p", "h1", "h2", "h3", "b", "strong", "small", "span", "br",
    "ul", "ol", "li", "dl", "dt", "dd", "a", "img", "figure", "figcaption", "table", "thead", "tbody", "tr", "th", "td",
    "details", "summary", "form", "fieldset", "legend", "label", "input", "textarea", "select", "option"],
  attributes: ["class", "id", "lang", "name", "type", "value", "required", "checked", "selected", "disabled", "readonly", "for", "rows",
    "maxlength", "min", "max", "step", "placeholder", "autocomplete", "inputmode", "spellcheck", "href", "src", "alt", "width", "height",
    "colspan", "rowspan", "open", "hidden", "title", "charset", "content", "style"],
  attribute_prefixes: ["data-", "aria-"],
  input_types: ["radio", "checkbox", "text", "date", "month", "number", "hidden"],
  meta: { charset: true, names: ["viewport", "color-scheme"] },
  href: "^(?:https://|mailto:|tel:|#)[^\\s<>\"'&]*$",
  img_src: "^data:image/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+$",
};
function allowlistReds(outside) {
  const red = [];
  const els = new Set(ALLOW.elements);
  const ats = new Set(ALLOW.attributes);
  for (const m of outside.matchAll(/<([A-Za-z][A-Za-z0-9-]*)((?:"[^"]*"|'[^']*'|[^'">])*)>/g)) {
    const tag = m[1].toLowerCase();
    const show = m[0].slice(0, 50);
    if (!els.has(tag)) {
      red.push(`型の外に許していない要素 <${tag}>（見た目と動きは型の中だけ）: ${show}`);
      continue;
    }
    const before = red.length;
    const attrs = {};
    for (const a of m[2].matchAll(/([^\s"'=/>]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?/g)) {
      const name = a[1].toLowerCase();
      const val = a[2] == null ? "" : a[2].replace(/^["']|["']$/g, "");
      if (name in attrs) red.push(`同じ属性「${name}」が 2 回ある（ブラウザは前の値を使う）: ${show}`);
      else attrs[name] = val;
      if (!ats.has(name) && !ALLOW.attribute_prefixes.some((p) => name.startsWith(p))) red.push(`型の外に許していない属性「${name}」: ${show}`);
    }
    if ("style" in attrs && tag !== "body") red.push(`<${tag}> に style がある（色や形は変えない・会社の色は body の --brand だけ）`);
    if (tag === "meta" && red.length === before && !("charset" in attrs) && !ALLOW.meta.names.includes((attrs.name ?? "").toLowerCase())) red.push(`許していない meta: ${show}`);
    if (tag === "input" && !ALLOW.input_types.includes((attrs.type ?? "text").toLowerCase())) red.push(`許していない入力の欄 type="${attrs.type}": ${show}`);
    if ("href" in attrs && !new RegExp(ALLOW.href, "i").test(attrs.href)) red.push(`許していない URL（https・mailto・tel・# だけ）: ${show}`);
    if ("src" in attrs && (tag !== "img" || !new RegExp(ALLOW.img_src).test(attrs.src))) red.push(`外のリソース・許していない src（写真は img の data:image/ だけ）: ${show}`);
  }
  return red;
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
  for (const name of FIXED) {
    const got = region(raw, name);
    const marks = raw.split(`<!--${name}-->`).length - 1;
    if (marks > 1) shape.push(`型の ${name} の印が ${marks} 回ある（ちょうど 1 回）`);
    if (got == null) shape.push(`型の ${name} の印が無い（型を丸ごと写す）`);
    else if (got !== tpl[name])
      shape.push(`${name} の中身が型と違う（宛先で変えてよいのは 差出人・宛名・連絡先・会社の色${name === "qa:foot" ? "・この後のこと" : ""} だけ）`);
  }
  // 型の外（動かない 3 か所は上で型と突き合わせた＝ここでは見ない）
  //   外すのは突き合わせた最初の 1 つの間だけ（2 つ目の印の間は外さない＝照らしに入る）
  //   コメントを伏せずに生の文字で見る（ブラウザと検査でコメントの閉じ方が違っても、隠した物を見逃さない）
  const outside = FIXED.reduce((t, n) => t.replace(new RegExp(`<!--${n}-->[\\s\\S]*?<!--/${n}-->`), " "), raw);
  for (const [tag, n] of [["style", 1], ["script", 1]]) {
    const got = (raw.match(new RegExp(`<${tag}\\b`, "gi")) ?? []).length;
    if (got !== n) shape.push(`<${tag}> はページ全体でちょうど ${n} つ（型の中の 1 つ・今 ${got}）`);
  }
  if (/--!>|<!--->|<!-->/.test(raw)) shape.push("崩れたコメント（--!> ・<!--> ・<!--->）がある（ブラウザと読み方が食い違う）");
  if (/<link\b[^>]*rel\s*=\s*["']?stylesheet/i.test(outside)) shape.push("外の見た目（link stylesheet）を読んでいる");
  for (const r of allowlistReds(outside)) shape.push(r);
  if (/prefers-color-scheme\s*:\s*dark|color-scheme\s*:\s*[^;"'}]*dark|<meta\b(?=[^>]*\bname\s*=\s*["']color-scheme["'])[^>]*\bcontent\s*=\s*["'][^"']*dark/i.test(raw))
    shape.push("暗い色の設定がある（明るい色で固定）");
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
  // 前提 ①: 読んだ資料の一覧と答えるまでの扱い
  const docsEl = byClass(header, "docs")[0];
  const docs = docsEl ? [...docsEl.inner.matchAll(/<li\b[^>]*>([\s\S]*?)<\/li\s*>/gi)].map((m) => ({ key: attr(m[0], "data-doc"), name: text(m[1]) })) : null;
  const holdEl = byClass(header, "hold")[0];
  const hold = holdEl ? text(holdEl.inner) : "";
  const forms = html.match(/<form\b/gi) ?? [];
  if (forms.length !== 1) shape.push(`form は 1 つ（今 ${forms.length}）`);
  const formTag = /<form\b[^>]*>/i.exec(html)?.[0] ?? "";
  if (/\s(method|action)\s*=/i.test(formTag)) shape.push("form に method・action を書かない（配る口が書き込む）");
  const ver = /<input\b[^>]*\bname\s*=\s*["']__版__["'][^>]*>/i.exec(html);
  const version = ver ? attr(ver[0], "value") ?? "" : null;
  if (version == null) shape.push('版（<input type="hidden" name="__版__">）が無い');
  else if (!/^[0-9A-Za-z._-]+$/.test(version) && !/^\{\{/.test(version)) shape.push(`版は半角英数字と . _ - だけ（今 ${version}）`);
  if (!/<input\b[^>]*\bname\s*=\s*["']__受付番号__["']/i.test(html)) shape.push('受付番号の欄（<input type="hidden" name="__受付番号__">）が無い');
  // 送る前の確認・受付・送るボタンは qa:foot（型と突き合わせ済み）。差してよいのは「この後のこと」だけ
  // 「この後のこと」は qa:foot の間の .next をちょうど 1 つ・script を落とす前の写しで見る（中の script も、外の囮も見逃さない）
  const foot = /<!--qa:foot-->([\s\S]*?)<!--\/qa:foot-->/.exec(raw)?.[1] ?? "";
  const nexts = byClass(mask(foot), "next");
  const next = nexts.length === 1 ? nexts[0] : null;
  if (nexts.length > 1) shape.push(`受付の「この後のこと」（.next）は 1 つだけ（今 ${nexts.length}）`);
  else if (!next || !text(next.inner)) shape.push("受付の「この後のこと」（.next）が無い");
  else if (/<(?!br\s*\/?>)[a-z!/]/i.test(mask(next.inner))) shape.push("「この後のこと」（.next）に書けるのは字と <br> だけ");

  const visible = textLines(html.replace(/<(head)\b[\s\S]*?<\/head\s*>/i, (m) => (/<title>([\s\S]*?)<\/title>/i.exec(m)?.[1] ?? "")));
  const attrTexts = [...html.matchAll(/\b(?:data-(?:qlabel|glabel)|alt)\s*=\s*(?:"([^"]*)"|'([^']*)')/gi)].map((m) => decode(m[1] ?? m[2]));

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
      const smalls = [...o[1].matchAll(/<small\b[^>]*>([\s\S]*?)<\/small>/gi)];
      const chg = smalls.find((x) => /\bclass\s*=\s*["'][^"']*\bchg\b/i.test(x[0]));
      const small = smalls.find((x) => x !== chg);
      return {
        value: attr(inp, "value"),
        all: text(o[1]),
        head: text((b ? b[1] : o[1]).replace(/<span\b[^>]*class\s*=\s*["'][^"']*tag-rec[\s\S]*?<\/span>/gi, "")),
        detail: small ? text(small[1]) : "",
        change: chg ? text(chg[1]) : "",
        rec: /tag-rec/.test(o[1]),
        needSupp: /\bdata-supp\s*=\s*["']?need\b/i.test(inp),
      };
    });
    // 前提 ②③: まとまりの 1 行・何について・なぜ聞くか・見つけた事の資料・切り抜き・くわしく
    const gleads = byClass(q.inner, "glead").map((g) => textLines(g.inner));
    // 4 欄の箱は 1 問に 1 つずつ（2 つ目に書いて上限・決まった文をすり抜けさせない）
    const boxes = Object.fromEntries(["about", "why", "known", "more", "clips"].map((c) => [c, byClass(q.inner, c).length]));
    const aboutEl = byClass(q.inner, "about")[0];
    const aboutSpans = aboutEl ? [...aboutEl.inner.matchAll(/<span\b[^>]*>([\s\S]*?)<\/span\s*>/gi)] : [];
    const whyEl = byClass(q.inner, "why")[0];
    const moreEl = byClass(q.inner, "more")[0];
    const clips = byClass(q.inner, "clip").map((f) => {
      const img = /<img\b[^>]*>/i.exec(f.inner)?.[0] ?? null;
      const cap = /<figcaption\b[^>]*>([\s\S]*?)<\/figcaption\s*>/i.exec(f.inner);
      return { doc: attr(f.tag, "data-doc"), hasShows: attr(f.tag, "data-shows") != null, shows: (attr(f.tag, "data-shows") ?? "").split(/[\s、,]+/).filter(Boolean), img: !!img, src: img ? attr(img, "src") : null,
        alt: img ? attr(img, "alt") ?? "" : "", caption: cap ? text(cap[1]) : "" };
    });
    const freeInputs = [...q.inner.matchAll(/<input\b[^>]*\btype\s*=\s*["']?(text|date|month|number)\b[^>]*>|<select\b[^>]*>|<textarea\b[^>]*\bname\s*=\s*["'](?!supp_)[^>]*>/gi)].map((i) => i[0]);
    questions.push({
      key: m[1],
      kind: attr(q.tag, "data-kind"),
      group: attr(q.tag, "data-group"),
      question: legend ? text(legend[1]) : "",
      multiline: !!legend && /<br\b/i.test(legend[1]),
      known: known ? textLines(known.inner.replace(/<table\b[\s\S]*?<\/table\s*>/gi, "")) : [],
      knownDocs: known ? (attr(known.tag, "data-docs") ?? "").split(/\s+/).filter(Boolean) : [],
      gleads,
      boxes,
      about: aboutSpans.map((x) => text(x[1])),
      who: aboutSpans.filter((x) => /\bclass\s*=\s*["'][^"']*\bwho\b/i.test(x[0])).map((x) => text(x[1])).filter(Boolean),
      why: whyEl ? attr(whyEl.tag, "data-why") : null,
      whyText: whyEl ? text(whyEl.inner) : null,
      more: moreEl ? textLines(moreEl.inner.replace(/<summary\b[\s\S]*?<\/summary\s*>/i, "").replace(/<div\b[^>]*class\s*=\s*["'][^"']*\borig\b[\s\S]*$/i, "")) : null,
      clips,
      tableRows: knownTables.reduce((n, t) => n + (t[0].match(/<tr\b/gi) ?? []).length, 0),
      options: opts,
      choices: inputs.length || sel.length,
      oneChoice: (inputs.length > 0 && inputs.length < 2) || (!inputs.length && sel.length === 1),
      freeInput: freeInputs.length > 0,
      // radio と入力の欄は required で送れなくする。checkbox は required にすると「その 1 つを必ず選ぶ」になる＝型の JS が見る
      required: inputs.every((t) => /type\s*=\s*["']?checkbox/i.test(t)) && !freeInputs.length ? inputs.length > 0 : [...inputs, ...freeInputs].some((t) => hasAttr(t, "required")),
      checkboxRequired: inputs.some((t) => /type\s*=\s*["']?checkbox/i.test(t) && hasAttr(t, "required")),
      unknownLast: opts.length > 0 && opts[opts.length - 1].value === UNKNOWN,
      supp: new RegExp(`\\bname\\s*=\\s*["']supp_${m[1]}["']`).test(q.inner),
    });
  }
  // まとまりの 1 行は問いの箱の中だけ（問いの間に説明を挟まない）
  const gleadAll = byClass(html, "glead").length;
  const gleadIn = questions.reduce((n, q) => n + q.gleads.length, 0);
  if (gleadAll !== gleadIn) shape.push(`まとまりの 1 行（.glead）が問いの箱の外に ${gleadAll - gleadIn} つある（説明を問いの間に挟まない）`);
  return { format: "html", dest, holes, shape, brand, docs, hold, texts: [...visible, ...attrTexts], questions };
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
            : { value: o?.value ?? null, head: String(o?.label ?? ""), detail: String(o?.detail ?? ""), change: String(o?.change ?? "").trim(),
                all: [o?.label, o?.detail, o?.change].filter(Boolean).join(" "), rec: !!o?.recommended, needSupp: o?.supp === "need" },
        );
      const table = Array.isArray(q.table) ? q.table : [];
      return {
        key: String(q.key ?? ""),
        kind: q.kind ?? null,
        group: q.group ?? null,
        question: String(q.question ?? "").trim(),
        multiline: /\n/.test(String(q.question ?? "").trim()),
        known: lines(q.known),
        knownDocs: Array.isArray(q.docs) ? q.docs.map(String) : [],
        gleads: q.glead == null ? [] : [lines(q.glead)],
        about: Array.isArray(q.about) ? q.about.map((x) => String(x ?? "").trim()) : [],
        who: (Array.isArray(q.who) ? q.who : q.who == null ? [] : [q.who]).map((x) => String(x).trim()).filter(Boolean),
        why: q.why ?? null,
        whyText: null, // 型の側が決まった文を出す
        more: q.more == null || !String(q.more).trim() ? null : lines(q.more),
        boxes: {},
        clips: (Array.isArray(q.clips) ? q.clips : []).map((c) => ({ doc: c?.doc ?? null, hasShows: Array.isArray(c?.shows), shows: Array.isArray(c?.shows) ? c.shows.map(String) : [], img: true, src: c?.src ?? null,
          alt: String(c?.alt ?? ""), caption: String(c?.caption ?? "") })),
        tableRows: table.length,
        options,
        choices: options.length,
        oneChoice: options.length === 1,
        freeInput: ["text", "date", "month", "number"].includes(q.input),
        required: true, // 型の側が付ける
        unknownLast: true, // 型の側が足す
        supp: q.supp !== false,
      };
    });
  const docsIn = Array.isArray(data?.docs) ? data.docs : null;
  const docs = docsIn ? docsIn.map((d) => ({ key: d?.key ?? null, name: String(d?.name ?? "").trim() })) : null;
  const texts = [data?.to, data?.from, data?.contact, data?.title, data?.lead, data?.due, data?.next, data?.hold, ...(docsIn ?? []).flatMap((d) => [d?.name, d?.received]),
    ...qsIn.flatMap((q) => [q?.label, q?.glabel, q?.glead, ...(Array.isArray(q?.about) ? q.about : []), q?.question, ...lines(q?.known), q?.more,
    ...(Array.isArray(q?.clips) ? q.clips.flatMap((c) => [c?.alt, c?.caption]) : []),
    ...(Array.isArray(q?.table) ? q.table.flat().map(String) : []),
    ...(Array.isArray(q?.options) ? q.options.flatMap((o) => (typeof o === "string" ? [o] : [o?.label, o?.detail, o?.change])) : [])])]
    .flatMap((x) => lines(x));
  const holes = [...new Set(JSON.stringify(data ?? {}).match(/\{\{[^}]*\}\}/g) ?? [])];
  return { format: "json", dest: data?.dest ?? null, holes, shape, brand: data?.brand ?? null, docs, hold: String(data?.hold ?? "").trim(), texts, questions };
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

  // 前提 ①: はじめの画面の読んだ資料の一覧と答えるまでの扱い
  const whyText = { ...RULES.why, ...(company.why ?? {}) };
  const docKeys = (page.docs ?? []).map((d) => d.key);
  if (!page.docs || !page.docs.length) red.push(`読んだ資料の一覧が無い（${page.format === "html" ? "header の .docs に li[data-doc]" : '"docs"'}・この中から聞く）`);
  for (const d of page.docs ?? []) {
    if (d.key == null || !/^[A-Za-z0-9_]+$/.test(d.key)) red.push(`読んだ資料の鍵（data-doc）は半角英数字と _ だけ（今 ${d.key ?? "無し"}）: ${d.name.slice(0, 30)}`);
    if (!d.name) red.push(`読んだ資料 ${d.key ?? ""} の名が空`);
  }
  for (const k of new Set(docKeys.filter((k, i) => k != null && docKeys.indexOf(k) !== i))) red.push(`読んだ資料の鍵「${k}」が重なっている`);
  if (!page.hold) red.push(`答えるまでの扱いが無い（${page.format === "html" ? "header の .hold" : '"hold"'}・例「答えが届くまで、この点は確定せずにお待ちします。」）`);
  const whoOf = new Map(qs.map((q) => [q.key, q.who]));

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
    // 前提 ②: まとまりの見出し＋1 行は、まとまりの最初の問いに 1 つだけ
    const first = gi >= 0 && gi !== lastGroup;
    if (gi >= lastGroup) lastGroup = gi;
    if (first && q.gleads.length !== 1) red.push(`${id}: まとまりの最初の問いに、まとまりの 1 行（${page.format === "html" ? ".glead" : '"glead"'}）が ${q.gleads.length} つ（ちょうど 1 つ）`);
    if (!first && gi >= 0 && q.gleads.length) red.push(`${id}: まとまりの 1 行はまとまりの最初の問いだけ（別の画面や 2 つ目の説明を挟まない）`);
    for (const g of q.gleads) {
      if (!g.length) red.push(`${id}: まとまりの 1 行が空`);
      else if (g.length > 1) red.push(`${id}: まとまりの 1 行が ${g.length} 行（1 行だけ）`);
      else if (len(g[0]) > limits.glead_chars) red.push(`${id}: まとまりの 1 行が ${len(g[0])} 字（${limits.glead_chars} 字まで）`);
    }

    // 前提 ③: 1 問の固定の 4 欄（何について・見つけた事・なぜ聞くか・くわしく）。書けない問いは出さない
    for (const [c, n] of Object.entries(q.boxes)) if (n > 1) red.push(`${id}: .${c} が ${n} つある（1 問に 1 つ）`);
    if (!q.about.length || q.about.some((a) => !a)) red.push(`${id}: 何について（誰・いつ・何の札 ${page.format === "html" ? ".about の span" : '"about"'}）が無い・空（前提が書けない問いは出さない）`);
    else if (q.about.length > limits.about_tags) red.push(`${id}: 何についての札が ${q.about.length} つ（${limits.about_tags} つまで）`);
    if (q.group === "person" && !q.who.length) red.push(`${id}: 人ごとの事実の問いに問いの人（${page.format === "html" ? "span.who" : '"who"'}）が無い`);
    for (const w of q.who) if (!q.about.includes(w)) red.push(`${id}: 問いの人「${w}」が何についての札に無い`);
    if (!WHYS.includes(q.why)) red.push(`${id}: なぜ聞くか（${page.format === "html" ? ".why の data-why" : '"why"'}）が ${WHYS.join("・")} のどれでもない（今 ${q.why ?? "無し"}）`);
    else if (q.whyText != null && q.whyText !== whyText[q.why]) red.push(`${id}: なぜ聞くかの文は決まった文「${whyText[q.why]}」のまま（今 ${q.whyText}）`);
    if (q.kind === "mismatch" && WHYS.includes(q.why) && q.why !== "mismatch") red.push(`${id}: 食い違いの問い（mismatch）のなぜ聞くかは「${whyText.mismatch}」`);
    if (!q.known.length) red.push(`${id}: 見つけた事（資料名・場所・値）が無い（前提が書けない問いは出さない）`);
    if (!q.knownDocs.length) red.push(`${id}: 見つけた事が読んだ資料を指していない（${page.format === "html" ? '.known に data-docs="資料の鍵"' : '"docs"'}）`);
    for (const d of q.knownDocs) if (!docKeys.includes(d)) red.push(`${id}: 見つけた事の資料「${d}」が読んだ資料の一覧に無い`);
    if (q.more == null || !q.more.length) red.push(`${id}: くわしく（${page.format === "html" ? "details.more" : '"more"'}）が無い・空`);
    else if (q.more.length > limits.more_lines) red.push(`${id}: くわしくが ${q.more.length} 行（${limits.more_lines} 行まで・資料の原文は ${page.format === "html" ? ".orig" : "切り抜き"} へ）`);
    // 切り抜き: 1 問 2 枚まで・一覧の資料・写っている名は問いの人だけ（ほかの人は塗る）
    if (q.clips.length > limits.clips) red.push(`${id}: 切り抜きが ${q.clips.length} 枚（${limits.clips} 枚まで）`);
    if (q.why === "mismatch" && q.clips.length === 1) red.push(`${id}: 食い違いの切り抜きは 2 枚を横に並べる（今 1 枚・出さないなら 0 枚）`);
    const others = [...new Set(qs.filter((o) => o !== q).flatMap((o) => whoOf.get(o.key) ?? []))].filter((n) => !q.who.includes(n));
    q.clips.forEach((c, i) => {
      const cid = `${id}: 切り抜き ${i + 1}`;
      if (!c.img || !c.src || !new RegExp(ALLOW.img_src).test(c.src)) red.push(`${cid} の画像が無い・ページに埋め込んでいない（data:image/… だけ）`);
      if (!c.alt) red.push(`${cid} に写っている事（alt）が無い`);
      if (!c.hasShows) red.push(`${cid} に写っている人の名（${page.format === "html" ? 'data-shows・誰も写らなければ data-shows=""' : '"shows"・誰も写らなければ []'}）が無い`);
      if (!c.doc || !docKeys.includes(c.doc)) red.push(`${cid} の資料「${c.doc ?? "無し"}」が読んだ資料の一覧に無い`);
      for (const n of c.shows) if (!q.who.includes(n)) red.push(`${cid} に問いの人の外の名「${n}」が写っている（ほかの人の行は塗る）`);
      for (const n of others) if ([c.alt, c.caption].some((t) => t.includes(n))) red.push(`${cid} の説明に問いの人の外の名「${n}」がある（ほかの人の行は塗る）`);
    });

    const qtext = q.question;
    if (!qtext) red.push(`${id}: 問いの 1 行（legend）が無い`);
    if (q.multiline) red.push(`${id}: 問いが 2 行以上（1 行にする）`);
    if (len(qtext) > limits.question_chars) red.push(`${id}: 問いが ${len(qtext)} 字（${limits.question_chars} 字まで）: ${qtext}`);
    const ends = qtext.match(new RegExp(RULES.question_end, "gu")) ?? [];
    if (ends.length > 1 || rx("two_in_one").test(qtext)) red.push(`${id}: 1 問に 2 つ以上を聞いている（1 問 1 つに分ける）: ${qtext}`);
    if (/^\s*(?:[A-Za-z]?-?\d+[.．]|問\s*\d+)/.test(qtext)) red.push(`${id}: 問いの頭に番号を付けない（進み具合は型が出す）: ${qtext}`);

    if (q.known.length > limits.known_lines) red.push(`${id}: 見つけた事が ${q.known.length} 行（${limits.known_lines} 行まで・数字は表に・残りは「くわしく」へ）`);
    for (const l of q.known) if (len(l) > limits.known_line_chars) red.push(`${id}: 見つけた事の 1 行が ${len(l)} 字（1 行 ${limits.known_line_chars} 字まで）: ${l.slice(0, 30)}…`);
    if (q.tableRows > limits.known_table_rows) red.push(`${id}: 数字の表が ${q.tableRows} 行（見出しを入れて ${limits.known_table_rows} 行まで）`);
    const asked = [qtext, ...q.known].join(" ");
    const num = rx("number_ask").exec(asked);
    if (num) red.push(`${id}: 数を書かせる問い「${num[0]}」（こちらで計算した候補を並べて「どちらが正しいですか」にする）`);
    const conf = rx("confirm").exec(asked);
    if (conf && q.kind !== "mismatch") red.push(`${id}: 「${conf[0]}」は資料どうしが食い違う時だけ（data-kind="mismatch"）`);
    const sym = rx("symbol_ref").exec(asked);
    if (sym) red.push(`${id}: 記号「${sym[0]}」で選択肢を指している（中身の言葉で書く）`);

    if (q.oneChoice) red.push(`${id}: 選択肢が 1 つだけ（「分からない」の外に 2 つ以上）`);
    if (!q.choices && !q.freeInput) red.push(`${id}: 答える欄が無い`);
    if (!q.required) red.push(`${id}: 答えずに送れる（最初の選択肢か入力の欄に required を付ける）`);
    if (q.checkboxRequired) red.push(`${id}: checkbox に required を付けない（その 1 つを選ばないと送れなくなる）`);
    const real = q.options.filter((o) => o.value !== UNKNOWN);
    if (real.filter((o) => o.rec).length > 1) red.push(`${id}: おすすめは 1 つまで`);
    const vals = [];
    for (const o of real) {
      if (len(o.head) > limits.option_chars) red.push(`${id}: 選択肢の見出しが ${len(o.head)} 字（${limits.option_chars} 字まで・中身は結果の 1 行へ）: ${o.head.slice(0, 30)}…`);
      if (len(o.detail) > limits.option_detail_chars) red.push(`${id}: 選択肢の添え書きが ${len(o.detail)} 字（${limits.option_detail_chars} 字まで）: ${o.detail.slice(0, 30)}…`);
      if (!(RULES.free_options[o.value] ?? []).includes(o.head) && o.head !== RULES.unknown.label) {
        if (!o.change) red.push(`${id}: 選択肢「${o.head.slice(0, 20)}」にこの答えで変わる事（誰の・何が・いくら ${page.format === "html" ? "small.chg" : '"change"'}）が無い`);
        else if (len(o.change) > limits.change_chars) red.push(`${id}: この答えで変わる事が ${len(o.change)} 字（${limits.change_chars} 字まで）: ${o.change.slice(0, 30)}…`);
      }
      if (RULES.supp_ask.test(`${o.head} ${o.detail} ${o.change}`) && !o.needSupp)
        red.push(`${id}: ひとことに書かせる選択肢「${o.head.slice(0, 20)}」に ${page.format === "html" ? 'data-supp="need"' : '"supp": "need"'} が無い（欄が「なくても大丈夫です」のままで、書かずに送れる）`);
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
