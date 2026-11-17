# HTML 推广视频

- `promo.html`：浏览器直接打开就能播放，配音用 `../out/voice.mp3`，字幕和时间轴对齐 `timing.json`
  - `?v` 竖屏 9:16　`?rec` 隐藏按钮自动播放（适合 OBS 录屏）　`?nosub` 关闭字幕
- `export.mjs`：逐帧渲染后用 ffmpeg 合成 mp4
  ```bash
  npm i puppeteer
  node export.mjs        # → ../out/推广_16x9.mp4
  node export.mjs v      # → ../out/推广_9x16.mp4
  ```
