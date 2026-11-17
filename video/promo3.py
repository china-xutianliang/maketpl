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

def make_music(total, path, hits, sr=44100):
    n = int((total + 1) * sr); out = np.zeros(n); rng = np.random.default_rng(7)
    def add(t0, sig):
        s0 = int(t0 * sr)
        if s0 < 0: sig = sig[-s0:]; s0 = 0
        if s0 >= n or len(sig) == 0: return
        e = min(n, s0 + len(sig)); out[s0:e] += sig[:e - s0]
    chords = [[220, 261.63, 329.63], [174.61, 220, 261.63], [261.63, 329.63, 392], [196, 246.94, 293.66]]
    beat = 0.5; bar = 4 * beat
    for k in range(int(total / bar) + 2):
        ch = chords[k % 4]
        L = int((bar + 0.3) * sr); tt = np.arange(L) / sr
        env = np.minimum(1, tt / 0.2) * np.exp(-tt * 0.8); sig = np.zeros(L)
        for f in ch: sig += 0.035 * env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt))
        add(k * bar, sig)
        for j in range(8):
            tb = np.arange(int(0.22 * sr)) / sr
            add(k * bar + j * beat / 2, 0.09 * np.exp(-tb * 9) * np.sin(np.pi * ch[0] * tb))
            tq = np.arange(int(0.2 * sr)) / sr
            f = ch[[0, 1, 2, 1][j % 4]] * 2
            add(k * bar + j * beat / 2 + beat / 4, 0.025 * np.exp(-tq * 12) * np.sin(2 * np.pi * f * tq))
    tk = np.arange(int(0.2 * sr)) / sr
    kick = 0.45 * np.exp(-tk * 14) * np.sin(2 * np.pi * (50 * tk + 90 * (1 - np.exp(-35 * tk)) / 35))
    Lh = int(0.05 * sr); hat = 0.06 * rng.standard_normal(Lh) * np.exp(-np.arange(Lh) / sr * 80); hat = np.diff(hat, prepend=0)
    for b in range(int(total / beat) + 2):
        add(b * beat, kick); add(b * beat + beat / 2, hat)
    Lw = int(0.45 * sr); tw = np.arange(Lw) / sr
    wn = np.convolve(rng.standard_normal(Lw), np.ones(6) / 6, 'same')
    whoosh = 0.25 * wn * (tw / tw[-1]) ** 2
    for h in hits:
        if h > 0.3: add(h - 0.45, whoosh); add(h, kick * 1.3)
    fi, fo, end = int(0.6 * sr), int(2.0 * sr), int(total * sr)
    out[:fi] *= np.linspace(0, 1, fi); out[end - fo:end] *= np.linspace(1, 0, fo); out[end:] = 0
    out = out / (np.abs(out).max() + 1e-9) * 0.8
    pcm = (np.stack([out, out], 1) * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

music = os.path.join(TMP, 'music.wav'); make_music(TOTAL, music, FLASH)
audio = os.path.join(TMP, 'audio.wav')
cmd = ['ffmpeg', '-y', '-v', 'error', '-i', music]
fc, mix = '[0:a]volume=0.28[m];', '[m]'
if HAS_VOICE:
    for i, s in enumerate(SCENES):
        cmd += ['-i', s['mp3']]; ms = int((s['start'] + LEAD) * 1000)
        fc += '[%d:a]aresample=44100,aformat=channel_layouts=stereo,adelay=%d|%d,volume=1.7[v%d];' % (i + 1, ms, ms, i)
        mix += '[v%d]' % i
n_in = len(SCENES) + 1 if HAS_VOICE else 1
fc += mix + 'amix=inputs=%d:normalize=0:duration=longest,alimiter=limit=0.95[a]' % n_in
cmd += ['-filter_complex', fc, '-map', '[a]', '-t', '%.3f' % TOTAL, audio]
subprocess.run(cmd, check=True)

FB, FR = 'C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'
_fc = {}
def F(sz, b=True):
    sz = max(6, int(sz)); k = (sz, b)
    if k not in _fc: _fc[k] = ImageFont.truetype(FB if b else FR, sz)
    return _fc[k]

INK, DIM = (240, 244, 255), (165, 175, 205)
ACC, YEL, RED, GRN = (90, 220, 190), (255, 214, 80), (255, 80, 95), (100, 225, 120)
DARK = (14, 16, 34)

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def eback(x):
    x = clamp(x); c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2

def vgrad(w, h, c1, c2):
    tt = np.linspace(0, 1, h)[:, None, None]
    arr = np.array(c1)[None, None, :] * (1 - tt) + np.array(c2)[None, None, :] * tt
    return Image.fromarray(arr.astype(np.uint8).repeat(w, axis=1), 'RGB')

def glow(r, c, a=80):
    im = Image.new('RGBA', (2 * r, 2 * r), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([r * 0.3, r * 0.3, r * 1.7, r * 1.7], fill=c + (a,))
    return im.filter(ImageFilter.GaussianBlur(r * 0.35))

BG = vgrad(W, H, (10, 12, 32), (34, 14, 58))
_d = ImageDraw.Draw(BG)
for y in range(0, H, 40):
    for x in range(0, W, 40): _d.point((x, y), fill=(48, 52, 90))
G1, G2 = glow(300, (40, 200, 170)), glow(340, (140, 70, 255))
GL = glow(70, (210, 255, 240), 160)
RING = glow(130, ACC, 100)
WHITE = Image.new('RGB', (W, H), (255, 255, 255))

def background(t):
    fr = BG.copy()
    fr.paste(G1, (int(-220 + 160 * math.sin(t * 0.35)), int(-200 + 100 * math.cos(t * 0.41))), G1)
    fr.paste(G2, (int(W - 480 + 140 * math.cos(t * 0.31)), int(H - 520 + 110 * math.sin(t * 0.37))), G2)
    return fr

def txt(d, xy, s, sz, fill=INK, b=True, anchor='la', shadow=True):
    f = F(sz, b)
    if shadow: d.text((xy[0] + 2, xy[1] + 3), s, font=f, fill=(0, 0, 0), anchor=anchor)
    d.text(xy, s, font=f, fill=fill, anchor=anchor)

def paste_a(fr, im, xy, a=1.0):
    if a <= 0: return
    if im.mode != 'RGBA': im = im.convert('RGBA')
    if a < 1:
        im = im.copy(); im.putalpha(im.getchannel('A').point(lambda v: int(v * a)))
    fr.paste(im, (int(xy[0]), int(xy[1])), im)

def pop_text(fr, s, cx, cy, sz, lt, fill=INK, delay=0.0):
    tl = lt - delay
    if tl < 0: return
    sc = 0.6 + 0.4 * eback(tl / 0.35); a = ease(tl / 0.2); f = F(sz * sc)
    tw = int(f.getlength(s)) + 60; th = int(sz * sc * 1.6) + 20
    lay = Image.new('RGBA', (tw, th), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.text((tw / 2, th / 2 + 4), s, font=f, fill=(0, 0, 0, 170), anchor='mm')
    d.text((tw / 2, th / 2), s, font=f, fill=fill, anchor='mm', stroke_width=max(2, int(sz * sc / 16)), stroke_fill=(10, 12, 30))
    paste_a(fr, lay, (cx - tw / 2, cy - th / 2), a)

def tag(fr, x, y, s, col, a=1.0, sz=24, fg=DARK):
    f = F(sz); w = int(f.getlength(s) + 32); h = sz + 18
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], h // 2, fill=col + (255,))
    d.text((w / 2, h / 2), s, font=f, fill=fg, anchor='mm')
    paste_a(fr, im, (x, y), a)

def checker(w, h, s=16):
    im = Image.new('RGB', (w, h), (205, 208, 216)); d = ImageDraw.Draw(im)
    for y in range(0, h, s):
        for x in range(0, w, s):
            if (x // s + y // s) % 2: d.rectangle([x, y, x + s - 1, y + s - 1], fill=(245, 246, 250))
    return im

def star(d, cx, cy, r, col):
    d.polygon([(cx, cy - r), (cx + r * .25, cy - r * .25), (cx + r, cy), (cx + r * .25, cy + r * .25), (cx, cy + r), (cx - r * .25, cy + r * .25), (cx - r, cy), (cx - r * .25, cy - r * .25)], fill=col)

def rr_mask(w, h, r):
    m = Image.new('L', (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=255); return m

_shc = {}
def panel(fr, img, cx, cy, w, h, border=ACC, a=1.0, r=18, bw=3):
    im = img if img.size == (w, h) else img.resize((w, h), Image.BILINEAR)
    key = (w, h, r)
    if key not in _shc:
        sh = Image.new('L', (w + 80, h + 80), 0); ImageDraw.Draw(sh).rounded_rectangle([40, 50, w + 40, h + 50], r, fill=180)
        _shc[key] = (sh.filter(ImageFilter.GaussianBlur(18)), rr_mask(w, h, r))
    sh, m = _shc[key]
    if a < 1: sh = sh.point(lambda v: int(v * a)); m = m.point(lambda v: int(v * a))
    x, y = int(cx - w / 2), int(cy - h / 2)
    fr.paste((0, 0, 0), (x - 40, y - 40), sh)
    fr.paste(im.convert('RGB'), (x, y), m)
    if border and a > 0.95: ImageDraw.Draw(fr).rounded_rectangle([x - 2, y - 2, x + w + 1, y + h + 1], r, outline=border, width=bw)
    return x, y

def header(fr, lt, badge, title):
    e = ease(lt / 0.4); dx = -380 * (1 - e)
    d = ImageDraw.Draw(fr); f = F(26); bw = f.getlength(badge) + 36
    d.rounded_rectangle([50 + dx, 34, 50 + dx + bw, 80], radius=23, fill=ACC)
    d.text((50 + dx + bw / 2, 57), badge, font=f, fill=DARK, anchor='mm')
    txt(d, (70 + dx + bw, 57), title, 38, anchor='lm')

ICON = Image.open(os.path.join(ROOT, 'icon.png')).convert('RGBA')
_icons = {}
def icon(sz):
    if sz not in _icons: _icons[sz] = ICON.resize((sz, sz), Image.LANCZOS)
    return _icons[sz]

def wrap(s, f, maxw):
    lines, cur = [], ''
    for c in s:
        if f.getlength(cur + c) > maxw and cur and c not in '。，！？、：；）」':
            lines.append(cur); cur = c
        else: cur += c
    if cur: lines.append(cur)
    return lines

def subtitle(fr, s, vt, vd):
    if vt < -0.1 or vt > vd + TAIL: return
    f = F(32); lines = wrap(s, f, 1120)
    total = sum(len(l) for l in lines); said = int(clamp(vt / max(vd, 0.1)) * total + 0.5)
    lh = 46; top = H - 26 - lh * len(lines); maxw = max(f.getlength(l) for l in lines)
    bw, bh = int(maxw + 48), lh * len(lines) + 16
    lay = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle([0, 0, bw - 1, bh - 1], 14, fill=(0, 0, 0, 160))
    fr.paste(lay, (int(W / 2 - bw / 2), top - 10), lay)
    d = ImageDraw.Draw(fr); k = 0
    for i, l in enumerate(lines):
        x = W / 2 - f.getlength(l) / 2; y = top + i * lh
        for c in l:
            d.text((x + 2, y + 2), c, font=f, fill=(0, 0, 0))
            d.text((x, y), c, font=f, fill=YEL if k < said else INK)
            x += f.getlength(c); k += 1

# ---------------- 演示动图：静止的小机器人 + 不停变化的背景 ----------------
DW, DH = 480, 320
_yy, _xx = np.mgrid[0:DH, 0:DW].astype(np.float32)
_rng = np.random.default_rng(3)
PARTS = [(_rng.uniform(0, DW), _rng.uniform(0, DH), _rng.uniform(-70, 70), _rng.uniform(-45, 45), _rng.uniform(6, 15),
          [(255, 255, 255), (255, 230, 120), (120, 255, 220), (255, 150, 200)][i % 4]) for i in range(14)]

def plasma(tt):
    r = 105 + 85 * np.sin(_xx * 0.017 + tt * 1.9) + 25 * np.sin(_yy * 0.031 - tt * 1.1)
    g = 85 + 75 * np.sin(_yy * 0.021 + tt * 1.5 + 2) + 20 * np.sin(_xx * 0.011 + tt)
    b = 150 + 85 * np.sin((_xx + _yy) * 0.012 + tt * 1.2 + 4)
    return np.clip(np.stack([r, g, b], -1), 0, 255).astype(np.uint8)

def make_subj():
    im = Image.new('RGBA', (DW, DH), (0, 0, 0, 0)); d = ImageDraw.Draw(im); o = DARK + (255,)
    d.line([(240, 52), (240, 26)], fill=o, width=6); d.ellipse([229, 12, 251, 34], fill=(255, 92, 92, 255), outline=o, width=4)
    d.rounded_rectangle([165, 155, 193, 228], 13, fill=(255, 214, 80, 255), outline=o, width=4)
    d.rounded_rectangle([287, 155, 315, 228], 13, fill=(255, 214, 80, 255), outline=o, width=4)
    d.rounded_rectangle([205, 246, 233, 292], 10, fill=(70, 80, 130, 255), outline=o, width=4)
    d.rounded_rectangle([247, 246, 275, 292], 10, fill=(70, 80, 130, 255), outline=o, width=4)
    d.rounded_rectangle([193, 143, 287, 256], 24, fill=(90, 220, 190, 255), outline=o, width=4)
    d.rounded_rectangle([212, 166, 268, 210], 10, fill=o); d.text((240, 188), 'PNG', font=F(18), fill=(90, 220, 190, 255), anchor='mm')
    d.rounded_rectangle([178, 48, 302, 142], 30, fill=(255, 214, 80, 255), outline=o, width=4)
    for ex in (220, 260):
        d.ellipse([ex - 16, 74, ex + 16, 106], fill=(255, 255, 255, 255), outline=o, width=3)
        d.ellipse([ex - 7, 83, ex + 7, 97], fill=o)
    d.arc([216, 96, 264, 130], 20, 160, fill=o, width=5)
    d.ellipse([186, 108, 202, 120], fill=(255, 140, 140, 255)); d.ellipse([278, 108, 294, 120], fill=(255, 140, 140, 255))
    return im
SUBJ = make_subj()
SBOX = SUBJ.getbbox()
ROBOT = SUBJ.crop(SBOX)

def demo_frame(tt):
    im = Image.fromarray(plasma(tt)); d = ImageDraw.Draw(im)
    for (x0, y0, vx, vy, r, c) in PARTS:
        x = (x0 + vx * tt) % (DW + 40) - 20; y = (y0 + vy * tt) % (DH + 40) - 20
        d.ellipse([x - r, y - r, x + r, y + r], fill=c)
    im.paste(SUBJ, (0, 0), SUBJ)
    return im

# 真正跑一遍多帧逐像素比对：任意帧与第 1 帧差异超过阈值 -> 透明
NCAP, CAPDT = 40, 0.09
caps = [np.asarray(demo_frame(k * CAPDT)).astype(np.int16) for k in range(NCAP)]
acc = np.zeros((DH, DW), bool); MASKS = []
for c in caps:
    acc = acc | (np.abs(c - caps[0]).max(-1) > 28); MASKS.append(acc.copy())
CAP0 = caps[0].astype(np.uint8)
CHK = np.asarray(checker(DW, DH))
SUBJ_A = np.asarray(SUBJ)[..., 3] > 128
CLEAN = Image.fromarray(np.where(SUBJ_A[..., None], CAP0, CHK).astype(np.uint8))
PCT = [100 * m[~SUBJ_A].mean() for m in MASKS]
print('bg transparent after %d frames: %.1f%%' % (NCAP, PCT[-1]))

def cap_result(k):
    m = MASKS[max(0, min(NCAP - 1, k))][..., None]
    return Image.fromarray(np.where(m, CHK, CAP0).astype(np.uint8))

RED_T = (CAP0 * 0.3 + np.array([255, 50, 80]) * 0.7).astype(np.uint8)
def cap_compare(k):
    m = MASKS[max(0, min(NCAP - 1, k))][..., None]
    return Image.fromarray(np.where(m, RED_T, CAP0).astype(np.uint8))

THUMBS = [demo_frame(i * 0.5).resize((165, 110), Image.BILINEAR) for i in range(5)]

def polaroid(img, label):
    c = Image.new('RGBA', (300, 250), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    d.rounded_rectangle([0, 0, 299, 249], 12, fill=(248, 248, 252, 255))
    c.paste(img.resize((276, 184), Image.BILINEAR), (12, 12))
    d.text((150, 222), label, font=F(24), fill=DARK, anchor='mm')
    return c
POLR = [polaroid(demo_frame(i * 0.55), '第 %d 帧' % (i + 1)).rotate(a, expand=True, resample=Image.BICUBIC) for i, a in enumerate([-8, 5, -4, 9])]

def make_stamp():
    im = Image.new('RGBA', (560, 150), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([5, 5, 554, 144], 20, fill=(40, 8, 20, 225), outline=RED + (255,), width=10)
    d.text((280, 75), '抠到天亮也不干净', font=F(54), fill=RED, anchor='mm')
    return im.rotate(-7, expand=True, resample=Image.BICUBIC)
STAMP = make_stamp()

def make_bgs():
    w, h = 360, 240
    a = checker(w, h)
    b = vgrad(w, h, (255, 150, 90), (130, 60, 170)); db = ImageDraw.Draw(b)
    db.text((22, 24), 'SUMMER', font=F(40), fill='white'); db.text((22, 74), 'SALE 50%', font=F(30), fill=(255, 240, 180))
    for i in range(6): db.ellipse([20 + i * 26, 190, 34 + i * 26, 204], fill=(255, 230, 170))
    c = Image.new('RGB', (w, h), (24, 28, 52)); dc = ImageDraw.Draw(c)
    dc.rounded_rectangle([14, 14, 346, 226], 10, fill=(248, 248, 252))
    dc.text((32, 40), '产品介绍', font=F(28), fill=DARK, anchor='lm')
    for j, ww in enumerate([150, 170, 120, 140]): dc.rounded_rectangle([32, 80 + j * 30, 32 + ww, 92 + j * 30], 6, fill=(200, 205, 220))
    return [a, b, c]
BGS = make_bgs()
RB = ROBOT.resize((int(ROBOT.width * 180 / ROBOT.height), 180), Image.LANCZOS)

def cursor(d, x, y):
    pts = [(0, 0), (0, 28), (7, 21), (12, 33), (18, 30), (13, 19), (22, 19)]
    d.polygon([(x + px, y + py) for px, py in pts], fill='white', outline=DARK)

def dashed(d, box, col, off, w=3, seg=10):
    x0, y0, x1, y1 = [int(v) for v in box]
    for x in range(x0 - off, x1, seg * 2):
        a, b = max(x0, x), min(x1, x + seg)
        if a < b: d.line([(a, y0), (b, y0)], fill=col, width=w); d.line([(a, y1), (b, y1)], fill=col, width=w)
    for y in range(y0 - off, y1, seg * 2):
        a, b = max(y0, y), min(y1, y + seg)
        if a < b: d.line([(x0, a), (x0, b)], fill=col, width=w); d.line([(x1, a), (x1, b)], fill=col, width=w)

# ---------------- 场景 1-3 ----------------
def sc_hook(fr, lt, sd):
    T = hook_T(sd); p = ease((lt - T) / 0.55)
    src = demo_frame(lt)
    if p > 0:
        cut = max(1, int(DW * p)); src = src.copy(); src.paste(CLEAN.crop((0, 0, cut, DH)), (0, 0))
    s = 0.82 + 0.18 * eback(lt / 0.5)
    w = int(624 * s) // 4 * 4; h = int(w / 1.5) // 4 * 4
    x, y = panel(fr, src.resize((w, h), Image.BILINEAR), 640, 372, w, h, border=ACC if p >= 1 else (255, 255, 255))
    d = ImageDraw.Draw(fr)
    if 0 < p < 1:
        sx = x + int(w * p); fr.paste(GL, (sx - 70, int(y + h / 2 - 70)), GL)
        d.rectangle([sx - 3, y, sx + 3, y + h], fill=(255, 255, 255))
    if p < 0.5: tag(fr, x + 16, y + 16, '动图 · 背景每帧都在变', RED, fg=(255, 255, 255))
    else: tag(fr, x + 16, y + 16, '透明 PNG · 只留主体', ACC)
    if p >= 1:
        for j, (a, b) in enumerate([(0.22, 0.2), (0.78, 0.28), (0.28, 0.78), (0.72, 0.82), (0.5, 0.08)]):
            r = 6 + 10 * math.sin(lt * 6 + j * 1.7)
            if r > 3: star(d, x + w * a, y + h * b, r, (255, 220, 90))
    if lt < T + 0.1: pop_text(fr, '会动的画面，想抠出主体？', W / 2, 80, 52, lt)
    else: pop_text(fr, '一键变成透明 PNG', W / 2, 80, 62, lt, fill=ACC, delay=T + 0.1)

def sc_pain(fr, lt, sd):
    pop_text(fr, '手动抠？每一帧都不一样', W / 2, 82, 50, lt)
    for i in range(4):
        tl = lt - 0.25 - i * 0.3
        if tl < 0: continue
        e = eback(tl / 0.4); im = POLR[i]
        cx = 230 + 273 * i; cy = 360 + 200 * (1 - e)
        paste_a(fr, im, (cx - im.width / 2, cy - im.height / 2), ease(tl / 0.25))
    ts = sd * 0.55
    if lt > ts:
        tl = lt - ts; sc = 1 + 1.2 * (1 - ease(tl / 0.25))
        im = STAMP.resize((int(STAMP.width * sc), int(STAMP.height * sc)), Image.BILINEAR)
        sh = int(8 * math.sin(tl * 60) * (1 - clamp(tl / 0.4)))
        paste_a(fr, im, (640 - im.width / 2 + sh, 370 - im.height / 2), ease(tl / 0.15))

def sc_principle(fr, lt, sd):
    header(fr, lt, '原理', '不动的留下，会动的变透明')
    d = ImageDraw.Draw(fr)
    d.rectangle([90, 122, 1190, 248], fill=(6, 6, 12))
    for x in range(100, 1185, 30):
        d.rectangle([x, 127, x + 14, 136], fill=(70, 70, 95)); d.rectangle([x, 234, x + 14, 243], fill=(70, 70, 95))
    for i in range(5):
        tl = lt - 0.1 - i * 0.12
        if tl < 0: continue
        x = 200 + 220 * i + 400 * (1 - ease(tl / 0.35))
        fr.paste(THUMBS[i], (int(x - 82), 130))
        txt(d, (x, 185), '帧 %d' % (i + 1), 18, fill=YEL, anchor='mm')
    t1 = 1.0
    k = int(clamp((lt - t1) / max(0.5, sd - t1 - 1.6)) * (NCAP - 1))
    a = ease((lt - t1 + 0.3) / 0.4)
    if a > 0:
        lx, ly = panel(fr, cap_compare(k).resize((360, 240), Image.BILINEAR), 400, 442, 360, 240, border=RED, a=a)
        rx, ry = panel(fr, cap_result(k).resize((360, 240), Image.NEAREST), 880, 442, 360, 240, border=ACC, a=a)
        d = ImageDraw.Draw(fr)
        sy = ly + int((lt * 1.3 % 1) * 240); d.line([(lx, sy), (lx + 360, sy)], fill=(255, 255, 255), width=3)
        ax = 596 + 10 * math.sin(lt * 6)
        d.polygon([(ax, 427), (ax + 40, 427), (ax + 40, 410), (ax + 72, 442), (ax + 40, 474), (ax + 40, 457), (ax, 457)], fill=YEL)
        tag(fr, lx, ly - 46, '红色 = 在变 → 变透明  %d/%d 帧' % (k + 1, NCAP), RED, a, sz=22, fg=(255, 255, 255))
        tag(fr, rx, ry - 46, '不动的主体 → 原样保留', GRN, a, sz=22)

# ---------------- 场景 4：模拟软件实操 ----------------
WIN = (150, 104, 1130, 568)
_wsh = Image.new('L', (WIN[2] - WIN[0] + 80, WIN[3] - WIN[1] + 80), 0)
ImageDraw.Draw(_wsh).rounded_rectangle([40, 50, WIN[2] - WIN[0] + 40, WIN[3] - WIN[1] + 50], 18, fill=170)
WSH = _wsh.filter(ImageFilter.GaussianBlur(20))

def sc_live(fr, lt, sd):
    header(fr, lt, '实操', '框选 → 动态截图 → 背景自动消失')
    x0, y0, x1, y1 = WIN
    fr.paste((0, 0, 0), (x0 - 40, y0 - 40), WSH)
    d = ImageDraw.Draw(fr)
    d.rounded_rectangle([x0, y0, x1, y1], 16, fill=(246, 247, 250))
    d.rounded_rectangle([x0, y0, x1, y0 + 44], 16, fill=(228, 231, 238)); d.rectangle([x0, y0 + 28, x1, y0 + 44], fill=(228, 231, 238))
    for j, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]): d.ellipse([x0 + 18 + j * 24, y0 + 15, x0 + 32 + j * 24, y0 + 29], fill=c)
    ic = icon(26); fr.paste(ic, (x0 + 100, y0 + 9), ic)
    d.text((x0 + 134, y0 + 22), '透明模板制作', font=F(20), fill=DARK, anchor='lm')
    sx, sy, sw, shh = x0 + 30, y0 + 90, 420, 280
    d.text((sx, sy - 26), '实时画面（动图）', font=F(20), fill=DARK, anchor='lm')
    fr.paste(demo_frame(lt).resize((sw, shh), Image.BILINEAR), (sx, sy))
    tb = ease(lt / 0.9)
    box = (sx + 30, sy + 10, sx + 30 + (sw - 60) * tb, sy + 10 + (shh - 20) * tb)
    if tb > 0.02: dashed(d, box, (255, 214, 80), int(lt * 40) % 20, w=4)
    px, py, pw, ph = x0 + 510, y0 + 90, 420, 280
    d.text((px, py - 26), '实时预览（透明结果）', font=F(20), fill=DARK, anchor='lm')
    ax = x0 + 462 + 6 * math.sin(lt * 6)
    d.polygon([(ax, sy + 125), (ax + 18, sy + 125), (ax + 18, sy + 112), (ax + 36, sy + 140), (ax + 18, sy + 168), (ax + 18, sy + 155), (ax, sy + 155)], fill=(255, 170, 40))
    tc = 1.4
    k = int(clamp((lt - tc) / max(0.5, sd - tc - 1.5)) * (NCAP - 1)) if lt > tc else -1
    if k < 0:
        fr.paste(Image.fromarray(CHK).resize((pw, ph), Image.NEAREST), (px, py))
        d.text((px + pw / 2, py + ph / 2), '等待开始…', font=F(26), fill=(120, 125, 140), anchor='mm')
    else:
        fr.paste(cap_result(k).resize((pw, ph), Image.NEAREST), (px, py))
    d.rectangle([px - 1, py - 1, px + pw, py + ph], outline=ACC, width=3)
    bx, by, bw, bh = sx, y1 - 74, 210, 52
    rec = lt > tc
    d.rounded_rectangle([bx, by, bx + bw, by + bh], 12, fill=RED if rec else ACC)
    d.text((bx + bw / 2, by + bh / 2), '停止生成' if rec else '动态截图', font=F(24), fill=(255, 255, 255) if rec else DARK, anchor='mm')
    if rec:
        if math.sin(lt * 8) > 0: d.ellipse([bx + bw + 14, by + 18, bx + bw + 30, by + 34], fill=RED)
        kk = max(k, 0)
        d.text((bx + bw + 38, by + bh / 2), '已采集 %d 帧' % (kk + 1), font=F(22), fill=DARK, anchor='lm')
        gx, gw = px, pw
        d.rounded_rectangle([gx, by + 14, gx + gw, by + 38], 12, fill=(220, 224, 232))
        d.rounded_rectangle([gx, by + 14, gx + max(24, int(gw * PCT[kk] / 100)), by + 38], 12, fill=GRN)
        d.text((gx + gw / 2, by + 26), '背景已透明 %d%%' % PCT[kk], font=F(18), fill=DARK, anchor='mm')
    bxc, byc = bx + bw / 2, by + bh / 2
    if lt < 0.9: cx, cy = box[2], box[3]
    else:
        e = ease((lt - 0.9) / 0.45); cx = box[2] + (bxc - box[2]) * e; cy = box[3] + (byc - box[3]) * e
    if tc <= lt < tc + 0.45:
        r = 10 + 60 * (lt - tc); d.ellipse([bxc - r, byc - r, bxc + r, byc + r], outline=YEL, width=4)
    cursor(d, cx, cy)
    if k >= NCAP - 1:
        tl = lt - (tc + max(0.5, sd - tc - 1.5))
        pop_text(fr, '主体自己浮出来了！', px + pw / 2, py + ph - 30, 34, tl, fill=YEL)

# ---------------- 场景 5-7 + 渲染 ----------------
def sc_proof(fr, lt, sd):
    header(fr, lt, '成品', '一张透明 PNG，放哪都干净')
    labels = ['透明底 PNG', '放进海报', '放进 PPT']
    for i in range(3):
        tl = lt - 0.2 - i * 0.35
        if tl < 0: continue
        bg = BGS[i].copy()
        e = eback(clamp((tl - 0.25) / 0.5))
        y = int(-RB.height + (40 + RB.height) * e)
        bg.paste(RB, (int(180 - RB.width / 2), y), RB)
        cx = 230 + 410 * i
        x, yy = panel(fr, bg, cx, 330, 360, 240, border=ACC, a=ease(tl / 0.25))
        if tl > 0.3:
            f = F(24); tw = f.getlength(labels[i]) + 32
            tag(fr, cx - tw / 2, yy + 258, labels[i], ACC)

VW, VH = 330, 220
def tip_vis(i, tl):
    if i == 0:
        im = demo_frame(tl).resize((VW, VH), Image.BILINEAR); d = ImageDraw.Draw(im)
        sx, sy = VW / DW, VH / DH
        e = ease((tl - 0.5) / 0.6)
        full = (8, 8, VW - 8, VH - 8); tight = (SBOX[0] * sx - 6, SBOX[1] * sy - 6, SBOX[2] * sx + 6, SBOX[3] * sy + 6)
        box = [full[j] + (tight[j] - full[j]) * e for j in range(4)]
        dashed(d, box, GRN if e >= 1 else RED, int(tl * 40) % 20, w=4)
    elif i == 1:
        k = int(clamp(tl / 1.6) * (NCAP - 1)); im = cap_result(k).resize((VW, VH), Image.NEAREST); d = ImageDraw.Draw(im)
        d.rounded_rectangle([8, 8, 190, 40], 10, fill=DARK); d.text((99, 24), '%d 帧 · 透明 %d%%' % (k + 1, PCT[k]), font=F(17), fill=YEL, anchor='mm')
    else:
        click = 0.9
        im = (cap_result(5) if tl < click else CLEAN).resize((VW, VH), Image.NEAREST); d = ImageDraw.Draw(im)
        cx, cy = 50 + 20 * ease(tl / 0.8), 175 - 30 * ease(tl / 0.8)
        if click <= tl < click + 0.4:
            r = 8 + 70 * (tl - click); d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=YEL, width=3)
        star(d, cx - 6, cy - 6, 12, YEL); cursor(d, cx, cy)
    return im

def sc_tips(fr, lt, sd):
    pop_text(fr, '3 个小技巧，少走弯路', W / 2, 78, 50, lt, fill=YEL)
    span = (sd - 1.2) / 3
    items = [('框选贴近主体', '干扰更少，结果更干净'), ('背景动得多更好', '多攒几帧，透明更彻底'), ('杂点魔术棒一点清', '反选透明，边缘利落')]
    for i, (t1, t2) in enumerate(items):
        tl = lt - 0.3 - i * span
        if tl < 0: continue
        cw, ch = 370, 360
        card = Image.new('RGBA', (cw, ch), (0, 0, 0, 0)); dc = ImageDraw.Draw(card)
        dc.rounded_rectangle([0, 0, cw - 1, ch - 1], 22, fill=(26, 30, 62, 240), outline=ACC + (255,), width=3)
        dc.ellipse([18, 18, 62, 62], fill=YEL); dc.text((40, 40), str(i + 1), font=F(28), fill=DARK, anchor='mm')
        dc.text((76, 40), t1, font=F(28), fill=INK, anchor='lm')
        card.paste(tip_vis(i, tl), (20, 80))
        dc.text((cw / 2, 330), t2, font=F(22, False), fill=DIM, anchor='mm')
        sc = 0.8 + 0.2 * eback(tl / 0.4)
        c2 = card.resize((int(cw * sc), int(ch * sc)), Image.BILINEAR)
        cx = 230 + 410 * i
        paste_a(fr, c2, (cx - c2.width / 2, 340 - c2.height / 2), ease(tl / 0.25))

def sc_cta(fr, lt, sd):
    fr.paste(RING, (W // 2 - 130, 170 - 130), RING)
    e = eback(lt / 0.6); sz = max(8, int(150 * e)); ic = icon(sz)
    fr.paste(ic, (int(W / 2 - sz / 2), int(170 - sz / 2)), ic)
    for j, xx in enumerate([110, W - 110 - RB.width]):
        tl = lt - 0.5 - j * 0.2
        if tl > 0:
            yb = 330 - abs(math.sin(lt * 4 + j)) * 30 + 200 * (1 - ease(tl / 0.4))
            fr.paste(RB, (int(xx), int(yb)), RB)
    pop_text(fr, '透明模板制作', W / 2, 315, 66, lt, fill=ACC, delay=0.3)
    pop_text(fr, '动图 → 透明 PNG · 双击即用 · 免安装', W / 2, 390, 28, lt, delay=0.6)
    b = ease((lt - 0.9) / 0.4)
    if b > 0:
        p = 1 + 0.05 * math.sin(lt * 5); bw, bh = int(340 * p), int(78 * p)
        btn = Image.new('RGBA', (bw + 40, bh + 40), (0, 0, 0, 0)); db = ImageDraw.Draw(btn)
        db.rounded_rectangle([20, 20, 20 + bw, 20 + bh], radius=bh // 2, fill=YEL + (255,))
        db.text((20 + bw / 2, 20 + bh / 2), '立即试用 →', font=F(36), fill=DARK, anchor='mm')
        paste_a(fr, btn, (W / 2 - btn.width / 2, 480 - btn.height / 2), b)

FUN = dict(hook=sc_hook, pain=sc_pain, principle=sc_principle, live=sc_live, proof=sc_proof, tips=sc_tips, cta=sc_cta)

def render_frame(t):
    i = 0
    while i + 1 < len(SCENES) and t >= SCENES[i + 1]['start']: i += 1
    s = SCENES[i]; lt = t - s['start']
    fr = background(t)
    FUN[s['k']](fr, lt, s['dur'])
    for fh in FLASH:
        x = t - fh
        if 0 <= x < 0.22: fr = Image.blend(fr, WHITE, 0.55 * (1 - x / 0.22))
    d = ImageDraw.Draw(fr)
    ic = icon(30); fr.paste(ic, (W - 210, 14), ic)
    d.text((W - 172, 29), '透明模板制作', font=F(20), fill=DIM, anchor='lm')
    d.rectangle([0, 0, int(W * t / TOTAL), 4], fill=ACC)
    subtitle(fr, s['v'], lt - LEAD, s['vd'])
    if t < 0.3: fr = Image.blend(Image.new('RGB', (W, H)), fr, clamp(t / 0.3))
    if t > TOTAL - 0.6: fr = Image.blend(fr, Image.new('RGB', (W, H)), clamp((t - (TOTAL - 0.6)) / 0.6))
    return fr

def unique(p):
    b, ext = os.path.splitext(p); i = 2
    while os.path.exists(p):
        p = '%s_%d%s' % (b, i, ext); i += 1
    return p

if __name__ == '__main__':
    out = unique(os.path.join(OUTDIR, '透明图制作_推广v3_16x9.mp4'))
    cmd = ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H), '-r', str(FPS), '-i', '-', '-i', audio, '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-shortest', out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(NF):
        proc.stdin.write(np.asarray(render_frame(f / FPS), dtype=np.uint8).tobytes())
        if f % 300 == 0: print('  %d/%d' % (f, NF), flush=True)
    proc.stdin.close(); proc.wait()
    prev = os.path.join(TMP, 'preview'); os.makedirs(prev, exist_ok=True)
    for i, s in enumerate(SCENES):
        render_frame(s['start'] + s['dur'] * 0.75).save(os.path.join(prev, '%02d_%s.png' % (i, s['k'])))
    cover = unique(os.path.join(OUTDIR, '透明图制作_推广v3_封面.png'))
    render_frame(SCENES[0]['start'] + hook_T(SCENES[0]['dur']) + 1.0).save(cover)
    srt = unique(os.path.join(OUTDIR, '透明图制作_推广v3.srt'))
    def ts(x):
        ms = int(round(x * 1000))
        return '%02d:%02d:%02d,%03d' % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)
    with open(srt, 'w', encoding='utf-8') as fh:
        for i, s in enumerate(SCENES):
            a0 = s['start'] + LEAD
            fh.write(str(i + 1) + NL + ts(a0) + ' --> ' + ts(a0 + s['vd']) + NL + s['v'] + NL + NL)
    print('OUT', out); print('COVER', cover); print('SRT', srt)
