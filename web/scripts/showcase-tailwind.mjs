// Compile the showcase stylesheet with the Tailwind v4 install the viewer already pins.
// Usage: node showcase-tailwind.mjs <web dir> <output css>  (input CSS on stdin)
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const [webDir, outFile] = process.argv.slice(2);
const require = createRequire(path.join(webDir, "package.json"));
const postcss = require("postcss");
const tailwind = require("@tailwindcss/postcss");

const input = readFileSync(0, "utf8");
// `from` sits inside web/ so `@import "tailwindcss"` resolves against its node_modules; sources are absolute.
const result = await postcss([tailwind({ optimize: { minify: true } })]).process(input, {
  from: path.join(webDir, "app", "showcase-input.css"),
});
writeFileSync(outFile, result.css);
