// Пересборка подмножества иконок.
//
//   node scripts/build-icons.mjs
//
// Зачем: полный шрифт Tabler весит 825 КБ ради 105 значков, которые мы реально
// используем. Скрипт собирает имена из кода (фронт, админка, лендинг и бэкенд —
// сервер тоже присылает имена иконок), вырезает из шрифта только их и
// переписывает src/icons.css.
//
// Нужен python с fonttools: pip install fonttools brotli
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const ROOTS = ["src", "../admin", "../landing", "../backend/app"];
const EXT = new Set([".js", ".jsx", ".css", ".html", ".py", ".json"]);

function walk(dir, acc = []) {
  let items = [];
  try { items = readdirSync(dir); } catch { return acc; }
  for (const it of items) {
    if (it === "node_modules" || it === "dist" || it === "__pycache__") continue;
    const p = join(dir, it);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, acc);
    else if (EXT.has(extname(p))) acc.push(p);
  }
  return acc;
}

const used = new Set();
for (const root of ROOTS)
  for (const f of walk(root))
    for (const m of readFileSync(f, "utf8").matchAll(/\bti-[a-z0-9-]+/g)) used.add(m[0].slice(3));

const css = readFileSync("node_modules/@tabler/icons-webfont/dist/tabler-icons.min.css", "utf8");
const codes = new Map();
for (const m of css.matchAll(/\.ti-([a-z0-9-]+):before\{content:"\\([0-9a-fA-F]+)"\}/g))
  codes.set(m[1], m[2]);

const found = [...used].filter((n) => codes.has(n)).sort();
const missing = [...used].filter((n) => !codes.has(n));
console.log(`иконок в коде: ${used.size}, найдено в шрифте: ${found.length}`);
if (missing.length) console.log("не иконки (пропускаем):", missing.join(", "));

const unicodes = found.map((n) => "U+" + codes.get(n).toUpperCase()).join(",");
execSync(`pyftsubset node_modules/@tabler/icons-webfont/dist/fonts/tabler-icons.woff2 ` +
         `--unicodes=${unicodes} --flavor=woff2 --output-file=src/assets/tabler-subset.woff2 ` +
         `--layout-features= --no-hinting --desubroutinize`, { stdio: "inherit" });

const out = [
  "/* Иконки: ТОЛЬКО те, что реально используются. Собрано scripts/build-icons.mjs —",
  "   руками не править. Полный шрифт Tabler весит 825 КБ, это больше всего JS",
  "   приложения вместе взятого. */",
  '@font-face{font-family:"tabler-icons-subset";',
  '  src:url("./assets/tabler-subset.woff2") format("woff2");',
  "  font-weight:400;font-style:normal;font-display:block}",
  '.ti{font-family:"tabler-icons-subset";font-style:normal;font-weight:400;',
  "  speak:none;display:inline-block;text-decoration:inherit;",
  "  font-variant:normal;text-transform:none;line-height:1;vertical-align:-.125em;",
  "  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}",
  ...found.map((n) => `.ti-${n}:before{content:"\\${codes.get(n)}"}`),
].join("\n");
writeFileSync("src/icons.css", out + "\n");
console.log("src/icons.css обновлён");
