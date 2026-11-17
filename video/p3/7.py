
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
