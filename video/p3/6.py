
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
    d.text((bx + bw / 2, by + bh / 2), '■ 停止生成' if rec else '▶ 动态截图', font=F(24), fill=(255, 255, 255) if rec else DARK, anchor='mm')
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
