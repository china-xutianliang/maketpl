# 视频管线（video/）

分享视频的全套制作管线，全本地、零素材依赖：

```
script.py    口播稿（每行一句 = 一段配音 = 一个场景）
tts.py       edge-tts 逐句配音 + 词边界 → out/voice.mp3, subtitles.srt, timing.json
_ui_capture.py  拉起真 app + 假目标窗抓真实界面图 → assets/ui/*.png
render.py    PIL 逐帧合成（数字人+演示动画+UI截图+karaoke字幕）→ ffmpeg 编码
preview.py   抽帧预览：python preview.py 9x16 <t秒> out.png
```

## 重出视频

```bash
python tts.py            # 改了 script.py 后先重配音
python render.py all     # 渲染 B-roll + 抖音9x16 + B站16x9
python render.py 9x16    # 只出一版
```

## 数字人说明

`render.py: make_avatar()` 用 PIL 画的机器人形象：
- 嘴型 3 档（闭/半开/全开），由配音实时音量（RMS 包络）驱动
- 每 ~3 秒眨眼一次，头部随音量轻微浮动
- 想换真人/照片形象：把 `AVA` 换成你的照片抠图（同样做 3 个嘴型变体），
  或只保留配音/字幕，把素材喂给剪映数字人

## 输出

- `out/成品_抖音9x16.mp4`  1080x1920，直接发抖音
- `out/成品_B站16x9.mp4`   1920x1080，直接发B站
- `out/素材_原理演示Broll.mp4`  无数字人/字幕的纯净演示段，给平台当 B-roll
- `out/口播稿.txt`        配音文案 + 发布文案参考
- `out/subtitles.srt`     句级字幕（剪映可直接导入）
- `out/voice.mp3`         AI 配音（备用，或用平台自己的声音）
- `assets/ui/*.png`       工具真实界面截图（可当平台素材）
