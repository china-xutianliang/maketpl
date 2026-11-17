# -*- coding: utf-8 -*-
# 推广视频 v2（通用版）：动态画面 -> 透明 PNG。不涉及任何游戏/脚本内容。
# 16:9 720p 30fps；AI 配音 + 合成 BGM + 逐字字幕。用法：python video/promo2.py -> 项目/output/
import asyncio, math, os, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UI = os.path.join(HERE, 'assets', 'ui')
OUTDIR = os.path.join(ROOT, 'output')
TMP = os.path.join(OUTDIR, '_promo2_tmp')
os.makedirs(TMP, exist_ok=True)
W, H, FPS = 1280, 720, 30
VOICE, RATE = 'zh-CN-YunxiNeural', '+6%'
LEAD, TAIL = 0.30, 0.45
NL = chr(10)

SCENES = [
    dict(k='hook', extra=0.3, v='想从一段会动的画面里，抠出一张干净的透明图？一帧帧手动擦，又慢又容易留残影。'),
    dict(k='reveal', extra=0.3, v='试试透明模板制作。盯住同一块画面连拍多帧，会动的自动变透明，不动的原样保留。'),
    dict(k='principle', extra=0.5, v='原理很简单：每个像素对比多帧，一直不变的留下，走过的人、飞过的鸟、闪烁的光，全部挖成透明。'),
    dict(k='step1', extra=0.2, v='用法只要三步。第一步，选好要抓的窗口，或者直接载入图片，框出你要的区域。'),
    dict(k='step2', extra=0.2, v='第二步，点动态截图，它实时盯着画面，动的像素自动去掉，右侧随时预览，满意就停止。'),
    dict(k='step3', extra=0.3, v='第三步，修图收尾。魔术棒点一下颜色，反选透明，再去掉杂点，主体干干净净。'),
    dict(k='result', extra=0.8, v='最后保存，得到带透明通道的 PNG，自动裁掉空边，拿去就能用。'),
    dict(k='tips', extra=1.2, v='新手少走弯路，记住四条：框选越小越干净，动得多就多攒几帧，用魔术棒和去杂点收尾，一定保存成 PNG。'),
    dict(k='cta', extra=1.8, v='透明模板制作，双击 exe 就能用。动态画面抠透明图，一步到位，赶紧试试吧！'),
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
    asyncio.run(tts_all())
    HAS_VOICE = True
except Exception as e:
    print('TTS failed, music only:', e)
    HAS_VOICE = False
    for s in SCENES:
        s['mp3'], s['vd'] = None, len(s['v']) * 0.21

t = 0.0
for s in SCENES:
    s['start'] = t
    s['dur'] = LEAD + s['vd'] + TAIL + s['extra']
    t += s['dur']
TOTAL = t
NF = int(math.ceil(TOTAL * FPS))
print('total %.1fs, %d frames, voice=%s' % (TOTAL, NF, HAS_VOICE))

def make_music(total, path, sr=44100):
    n = int((total + 1) * sr); ta = np.arange(n) / sr; out = np.zeros(n)
    chords = [[220, 261.63, 329.63], [174.61, 220, 261.63], [261.63, 329.63, 392], [196, 246.94, 293.66]]
    bar = 2.4
    for k in range(int(total / bar) + 2):
        s0 = int(k * bar * sr)
        if s0 >= n: break
        e0 = min(n, int((k + 1) * bar * sr) + int(0.4 * sr))
        tt = ta[s0:e0] - k * bar
        env = np.minimum(1, tt / 0.35) * np.exp(-tt * 0.45)
        ch = chords[k % 4]
        for fq in ch:
            out[s0:e0] += 0.05 * env * (np.sin(2 * np.pi * fq * tt) + 0.25 * np.sin(4 * np.pi * fq * tt))
        out[s0:e0] += 0.08 * env * np.sin(np.pi * ch[0] * tt)
        for j in range(8):
            ps = s0 + int(j * bar / 8 * sr)
            if ps >= n: break
            pe = min(n, ps + int(0.4 * sr)); pt = ta[ps:pe] - ta[ps]
            out[ps:pe] += 0.03 * np.exp(-pt * 8) * np.sin(4 * np.pi * ch[j % 3] * pt)
        for j in range(4):
            ps = s0 + int(j * bar / 4 * sr)
            if ps >= n: break
            pe = min(n, ps + int(0.12 * sr)); pt = ta[ps:pe] - ta[ps]
            out[ps:pe] += 0.10 * np.exp(-pt * 35) * np.sin(2 * np.pi * (90 - 200 * pt) * pt)
    fi, fo, end = int(1.0 * sr), int(2.5 * sr), int(total * sr)
    out[:fi] *= np.linspace(0, 1, fi)
    out[end - fo:end] *= np.linspace(1, 0, fo); out[end:] = 0
    out = out / (np.abs(out).max() + 1e-9) * 0.8
    pcm = (np.stack([out, out], 1) * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

music = os.path.join(TMP, 'music.wav')
make_music(TOTAL, music)
audio = os.path.join(TMP, 'audio.wav')
cmd = ['ffmpeg', '-y', '-v', 'error', '-i', music]
fc, mix = '[0:a]volume=0.30[m];', '[m]'
if HAS_VOICE:
    for i, s in enumerate(SCENES):
        cmd += ['-i', s['mp3']]
        ms = int((s['start'] + LEAD) * 1000)
        fc += '[%d:a]aresample=44100,aformat=channel_layouts=stereo,adelay=%d|%d,volume=1.6[v%d];' % (i + 1, ms, ms, i)
        mix += '[v%d]' % i
n_in = len(SCENES) + 1 if HAS_VOICE else 1
fc += mix + 'amix=inputs=%d:normalize=0:duration=longest,alimiter=limit=0.95[a]' % n_in
cmd += ['-filter_complex', fc, '-map', '[a]', '-t', '%.3f' % TOTAL, audio]
subprocess.run(cmd, check=True)

FB, FR = 'C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'
_fc = {}
def F(sz, b=True):
    k = (sz, b)
    if k not in _fc: _fc[k] = ImageFont.truetype(FB if b else FR, sz)
    return _fc[k]

INK, DIM = (240, 244, 255), (165, 175, 205)
ACC, YEL, RED, GRN = (90, 220, 190), (255, 214, 80), (255, 92, 92), (100, 225, 120)
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

BG = vgrad(W, H, (10, 12, 30), (30, 16, 54))
_d = ImageDraw.Draw(BG)
for y in range(0, H, 40):
    for x in range(0, W, 40):
        _d.point((x, y), fill=(45, 50, 85))
G1, G2 = glow(300, (50, 190, 170)), glow(340, (120, 70, 255))
RING1, RING2 = glow(110, ACC, 90), {}

def background(t):
    fr = BG.copy()
    fr.paste(G1, (int(-220 + 140 * math.sin(t * 0.25)), int(-200 + 90 * math.cos(t * 0.31))), G1)
    fr.paste(G2, (int(W - 480 + 120 * math.cos(t * 0.21)), int(H - 520 + 100 * math.sin(t * 0.27))), G2)
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

def pill(fr, cx, cy, s, a=1.0, scale=1.0, sz=28, fg=INK, bg=(18, 22, 46, 230), border=ACC):
    f = F(sz); pw, ph = int(f.getlength(s) + 48), sz + 24
    im = Image.new('RGBA', (pw + 4, ph + 4), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([2, 2, pw + 1, ph + 1], radius=ph // 2, fill=bg, outline=border, width=2)
    d.text((pw / 2 + 2, ph / 2 + 2), s, font=f, fill=fg, anchor='mm')
    if scale != 1.0:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    paste_a(fr, im, (cx - im.width / 2, cy - im.height / 2), a)

def checker(w, h, s=18):
    im = Image.new('RGB', (w, h), (58, 60, 78)); d = ImageDraw.Draw(im)
    for y in range(0, h, s):
        for x in range(0, w, s):
            if (x // s + y // s) % 2: d.rectangle([x, y, x + s - 1, y + s - 1], fill=(88, 92, 116))
    return im

def icon_mark(d, cx, cy, r, ok):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GRN if ok else RED)
    w = max(3, r // 4)
    if ok:
        d.line([(cx - r * .5, cy), (cx - r * .12, cy + r * .4), (cx + r * .52, cy - r * .38)], fill=DARK, width=w, joint='curve')
    else:
        k = r * .42
        d.line([(cx - k, cy - k), (cx + k, cy + k)], fill='white', width=w)
        d.line([(cx - k, cy + k), (cx + k, cy - k)], fill='white', width=w)

_ui = {}
def ui(name):
    if name not in _ui:
        im = Image.open(os.path.join(UI, name)).convert('RGB')
        a = np.asarray(im).astype(np.int16).copy()
        h, w = a.shape[:2]
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        m = (r > g + 50) & (r > b + 50)
        m[int(h * 0.36):, :] = False; m[:, int(w * 0.5):] = False; m[:, :int(w * 0.075)] = False
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
        a[m] = (255, 255, 255)
        a[int(h * 0.15):int(h * 0.30), int(w * 0.09):int(w * 0.36)] = (255, 255, 255)
        im2 = Image.fromarray(a.astype(np.uint8)); d2 = ImageDraw.Draw(im2)
        d2.text((int(w * 0.095), int(h * 0.205)), '● 已绑定目标窗口', font=F(max(10, int(w * 0.016))), fill=(60, 120, 90), anchor='lm')
        _ui[name] = im2
    return _ui[name]

ICON = Image.open(os.path.join(ROOT, 'icon.png')).convert('RGBA')
_icons = {}
def icon(sz):
    if sz not in _icons: _icons[sz] = ICON.resize((sz, sz), Image.LANCZOS)
    return _icons[sz]

_sh = {}
def shot(fr, img, box, lt, a=1.0, zoom=0.05, sd=5.0):
    bx0, by0, bx1, by1 = box; bw, bh = bx1 - bx0, by1 - by0
    s = min(bw / img.width, bh / img.height) * (0.93 + 0.07 * eback(lt / 0.55))
    w, h = int(img.width * s), int(img.height * s)
    z = 1 + zoom * clamp(lt / sd)
    cw, chh = img.width / z, img.height / z
    cx, cy = img.width / 2, img.height / 2
    crop = img.crop((int(cx - cw / 2), int(cy - chh / 2), int(cx + cw / 2), int(cy + chh / 2))).resize((w, h), Image.BILINEAR)
    x, y = bx0 + (bw - w) // 2, by0 + (bh - h) // 2
    if (w, h) not in _sh:
        sh = Image.new('L', (w + 60, h + 60), 0)
        ImageDraw.Draw(sh).rounded_rectangle([30, 36, w + 30, h + 36], 16, fill=170)
        m = Image.new('L', (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], 14, fill=255)
        _sh[(w, h)] = (sh.filter(ImageFilter.GaussianBlur(16)), m)
    sh, m = _sh[(w, h)]
    if a < 1:
        sh = sh.point(lambda v: int(v * a)); m = m.point(lambda v: int(v * a))
    fr.paste((0, 0, 0), (x - 30, y - 30), sh)
    fr.paste(crop, (x, y), m)
    if a > 0.98:
        ImageDraw.Draw(fr).rounded_rectangle([x - 1, y - 1, x + w, y + h], 14, outline=ACC, width=2)

def header(fr, lt, badge, title):
    e = ease(lt / 0.5); dx = -380 * (1 - e)
    d = ImageDraw.Draw(fr)
    f = F(26); bw = f.getlength(badge) + 36
    d.rounded_rectangle([50 + dx, 34, 50 + dx + bw, 80], radius=23, fill=ACC)
    d.text((50 + dx + bw / 2, 57), badge, font=f, fill=DARK, anchor='mm')
    txt(d, (70 + dx + bw, 57), title, 38, anchor='lm')

def wrap(s, f, maxw):
    lines, cur = [], ''
    for c in s:
        if f.getlength(cur + c) > maxw and cur and c not in '。，！？、：；）」':
            lines.append(cur); cur = c
        else:
            cur += c
    if cur: lines.append(cur)
    return lines

def subtitle(fr, s, vt, vd):
    if vt < -0.1 or vt > vd + TAIL: return
    f = F(32); lines = wrap(s, f, 1120)
    total = sum(len(l) for l in lines)
    said = int(clamp(vt / max(vd, 0.1)) * total + 0.5)
    lh = 46; top = H - 26 - lh * len(lines)
    maxw = max(f.getlength(l) for l in lines)
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle([W / 2 - maxw / 2 - 24, top - 10, W / 2 + maxw / 2 + 24, top + lh * len(lines) + 6], 14, fill=(0, 0, 0, 150))
    fr.paste(lay, (0, 0), lay)
    d = ImageDraw.Draw(fr); k = 0
    for i, l in enumerate(lines):
        x = W / 2 - f.getlength(l) / 2; y = top + i * lh
        for c in l:
            d.text((x + 2, y + 2), c, font=f, fill=(0, 0, 0))
            d.text((x, y), c, font=f, fill=YEL if k < said else INK)
            x += f.getlength(c); k += 1

# ---------- 演示用动图：静态风景 + 走过的人 + 飞过的鸟 + 闪烁的光 ----------
SW, SH = 420, 270
def make_static():
    im = vgrad(SW, SH, (95, 160, 225), (195, 222, 240)); d = ImageDraw.Draw(im)
    d.ellipse([20, 18, 70, 68], fill=(255, 236, 150))
    d.rectangle([0, 195, SW, SH], fill=(86, 146, 78))
    d.rectangle([40, 112, 140, 195], fill=(186, 124, 82)); d.polygon([(30, 115), (90, 70), (150, 115)], fill=(150, 60, 50))
    d.rectangle([78, 150, 102, 195], fill=(90, 56, 40)); d.rectangle([110, 130, 130, 150], fill=(200, 230, 250))
    d.rectangle([355, 120, 368, 195], fill=(110, 75, 45)); d.ellipse([325, 70, 400, 140], fill=(50, 130, 60))
    d.rectangle([286, 110, 290, 195], fill=(70, 70, 80)); d.ellipse([278, 98, 298, 116], fill=(255, 230, 140))
    return im
STATIC = make_static()
CHK = checker(SW, SH)

def walk_x(lt): return 30 + (SW - 60) * ((lt / 3.4) % 1.0)
def bird_x(lt): return SW - 30 - (SW - 60) * ((lt / 2.6) % 1.0)
def sim_frame(lt):
    im = STATIC.copy(); d = ImageDraw.Draw(im)
    bx = walk_x(lt)
    d.ellipse([bx - 20, 182, bx + 20, 230], fill=(230, 60, 70)); d.ellipse([bx - 13, 160, bx + 13, 186], fill=(250, 210, 160))
    by = bird_x(lt); wy = 6 * math.sin(lt * 18)
    d.line([(by - 16, 40 - wy), (by, 48), (by + 16, 40 - wy)], fill=(40, 40, 60), width=4)
    if math.sin(lt * 14) > -0.2:
        cx, cy, r = 215, 120, 16 + 5 * math.sin(lt * 9)
        d.polygon([(cx, cy - r), (cx + r * .3, cy - r * .3), (cx + r, cy), (cx + r * .3, cy + r * .3), (cx, cy + r), (cx - r * .3, cy + r * .3), (cx - r, cy), (cx - r * .3, cy - r * .3)], fill=(255, 250, 160))
    return im

def sim_mask(lt, full=False):
    m = Image.new('L', (SW, SH), 255); d = ImageDraw.Draw(m)
    xr = SW - 6 if full or lt >= 3.4 else walk_x(lt) + 24
    d.rounded_rectangle([6, 156, xr, 234], 24, fill=0)
    xl = 6 if full or lt >= 2.6 else bird_x(lt) - 20
    d.rounded_rectangle([xl, 26, SW - 6, 58], 14, fill=0)
    if full or lt > 0.25: d.ellipse([193, 98, 237, 142], fill=0)
    return m

def sim_result(lt, full=False):
    res = CHK.copy(); res.paste(STATIC, (0, 0), sim_mask(lt, full))
    return res

BOX = (110, 104, 1170, 588)

def sc_hook(fr, lt, sd):
    d = ImageDraw.Draw(fr)
    e = eback(lt / 0.6)
    s = '想从动态画面里抠出透明图？'
    tw = F(58).getlength(s); x = W / 2 - tw / 2
    txt(d, (W / 2, 160 - 40 * (1 - e)), s, 58, anchor='mm')
    d.rectangle([x, 200, x + tw * ease(lt / 0.8), 206], fill=RED)
    items = ['画面一直在动，这帧抠完下帧又变', '手动一帧帧擦，费时又费眼', '残影、杂点，边缘怎么也清不干净']
    for i, s2 in enumerate(items):
        tl = lt - (0.9 + i * 0.9)
        if tl < 0: continue
        e2 = ease(tl / 0.45); y = 290 + i * 95; x0 = 300 + 200 * (1 - e2)
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
        dl.rounded_rectangle([x0 - 50, y - 40, x0 + 700, y + 40], 20, fill=(40, 20, 40, 200), outline=(255, 92, 92, 160), width=2)
        icon_mark(dl, x0, y, 22, False)
        dl.text((x0 + 44, y), s2, font=F(34), fill=INK, anchor='lm')
        paste_a(fr, lay, (0, 0), e2)

def sc_reveal(fr, lt, sd):
    e = eback(lt / 0.7); sz = max(8, int(170 * e))
    pr = int(120 + 20 * math.sin(lt * 4))
    if pr not in RING2: RING2[pr] = glow(pr, ACC, 110)
    ring = RING2[pr]; fr.paste(ring, (W // 2 - pr, 220 - pr), ring)
    ic = icon(sz); fr.paste(ic, (int(W / 2 - sz / 2), int(220 - sz / 2)), ic)
    a = ease((lt - 0.4) / 0.5)
    if a > 0:
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
        dl.text((W / 2 + 3, 383), '透明模板制作', font=F(66), fill=(0, 0, 0), anchor='mm')
        dl.text((W / 2, 380), '透明模板制作', font=F(66), fill=ACC, anchor='mm')
        dl.text((W / 2, 452), '动态画面 → 透明 PNG，会动的自动抠掉', font=F(30, False), fill=DIM, anchor='mm')
        paste_a(fr, lay, (0, 30 * (1 - a)), a)
    for i, c in enumerate(['连拍多帧', '逐像素比对', '动的自动透明']):
        tl = lt - (1.6 + i * 0.5)
        if tl > 0: pill(fr, 360 + i * 280, 535, c, a=ease(tl / 0.3), scale=0.8 + 0.2 * eback(tl / 0.4))

def sc_principle(fr, lt, sd):
    d = ImageDraw.Draw(fr)
    header(fr, lt, '原理', '不变的留下，会动的挖掉')
    lx, rx, y0 = 120, 740, 200
    for back in [3, 2, 1]:
        g = sim_frame(max(0, lt - back * 0.25)).point(lambda v: int(v * 0.45))
        fr.paste(g, (lx - back * 10, y0 - back * 10))
    fr.paste(sim_frame(lt), (lx, y0))
    d.rectangle([lx - 1, y0 - 1, lx + SW, y0 + SH], outline=INK, width=2)
    n = min(30, int(lt * 9) + 1)
    txt(d, (lx + SW / 2 - 15, y0 - 52), '动态画面 · 第 %d 帧' % n, 28, anchor='mm')
    fr.paste(sim_result(lt), (rx, y0))
    d.rectangle([rx - 1, y0 - 1, rx + SW, y0 + SH], outline=ACC, width=3)
    txt(d, (rx + SW / 2, y0 - 52), '输出：透明 PNG', 28, fill=ACC, anchor='mm')
    ax = 562 + 18 * math.sin(lt * 5)
    d.polygon([(ax, 320), (ax + 120, 320), (ax + 120, 304), (ax + 160, 335), (ax + 120, 366), (ax + 120, 350), (ax, 350)], fill=YEL)
    txt(d, (642, 395), '逐像素比对', 24, fill=YEL, anchor='mm')
    a = ease((lt - 1.5) / 0.5)
    if a > 0:
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
        icon_mark(dl, 300, 525, 18, True); dl.text((330, 525), '多帧都不变 → 保留', font=F(30), fill=GRN, anchor='lm')
        icon_mark(dl, 720, 525, 18, False); dl.text((750, 525), '会动 / 会闪 → 透明', font=F(30), fill=RED, anchor='lm')
        paste_a(fr, lay, (0, 0), a)

def sc_step1(fr, lt, sd):
    t1 = sd * 0.45
    shot(fr, ui('02_bound_live.png'), BOX, lt, sd=sd)
    if lt > t1: shot(fr, ui('03_boxed.png'), BOX, lt - t1, a=ease((lt - t1) / 0.4), sd=sd)
    header(fr, lt, '第 1 步', '选窗口 / 载入图片，框选区域')
    pill(fr, W / 2, 560, '准星拖到窗口上松手即可' if lt < t1 else '按住拖动框选，方向键微调')

def sc_step2(fr, lt, sd):
    shot(fr, ui('04_dyn_monitoring.png'), BOX, lt, sd=sd, zoom=0.08)
    header(fr, lt, '第 2 步', '动态截图：动的像素自动去掉')
    d = ImageDraw.Draw(fr)
    if math.sin(lt * 6) > 0: d.ellipse([1086, 44, 1110, 68], fill=RED)
    txt(d, (1120, 56), '实时监测', 24, fill=RED, anchor='lm')
    pill(fr, W / 2, 560, '边看边抠 · 右侧实时预览 · 满意再停止')

def sc_step3(fr, lt, sd):
    for i, nm in enumerate(['05_edit_mode.png', '06_wand_selection.png', '09_inverted.png']):
        t0 = sd * 0.3 * i
        if lt >= t0: shot(fr, ui(nm), BOX, lt - t0, a=1.0 if i == 0 else ease((lt - t0) / 0.4), sd=sd)
    header(fr, lt, '第 3 步', '修图收尾，只留你要的主体')
    for i, c in enumerate(['魔术棒', '反选透明', '去杂点', '撤销随时退']):
        on = lt > 0.6 + i * (sd - 1.2) / 4
        pill(fr, 280 + i * 240, 560, c, sz=26, fg=DARK if on else DIM, bg=ACC + (255,) if on else (18, 22, 46, 220), border=ACC if on else (90, 100, 130))

RW, RH = 630, 405
def sc_result(fr, lt, sd):
    header(fr, lt, '成品', '带透明通道的 PNG')
    a = ease(lt / 0.4)
    x0, y0 = (W - RW) // 2, 112
    src = sim_frame(lt).resize((RW, RH), Image.BILINEAR)
    res = sim_result(0, full=True).resize((RW, RH), Image.NEAREST)
    p = 0.5 + 0.38 * math.sin(lt * 1.3 - 1.2)
    cut = int(RW * p)
    comp = res.copy(); comp.paste(src.crop((0, 0, cut, RH)), (0, 0))
    paste_a(fr, comp, (x0, y0), a)
    d = ImageDraw.Draw(fr)
    d.rectangle([x0 - 2, y0 - 2, x0 + RW + 1, y0 + RH + 1], outline=ACC, width=3)
    hx = x0 + cut
    d.line([(hx, y0), (hx, y0 + RH)], fill=INK, width=4)
    d.ellipse([hx - 18, y0 + RH / 2 - 18, hx + 18, y0 + RH / 2 + 18], fill=INK)
    d.polygon([(hx - 12, y0 + RH / 2), (hx - 4, y0 + RH / 2 - 7), (hx - 4, y0 + RH / 2 + 7)], fill=DARK)
    d.polygon([(hx + 12, y0 + RH / 2), (hx + 4, y0 + RH / 2 - 7), (hx + 4, y0 + RH / 2 + 7)], fill=DARK)
    txt(d, (x0 - 20, y0 + 30), '原画面', 28, anchor='rm')
    txt(d, (x0 + RW + 20, y0 + 30), '透明 PNG', 28, fill=ACC, anchor='lm')
    for i, c in enumerate(['Alpha 透明通道', '自动裁掉空边', '载入还能接着修']):
        tl = lt - (0.8 + i * 0.5)
        if tl > 0: pill(fr, 330 + i * 310, 562, c, a=ease(tl / 0.3), sz=26)

def sc_tips(fr, lt, sd):
    d = ImageDraw.Draw(fr)
    e = eback(lt / 0.5)
    txt(d, (W / 2, 120 - 30 * (1 - e)), '新手少走弯路 · 4 个要点', 52, fill=YEL, anchor='mm')
    cards = [('框选越小越干净', '只框需要的区域，干扰更少'), ('动得多就多攒几帧', '帧数越多，结果越稳'), ('魔术棒 + 去杂点收尾', '反选透明，清掉孤立碎块'), ('一定保存成 PNG', 'JPG / BMP 会丢掉透明')]
    span = (sd - 1.6) / 4
    for i, (t1, t2) in enumerate(cards):
        tl = lt - (0.6 + i * span)
        if tl < 0: continue
        a = ease(tl / 0.35); sc = 0.85 + 0.15 * eback(tl / 0.45)
        cw, chh = 540, 150
        card = Image.new('RGBA', (cw, chh), (0, 0, 0, 0)); dc = ImageDraw.Draw(card)
        dc.rounded_rectangle([0, 0, cw - 1, chh - 1], 20, fill=(28, 32, 66, 235), outline=ACC + (255,), width=2)
        icon_mark(dc, 52, 75, 26, True)
        dc.text((100, 52), '%d. %s' % (i + 1, t1), font=F(32), fill=INK, anchor='lm')
        dc.text((100, 104), t2, font=F(23, False), fill=DIM, anchor='lm')
        card = card.resize((int(cw * sc), int(chh * sc)), Image.BILINEAR)
        cx = 360 + (i % 2) * 570; cy = 260 + (i // 2) * 180
        paste_a(fr, card, (cx - card.width / 2, cy - card.height / 2), a)

def sc_cta(fr, lt, sd):
    d = ImageDraw.Draw(fr)
    e = eback(lt / 0.6); sz = max(8, int(140 * e))
    fr.paste(RING1, (W // 2 - 110, 60), RING1)
    ic = icon(sz); fr.paste(ic, (int(W / 2 - sz / 2), int(170 - sz / 2)), ic)
    a = ease((lt - 0.3) / 0.5)
    if a > 0:
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
        dl.text((W / 2 + 3, 313), '透明模板制作.exe', font=F(60), fill=(0, 0, 0), anchor='mm')
        dl.text((W / 2, 310), '透明模板制作.exe', font=F(60), fill=INK, anchor='mm')
        dl.text((W / 2, 378), '双击即用 · 无需安装 Python · 也能载入帧文件夹', font=F(28, False), fill=DIM, anchor='mm')
        paste_a(fr, lay, (0, 0), a)
    b = ease((lt - 0.9) / 0.4)
    if b > 0:
        p = 1 + 0.04 * math.sin(lt * 5)
        bw, bh = int(340 * p), int(78 * p)
        btn = Image.new('RGBA', (bw + 40, bh + 40), (0, 0, 0, 0)); db = ImageDraw.Draw(btn)
        db.rounded_rectangle([20, 20, 20 + bw, 20 + bh], radius=bh // 2, fill=ACC + (255,))
        db.text((20 + bw / 2, 20 + bh / 2), '立即试用 →', font=F(36), fill=DARK, anchor='mm')
        paste_a(fr, btn, (W / 2 - btn.width / 2, 465 - btn.height / 2), b)
        txt(d, (W / 2, 548), '动态画面抠透明图，一步到位', 30, fill=YEL, anchor='mm')

FUN = dict(hook=sc_hook, reveal=sc_reveal, principle=sc_principle, step1=sc_step1, step2=sc_step2, step3=sc_step3, result=sc_result, tips=sc_tips, cta=sc_cta)

def render_frame(t):
    i = 0
    while i + 1 < len(SCENES) and t >= SCENES[i + 1]['start']: i += 1
    s = SCENES[i]; lt = t - s['start']
    bgf = background(t); fr = bgf.copy()
    FUN[s['k']](fr, lt, s['dur'])
    if lt < 0.3: fr = Image.blend(bgf, fr, ease(lt / 0.3))
    d = ImageDraw.Draw(fr)
    ic = icon(30); fr.paste(ic, (W - 210, 14), ic)
    d.text((W - 172, 29), '透明模板制作', font=F(20), fill=DIM, anchor='lm')
    d.rectangle([0, 0, int(W * t / TOTAL), 4], fill=ACC)
    subtitle(fr, s['v'], lt - LEAD, s['vd'])
    if t > TOTAL - 0.6: fr = Image.blend(fr, Image.new('RGB', (W, H)), clamp((t - (TOTAL - 0.6)) / 0.6))
    return fr

def unique(p):
    b, ext = os.path.splitext(p); i = 2
    while os.path.exists(p):
        p = '%s_%d%s' % (b, i, ext); i += 1
    return p

if __name__ == '__main__':
    out = unique(os.path.join(OUTDIR, '透明图制作_通用推广_16x9.mp4'))
    cmd = ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H), '-r', str(FPS), '-i', '-', '-i', audio, '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-shortest', out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(NF):
        proc.stdin.write(np.asarray(render_frame(f / FPS), dtype=np.uint8).tobytes())
        if f % 300 == 0: print('  %d/%d' % (f, NF), flush=True)
    proc.stdin.close(); proc.wait()
    prev = os.path.join(TMP, 'preview')
    os.makedirs(prev, exist_ok=True)
    for i, s in enumerate(SCENES):
        render_frame(s['start'] + s['dur'] * 0.7).save(os.path.join(prev, '%02d_%s.png' % (i, s['k'])))
    cover = unique(os.path.join(OUTDIR, '透明图制作_通用推广_封面.png'))
    render_frame(SCENES[6]['start'] + 2.0).save(cover)
    srt = unique(os.path.join(OUTDIR, '透明图制作_通用推广.srt'))
    def ts(x):
        ms = int(round(x * 1000))
        return '%02d:%02d:%02d,%03d' % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)
    with open(srt, 'w', encoding='utf-8') as fh:
        for i, s in enumerate(SCENES):
            a0 = s['start'] + LEAD
            fh.write(str(i + 1) + NL + ts(a0) + ' --> ' + ts(a0 + s['vd']) + NL + s['v'] + NL + NL)
    print('OUT', out); print('COVER', cover); print('SRT', srt)
