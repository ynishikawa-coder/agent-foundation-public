#!/usr/bin/env node
// qa-html の確認ページの検査（外部依存ゼロ・node だけで動く）。決まりの表はこのファイルの頭の RULES の 1 か所。
//   repo ごとに足す語・上限は repo の根の config/skill-values.json の docs-kit.qa-html.internal_words・limits。
// 赤にする物（形の約束は SKILL.md §型の約束）:
//   型: 宛先の印（data-dest＝send・copy・artifact）が無い／qa:css・qa:js・qa:foot が型（references/template.html）と違う
//     （qa:foot は「この後のこと」だけ差してよい）／型の外に許す物の表（ALLOW）に無い要素・属性・URL を書いた
//     （script・style・iframe・on… の属性・javascript:・外のリソースなど）／暗い色の設定／会社の色（--brand）が body の style の外・白地で読めない濃さ／
//     宛名が無い／差出人・連絡先の欄が残っている（外した欄）／版（__版__）が無い／送る前の確認と受付の部品が無い
//   前提（3 段）: 読んだ資料の一覧（.docs の li[data-doc]）・答えるまでの扱い（.hold）が無い／資料にリンク（data-url）も
//     リンクが無い訳（data-no-url）も無い／まとまりの 1 行（.glead）が
//     各まとまりの最初の問いに 1 つでない／1 問の 4 欄（何について .about・見つけた事 .known と data-docs・なぜ聞くか .why・
//     くわしく details.more）のどれかが空・上限超え・見つけた事が一覧に無い資料を指す／なぜ聞くかが決まった 5 文でない／
//     切り抜き（figure.clip）が 3 枚以上・一覧に無い資料・問いの人の外の名が写る／選択肢にこの答えで変わる事（small.chg）が無い
//   根拠と読み: 根拠（.evidence の li[data-doc][data-where]）が無い・場所が空・一覧に無い資料／実物（切り抜きか原文の引用 .quote）が
//     1 つも無い／AI の読み（.reading）が無い・4 行以上／推奨の印（small.rec・recommended）がオーナー宛て（copy・artifact）の
//     作り方の分かれ道の問い（judge）の外・1 つ目の選択肢の外・1 問に 2 つ・「分からない」に在る・理由が無い／AI の今の見込み（.estimate）の
//     根拠（data-basis）が空・選択肢より前／見込みの言葉を見込みの枠の外で使う／「前の問い」など、ほかの問いに頼る言い方
//   問い: 問いの形（data-kind）が 5 つ以外／並び（data-group）が 会社の決まり→人ごとの事実→今回だけの事→先に決めておきたい事 でない／
//     先に決めておきたい事（later）の 1 行が決まった文でない／
//     内部の言葉／番号で過去の問いを指す／数を書かせる問い（資料の外の事実で数を打つ欄の時を除く）／長さ・問いの数の上限超え／選択肢が 1 つだけ／
//     選択肢に A・B などの記号／選択肢の鍵（value）の形・重なり／「分からない」（__unknown__）が無い・最後でない／
//     答えずに送れる（required が無い）／1 問に 2 つ以上／「合っていますか」を食い違いの外で使う／
//     資料の外の事実に「当てはまらない」が無い／資料がそろっているかの問いに足りない資料を書かせる選択肢が無い／ひとこと（supp_鍵）が無い／鍵の重なり
//   前の答え: 引いた結果（--prior・ページの隣の <名>.prior.json）の answered に在る鍵が問いに残っている／引いた結果が読めない・
//     形が違う・命令が落ちた・別の版のページで引いた／--prior に渡した file が無い／値の表に prior_check_cmd が在る時だけ、
//     引いた結果が無い・引いた結果の無い問いがある（値の表に無く引いた結果も無ければ見ない＝今までどおり）
// 読める物は 2 つで、問いの決まりは同じ 1 か所（checkPage）が見る:
//   ① 1 枚の HTML（型を写した物・<body data-dest="send|copy|artifact">・確認のページ（Artifact）も同じ HTML）
//   ② 問いのデータ（JSON・Artifact 型に中身をデータで渡す時。形は SKILL.md §問いのデータ）
// 使い方: node check.mjs <file.html|file.json> [--json] [--values <skill-values.json>] [--prior <引いた結果.json>] [--run-prior] [--prior-input]
//   前の答えを照らす（作り方 0）: 値の表の docs-kit.qa-html.prior_check_cmd を --run-prior で走らせ、引いた結果をページの隣の
//   <名>.prior.json（--prior で替える）に書いてから検査する。--prior-input は命令へ渡す JSON を出すだけ。
//   別の検査（配る口の検査など）からは import { checkQa, checkQaJson, checkFile } で呼ぶ。
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// ── 問いの決まりの表（1 か所）。会社ごとに足す語は config/skill-values.json の docs-kit.qa-html.internal_words
//    （文字列か {語, 正規表現, 言い換え}）、上限は docs-kit.qa-html.limits で上書きする。
// 外した欄（差出人・連絡先の欄は要らない）。HTML の class と JSON の鍵が同じ名。
const DROPPED = [["from", "差出人"], ["contact", "連絡先"]];
const ROOT_CAUSE = "  直し: 赤の行を 1 つずつ潰さず、細目 §3「まず構造を疑う」で原因（問いの元の表・前提の写し方）から直す";

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
    "questions_per_page": 12,
    "evidence": 3,
    "where_chars": 60,
    "quote_chars": 80,
    "reading_lines": 3,
    "reading_line_chars": 80,
    "estimate_chars": 40,
    "basis_chars": 60,
    "rec_chars": 40
  },
  // なぜ聞くか（決まった 5 文）。会社の表の docs-kit.qa-html.why で文だけ替えられる（例 once を「この月だけの事を確かめます」）
  "why": {
    "mismatch": "資料どうしで食い違っています",
    "missing": "資料に書いてありません",
    "law": "今の決まりが法律の決まりと合っていません",
    "once": "今回だけの事を確かめます",
    "ambiguous": "資料の書き方が 2 通りに読めます"
  },
  // この答えで変わる事を書かなくてよい選択肢＝ひとことに書かせる逃げ道だけ（鍵と見出しの両方が合う時）
  "free_options": { "other": ["ほかの答え", "別の決め方"], "none": ["当てはまらない"] },
  // ひとことに書かせる選択肢＝鍵が free_options.other（ほかの答え・別の決め方）か、字（見出し・添え書き・変わる事）がこれに当たる物。data-supp="need"（JSON は "supp": "need"）が要る
  "supp_ask": /ひとこと|補足に書|補足欄|下の欄/,
  "kinds": {
    "choose": "どちらが正しいですか＝こちらが計算した候補を並べる（候補 2 つ以上）",
    "mismatch": "資料どうしが食い違う＝「合っていますか」を使ってよいのはここだけ（候補 2 つ以上）",
    "fact": "資料の外にしか無い事実（「当てはまらない」を必ず置く）",
    "judge": "読んでも決まりが分からない時の判断（候補 2 つ以上）",
    "complete": "読んだ資料で全部か（「これで全部」と、足りない資料の名をひとことに書かせる選択肢〔supp: need〕を置く）"
  },
  "groups": {
    "rule": "会社の決まり（全員に効く）",
    "person": "人ごとの事実",
    "once": "今回だけの事",
    "later": "先に決めておきたい事（いつも最後）"
  },
  // 先に決めておきたい事（later）の最初の問いのまとまりの 1 行（決まった文・会社の表の docs-kit.qa-html.later_lead で替えられる）
  "later_lead": "今月の計算には関係しません。起きた時の決め方を先に伺います。",
  // 推奨の印（選択肢の画面の印と同じ決め方＝細目 §4）: オーナー宛て（dests）の作り方の分かれ道の問い（kinds）だけ・
  //   1 問に 1 つ・1 つ目の選択肢だけ・「分からない」に付けない・理由はその選択肢に 1 行（HTML は <small class="rec">理由</small>＝
  //   「推奨」の字は型の CSS が出す・JSON は "recommended": "理由"）。お客さん宛て（send）と事実を聞く問いは印なし＝見込みは .estimate の枠だけ
  "rec": { "dests": ["copy", "artifact"], "kinds": ["judge"] },
  // 印の字は型が出す＝ページの文に書いたこの言葉は赤（印は small.rec・"recommended" で付ける）
  "recommend": "おすすめ|お勧め|お薦め|オススメ|推奨",
  "estimate_word": "見込み|予測",
  // 1 画面 1 問＝ほかの問いの答えに頼らない（「前の問いの答えで決まります」の類は赤）
  "prior_ref": "(?:前|上|ひとつ前|1\\s*つ前|さっき)の(?:問(?!い合)|質問|設問|答え|回答)|前問",
  "unknown": { "value": "__unknown__", "label": "分からない・確かめてから答える" },
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
      "言い換え": "（書かない・見込みは AI の今の見込みの枠へ）"
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

// 型の外で使える class＝型が型の外（qa:css・qa:js・qa:foot と注の外）で使っている class と、推奨の印の rec だけ（正本は型 1 つ）。
//   型の CSS・JS が知っているのに型の外で使わない class（step・err・bar・pg・big など＝見せ方を切り替える物）を付けて選択肢を隠させない
//   （CSS・JS の知らない class は見せ方を変えないので通す）
let outsideClassCache = null;
const templateOutsideClasses = () =>
  (outsideClassCache ??= (() => {
    let t = readFileSync(TEMPLATE, "utf8");
    t = t.slice(t.indexOf("-->") + 3);
    for (const n of FIXED) t = t.replace(new RegExp(`<!--${n}-->[\\s\\S]*?<!--/${n}-->`), " ");
    t = t.replace(/<!--[\s\S]*?-->/g, " ");
    const set = new Set(["rec", "next"]);   // next＝qa:foot の「この後のこと」（差してよい所・別の赤が中身を見る）
    for (const m of t.matchAll(/\bclass="([^"]*)"/g)) for (const c of m[1].split(/[ \t\n\f\r]+/)) if (c) set.add(c);
    // 型の CSS・JS が知っている語（見せ方を切り替えうる class の候補）
    const full = readFileSync(TEMPLATE, "utf8");
    const known = new Set();
    for (const n of FIXED) {
      const r = new RegExp(`<!--${n}-->([\\s\\S]*?)<!--/${n}-->`).exec(full)?.[1] ?? "";
      for (const w of r.matchAll(/[A-Za-z_][A-Za-z0-9_-]*/g)) known.add(w[0]);
    }
    return { allowed: set, known };
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
// HTML の空白（ブラウザが区切りに使う字だけ・NBSP などは含まない）
const WS = "[ \\t\\n\\f\\r]";
// 型の外の字の並びを、検査が読み切れる書き方だけにする（読みの道筋を 1 つ: 検査はページを正規表現で読むので、
//   ブラウザと読みが分かれる書き方を入口で止める）。通すのは: 先頭の <!doctype html>・ふつうのコメント <!-- … -->・
//   決まった形の開きタグ（属性は空白で区切り値は引用符で囲む）・閉じタグ </名>（中に空白を入れない＝読む側は </名> だけを受ける）。textarea・title の中に < を書かない。
// class に rec を持つか（区切りは HTML の空白だけ＝ブラウザと同じ・印の読みはこの 1 つ）
const hasRec = (tag) => /(?:^|[ \t\n\f\r])rec(?:[ \t\n\f\r]|$)/.test(attr(tag, "class") ?? "");
// ブラウザが要素の木を組み直す書き方（閉じ忘れ・入れ子の崩れ・表や select の中の移し替え・<p> の自動の閉じ・<a> の中の <a>）は赤
//   ＝タグの並びがそのまま木になる形だけを通し、検査の読み（正規表現で切る）とブラウザの木を同じにする
const VOID = new Set(["br", "img", "input", "meta"]);
// 開くと、表の区切り（table・td・th）の内で開いている <p> をブラウザが閉じる要素（HTML の決まりの「button scope の p を閉じる」物）
const BLOCK = new Set(["div", "section", "header", "p", "h1", "h2", "h3", "ul", "ol", "dl", "table", "figure", "figcaption", "details", "summary", "form", "fieldset", "li", "dd", "dt"]);
// 開くと、同じ種類（か対の相手）の開いている物をブラウザが閉じる要素
const SELF_CLOSE = { li: ["li"], dt: ["dt", "dd"], dd: ["dt", "dd"], td: ["td", "th"], th: ["td", "th"], tr: ["tr"], thead: ["thead", "tbody"], tbody: ["thead", "tbody"], option: ["option"], form: ["form"], p: ["p"] };
const HEAD = new Set(["h1", "h2", "h3"]);
const SCOPE = new Set(["table", "td", "th"]);
const ONLY = { table: ["thead", "tbody", "tr"], thead: ["tr"], tbody: ["tr"], tr: ["th", "td"], select: ["option"], ul: ["li"], ol: ["li"], dl: ["dt", "dd"] };
function treeReds(rest) {
  const red = [];
  const stack = [];
  const tags = [];   // stack と同じ並びで開きタグの字（選択肢の枠の読みに使う）
  let optControls = 0;
  const isOpt = (t) => /^<label\b/i.test(t) && /(?:^|[ \t\n\f\r])opt(?:[ \t\n\f\r]|$)/.test(attr(t, "class") ?? "");
  // 型の外の区画（qa:css・qa:js・qa:foot）は空白で伏せてあり、その前後で木が切れる＝head と body の外枠は数えない
  for (const m of rest.matchAll(/<(\/?)([A-Za-z][A-Za-z0-9-]*)[^>]*>|([^<]+)/g)) {
    if (m[3] != null) {
      const top = stack[stack.length - 1];
      if (top && ONLY[top] && m[3].trim()) { red.push(`<${top}> の中に字をじかに書かない（ブラウザが表や一覧の外へ移す）: ${m[3].trim().slice(0, 20)}`); break; }
      continue;
    }
    const tag = m[2].toLowerCase();
    if (["html", "head", "body"].includes(tag) || !ALLOW.elements.includes(tag)) continue;   // 許さない要素は別の赤
    if (!m[1]) {
      const top = stack[stack.length - 1];
      if (top && ONLY[top] && !ONLY[top].includes(tag)) { red.push(`<${top}> の中にじかに <${tag}> を置かない（ブラウザが外へ移す）`); break; }
      // 選択肢の枠（label.opt）＝押すとその中の radio・checkbox 1 つが選ばれ、見えて、選べる物。ブラウザと同じ読みになる形だけ通す
      if (["input", "select", "textarea"].includes(tag)) {
        const lab = tags.findLast((t) => /^<label\b/i.test(t));
        if (lab && hasAttr(lab, "for")) { red.push(`for の付いた <label> の中に答えの欄を置かない（押した先が for の欄になる）: ${m[0].slice(0, 50)}`); break; }
        if (lab && isOpt(lab) && (tag !== "input" || !/^(?:radio|checkbox)$/i.test(attr(m[0], "type") ?? "") || ++optControls > 1)) {
          red.push(`選択肢の枠（label.opt）の中の欄は radio か checkbox 1 つだけ（ほかの欄があると押した先が替わる）: ${m[0].slice(0, 50)}`); break;
        }
        if (lab && isOpt(lab)) {
          // 選択の name は包む問いの箱の鍵と同じ（別の問いの答えを書き換えさせない・印の選択肢を答えに選べなくさせない）
          const box = tags.findLast((t) => /^<fieldset\b/i.test(t)) ?? "";
          if (attr(m[0], "name") !== attr(box, "data-qkey")) { red.push(`選択肢の欄の name は包む問いの箱の鍵（data-qkey="${attr(box, "data-qkey") ?? ""}"）と同じにする: ${m[0].slice(0, 50)}`); break; }
        }
      }
      // 問いの箱＝型の JS が画面と答えとして集める物（form の中の fieldset.q[data-qkey]）と同じ物だけを、検査も問いと読む
      if (hasAttr(m[0], "data-qkey") && !(tag === "fieldset" && /(?:^|[ \t\n\f\r])q(?:[ \t\n\f\r]|$)/.test(attr(m[0], "class") ?? "") && stack.includes("form")))
        { red.push(`data-qkey は form の中の fieldset.q にだけ付ける（型の JS が問いとして集めず、検査の読みとずれる）: ${m[0].slice(0, 50)}`); break; }
      // 型の JS は fieldset.q[data-qkey] を入れ子も問わず別の画面として集める＝fieldset は入れ子にしない
      if (tag === "fieldset" && stack.includes("fieldset")) { red.push("<fieldset> の中に <fieldset> を置かない（型の JS が別の画面として集め、中の選択肢が隠れる）"); break; }
      // 選択肢の枠の中身も型と同じ形だけ: label.opt ＞ input（radio・checkbox）と span ／ span ＞ b・small・br ／ b・small ＞ 字と br
      {
        const p1 = tags[tags.length - 1] ?? "", p2 = tags[tags.length - 2] ?? "", p3 = tags[tags.length - 3] ?? "";
        const inOpt = isOpt(p1) ? ["input", "span"] : /^<span\b/i.test(p1) && isOpt(p2) ? ["b", "small", "br"] : /^<(?:b|small)\b/i.test(p1) && /^<span\b/i.test(p2) && isOpt(p3) ? ["br"] : null;
        if (inOpt && !inOpt.includes(tag)) { red.push(`選択肢の枠の中身は型と同じ形だけ（label.opt ＞ input と span ／ span ＞ b・small ／ b・small ＞ 字）: <${tag}>`); break; }
      }
      if (VOID.has(tag)) continue;
      // 型の JS が中身を書き換える目印（.supp）は、問いの箱のじかの子の div だけ（中に選択肢を入れて消させない）
      if (/(?:^|[ \t\n\f\r])supp(?:[ \t\n\f\r]|$)/.test(attr(m[0], "class") ?? "") && !(tag === "div" && attr(m[0], "class") === "supp" && /^<fieldset\b/i.test(tags[tags.length - 1] ?? "")))
        { red.push(`class の supp は問いの箱（fieldset.q）のじかの子の <div class="supp"> だけ（型の JS が中の見出しを書き換える）: ${m[0].slice(0, 50)}`); break; }
      if (isOpt(m[0])) {
        optControls = 0;
        // 選択肢の枠の置き場は型と同じ形だけ: fieldset.q（class は q だけ）＞ div.opts（class は opts だけ）＞ label.opt（class は opt だけ）
        const [gp, p1] = [tags[tags.length - 2] ?? "", tags[tags.length - 1] ?? ""];
        //   （包む要素で隠す・押した先を替える・別の画面にする形〔details・a・summary・figure・hidden の箱・.supp・鍵の無い箱〕はこれで全部閉じる）
        if (attr(m[0], "class") !== "opt" || !/^<div\b/i.test(p1) || attr(p1, "class") !== "opts" || !/^<fieldset\b/i.test(gp) || attr(gp, "class") !== "q"
            || !/^[A-Za-z0-9_]+$/.test(attr(gp, "data-qkey") ?? ""))
          { red.push(`選択肢の枠は型と同じ置き場だけ（<fieldset class="q"> のじかの子の <div class="opts"> のじかの子の <label class="opt">・箱は鍵 data-qkey を持つ・class は足さない）: ${m[0].slice(0, 50)}`); break; }
        if (hasAttr(m[0], "for")) { red.push(`選択肢の枠（label.opt）に for を付けない（押した先が for の欄になる）: ${m[0].slice(0, 50)}`); break; }
      }
      // 表の区切りより内側（一番近い table・td・th より上）に開いている物だけが、ブラウザの閉じの的になる
      let from = 0;
      for (let i = stack.length - 1; i >= 0; i--) if (SCOPE.has(stack[i])) { from = i + 1; break; }
      const inScope = stack.slice(from);
      if (BLOCK.has(tag) && inScope.includes("p")) { red.push(`<p> の中に <${tag}> を置かない（ブラウザが <p> をそこで閉じる）`); break; }
      const same = (SELF_CLOSE[tag] ?? []).find((t) => (["td", "th", "tr", "thead", "tbody"].includes(tag) ? stack.slice(stack.lastIndexOf("table") + 1) : inScope).includes(t));
      if (same && tag !== "p") { red.push(`<${same}> の中に <${tag}> を開かない（ブラウザが前の <${same}> をそこで閉じる）`); break; }
      if (HEAD.has(tag) && HEAD.has(top)) { red.push(`<${top}> の中に <${tag}> を置かない（ブラウザが見出しを閉じる）`); break; }
      if (tag === "a" && stack.includes("a")) { red.push("<a> の中に <a> を置かない（ブラウザが組み直す）"); break; }
      if (["textarea", "title", "option"].includes(top)) { red.push(`<${top}> の中にタグを書かない`); break; }
      stack.push(tag);
      tags.push(m[0]);
    } else {
      if (stack[stack.length - 1] !== tag) { red.push(`閉じタグ </${tag}> が開いた順と合わない（開いているのは ${stack[stack.length - 1] ? `<${stack[stack.length - 1]}>` : "無し"}・ブラウザが木を組み直す）`); break; }
      stack.pop();
      tags.pop();
    }
  }
  return red;
}

function tokenReds(outside) {
  const red = [];
  if (!/^\uFEFF?[ \t\n\f\r]*<!doctype html>/i.test(outside)) red.push("先頭に <!doctype html> が要る（無いとブラウザが古い読み方になり、class の大小を区別しない）");
  for (const m of outside.matchAll(/<(textarea|title)\b[^>]*>([\s\S]*?)<\/\1/gi))
    if (m[2].includes("<")) red.push(`<${m[1].toLowerCase()}> の中に < を書かない（ブラウザは字として読む）: ${m[2].slice(0, 40)}`);
  const open = new RegExp(`^<[A-Za-z][A-Za-z0-9-]*(?:${WS}+[^ \\t\\n\\f\\r"'=<>/]+(?:${WS}*=${WS}*(?:"[^"]*"|'[^']*'))?)*${WS}*/?>`);
  const rest = outside.replace(/^\uFEFF?[ \t\n\f\r]*<!doctype html>/i, "").replace(/<!--(?!>|->)[\s\S]*?-->/g, (c) => " ".repeat(c.length));
  for (const m of rest.matchAll(/</g)) {
    const at = rest.slice(m.index);
    // 開きタグ（崩れた区切りは下の allowlistReds の strict が見る）・閉じタグ・崩れたコメント（別の赤が見る）は通す
    if (open.test(at) || /^<[A-Za-z][A-Za-z0-9-]*(?:"[^"]*"|'[^']*'|[^'">])*>/.test(at) || /^<\/[A-Za-z][A-Za-z0-9-]*>/.test(at) || /^<!--(?:>|->)/.test(at)) continue;
    red.push(`検査が読めない < の書き方（<? <! </ の崩れ・閉じないコメント・崩れたタグ）: ${at.slice(0, 40)}`);
  }
  red.push(...treeReds(rest));
  // 検査が中身を切る要素（選択肢の label・印や変わる事の small）は入れ子にしない＝検査は最初の閉じタグで切るので、
  //   入れ子にすると検査とブラウザで「どの選択肢・どの欄の中か」が分かれる
  for (const t of ["label", "small"]) {
    let depth = 0;
    for (const m of rest.matchAll(new RegExp(`<(/?)${t}(?=[ \\t\\n\\f\\r/>])`, "gi"))) {
      depth += m[1] ? -1 : 1;
      if (depth > 1) { red.push(`<${t}> の中に <${t}> を入れない（検査とブラウザで中身の切り方が分かれる）`); break; }
      if (depth < 0) depth = 0;
    }
  }
  return red;
}

function allowlistReds(outside) {
  const red = tokenReds(outside);
  const els = new Set(ALLOW.elements);
  const ats = new Set(ALLOW.attributes);
  const ids = new Map();
  const fors = [];
  for (const m of outside.matchAll(/<([A-Za-z][A-Za-z0-9-]*)((?:"[^"]*"|'[^']*'|[^'">])*)>/g)) {
    const tag = m[1].toLowerCase();
    const show = m[0].slice(0, 50);
    if (!els.has(tag)) {
      red.push(`型の外に許していない要素 <${tag}>（見た目と動きは型の中だけ）: ${show}`);
      continue;
    }
    const before = red.length;
    const strict = new RegExp(`^<[A-Za-z][A-Za-z0-9-]*(?:${WS}+[^ \\t\\n\\f\\r"'=<>/]+(?:${WS}*=${WS}*(?:"[^"]*"|'[^']*'))?)*${WS}*/?>$`).test(m[0]);
    // 検査の読み（attr・class）とブラウザの読みを 1 つにそろえる形だけを通す: 属性は空白で区切り、値は引用符で囲む
    //   （<small/class="rec">・class=rec のような書き方は、ブラウザは読むが検査は読めない＝すり抜けるので赤）
    const attrs = {};
    for (const a of m[2].matchAll(/([^\s"'=/>]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?/g)) {
      const name = a[1].toLowerCase();
      const val = a[2] == null ? "" : a[2].replace(/^["']|["']$/g, "");
      // 値の中に別の属性に見える字（title=" class='x'" の類）や、検査が戻せない文字参照（&#114; &Tab; の類）は赤
      //   ＝検査の読み（attr・class）がブラウザと同じ値を読むように、読みが分かれる書き方を入口で止める
      if (a[2] != null && /^["']/.test(a[2])) {
        if (/\s[A-Za-z_:][-A-Za-z0-9_:.]*\s*=/.test(val)) red.push(`属性「${name}」の値の中に「名=」の形を書かない（検査とブラウザで読む属性が分かれる）: ${show}`);
        if (/[<>]/.test(val)) red.push(`属性「${name}」の値に < > を書かない（検査がタグとして読み、ブラウザと中身の切り方が分かれる）: ${show}`);
        if (name === "class" && !/^[A-Za-z0-9_ -]*$/.test(val)) red.push(`class の値は半角英数字・_・- と空白だけ（区切りの読みを検査とブラウザでそろえる）: ${show}`);
        if (/&(?!(?:nbsp|lt|gt|quot|amp|#39);)(?:#|[A-Za-z][A-Za-z0-9]*;)/.test(val)) red.push(`属性「${name}」の値に文字参照（&#…; など）を書かない（字のまま書く）: ${show}`);
      }
      if (name in attrs) red.push(`同じ属性「${name}」が 2 回ある（ブラウザは前の値を使う）: ${show}`);
      else attrs[name] = val;
      if (!ats.has(name) && !ALLOW.attribute_prefixes.some((p) => name.startsWith(p))) red.push(`型の外に許していない属性「${name}」: ${show}`);
    }
    // label の for は、ひとことの欄（textarea#supp_鍵）を指す形だけ＝選択肢と答えの欄の結び付きを「label.opt の中の欄」1 つにする
    if ("for" in attrs) {
      if (tag !== "label" || !/^supp_[A-Za-z0-9_]+$/.test(attrs.for)) red.push(`for はひとことの欄を指す label だけ（for="supp_問いの鍵"）＝選択肢の label に付けると押した時に選ばれる欄がずれる: ${show}`);
      else fors.push([attrs.for, show]);
    }
    if ("class" in attrs) {
      const { allowed, known } = templateOutsideClasses();
      for (const c of attrs.class.split(/[ \t\n\f\r]+/).filter(Boolean))
        if (known.has(c) && !allowed.has(c)) { red.push(`型の外に class「${c}」を付けない（型の CSS・JS が見せ方を切り替える class で選択肢を隠させない）: ${show}`); break; }
    }
    // id はひとことの欄（textarea#supp_鍵）だけ（型の CSS・JS が使う id〔qa-print など〕で隠させない）
    if ("id" in attrs && !/^supp_[A-Za-z0-9_]+$/.test(attrs.id) && !(tag === "input" && /^(?:radio|checkbox)$/i.test(attrs.type ?? ""))) red.push(`型の外の id はひとことの欄の supp_問いの鍵 だけ（今 ${attrs.id}）: ${show}`);
    if ("id" in attrs) {
      if (ids.has(attrs.id)) red.push(`id「${attrs.id}」が 2 つある: ${show}`);
      ids.set(attrs.id, tag);
      if (tag === "input" && /^(?:radio|checkbox)$/i.test(attrs.type ?? "")) red.push(`選択（radio・checkbox）に id を付けない（label の for で別の選択肢から選ばせない）: ${show}`);
    }
    // 型は hidden・disabled の属性を使わない＝型の外に置けば赤（包む要素に付けて選択肢を隠す・押せなくする形を通さない）
    for (const a of ["hidden", "disabled"]) if (a in attrs) red.push(`${a} の属性を付けない（選択肢が見えない・押せない形にしない）: ${show}`);
    if ("name" in attrs && !["input", "select", "textarea", "meta"].includes(tag)) red.push(`<${tag}> に name を付けない（name は答えの欄 input・select・textarea だけ＝型の JS は name を持つ要素を答えとして読む）: ${show}`);
    if ("style" in attrs && tag !== "body") red.push(`<${tag}> に style がある（色や形は変えない・会社の色は body の --brand だけ）`);
    if (tag === "meta" && red.length === before && !("charset" in attrs) && !ALLOW.meta.names.includes((attrs.name ?? "").toLowerCase())) red.push(`許していない meta: ${show}`);
    if (tag === "input" && !ALLOW.input_types.includes((attrs.type ?? "text").toLowerCase())) red.push(`許していない入力の欄 type="${attrs.type}": ${show}`);
    if ("href" in attrs && !new RegExp(ALLOW.href, "i").test(attrs.href)) red.push(`許していない URL（https・mailto・tel・# だけ）: ${show}`);
    if ("src" in attrs && (tag !== "img" || !new RegExp(ALLOW.img_src).test(attrs.src))) red.push(`外のリソース・許していない src（写真は img の data:image/ だけ）: ${show}`);
    if (!strict && red.length === before) red.push(`属性は空白で区切り、値は引用符（"…"）で囲む（検査が読めない書き方）: ${show}`);
  }
  for (const [f, show] of fors) if (ids.get(f) !== "textarea") red.push(`for="${f}" の指す ひとことの欄（textarea id="${f}"）が無い: ${show}`);
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
      shape.push(`${name} の中身が型と違う（宛先で変えてよいのは 宛名・会社の色${name === "qa:foot" ? "・この後のこと" : ""} だけ）`);
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

  // 宛名・版・送る前の確認と受付（差出人・連絡先の欄は外した＝残っていれば赤・配る人が送る文で名乗る）
  const header = /<header\b[^>]*>[\s\S]*?<\/header\s*>/i.exec(html)?.[0] ?? "";
  const toEl = byClass(header, "to")[0];
  if (!toEl || !text(toEl.inner)) shape.push("宛名（header の .to）が無い");
  for (const [cls, name] of DROPPED) if (byClass(html, cls).length) shape.push(`${name}の欄（.${cls}）は外した（宛先で変えるのは宛名と会社の色だけ・名乗りは配る人の送る文で）`);
  // 前提 ①: 読んだ資料の一覧と答えるまでの扱い
  const docsEl = byClass(header, "docs")[0];
  // 資料のリンク: li の data-url（リンクが無い資料は data-url="" と data-no-url="訳"）。リンクは li の中の <a href> と同じ物
  const docs = docsEl
    ? [...docsEl.inner.matchAll(/<li\b[^>]*>([\s\S]*?)<\/li\s*>/gi)].map((m) => {
        const li = /^<li\b[^>]*>/i.exec(m[0])[0];
        return { key: attr(li, "data-doc"), name: text(m[1]), url: attr(li, "data-url"), noUrl: (attr(li, "data-no-url") ?? "").trim(),
          hrefs: [...m[1].matchAll(/<a\b[^>]*>/gi)].map((a) => attr(a[0], "href")).filter(Boolean) };
      })
    : null;
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

  // 古い印の形（tag-rec＝字を書く印）は畳んだ＝推奨の印は small.rec に理由と一緒に置く（字は型の CSS が出す）
  if (/\btag-rec\b/.test(html)) shape.push('推奨の印の古い形（tag-rec）は使わない（オーナー宛ての作り方の分かれ道の問いだけ、1 つ目の選択肢に <small class="rec">理由</small>）');
  // 見込みの枠（.estimate）の字は別に持つ（枠の外に見込みの言葉があれば赤にするため）
  const estEls = byClass(html, "estimate");
  const estTexts = estEls.flatMap((e) => [...textLines(e.inner), attr(e.tag, "data-basis") ?? ""]).filter(Boolean);
  const noEst = estEls.reduceRight((t, e) => t.slice(0, e.start) + " ".repeat(e.end - e.start) + t.slice(e.end), html);
  const visible = textLines(noEst.replace(/<(head)\b[\s\S]*?<\/head\s*>/i, (m) => (/<title>([\s\S]*?)<\/title>/i.exec(m)?.[1] ?? "")));
  const attrTexts = [...noEst.matchAll(/\b(?:data-(?:qlabel|glabel|where|no-url)|alt)\s*=\s*(?:"([^"]*)"|'([^']*)')/gi)].map((m) => decode(m[1] ?? m[2]));

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
    // 選択肢＝class の区切り（HTML の空白）で opt を持つ label（x-opt・opt-x は選択肢でない＝ブラウザの label.opt と同じ読み）
    const opts = [...q.inner.matchAll(/<label\b[^>]*>([\s\S]*?)<\/label>/gi)].filter((o) => /(?:^|[ \t\n\f\r])opt(?:[ \t\n\f\r]|$)/.test(attr(/<label\b[^>]*>/i.exec(o[0])[0], "class") ?? "")).map((o) => {
      const inp = /<input\b[^>]*>/i.exec(o[1])?.[0] ?? "";
      const b = /<b\b[^>]*>([\s\S]*?)<\/b>/i.exec(o[1]);
      const smalls = [...o[1].matchAll(/<small\b[^>]*>([\s\S]*?)<\/small>/gi)];
      const chg = smalls.find((x) => /\bclass\s*=\s*["'][^"']*\bchg\b/i.test(x[0]));
      const recs = smalls.filter((x) => hasRec(x[0]));
      const small = smalls.find((x) => x !== chg && !recs.includes(x));
      return {
        value: attr(inp, "value"),
        all: text(o[1]),
        head: text(b ? b[1] : o[1]),
        detail: small ? text(small[1]) : "",
        change: chg ? text(chg[1]) : "",
        rec: recs.length ? text(recs[0][1]) : null,   // null＝印なし・字＝理由
        hasInput: /^(?:radio|checkbox)$/i.test(attr(inp, "type") ?? "") && (o[1].match(/<input\b/gi) ?? []).length === 1,
        inputName: attr(inp, "name"),
        inputType: (attr(inp, "type") ?? "").toLowerCase(),
        hasB: !!b && text(b[1]).length > 0,
        // 初めから選ばれている・選べない・見えない選択肢（印の付いた問いでは赤）
        locked: hasAttr(inp, "checked") || hasAttr(inp, "disabled") || hasAttr(inp, "hidden") || hasAttr(/<label\b[^>]*>/i.exec(o[0])[0], "hidden"),
        recCount: recs.length,
        needSupp: attr(inp, "data-supp") === "need",
        suppBad: attr(inp, "data-supp") != null && attr(inp, "data-supp") !== "need" ? String(attr(inp, "data-supp")) : null,
      };
    });
    // 前提 ②③: まとまりの 1 行・何について・なぜ聞くか・見つけた事の資料・切り抜き・くわしく
    const gleads = byClass(q.inner, "glead").map((g) => textLines(g.inner));
    // 4 欄の箱は 1 問に 1 つずつ（2 つ目に書いて上限・決まった文をすり抜けさせない）
    const boxes = Object.fromEntries(["about", "why", "reading", "known", "evidence", "more", "clips", "estimate"].map((c) => [c, byClass(q.inner, c).length]));
    const aboutEl = byClass(q.inner, "about")[0];
    const aboutSpans = aboutEl ? [...aboutEl.inner.matchAll(/<span\b[^>]*>([\s\S]*?)<\/span\s*>/gi)] : [];
    const whyEl = byClass(q.inner, "why")[0];
    const moreEl = byClass(q.inner, "more")[0];
    // 根拠と読みと見込み: .evidence の li[data-doc][data-where]（原文の引用は中の .quote）・.reading・.estimate[data-basis]
    const readingEl = byClass(q.inner, "reading")[0];
    const evEl = byClass(q.inner, "evidence")[0];
    const evidence = evEl
      ? [...evEl.inner.matchAll(/<li\b[^>]*>([\s\S]*?)<\/li\s*>/gi)].map((li) => {
          const qt = byClass(li[1], "quote")[0];
          return { doc: attr(li[0], "data-doc"), where: (attr(li[0], "data-where") ?? "").trim(), quote: qt ? text(qt.inner).replace(/^[「『"]|[」』"]$/g, "").trim() : "" };
        })
      : [];
    const estEl = byClass(q.inner, "estimate")[0];
    const optsEl = byClass(q.inner, "opts")[0];
    const clips = byClass(q.inner, "clip").map((f) => {
      const img = /<img\b[^>]*>/i.exec(f.inner)?.[0] ?? null;
      const cap = /<figcaption\b[^>]*>([\s\S]*?)<\/figcaption\s*>/i.exec(f.inner);
      return { doc: attr(f.tag, "data-doc"), hasShows: attr(f.tag, "data-shows") != null, shows: (attr(f.tag, "data-shows") ?? "").split(/[\s、,]+/).filter(Boolean), img: !!img, src: img ? attr(img, "src") : null,
        alt: img ? attr(img, "alt") ?? "" : "", caption: cap ? text(cap[1]) : "" };
    });
    const freeInputs = [...q.inner.matchAll(/<input\b[^>]*\btype\s*=\s*["']?(text|date|month|number)\b[^>]*>|<select\b[^>]*>|<textarea\b[^>]*\bname\s*=\s*["'](?!supp_)[^>]*>/gi)].map((i) => i[0]);
    questions.push({
      key: m[1],
      label: (attr(q.tag, "data-qlabel") ?? "").trim(),
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
      reading: readingEl ? textLines(readingEl.inner) : null,
      readingAfterWhy: !readingEl || !whyEl || readingEl.start > whyEl.start,
      evidence,
      estimate: estEl ? { value: text(estEl.inner), basis: (attr(estEl.tag, "data-basis") ?? "").trim(), afterOpts: !optsEl || estEl.start >= optsEl.end } : null,
      more: moreEl ? textLines(moreEl.inner.replace(/<summary\b[\s\S]*?<\/summary\s*>/i, "").replace(/<div\b[^>]*class\s*=\s*["'][^"']*\borig\b[\s\S]*$/i, "")) : null,
      clips,
      tableRows: knownTables.reduce((n, t) => n + (t[0].match(/<tr\b/gi) ?? []).length, 0),
      options: opts,
      choices: inputs.length || sel.length,
      oneChoice: (inputs.length > 0 && inputs.length < 2) || (!inputs.length && sel.length === 1),
      freeInput: freeInputs.length > 0,
      // 問いの鍵を name に持つ欄（ページのどこでも・select・字の欄・hidden も）が、どれも label.opt の中の選択か（印の 1 つ目を検査とブラウザで同じにする）
      //   型の JS は name を持つ要素ならどれも答えの欄として読む＝要素の種類を問わず数える
      keyFieldsInOpts: [...html.matchAll(/<[A-Za-z][A-Za-z0-9-]*\b[^>]*>/g)].filter((t) => attr(t[0], "name") === m[1]).length
        === opts.filter((o) => o.hasInput && o.inputName === m[1]).length,
      numberInput: freeInputs.some((t) => /\btype\s*=\s*["']?number\b/i.test(t)),
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
  // 選択（radio・checkbox）はどれも問いの label.opt の中に置く（選択肢の定義を 1 つにする＝label.opt の外の選択で 1 つ目をずらさせない）
  const picksAll = [...html.matchAll(/<input\b[^>]*>/gi)].filter((t) => /^(?:radio|checkbox)$/i.test(attr(t[0], "type") ?? "")).length;
  const picksRead = questions.reduce((n, q) => n + q.options.filter((o) => o.hasInput).length, 0);
  if (picksAll !== picksRead) shape.push(`選択（radio・checkbox）が問いの選択肢（label.opt）の外に在る（ページに ${picksAll}・選択肢の中に ${picksRead}）`);
  // 推奨の印はページ全体で数え、問いの選択肢の決まった所で読めた数と合わなければ赤（問いの外・選択肢の外に置いて判定を逃れさせない）
  const recAll = [...html.matchAll(/<[A-Za-z][A-Za-z0-9-]*\b[^>]*>/g)].filter((t) => hasRec(t[0])).length;
  const recRead = questions.reduce((n, q) => n + q.options.reduce((k, o) => k + (o.recCount ?? 0), 0), 0);
  if (recAll !== recRead) shape.push(`推奨の印（class="rec"）が問いの選択肢（label.opt の中の small）の外に在る（ページに ${recAll}・選択肢の中に ${recRead}）`);
  return { format: "html", version, dest, holes, shape, brand, docs, hold, texts: [...visible, ...attrTexts], estTexts, questions };
}

// ── 読み取り 2: 問いのデータ（JSON）。確認のページを Artifact 型で作り、問いをデータで渡す時の形（SKILL.md §問いのデータ）。
//   「分からない」と「ほかに伝えたい事」は型の側が足す＝データに書かない。
const lines = (v) => (Array.isArray(v) ? v : typeof v === "string" ? v.split("\n") : []).map((x) => String(x).trim()).filter(Boolean);
export function readJson(data) {
  const shape = [];
  const qsIn = Array.isArray(data?.questions) ? data.questions : [];
  for (const [k, name] of [["to", "宛名"], ["title", "件名"], ["next", "この後のこと"]]) {
    if (!String(data?.[k] ?? "").trim()) shape.push(`${name}（"${k}"）が無い`);
  }
  for (const [k, name] of DROPPED) if (data && Object.hasOwn(data, k)) shape.push(`${name}（"${k}"）は外した（宛先で変えるのは宛名と会社の色だけ）`);
  const version = data?.version;
  if (version == null || !String(version).trim()) shape.push('版（"version"）が無い');
  else if (!/^[0-9A-Za-z._-]+$/.test(String(version))) shape.push(`版は半角英数字と . _ - だけ（今 ${version}）`);
  const questions = qsIn
    .filter((q) => q?.key !== FREE)
    .map((q) => {
      const raw = Array.isArray(q.options) ? q.options : [];
      if (raw.some((o) => typeof o === "string")) shape.push(`問い ${q.key}: 選択肢は {"value","label"} の形で書く（文字だけでは機械で戻せない）`);
      if (raw.some((o) => o && typeof o === "object" && o.value === UNKNOWN && Object.hasOwn(o, "recommended")))
        shape.push(`問い ${q.key}: 「分からない」に推奨の印（"recommended"）を付けない`);
      const options = raw
        .filter((o) => o && typeof o === "object" ? o.value !== UNKNOWN : true)
        .map((o) =>
          typeof o === "string"
            ? { value: null, head: o, all: o, detail: "" }
            : { value: o?.value ?? null, head: String(o?.label ?? ""), detail: String(o?.detail ?? ""), change: String(o?.change ?? "").trim(),
                all: [o?.label, o?.detail, o?.change].filter(Boolean).join(" "), rec: !Object.hasOwn(o ?? {}, "recommended") ? null : typeof o.recommended === "string" ? o.recommended.trim() : false, recCount: Object.hasOwn(o ?? {}, "recommended") ? 1 : 0, needSupp: o?.supp === "need",
                suppBad: o?.supp != null && o?.supp !== "need" ? JSON.stringify(o.supp) : null },
        );
      const table = Array.isArray(q.table) ? q.table : [];
      return {
        key: String(q.key ?? ""),
        label: String(q.label ?? "").trim(),
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
        reading: q.reading == null ? null : lines(q.reading),
        readingAfterWhy: true, // 型の側が並べる
        evidence: (Array.isArray(q.evidence) ? q.evidence : []).map((e) => ({ doc: e?.doc ?? null, where: String(e?.where ?? "").trim(), quote: String(e?.quote ?? "").trim() })),
        estimate: q.estimate == null ? null : { value: String(q.estimate?.value ?? "").trim(), basis: String(q.estimate?.basis ?? "").trim(), afterOpts: true },
        boxes: {},
        clips: (Array.isArray(q.clips) ? q.clips : []).map((c) => ({ doc: c?.doc ?? null, hasShows: Array.isArray(c?.shows), shows: Array.isArray(c?.shows) ? c.shows.map(String) : [], img: true, src: c?.src ?? null,
          alt: String(c?.alt ?? ""), caption: String(c?.caption ?? "") })),
        tableRows: table.length,
        options,
        choices: options.length,
        oneChoice: options.length === 1,
        freeInput: ["text", "date", "month", "number"].includes(q.input),
        numberInput: q.input === "number",
        required: true, // 型の側が付ける
        unknownLast: true, // 型の側が足す
        supp: q.supp !== false,
      };
    });
  const docsIn = Array.isArray(data?.docs) ? data.docs : null;
  const docs = docsIn
    ? docsIn.map((d) => ({ key: d?.key ?? null, name: String(d?.name ?? "").trim(), url: d?.url == null ? null : String(d.url).trim(), noUrl: String(d?.no_url ?? "").trim(), hrefs: null }))
    : null;
  const texts = [data?.to, data?.title, data?.lead, data?.due, data?.next, data?.hold, ...(docsIn ?? []).flatMap((d) => [d?.name, d?.received, d?.no_url]),
    ...qsIn.flatMap((q) => [q?.label, q?.glabel, q?.glead, ...(Array.isArray(q?.about) ? q.about : []), q?.question, ...lines(q?.known), q?.more,
    ...lines(q?.reading), ...(Array.isArray(q?.evidence) ? q.evidence.flatMap((e) => [e?.where, e?.quote]) : []),
    ...(Array.isArray(q?.clips) ? q.clips.flatMap((c) => [c?.alt, c?.caption]) : []),
    ...(Array.isArray(q?.table) ? q.table.flat().map(String) : []),
    ...(Array.isArray(q?.options) ? q.options.flatMap((o) => (typeof o === "string" ? [o] : [o?.label, o?.detail, o?.change, typeof o?.recommended === "string" ? o.recommended : null])) : [])])]
    .flatMap((x) => lines(x));
  const estTexts = qsIn.flatMap((q) => (q?.estimate ? [q.estimate.value, q.estimate.basis] : [])).flatMap((x) => lines(x));
  const holes = [...new Set(JSON.stringify(data ?? {}).match(/\{\{[^}]*\}\}/g) ?? [])];
  return { format: "json", version: version == null ? null : String(version), dest: data?.dest ?? null, holes, shape, brand: data?.brand ?? null, docs, hold: String(data?.hold ?? "").trim(), texts, estTexts, questions };
}

// ── 推奨の印（RULES.rec）: オーナー宛ての作り方の分かれ道の問いだけ・1 問に 1 つ・1 つ目・「分からない」に付けない・理由つき
function checkRec(q, id, dest, format, limits, red) {
  const marked = q.options.map((o, i) => ({ o, i })).filter(({ o }) => o.rec != null);
  if (!marked.length) return;
  const mark = format === "html" ? "small.rec" : '"recommended"';
  if (new Set(q.options.filter((o) => o.inputType).map((o) => o.inputType)).size > 1)
    red.push(`${id}: 推奨の印の付いた問いの選択は radio か checkbox のどちらか 1 つにそろえる（印の選択肢と別の選択肢を両方選べる形にしない）`);
  if (q.options.some((o) => o.locked))
    red.push(`${id}: 推奨の印の付いた問いの選択肢に checked・disabled・hidden を付けない（印の選択肢が初めから選ばれている・選べない・見えない形にしない）`);
  if (q.keyFieldsInOpts === false)
    red.push(`${id}: 推奨の印の付いた問いは、答えの欄（name="${q.key}"）をどれも選択肢（label.opt）の中の radio・checkbox にする（select・字の欄・hidden・label.opt の外の欄があると、ブラウザでは 1 つ目がずれる）`);
  const est = format === "html" ? ".estimate" : '"estimate"';
  if (!RULES.rec.dests.includes(dest))
    red.push(`${id}: 推奨の印（${mark}）はオーナー宛て（copy・artifact）のページだけ。お客さん宛て（${dest ?? "宛先なし"}）は印を付けず、AI の今の見込みは根拠つきで ${est} へ`);
  else if (!RULES.rec.kinds.includes(q.kind))
    red.push(`${id}: 推奨の印（${mark}）は作り方の分かれ道の問い（judge）だけ。事実を聞く問い（${q.kind ?? "形なし"}）は印を付けず、AI の今の見込みは根拠つきで ${est} へ`);
  const n = marked.reduce((s, { o }) => s + (o.recCount ?? 1), 0);
  if (n > 1) red.push(`${id}: 推奨の印は 1 問に 1 つ（今 ${n}）。推せる案が 2 つあるなら問いを分けるか印を外す`);
  for (const { o, i } of marked) {
    const name = `${id}: 選択肢「${o.head.slice(0, 20)}」の推奨の印`;
    if (o.value === UNKNOWN) { red.push(`${name}: 「分からない」には付けない`); continue; }
    if (format === "html" && !o.hasB) red.push(`${name}: 見出し（<b>）が要る（「（推奨）」の字は見出しの後に出る）`);
    if (i !== 0 && n === 1) red.push(`${name}: 印は 1 つ目の選択肢だけ（推す案を 1 つ目に置く）`);
    if (o.rec === false) red.push(`${name}: "recommended" は理由の文字（推す理由 1 行）で書く`);
    else if (!o.rec) red.push(`${name}に理由が無い（推す理由を 1 行・${mark}）`);
    else if (len(o.rec) > limits.rec_chars) red.push(`${name}の理由が ${len(o.rec)} 字（${limits.rec_chars} 字まで）: ${o.rec.slice(0, 30)}…`);
  }
}

// ── 決まり: 問いの形（HTML でも JSON でも同じ物）を 1 か所で見る
export function checkPage(page, { valuesPath = null, prior = null } = {}) {
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

  const estTexts = page.estTexts ?? [];
  for (const line of [...page.texts, ...estTexts]) {
    for (const [k, why] of [["recommend", "選択肢にも文にも付けない・AI の今の見込みは根拠つきで見込みの枠へ"], ["prior_ref", "1 画面 1 問＝この問いだけで答えられるように、要る事をこの問いに書く"]]) {
      const m = rx(k).exec(line);
      if (m) red.push(`「${m[0]}」は書かない（${why}）: ${line.slice(0, 60)}`);
    }
  }
  for (const line of page.texts) {
    const m = rx("estimate_word").exec(line);
    if (m) red.push(`「${m[0]}」は AI の今の見込みの枠（${page.format === "html" ? ".estimate" : '"estimate"'}）の外に書かない（見込みを前提に見せない）: ${line.slice(0, 60)}`);
  }
  for (const line of [...page.texts, ...estTexts]) {
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
    // 資料のリンク（Drive などの URL）。リンクが無い資料は訳を書く。宛先が開けない時のため、実物（切り抜き・引用）が主でリンクは添え
    const where = page.format === "html" ? "data-url" : '"url"';
    if (!d.url && !d.noUrl) red.push(`読んだ資料 ${d.key ?? ""} にリンク（${where}）もリンクが無い訳（${page.format === "html" ? "data-no-url" : '"no_url"'}）も無い: ${d.name.slice(0, 30)}`);
    else if (d.url && !/^https:\/\/[^\s<>"'&]+$/.test(d.url)) red.push(`読んだ資料 ${d.key ?? ""} のリンクは https:// で始まる URL だけ（今 ${d.url.slice(0, 40)}）`);
    else if (d.url && d.hrefs && !d.hrefs.includes(d.url)) red.push(`読んだ資料 ${d.key ?? ""} のリンクが見えない（li の中に <a href="${d.url.slice(0, 30)}…"> を置く）`);
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
    const laterLead = company.later_lead ?? RULES.later_lead;
    if (first && q.group === "later" && q.gleads.length === 1 && q.gleads[0].join("") !== laterLead)
      red.push(`${id}: 先に決めておきたい事のまとまりの 1 行は決まった文「${laterLead}」のまま`);
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
    // 根拠（どの資料のどこを見たか）と実物（切り抜きか原文の引用）と AI の読み。ほかの資料を開かずに答えられるように
    const evWhere = page.format === "html" ? '.evidence の li[data-doc][data-where]' : '"evidence": [{"doc","where","quote"}]';
    if (!q.evidence.length) red.push(`${id}: 根拠（どの資料のどこを見たか ${evWhere}）が無い`);
    else if (q.evidence.length > limits.evidence) red.push(`${id}: 根拠が ${q.evidence.length} つ（${limits.evidence} つまで）`);
    q.evidence.forEach((e, i) => {
      const eid = `${id}: 根拠 ${i + 1}`;
      if (!e.doc || !docKeys.includes(e.doc)) red.push(`${eid} の資料「${e.doc ?? "無し"}」が読んだ資料の一覧に無い`);
      if (!e.where) red.push(`${eid} の場所（${page.format === "html" ? "data-where" : '"where"'}＝ページ・欄・行、シートならタブ名とセル範囲）が空`);
      else if (len(e.where) > limits.where_chars) red.push(`${eid} の場所が ${len(e.where)} 字（${limits.where_chars} 字まで）`);
      if (len(e.quote) > limits.quote_chars) red.push(`${eid} の原文の引用が ${len(e.quote)} 字（${limits.quote_chars} 字まで・長い原文はくわしくの中へ）`);
    });
    if (!q.clips.length && !q.evidence.some((e) => e.quote))
      red.push(`${id}: 実物が無い（切り抜き ${page.format === "html" ? "figure.clip" : '"clips"'} か、根拠の原文の引用 ${page.format === "html" ? ".evidence の .quote" : '"quote"'} を 1 つ以上・決まりの問いは規程の条文を引く）`);
    if (q.reading == null || !q.reading.length) red.push(`${id}: AI の読み（${page.format === "html" ? ".reading" : '"reading"'}＝「こう読んだ → ここが合わない／決まらない」）が無い`);
    else {
      if (q.reading.length > limits.reading_lines) red.push(`${id}: AI の読みが ${q.reading.length} 行（${limits.reading_lines} 行まで）`);
      for (const l of q.reading) if (len(l) > limits.reading_line_chars) red.push(`${id}: AI の読みの 1 行が ${len(l)} 字（${limits.reading_line_chars} 字まで）: ${l.slice(0, 30)}…`);
      if (!q.readingAfterWhy) red.push(`${id}: AI の読み（.reading）はなぜ聞くか（.why）の下に置く`);
    }
    if (q.estimate) {
      if (!q.estimate.value) red.push(`${id}: AI の今の見込みの中身が空（無いなら枠ごと外す）`);
      else if (len(q.estimate.value) > limits.estimate_chars) red.push(`${id}: AI の今の見込みが ${len(q.estimate.value)} 字（${limits.estimate_chars} 字まで）`);
      if (!q.estimate.basis) red.push(`${id}: AI の今の見込みの根拠（${page.format === "html" ? "data-basis" : '"basis"'}）が空（根拠がある時だけ見込みを出す）`);
      else if (len(q.estimate.basis) > limits.basis_chars) red.push(`${id}: AI の今の見込みの根拠が ${len(q.estimate.basis)} 字（${limits.basis_chars} 字まで）`);
      if (!q.estimate.afterOpts) red.push(`${id}: AI の今の見込み（.estimate）は選択肢（.opts）の後に置く`);
    }

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
    // 数を書かせてよいのは資料の外にしか無い数だけ（資料の外の事実 fact の問いで、数を打つ欄 number の時）。計算できる数は候補に出す
    const num = rx("number_ask").exec(asked);
    if (num && !(q.kind === "fact" && q.numberInput))
      red.push(`${id}: 数を書かせる問い「${num[0]}」（資料から計算できる数は候補を並べて「どちらが正しいですか」にする・資料の外にしか無い数だけ data-kind="fact" と数を打つ欄 type="number" で聞く）`);
    const conf = rx("confirm").exec(asked);
    if (conf && q.kind !== "mismatch") red.push(`${id}: 「${conf[0]}」は資料どうしが食い違う時だけ（data-kind="mismatch"）`);
    const sym = rx("symbol_ref").exec(asked);
    if (sym) red.push(`${id}: 記号「${sym[0]}」で選択肢を指している（中身の言葉で書く）`);

    // 選択肢 1 つでよいのは、資料の外にしか無い数を数の欄で聞く時だけ（「当てはまらない」1 つと数の欄で答えが決まる）
    if (q.oneChoice && !(q.kind === "fact" && q.numberInput)) red.push(`${id}: 選択肢が 1 つだけ（「分からない」の外に 2 つ以上）`);
    if (!q.choices && !q.freeInput) red.push(`${id}: 答える欄が無い`);
    if (!q.required) red.push(`${id}: 答えずに送れる（最初の選択肢か入力の欄に required を付ける）`);
    if (q.checkboxRequired) red.push(`${id}: checkbox に required を付けない（その 1 つを選ばないと送れなくなる）`);
    const real = q.options.filter((o) => o.value !== UNKNOWN);
    checkRec(q, id, dest, page.format, limits, red);
    const vals = [];
    for (const o of real) {
      if (len(o.head) > limits.option_chars) red.push(`${id}: 選択肢の見出しが ${len(o.head)} 字（${limits.option_chars} 字まで・中身は結果の 1 行へ）: ${o.head.slice(0, 30)}…`);
      if (len(o.detail) > limits.option_detail_chars) red.push(`${id}: 選択肢の添え書きが ${len(o.detail)} 字（${limits.option_detail_chars} 字まで）: ${o.detail.slice(0, 30)}…`);
      if (!(RULES.free_options[o.value] ?? []).includes(o.head) && o.head !== RULES.unknown.label) {
        if (!o.change) red.push(`${id}: 選択肢「${o.head.slice(0, 20)}」にこの答えで変わる事（誰の・何が・いくら ${page.format === "html" ? "small.chg" : '"change"'}）が無い`);
        else if (len(o.change) > limits.change_chars) red.push(`${id}: この答えで変わる事が ${len(o.change)} 字（${limits.change_chars} 字まで）: ${o.change.slice(0, 30)}…`);
      }
      if (o.suppBad) red.push(`${id}: 選択肢「${o.head.slice(0, 20)}」の ${page.format === "html" ? "data-supp" : '"supp"'} は "need" だけ（今 ${o.suppBad}）`);
      else if (((RULES.free_options.other ?? []).includes(o.head) || RULES.supp_ask.test(`${o.head} ${o.detail} ${o.change}`)) && !o.needSupp)
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
    if (q.kind === "complete" && !q.options.some((o) => o.value !== UNKNOWN && o.needSupp))
      red.push(`${id}: 資料がそろっているかの問いに、足りない資料の名をひとことに書かせる選択肢（${page.format === "html" ? 'data-supp="need"' : '"supp": "need"'}）が無い`);
    if (q.kind === "fact") {
      for (const must of RULES.fact_must_have) if (!q.options.some((o) => o.all.includes(must))) red.push(`${id}: 資料の外の事実の問いに「${must}」の選択肢が無い`);
    }
    if (!q.supp) red.push(`${id}: ひとことの欄（name="supp_${q.key}"）が無い`);
  }
  checkPrior(qs, company, prior, red, page.version);
  return { ok: red.length === 0, format: page.format, dest, questions: keys, red: [...new Set(red)], warn };
}

// ── 前の答えを照らす口（作り方 0 を機械にする・値の表の docs-kit.qa-html.prior_check_cmd）
//   命令は標準入力に priorInput の JSON（形 qa-prior/1）を受け、標準出力に
//   {"answered": {"問いの鍵": "前の答えの ID か URL"}, "checked": {"問いの鍵": "引いた結果（ID・URL・引いた言葉）"}} を返す。
//   answered に在る鍵が問いに残っていれば赤。値の表に命令が在る時だけ、引いた結果（answered か checked）の無い問いも赤。
//   値の表に命令が無く --prior も無ければ何も見ない（今までどおり）。
export const PRIOR_FORMAT = "qa-prior/1";
export function priorInput(page) {
  return {
    format: PRIOR_FORMAT,
    questions: page.questions.map((q) => ({ key: q.key, label: q.label ?? "", question: q.question, about: q.about, known: q.known, group: q.group, kind: q.kind })),
  };
}
// 引いた結果の置き場の既定＝ページの隣（確認_x.html → 確認_x.prior.json）。guard の qa_page もページの path だけで同じ物を読む。
export const priorPathFor = (file) => resolve(file).replace(/(\.(html?|json))?$/i, "") + ".prior.json";
const isMap = (x) => x != null && typeof x === "object" && !Array.isArray(x);
// 引いた結果を読む。形が違えば { error }。
export function readPrior(data) {
  if (!isMap(data)) return { error: "JSON の物（{…}）でない" };
  if (data.error != null) return { error: `命令が落ちた回の結果: ${data.error}` };
  const out = { answered: new Map(), checked: new Map(), pageVersion: data.page_version == null ? null : String(data.page_version) };
  for (const k of ["answered", "checked"]) {
    if (data[k] == null) continue;
    if (!isMap(data[k])) return { error: `"${k}" は {"問いの鍵": "引いた結果"} の形で書く` };
    for (const [key, ref] of Object.entries(data[k])) {
      if (typeof ref !== "string") return { error: `"${k}" の「${key}」の値は文字（引いた結果）で書く` };
      out[k].set(key, ref.trim());
    }
  }
  return out;
}
function checkPrior(qs, company, prior, red, version) {
  const cmd = String(company.prior_check_cmd ?? "").trim();
  if (!prior) {
    if (cmd) red.push("前の答えを照らした結果が無い（値の表に prior_check_cmd がある）: node check.mjs <file> --run-prior で引いてから検査する");
    return;
  }
  if (prior.error) {
    red.push(`前の答えを照らした結果が読めない（${prior.from ?? "--prior"}）: ${prior.error}`);
    return;
  }
  if (prior.pageVersion != null && version != null && prior.pageVersion !== String(version)) {
    red.push(`前の答えを照らした結果が別の版（${prior.pageVersion}）のページで引いた物: 今の版（${version}）で --run-prior を引き直す`);
    return;
  }
  for (const q of qs) {
    const id = `問い ${q.key}`;
    if (prior.answered.has(q.key)) red.push(`${id}: 前の答えで答え済み（${prior.answered.get(q.key) || "引いた結果が空"}）＝問いから外す（作り方 0）`);
    else if (cmd && !prior.checked.get(q.key)) red.push(`${id}: 前の答えを照らした結果が無い（--run-prior で引き直す）`);
  }
}
// 値の表の命令を走らせ、引いた結果を返す。走らない・JSON でない時は { error }。
export function runPrior(page, cmd, { cwd = process.cwd(), timeoutMs = 120000 } = {}) {
  const r = spawnSync(cmd, { shell: true, cwd, input: JSON.stringify(priorInput(page)), encoding: "utf8", timeout: timeoutMs });
  if (r.error) return { error: `命令が走らない: ${r.error.message}`, raw: null };
  if (r.status !== 0) return { error: `命令が ${r.status ?? r.signal} で終わった: ${String(r.stderr ?? "").trim().slice(0, 200)}`, raw: null };
  let data;
  try {
    data = JSON.parse(r.stdout);
  } catch (e) {
    return { error: `命令の出力が JSON でない: ${e.message}`, raw: null };
  }
  return { ...readPrior(data), raw: data };
}

// 入口（ほかの検査は import して呼ぶ）
export const checkQa = (raw, opts) => checkPage(readHtml(raw), opts);
export const checkQaJson = (data, opts) => checkPage(readJson(typeof data === "string" ? JSON.parse(data) : data), opts);
export function readPage(path) {
  const raw = readFileSync(path, "utf8");
  if (/\.json$/i.test(path) || /^\s*\{/.test(raw)) {
    let data;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      return { error: `JSON として読めない: ${e.message}` };
    }
    return readJson(data);
  }
  return readHtml(raw);
}
// 引いた結果を file から読む。file が無ければ null（＝引いていない）。
export function loadPrior(path, { explicit = false } = {}) {
  if (!path || !existsSync(path)) return explicit ? { error: "file が無い", from: path } : null;
  try {
    return { ...readPrior(JSON.parse(readFileSync(path, "utf8"))), from: path };
  } catch (e) {
    return { error: `JSON として読めない: ${e.message}`, from: path };
  }
}
// opts.priorPath を渡さなければ、ページの隣（priorPathFor）に在る時だけ読む。
export function checkFile(path, { priorPath, priorExplicit = false, ...opts } = {}) {
  const page = readPage(path);
  if (page.error) return { ok: false, format: "json", dest: null, questions: [], red: [page.error], warn: [] };
  const prior = opts.prior ?? loadPrior(priorPath ?? priorPathFor(path), { explicit: priorExplicit && !!priorPath });
  return checkPage(page, { ...opts, prior });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const takesValue = new Set(["--values", "--prior"]);
  const KNOWN = new Set([...takesValue, "--json", "--run-prior", "--prior-input"]);
  // 知らない印・同じ印の 2 度書きは既定で止める（打ち間違えた印を黙って無視して、頼んだ検査をせずに緑にしない。
  // checker の verdict_form.py と同じ決まり）
  const flags = args.filter((a, i) => a.startsWith("--") && !takesValue.has(args[i - 1]));
  const unknown = flags.filter((f) => !KNOWN.has(f));
  if (unknown.length) {
    console.error(`知らない印: ${unknown.join(" ")}（使える印: ${[...KNOWN].join(" ")}）`);
    process.exit(2);
  }
  const twice = [...KNOWN].filter((f) => flags.filter((x) => x === f).length > 1);
  if (twice.length) {
    console.error(`${twice.join("・")} を 2 度書いている（どちらを使うか決められない）`);
    process.exit(2);
  }
  // file は全部照らす（1 つ目だけ照らして残りを黙って通さない）
  const files = args.filter((a, i) => !a.startsWith("--") && !takesValue.has(args[i - 1]));
  if (!files.length) {
    console.error("使い方: check.mjs <file.html|file.json> [<file> …] [--json] [--values <skill-values.json>] [--prior <引いた結果.json>] [--run-prior] [--prior-input]");
    process.exit(2);
  }
  const perPage = ["--prior", "--run-prior", "--prior-input"].filter((f) => args.includes(f));
  if (files.length > 1 && perPage.length) {
    console.error(`${perPage.join("・")} は 1 枚ずつ（file が ${files.length} 個ある）: ${files.join(" ")}`);
    process.exit(2);
  }
  const file = files[0];
  const at = (flag) => (args.indexOf(flag) >= 0 ? args[args.indexOf(flag) + 1] : undefined);
  for (const flag of takesValue) {
    if (args.includes(flag) && (at(flag) == null || at(flag).startsWith("--"))) {
      console.error(`${flag} の後に file を書く`);
      process.exit(2);
    }
  }
  // guard の qa_page は cwd をページの dir にして呼ぶ＝ページが repo の外（窓の scratchpad）でも値の表を見つけるため、窓の repo も起点に足す
  const valuesPath = at("--values") ?? findValues(dirname(resolve(file)), process.cwd(), process.env.CLAUDE_PROJECT_DIR);
  const priorPath = at("--prior") ?? priorPathFor(file);
  let opts = { valuesPath, priorPath, priorExplicit: args.includes("--prior") };
  if (args.includes("--prior-input") || args.includes("--run-prior")) {
    const page = readPage(file);
    if (page.error) {
      console.error(page.error);
      process.exit(2);
    }
    if (args.includes("--prior-input")) {
      console.log(JSON.stringify(priorInput(page), null, 2));
      process.exit(0);
    }
    const cmd = String(loadCompany(valuesPath).prior_check_cmd ?? "").trim();
    if (!cmd) {
      console.error("--run-prior: 値の表（config/skill-values.json）に docs-kit.qa-html.prior_check_cmd が無い");
      process.exit(2);
    }
    const got = runPrior(page, cmd, { cwd: valuesPath ? dirname(dirname(resolve(valuesPath))) : process.cwd() });
    // 落ちた時も書き換える（前の回の結果を残すと、後でページの path だけで呼ぶ guard が古い結果で緑にする）
    writeFileSync(priorPath, JSON.stringify(got.raw ? { ...got.raw, page_version: page.version } : { error: got.error }, null, 2) + "\n");
    opts = { valuesPath, prior: { ...got, from: `prior_check_cmd → ${priorPath}` } };
  }
  const results = files.map((f) => {
    const v = at("--values") ?? findValues(dirname(resolve(f)), process.cwd(), process.env.CLAUDE_PROJECT_DIR);
    const o = f === file ? opts : { valuesPath: v, priorPath: priorPathFor(f), priorExplicit: false };
    return { file: resolve(f), ...checkFile(f, o) };
  });
  if (args.includes("--json")) console.log(JSON.stringify(results.length === 1 ? results[0] : results, null, 2));
  else {
    for (const res of results) {
      console.log(`${res.ok ? "🟢 緑" : "🔴 赤"}  ${res.file}（${res.format}・問い ${res.questions.length}・宛先 ${res.dest ?? "?"}）`);
      for (const r of res.red) console.log(`  ✗ ${r}`);
    }
    if (results.some((r) => !r.ok)) console.log(ROOT_CAUSE);
    if (results.length > 1) console.log(`照らした file ${results.length}・赤 ${results.filter((r) => !r.ok).length}`);
  }
  process.exit(results.every((r) => r.ok) ? 0 : 1);
}
