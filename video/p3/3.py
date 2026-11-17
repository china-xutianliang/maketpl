
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
