# -*- coding: utf-8 -*-
# 推广视频 v3：动图 -> 透明 PNG。全动画演示，快节奏 + 强转场。用法：python video/promo3.py
import asyncio, math, os, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTDIR = os.path.join(ROOT, 'output')
TMP = os.path.join(OUTDIR, '_promo3_tmp')
os.makedirs(TMP, exist_ok=True)
W, H, FPS = 1280, 720, 30
VOICE, RATE = 'zh-CN-YunxiNeural', '+12%'
LEAD, TAIL = 0.25, 0.35
NL = chr(10)

SCENES = [
    dict(k='hook', extra=1.8, v='会动的画面，也能一键抠成透明图！'),
    dict(k='pain', extra=0.7, v='手动抠？每一帧都不一样，抠到天亮也抠不干净。'),
    dict(k='principle', extra=1.4, v='透明模板制作的思路很简单：连拍多帧，逐个像素比对。一直在变的，自动变透明；始终不动的主体，原样留下。'),
    dict(k='live', extra=1.2, v='框住区域，点一下动态截图，背景一点点消失，主体自己浮出来。'),
    dict(k='proof', extra=1.0, v='保存成透明 PNG，放到海报、视频、PPT 上，边缘都干干净净。'),
    dict(k='tips', extra=0.8, v='三个小技巧：框选贴近主体；背景动得越多，抠得越干净；剩下的杂点，魔术棒一点就清。'),
    dict(k='cta', extra=1.8, v='透明模板制作，双击就能用，现在就试试吧！'),
]

def ffdur(p):
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', p], capture_output=True, text=True)
    return float(r.stdout.strip())

async def tts_all():
    import edge_tts
    for i, s in enumerate(SCENES):
        p = os.path.join(TMP, 'v%d.mp3' % i)
        await edge_tts.Communicate(s['v'], VOICE, rate=RATE).save(p)
        s['mp3'], s['vd'] = p, ffdur(p)

try:
    asyncio.run(tts_all()); HAS_VOICE = True
except Exception as e:
    print('TTS failed, music only:', e); HAS_VOICE = False
    for s in SCENES: s['mp3'], s['vd'] = None, len(s['v']) * 0.19

t = 0.0
for s in SCENES:
    s['start'] = t; s['dur'] = LEAD + s['vd'] + TAIL + s['extra']; t += s['dur']
TOTAL = t
NF = int(math.ceil(TOTAL * FPS))
def hook_T(sd): return min(sd * 0.45, 2.2)
FLASH = [s['start'] for s in SCENES[1:]] + [SCENES[0]['start'] + hook_T(SCENES[0]['dur'])]
print('total %.1fs, %d frames, voice=%s' % (TOTAL, NF, HAS_VOICE))
