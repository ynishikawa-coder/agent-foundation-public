#!/usr/bin/env node
// qa-html の問いの検査（外部依存ゼロ・node だけで動く）。決まりの表はこのファイルの頭の RULES の 1 か所。
//   repo ごとに足す語・上限は repo の根の config/skill-values.json の docs-kit.qa-html.internal_words・limits。
// 赤にする物: 宛先の印（data-dest＝send・copy・artifact）が無い／問いの形（data-kind）が 4 つ以外／内部の言葉／
//   番号（Q2026.11-37 のような）だけで過去の問いを指す字／数を書かせる問い／長さの上限超え・問いの数の上限超え／
//   選択肢が 1 つだけ／1 問に 2 つ以上を詰めた問い／「合っていますか」を食い違いの外で使う／資料の外の事実に
//   「まだ分からない」「該当しない」が無い／自由記述の補足（supp_鍵）が無い／鍵の重なり。
// 読める物は 3 つで、決まりは同じ 1 か所（checkPage）が見る:
//   ① 1 枚の HTML（<body data-dest="copy|send">）
//   ② 確認のページ（Artifact）の HTML（公開の時に body が包まれる＝ページの根の要素に data-dest="artifact" など）
//   ③ 問いのデータ（JSON・Artifact 型に中身をデータで渡す時。形は SKILL.md の §問いのデータ）
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
    "decides_chars": 40,
    "option_chars": 50,
    "questions_per_page": 12
  },
  "kinds": {
    "choose": "どちらが正しいですか＝こちらが計算した候補を並べる（候補 2 つ以上）",
    "mismatch": "資料どうしが食い違う＝「合っていますか」を使ってよいのはここだけ（候補 2 つ以上）",
    "fact": "資料の外にしか無い事実（「まだ分からない」「該当しない」を必ず置く）",
    "judge": "読んでも決まりが分からない時の判断（候補 2 つ以上）"
  },
  "fact_must_have": [
    "まだ分からない",
    "該当しない"
  ],
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
  "question_end": "ですか|ますか|でしょうか|ください|[？?]"
};
const KINDS = Object.keys(RULES.kinds);
const FREE = "__自由記入__";

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
    .replace(/<\/(li|p|div|tr|h\d|legend|summary|label)\s*>/gi, "\n")
    .replace(/<[^>]+>/g, "");
  return decode(t)
    .split("\n")
    .map((x) => x.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}
const text = (html) => textLines(html).join(" ");
const len = (s) => [...s.replace(/\s+/g, "")].length;
const attr = (tag, name) => {
  const m = new RegExp(`\\s${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`, "i").exec(tag);
  return m ? decode(m[1] ?? m[2]) : null;
};

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

// 宛先: send＝素のフォームで配る口へ・copy＝貼り戻しのテキストを写す・artifact＝確認のページ（Artifact）が答えを持つ
export const DESTS = ["send", "copy", "artifact"];

function compileWords(company) {
  return [...RULES.internal_words, ...(company.internal_words ?? [])].map((w) =>
    typeof w === "string" ? { 語: w, re: new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "u") } : { ...w, re: new RegExp(w.正規表現 ?? w.語, "u") },
  );
}

// ── 読み取り 1: HTML（file:// の 1 枚・確認のページの HTML） → 問いの形
export function readHtml(raw) {
  const html = dropCode(mask(raw));
  const holes = [...new Set(html.match(/\{\{[^}]*\}\}/g) ?? [])];

  // 宛先の印は 1 つ。<body data-dest> が正。確認のページ（Artifact）は公開の時に骨組み（body）が包まれるので、
  // body に印が無ければ、最初に data-dest を持つ要素（ページの根の要素）の印を読む。
  const body = /<body\b[^>]*>/i.exec(html)?.[0] ?? "";
  let dest = attr(body, "data-dest");
  if (dest == null) {
    const m = /<[a-z][a-z0-9]*\b[^>]*\bdata-dest\s*=[^>]*>/i.exec(html);
    dest = m ? attr(m[0], "data-dest") : null;
  }
  const hasCopyBtn = /\bid\s*=\s*["']copybtn["']/.test(html);

  const visible = textLines(html.replace(/<(head)\b[\s\S]*?<\/head\s*>/i, (m) => (/<title>([\s\S]*?)<\/title>/i.exec(m)?.[1] ?? "")));
  const labels = [...html.matchAll(/\bdata-qlabel\s*=\s*(?:"([^"]*)"|'([^']*)')/gi)].map((m) => decode(m[1] ?? m[2]));

  const questions = [];
  for (const m of html.matchAll(/<[a-z][a-z0-9]*\b[^>]*\bdata-qkey\s*=\s*["']([^"']+)["'][^>]*>/gi)) {
    if (m[1] === FREE) continue;
    const q = elementAt(html, m.index);
    if (!q) continue;
    const legend = /<legend\b[^>]*>([\s\S]*?)<\/legend\s*>/i.exec(q.inner);
    const known = byClass(q.inner, "known")[0];
    const decides = byClass(q.inner, "decides")[0];
    const radios = [...q.inner.matchAll(/<input\b[^>]*\btype\s*=\s*["']?(radio|checkbox)\b[^>]*>/gi)];
    const sel = [...q.inner.matchAll(/<option\b[^>]*>([\s\S]*?)<\/option>/gi)].filter((o) => attr(o[0], "value") !== "" && text(o[1]));
    const opts = [...q.inner.matchAll(/<label\b[^>]*\bclass\s*=\s*["'][^"']*\bopt\b[^"']*["'][^>]*>([\s\S]*?)<\/label>/gi)].map((o) => {
      const b = /<b\b[^>]*>([\s\S]*?)<\/b>/i.exec(o[1]);
      return { all: text(o[1]), head: text((b ? b[1] : o[1]).replace(/<span\b[^>]*class\s*=\s*["'][^"']*tag-rec[\s\S]*?<\/span>/gi, "")) };
    });
    questions.push({
      key: m[1],
      kind: attr(q.tag, "data-kind"),
      question: legend ? text(legend[1]).replace(/^[A-Za-z]?-?\d+[.．]?\s*/, "") : "",
      multiline: !!legend && /<br\b/i.test(legend[1]),
      known: known ? textLines(known.inner) : [],
      decides: decides ? text(decides.inner).replace(/^この答えで決まる事\s*[:：]?\s*/, "") : "",
      options: opts,
      choices: radios.length || sel.length,
      oneChoice: (radios.length > 0 && radios.length < 2) || (!radios.length && sel.length === 1),
      freeInput: /<input\b[^>]*\btype\s*=\s*["']?(text|date|month|number)\b|<textarea\b[^>]*\bname\s*=\s*["'](?!supp_)/i.test(q.inner),
      supp: new RegExp(`\\bname\\s*=\\s*["']supp_${m[1]}["']`).test(q.inner),
    });
  }
  return { format: "html", dest, holes, needsCopyBtn: dest === "copy" && !hasCopyBtn, texts: [...visible, ...labels], questions };
}

// ── 読み取り 2: 問いのデータ（JSON）。確認のページを Artifact 型で作り、問いをデータで渡す時の形。
//   { "dest": "artifact|copy|send", "to": 宛名, "title": 題, "lead": 前書き,
//     "questions": [ { "key", "label", "kind", "question", "known": [行…], "options": [ "見出し" | {"label","detail","recommended"} ],
//                      "input": "text|date|month|number"（選ばせない時）, "more": たたんだ補足, "decides", "supp": 補足の欄（既定 true） } ] }
const lines = (v) => (Array.isArray(v) ? v : typeof v === "string" ? v.split("\n") : []).map((x) => String(x).trim()).filter(Boolean);
export function readJson(data) {
  const qsIn = Array.isArray(data?.questions) ? data.questions : [];
  const questions = qsIn
    .filter((q) => q?.key !== FREE)
    .map((q) => {
      const options = (Array.isArray(q.options) ? q.options : []).map((o) =>
        typeof o === "string" ? { head: o, all: o } : { head: String(o?.label ?? ""), all: [o?.label, o?.detail].filter(Boolean).join(" ") },
      );
      return {
        key: String(q.key ?? ""),
        kind: q.kind ?? null,
        question: String(q.question ?? "").trim(),
        multiline: /\n/.test(String(q.question ?? "").trim()),
        known: lines(q.known),
        decides: String(q.decides ?? "").trim(),
        options,
        choices: options.length,
        oneChoice: options.length === 1,
        freeInput: ["text", "date", "month", "number"].includes(q.input),
        supp: q.supp !== false,
      };
    });
  const texts = [data?.to, data?.title, data?.lead, ...qsIn.flatMap((q) => [q?.label, q?.question, ...lines(q?.known), q?.more, q?.decides,
    ...(Array.isArray(q?.options) ? q.options.flatMap((o) => (typeof o === "string" ? [o] : [o?.label, o?.detail])) : [])])]
    .flatMap((x) => lines(x));
  const holes = [...new Set(JSON.stringify(data ?? {}).match(/\{\{[^}]*\}\}/g) ?? [])];
  return { format: "json", dest: data?.dest ?? null, holes, needsCopyBtn: false, texts, questions };
}

// ── 決まり: 問いの形（HTML でも JSON でも同じ物）を 1 か所で見る
export function checkPage(page, { valuesPath = null } = {}) {
  const company = loadCompany(valuesPath);
  const limits = { ...RULES.limits, ...(company.limits ?? {}) };
  const words = compileWords(company);
  const rx = (k) => new RegExp(RULES[k], "u");
  const red = [];
  const warn = [];
  const { dest, holes, questions: qs } = page;

  if (holes.length) red.push(`型の差し込みが残っている: ${holes.slice(0, 3).join("、")}${holes.length > 3 ? ` ほか ${holes.length - 3} 個` : ""}`);
  if (!DESTS.includes(dest))
    red.push(`宛先の印が無い: data-dest="send|copy|artifact"（HTML は <body data-dest>・確認のページはページの根の要素・データは "dest"）`);
  if (page.needsCopyBtn) red.push("写す宛先なのに写すボタン（id=copybtn）が無い");

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

  for (const q of qs) {
    const id = `問い ${q.key || "(鍵なし)"}`;
    if (!/^[A-Za-z0-9_]+$/.test(q.key)) red.push(`${id}: 鍵は半角英数字と _ だけ`);
    if (!KINDS.includes(q.kind)) red.push(`${id}: 問いの形 data-kind が ${KINDS.join("・")} のどれでもない（今 ${q.kind ?? "無し"}）`);
    const qtext = q.question;
    if (!qtext) red.push(`${id}: 問いの 1 行（legend）が無い`);
    if (q.multiline) red.push(`${id}: 問いが 2 行以上（1 行にする）`);
    if (len(qtext) > limits.question_chars) red.push(`${id}: 問いが ${len(qtext)} 字（${limits.question_chars} 字まで）: ${qtext}`);
    const ends = qtext.match(new RegExp(RULES.question_end, "gu")) ?? [];
    if (ends.length > 1 || rx("two_in_one").test(qtext)) red.push(`${id}: 1 問に 2 つ以上を聞いている（1 問 1 つに分ける）: ${qtext}`);

    if (q.known.length > limits.known_lines) red.push(`${id}: 分かっている事が ${q.known.length} 行（${limits.known_lines} 行まで・残りはたたんだ補足へ）`);
    if (len(q.known.join("")) > limits.known_chars) red.push(`${id}: 分かっている事が ${len(q.known.join(""))} 字（${limits.known_chars} 字まで）`);
    const asked = [qtext, ...q.known].join(" ");
    const num = rx("number_ask").exec(asked);
    if (num) red.push(`${id}: 数を書かせる問い「${num[0]}」（こちらで計算した候補を並べて「どちらが正しいですか」にする）`);
    const conf = rx("confirm").exec(asked);
    if (conf && q.kind !== "mismatch") red.push(`${id}: 「${conf[0]}」は資料どうしが食い違う時だけ（data-kind="mismatch"）`);

    if (!q.decides) red.push(`${id}: 「この答えで決まる事」の 1 行（class="decides"）が無い`);
    else if (len(q.decides) > limits.decides_chars) red.push(`${id}: この答えで決まる事が ${len(q.decides)} 字（${limits.decides_chars} 字まで）`);

    if (q.oneChoice) red.push(`${id}: 選択肢が 1 つだけ（どう答えても聞き直さずに済むよう 2 つ以上）`);
    if (!q.choices && !q.freeInput) red.push(`${id}: 答える欄が無い`);
    for (const o of q.options) {
      if (len(o.head) > limits.option_chars) red.push(`${id}: 選択肢が ${len(o.head)} 字（${limits.option_chars} 字まで）: ${o.head.slice(0, 30)}…`);
    }
    if (q.kind === "fact") {
      for (const must of RULES.fact_must_have) if (!q.options.some((o) => o.all.includes(must))) red.push(`${id}: 資料の外の事実の問いに「${must}」の選択肢が無い`);
    }
    if (!q.supp) red.push(`${id}: 自由記述の補足（name="supp_${q.key}"）が無い`);
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
