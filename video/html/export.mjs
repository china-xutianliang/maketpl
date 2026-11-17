// 把 promo.html 逐帧导出成 mp4（带 voice.mp3 配音）
// 用法：
//   npm i puppeteer            （或 puppeteer-core + 本机 Chrome，设 CHROME=路径）
//   node export.mjs            → ../out/推广_16x9.mp4
//   node export.mjs v          → ../out/推广_9x16.mp4
//   node export.mjs shots 3,12,30   只截几帧预览 → ../out/preview_*.png
// 需要 ffmpeg（PATH 里，或设 FFMPEG=路径）
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, "../out");
const args = process.argv.slice(2);
const vertical = args.includes("v");
const shotsIdx = args.indexOf("shots");
const FPS = Number(process.env.FPS || 30);
const TOTAL = 58.6;
const [W, H] = vertical ? [1080, 1920] : [1920, 1080];

let launch;
try {
  const c = (await import("@sparticuz/chromium")).default;
  const p = (await import("puppeteer-core")).default;
  launch = async () => p.launch({ executablePath: process.env.CHROME || await c.executablePath(), args: c.args, headless: true });
} catch {
  const p = (await import("puppeteer")).default;
  launch = async () => p.launch({ headless: true, executablePath: process.env.CHROME });
}

const browser = await launch();
const page = await browser.newPage();
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
const url = pathToFileURL(path.join(here, "promo.html")).href + "?export" + (vertical ? "&v" : "");
await page.goto(url, { waitUntil: "networkidle0" });
await page.evaluate(() => document.fonts.ready);
await page.addStyleTag({ content: "#wrap{position:static!important;display:block!important}" });
await page.evaluate(() => window.dispatchEvent(new Event("resize")));

const tag = vertical ? "9x16" : "16x9";
if (shotsIdx >= 0) {
  for (const s of (args[shotsIdx + 1] || "3,12,20,27,34,41,45,50,56").split(",")) {
    await page.evaluate(t => window.renderAt(t), Number(s));
    await page.screenshot({ path: path.join(out, `preview_${tag}_${s}.png`) });
  }
  await browser.close();
  process.exit(0);
}

const ffmpeg = process.env.FFMPEG || "ffmpeg";
const dst = path.join(out, `推广_${tag}.mp4`);
const fs = await import("node:fs");
const tmp = path.join(out, `_frames_${tag}`);
fs.rmSync(tmp, { recursive: true, force: true }); fs.mkdirSync(tmp, { recursive: true });
const N = Math.round(TOTAL * FPS);
const WORKERS = Number(process.env.WORKERS || 4);
const pages = [page];
for (let w = 1; w < WORKERS; w++) {
  const pg = await browser.newPage();
  await pg.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
  await pg.goto(url, { waitUntil: "networkidle0" });
  await pg.evaluate(() => document.fonts.ready);
  await pg.addStyleTag({ content: "#wrap{position:static!important;display:block!important}" });
  await pg.evaluate(() => window.dispatchEvent(new Event("resize")));
  pages.push(pg);
}
let next = 0, done = 0;
await Promise.all(pages.map(async pg => {
  while (true) {
    const i = next++; if (i >= N) return;
    await pg.evaluate(t => window.renderAt(t), i / FPS);
    await pg.screenshot({ path: path.join(tmp, `f${String(i).padStart(5, "0")}.jpg`), type: "jpeg", quality: 92 });
    if (++done % FPS === 0) process.stdout.write(`\r${(done / FPS).toFixed(0)}s / ${TOTAL}s`);
  }
}));
await browser.close();
await new Promise((res, rej) => spawn(ffmpeg, ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", path.join(tmp, "f%05d.jpg"),
  "-i", path.join(out, "voice.mp3"), "-c:v", "libx264", "-threads", "2", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
  "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", dst], { stdio: "inherit" })
  .on("close", (c, sig) => (c || sig) ? rej(new Error("ffmpeg " + (c ?? sig))) : res()));
fs.rmSync(tmp, { recursive: true, force: true });
console.log("\n→", dst);
