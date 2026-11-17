
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
