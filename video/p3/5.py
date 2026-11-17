
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
