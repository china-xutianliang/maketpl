# -*- coding: utf-8 -*-
# 渲染管线：PIL 逐帧合成 → ffmpeg 编码。输出抖音 9:16 与 B站 16:9 两版 + 平台用演示 B-roll。
import json, math, os, subprocess, sys, wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out")
UI = os.path.join(HERE, "assets", "ui")
sys.path.insert(0, HERE)
from script import LINES, LINE_GAP

FPS = 30
timing = json.load(open(os.path.join(OUT, "timing.json"), encoding="utf-8"))
TRACKS, TOTAL = timing["tracks"], timing["total"]
NF = int(math.ceil(TOTAL * FPS))

FB, FB_D = "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"
_font_cache = {}
def font(sz, bold=True):
    key = (sz, bold)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FB if bold else FB_D, sz)
    return _font_cache[key]

# ---------- 配色 ----------
BG_TOP, BG_BOT = (16, 18, 38), (26, 20, 52)
INK = (240, 244, 255)
DIM = (160, 170, 200)
ACC = (90, 220, 190)      # 青绿主色
YEL = (255, 214, 80)
RED = (255, 90, 90)
CHK_A, CHK_B = (58, 60, 78), (88, 92, 116)   # 棋盘格

def vgrad(w, h, c1, c2):
    t = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(c1)[None, None, :] * (1 - t) + np.array(c2)[None, None, :] * t)
    return Image.fromarray(arr.astype(np.uint8).repeat(w, axis=1), "RGB")

def checker(w, h, s=26):
    im = Image.new("RGB", (w, h), CHK_A)
    d = ImageDraw.Draw(im)
    for y in range(0, h, s):
        for x in range(0, w, s):
            if (x // s + y // s) % 2:
                d.rectangle([x, y, x + s - 1, y + s - 1], fill=CHK_B)
    return im

def rrect(d, box, r, **kw):
    d.rounded_rectangle(box, radius=r, **kw)

def text_w(fnt, s):
    return fnt.getlength(s)

# ---------- 音幅包络（驱动口型/点头）----------
def load_env():
    wav = os.path.join(OUT, "voice.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i",
                    os.path.join(OUT, "voice.mp3"),
                    "-ac", "1", "-ar", "16000", "-f", "wav", wav], check=True)
    with wave.open(wav) as w:
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    spf = 16000 // FPS
    env = np.array([np.sqrt(np.mean(raw[i*spf:(i+1)*spf].astype(float) ** 2))
                    if len(raw[i*spf:(i+1)*spf]) else 0 for i in range(NF + 60)])
    k = np.ones(5) / 5
    env = np.convolve(env, k, "same")
    return env / (env.max() + 1e-6)
ENV = load_env()

def amp(f):
    return float(ENV[min(f, len(ENV) - 1)])

def mouth_level(f):
    a = amp(f)
    return 0 if a < 0.10 else (1 if a < 0.38 else 2)

def blink(f):
    return 1 if (f % 95) in (0, 1, 2) else 0

# ---------- 数字人形象 ----------
def make_avatar(mouth, blink_on):
    """600x760 RGBA 机器人形象"""
    W, H = 600, 760
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = W // 2
    # 身体（深色外套）
    d.rounded_rectangle([cx-190, 560, cx+190, 830], radius=90, fill=(36, 42, 70))
    d.rounded_rectangle([cx-190, 560, cx+190, 830], radius=90,
                        outline=(70, 82, 130), width=6)
    d.polygon([(cx-60, 575), (cx+60, 575), (cx+30, 700), (cx-30, 700)],
              fill=(52, 60, 96))
    d.ellipse([cx-16, 640, cx+16, 672], fill=ACC)          # 胸口灯
    # 脖子
    d.rectangle([cx-46, 505, cx+46, 580], fill=(214, 220, 235))
    d.rectangle([cx-46, 505, cx+46, 525], fill=(190, 197, 216))
    # 头
    d.rounded_rectangle([cx-210, 60, cx+210, 520], radius=150,
                        fill=(235, 240, 252), outline=(180, 190, 215), width=6)
    # 耳朵
    for sx in (-1, 1):
        d.ellipse([cx + sx*208 - 26, 260, cx + sx*208 + 26, 330],
                  fill=(200, 208, 228), outline=(170, 180, 205), width=5)
        d.ellipse([cx + sx*208 - 12, 275, cx + sx*208 + 12, 315], fill=ACC)
    # 天线
    d.line([cx, 60, cx, 10], fill=(170, 180, 205), width=8)
    d.ellipse([cx-18, -8, cx+18, 28], fill=ACC, outline=(50, 170, 145), width=4)
    # 面罩
    d.rounded_rectangle([cx-165, 150, cx+165, 420], radius=95, fill=(24, 28, 50))
    # 眼睛
    ey, er = 260, 44
    for sx in (-1, 1):
        ex = cx + sx * 82
        if blink_on:
            d.rounded_rectangle([ex-er, ey-8, ex+er, ey+8], radius=8, fill=(110, 235, 210))
        else:
            d.ellipse([ex-er, ey-er, ex+er, ey+er], fill=(110, 235, 210))
            d.ellipse([ex-er+14, ey-er+14, ex+er-14, ey+er-14], fill=(20, 24, 44))
            d.ellipse([ex-16, ey-24, ex+2, ey-8], fill=(235, 255, 250))
    # 腮红
    for sx in (-1, 1):
        d.ellipse([cx + sx*140 - 26, 330, cx + sx*140 + 26, 356],
                  fill=(255, 150, 160, 90))
    # 嘴
    my = 375
    if mouth == 0:
        d.rounded_rectangle([cx-34, my-6, cx+34, my+6], radius=6, fill=(110, 235, 210))
    elif mouth == 1:
        d.ellipse([cx-30, my-16, cx+30, my+22], fill=(110, 235, 210))
        d.ellipse([cx-30, my-16, cx+30, my+4], fill=(24, 28, 50))
    else:
        d.ellipse([cx-38, my-24, cx+38, my+40], fill=(110, 235, 210))
        d.ellipse([cx-38, my-24, cx+38, my], fill=(24, 28, 50))
        d.ellipse([cx-20, my+14, cx+20, my+38], fill=(255, 130, 140))
    return im

AVA = {(m, b): make_avatar(m, b) for m in (0, 1, 2) for b in (0, 1)}

def paste_avatar(frame, box, f, t):
    """box=(x,y,w) 圆形底座里的数字人；振幅驱动嘴型和上下浮动"""
    x, y, w = box
    bob = int(amp(f) * 10 + math.sin(t * 1.8) * 4)
    av = AVA[(mouth_level(f), blink(f))]
    aw = w
    ah = int(av.height * aw / av.width)
    av = av.resize((aw, ah), Image.LANCZOS)
    d = ImageDraw.Draw(frame)
    # 圆形底座在头肩部后面
    d.ellipse([x, y + bob + 40, x + w, y + bob + 40 + w],
              fill=(30, 36, 66), outline=ACC, width=5)
    frame.paste(av, (x + (w - aw) // 2, y + bob), av)

# ---------- 假游戏画面（演示动画用）----------
GW, GH = 800, 600        # 游戏窗口逻辑分辨率
def draw_game(t, moving=True, phase2_gone=False):
    """返回 (img, motion_mask)。phase2_gone=True 时运动像素已挖成透明棋盘。"""
    im = Image.new("RGB", (GW, GH), (32, 48, 64))
    d = ImageDraw.Draw(im)
    for gx in range(0, GW, 50):                     # 地砖网格
        d.line([gx, 0, gx, GH], fill=(40, 58, 76), width=1)
    for gy in range(0, GH, 50):
        d.line([0, gy, GW, gy], fill=(40, 58, 76), width=1)
    mask = Image.new("L", (GW, GH), 0)
    dm = ImageDraw.Draw(mask)

    # 静态建筑
    for bx, by, col in [(60, 60, (200, 70, 70)), (300, 60, (70, 160, 80)),
                        (540, 60, (70, 90, 210)), (180, 240, (200, 170, 60)),
                        (420, 240, (200, 90, 180))]:
        d.rounded_rectangle([bx, by, bx + 130, by + 120], radius=14,
                            fill=col, outline=(235, 240, 250), width=4)
        d.rectangle([bx + 45, by + 78, bx + 85, by + 120], fill=(30, 38, 52))
    # 静态 NPC（红方块小人）
    nx, ny = 590, 360
    d.rectangle([nx, ny, nx + 72, ny + 85], fill=(220, 60, 60),
                outline=(120, 20, 20), width=3)
    d.ellipse([nx + 14, ny + 18, nx + 30, ny + 34], fill=(255, 240, 235))
    d.ellipse([nx + 42, ny + 18, nx + 58, ny + 34], fill=(255, 240, 235))
    # 底部静态文字条
    d.rectangle([40, 530, 420, 575], fill=(24, 34, 48))
    d.text((55, 538), "STATIC-TEXT-12345", font=font(28, True), fill=(140, 220, 150))

    if moving and not phase2_gone:
        # 走动玩家（黄小人，来回走）
        px = int(80 + (GW - 280) * abs((t * 0.42) % 2 - 1))
        py = 430 + int(14 * math.sin(t * 6))
        d.rectangle([px, py, px + 66, py + 80], fill=(250, 210, 60),
                    outline=(150, 110, 20), width=3)
        d.ellipse([px + 14, py + 16, px + 28, py + 30], fill=(60, 50, 30))
        d.ellipse([px + 38, py + 16, px + 52, py + 30], fill=(60, 50, 30))
        dm.rectangle([px - 4, py - 4, px + 70, py + 84], fill=255)
        # 飘动光效粒子
        for i in range(4):
            qx = int((t * 55 + i * 190) % (GW + 60)) - 30
            qy = int(150 + 90 * math.sin(t * 1.4 + i * 1.7) + i * 60)
            d.ellipse([qx - 12, qy - 12, qx + 12, qy + 12],
                      fill=(140, 230, 255), outline=(220, 250, 255), width=2)
            dm.ellipse([qx - 16, qy - 16, qx + 16, qy + 16], fill=255)
        # 右上角计数（像真目标窗一样每帧变）
        cnt = str(int(t * 30) % 1000)
        d.text((GW - 130, 18), cnt, font=font(30, True), fill=(255, 240, 140))
        dm.rectangle([GW - 140, 10, GW - 10, 62], fill=255)
    return im, mask

# ---------- 通用绘制 ----------
def chip(d, xy, s, fnt, fg=(20, 26, 44), bg=ACC, pad=18):
    w = text_w(fnt, s) + pad * 2
    h = fnt.size + pad
    rrect(d, [xy[0], xy[1], xy[0] + w, xy[1] + h], h // 2, fill=bg)
    d.text((xy[0] + pad, xy[1] + pad // 2 + 2), s, font=fnt, fill=fg)
    return w, h

def fit_into(im, w, h):
    s = min(w / im.width, h / im.height)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                     Image.LANCZOS)

def ui_card(im, w, h, zoom=1.0):
    """UI 截图放进圆角卡片，zoom>1 轻微推近"""
    if zoom > 1.001:
        cw, ch = im.width / zoom, im.height / zoom
        cx, cy = im.width / 2, im.height / 2
        im = im.crop((int(cx - cw / 2), int(cy - ch / 2),
                      int(cx + cw / 2), int(cy + ch / 2)))
    im2 = fit_into(im, w, h)
    card = Image.new("RGB", (im2.width + 24, im2.height + 24), (228, 232, 244))
    card.paste(im2, (12, 12))
    return card

_ui_cache = {}
def ui(name):
    if name not in _ui_cache:
        _ui_cache[name] = Image.open(os.path.join(UI, name + ".png")).convert("RGB")
    return _ui_cache[name]

def game_card(t, w, h, t_mul=1.0):
    """假游戏画面装进白边卡片，限制在 (w,h) 内"""
    g, _ = draw_game(t * t_mul)
    gm = fit_into(g, w, h)
    card = Image.new("RGB", (gm.width + 20, gm.height + 20), (228, 232, 244))
    card.paste(gm, (10, 10))
    return card

# ---------- 场景 ----------
def scene0(ctx, lt, f):   # hook：痛点
    d, (x0, y0, W, H), L = ctx["d"], ctx["content"], ctx["L"]
    x, y, w, h = map(int, (x0, y0, W, H))
    # 模板缩略图被"路人"污染
    card = game_card(lt, int(w * 0.92), int(h * 0.46))
    cy = y + int(h * 0.30)
    frame.paste(card, (x + (w - card.width) // 2, cy))
    # 红色警示章
    stamp = ctx["L"]["f_warn"]
    d = ImageDraw.Draw(frame)
    msg = "路人路过 → 识别报废!"
    sw = text_w(stamp, msg)
    sx = x + (w - sw) // 2 - 30
    sy = cy + card.height + 34
    rrect(d, [sx - 20, sy - 12, sx + sw + 20, sy + stamp.size + 18], 16,
          fill=(60, 18, 24), outline=RED, width=5)
    d.text((sx, sy), msg, font=stamp, fill=RED)
    # 大标题
    t1, t2 = "识图模板里", "混进会动的东西？"
    fT = ctx["L"]["f_title"]
    y_t = y + int(h * 0.045)
    for i, s in enumerate((t1, t2)):
        d.text((x + (w - text_w(fT, s)) // 2, y_t + i * (fT.size + 14)),
               s, font=fT, fill=INK if i == 0 else YEL)

def scene1(ctx, lt, f):   # 连拍 N 帧
    d, (x0, y0, W, H), L = ctx["d"], ctx["content"], ctx["L"]
    x, y, w, h = map(int, (x0, y0, W, H))
    card = game_card(lt * 2.0, int(w * 0.94), int(h * 0.52))
    cx = x + (w - card.width) // 2
    cy = y + int(h * 0.12)
    frame.paste(card, (cx, cy))
    d = ImageDraw.Draw(frame)
    # 连拍帧角标
    nshot = int(lt * 6) % 13 or 1
    chip(d, (cx + 10, cy - ctx["L"]["f_chip"].size - 28),
         f"连拍中 · 第 {nshot} 帧", ctx["L"]["f_chip"], bg=RED, fg=(255, 245, 245))
    # 胶片条
    fy = cy + card.height + 36
    fh = int(w * 0.15 * GH / GW)
    fw = int(fh * GW / GH)
    gap = 16
    total_w = 6 * fw + 5 * gap
    fx = x + (w - total_w) // 2
    for i in range(6):
        k = (int(lt * 6) + i) % 6
        th2 = _film_thumb(i, k).resize((fw, fh), Image.LANCZOS)
        frame.paste(th2, (fx + i * (fw + gap), fy))
        if i == 0:
            d.rectangle([fx - 4, fy - 4, fx + fw + 4, fy + fh + 4],
                        outline=YEL, width=4)
    cap = "同一区域，连拍 N 帧"
    d.text((x + (w - text_w(ctx["L"]["f_body"], cap)) // 2,
            fy + fh + 20), cap, font=ctx["L"]["f_body"], fill=DIM)

_film_cache = {}
def _film_thumb(i, k):
    key = (i, k)
    if key in _film_cache:
        return _film_cache[key]
    g, _ = draw_game(k * 0.7)
    _film_cache[key] = g
    return g

def scene2(ctx, lt, f):   # 逐像素审判 → 挖透明
    d, (x0, y0, W, H), L = ctx["d"], ctx["content"], ctx["L"]
    x, y, w, h = map(int, (x0, y0, W, H))
    th = int(h * 0.56)
    tw = min(int(w * 0.94), int(th * GW / GH))
    th = int(tw * GH / GW)
    base, mask = draw_game(0.0, moving=True)       # 冻结在 t=0
    chk = checker(tw, th)
    src = base.resize((tw, th), Image.NEAREST)
    m_small = mask.resize((tw, th), Image.NEAREST)
    prog = min(1.0, lt / (TRACKS[2]["dur"] * 0.62))   # 扫描进度
    scanx = int(tw * prog)
    out = src.copy()
    # 扫描线扫过的左侧 → 运动像素已挖成棋盘
    er = Image.composite(chk, src, m_small.point(lambda v: 255 if v else 0))
    if scanx > 0:
        out.paste(er.crop((0, 0, scanx, th)), (0, 0))
    d2 = ImageDraw.Draw(out)
    if prog < 1.0:
        d2.rectangle([scanx - 4, 0, scanx + 4, out.height], fill=YEL)
    # 半透明红闪标记将消失的像素
    card = Image.new("RGB", (out.width + 20, out.height + 20), (228, 232, 244))
    card.paste(out, (10, 10))
    cx = x + (w - card.width) // 2
    cy = y + int(h * 0.18)
    frame.paste(card, (cx, cy))
    d = ImageDraw.Draw(frame)
    fT = ctx["L"]["f_h2"]
    msg = "每个像素单独审判"
    d.text((x + (w - text_w(fT, msg)) // 2, y + int(h * 0.05)), msg,
           font=fT, fill=INK)
    sub = "动的 → 透明     不动的 → 留下" if prog >= 1.0 else \
          "扫描比对中… 变的像素挖成透明"
    fS = ctx["L"]["f_body"]
    d.text((x + (w - text_w(fS, sub)) // 2, cy + card.height + 30),
           sub, font=fS, fill=(ACC if prog >= 1.0 else YEL))

def scene3(ctx, lt, f):   # 操作三步：绑定→框选→动态截图
    d, (x0, y0, W, H), L = ctx["d"], ctx["content"], ctx["L"]
    x, y, w, h = map(int, (x0, y0, W, H))
    shots = [("02_bound_live", "① 准星拖过去绑定"),
             ("03_boxed", "② 框选要抠的区域"),
             ("04_dyn_monitoring", "③ 点动态截图")]
    dur = TRACKS[3]["dur"]
    idx = min(2, int(lt / (dur / 3)))
    name, cap = shots[idx]
    z = 1.0 + 0.10 * ((lt - idx * dur / 3) / (dur / 3))
    card = ui_card(ui(name), int(w * 0.98), int(h * 0.58), zoom=z)
    cy = y + int(h * 0.24)
    frame.paste(card, (x + (w - card.width) // 2, cy))
    d = ImageDraw.Draw(frame)
    fS = ctx["L"]["f_h2"]
    d.text((x + (w - text_w(fS, cap)) // 2, cy + card.height + 28),
           cap, font=fS, fill=YEL)
    for i, (_, c) in enumerate(shots):   # 进度点
        bx = x + w // 2 + (i - 1) * 120
        by = y + int(h * 0.07)
        col = ACC if i == idx else (70, 78, 110)
        d.ellipse([bx - 16, by - 16, bx + 16, by + 16], fill=col)

def scene4(ctx, lt, f):   # 动态监测特写：左盯帧右预览
    d, (x0, y0, W, H), L = ctx["d"], ctx["content"], ctx["L"]
    x, y, w, h = map(int, (x0, y0, W, H))
    card = ui_card(ui("04_dyn_monitoring"), int(w * 0.98), int(h * 0.58),
                   zoom=1.0 + 0.08 * lt / TRACKS[4]["dur"])
    cy = y + int(h * 0.20)
    frame.paste(card, (x + (w - card.width) // 2, cy))
    d = ImageDraw.Draw(frame)
    for i, s in enumerate(("动的像素 → 实时被抠掉", "灰格 = 已变透明")):
        fS = ctx["L"]["f_body"]
        chip(d, (x + (w - text_w(fS, s)) // 2 - 20,
                 cy + card.height + 26 + i * (fS.size + 40)),
             s, fS, bg=(ACC if i == 0 else YEL))

def scene5(ctx, lt, f):   # 修图：魔术棒→反选→成品
    d, (x0, y0, W, H), L = ctx["d"], ctx["content"], ctx["L"]
    x, y, w, h = map(int, (x0, y0, W, H))
    dur = TRACKS[5]["dur"]
    if lt < dur * 0.55:                    # 前半：界面双拼
        for j, name in enumerate(("06_wand_selection", "09_inverted")):
            card = ui_card(ui(name), int(w * 0.48), int(h * 0.46))
            frame.paste(card, (x + int(w * (0.01 + j * 0.51)),
                               y + int(h * 0.18)))
        caps = ["魔术棒点色", "反选透明"]
        d = ImageDraw.Draw(frame)
        fS = ctx["L"]["f_body"]
        ch = ui_card(ui("06_wand_selection"), int(w * 0.48),
                     int(h * 0.46)).height
        for j, s in enumerate(caps):
            cx = x + int(w * (0.01 + j * 0.51)) + int(w * 0.24)
            d.text((cx - text_w(fS, s) // 2, y + int(h * 0.18) + ch + 18),
                   s, font=fS, fill=ACC)
    else:                                  # 后半：成品特写（NPC 精灵放棋盘上）
        base, _ = draw_game(0.0, moving=False)
        tpl = base.crop((590, 360, 662, 445)).convert("RGBA")
        cw, chh = int(w * 0.66), int(h * 0.44)
        chk = checker(cw, chh, s=int(cw / 18))
        cx = x + (w - cw) // 2
        cy = y + int(h * 0.18)
        frame.paste(chk, (cx, cy))
        sh = int(chh * 0.72)
        sw = int(sh * tpl.width / tpl.height)
        big = tpl.resize((sw, sh), Image.NEAREST)
        frame.paste(big, (cx + (cw - sw) // 2, cy + (chh - sh) // 2), big)
        d = ImageDraw.Draw(frame)
        d.rectangle([cx, cy, cx + cw, cy + chh], outline=ACC, width=6)
        chip(d, (cx + 10, cy + 10), "RGBA · alpha", ctx["L"]["f_chip"],
             bg=YEL, fg=(40, 30, 10))
        fS = ctx["L"]["f_h2"]
        s = "只留主体 · 带 alpha 的 PNG"
        d.text((x + (w - text_w(fS, s)) // 2,
                cy + chh + 30), s, font=fS, fill=YEL)

def scene6(ctx, lt, f):   # 测试匹配
    d, (x0, y0, W, H), L = ctx["d"], ctx["content"], ctx["L"]
    x, y, w, h = map(int, (x0, y0, W, H))
    card = ui_card(ui("10_test_match"), int(w * 0.98), int(h * 0.62),
                   zoom=1.0 + 0.07 * lt / TRACKS[6]["dur"])
    cy = y + int(h * 0.20)
    frame.paste(card, (x + (w - card.width) // 2, cy))
    d = ImageDraw.Draw(frame)
    fS = ctx["L"]["f_h2"]
    s = "同款算法 · 当场看命中率"
    d.text((x + (w - text_w(fS, s)) // 2,
            cy + card.height + 30), s, font=fS, fill=ACC)

def scene7(ctx, lt, f):   # CTA
    d, (x0, y0, W, H), L = ctx["d"], ctx["content"], ctx["L"]
    x, y, w, h = map(int, (x0, y0, W, H))
    fT, fB = ctx["L"]["f_title"], ctx["L"]["f_h2"]
    s1, s2 = "评论区扣 1", "源码 + 打包好的 exe 发你"
    d.text((x + (w - text_w(fT, s1)) // 2, y + int(h * 0.16)), s1,
           font=fT, fill=YEL)
    d.text((x + (w - text_w(fB, s2)) // 2, y + int(h * 0.16) + fT.size + 40),
           s2, font=fB, fill=INK)
    icon = Image.open(os.path.join(ROOT, "icon.png")).convert("RGBA")
    iw = int(w * 0.30)
    icon = icon.resize((iw, iw), Image.LANCZOS)
    frame.paste(icon, (x + (w - iw) // 2, y + int(h * 0.40)), icon)
    pulse = 1 + 0.5 * math.sin(lt * 5)
    d.ellipse([x + w // 2 - iw * 0.62 * pulse,
               y + int(h * 0.40) + iw // 2 - iw * 0.62 * pulse,
               x + w // 2 + iw * 0.62 * pulse,
               y + int(h * 0.40) + iw // 2 + iw * 0.62 * pulse],
              outline=(90, 220, 190, 160), width=6)

SCENES = [scene0, scene1, scene2, scene3, scene4, scene5, scene6, scene7]

def active_line(f):
    t = f / FPS
    cur = 0
    for tr in TRACKS:
        if t >= tr["start"]:
            cur = tr["i"]
        else:
            break
    return cur

def _wrap(line, fS, max_w):
    """超长拆两行：优先在靠近中点的标点处断"""
    if text_w(fS, line) <= max_w:
        return [line]
    mid = len(line) // 2
    for off in range(mid):
        for k in (mid - off, mid + off):
            if 0 < k < len(line) and line[k - 1] in "，。、；：":
                return [line[:k], line[k:]]
    return [line[:mid], line[mid:]]

def _fit_rows(line, fS, max_w):
    """拆行后仍超宽就逐级缩字号"""
    sz = fS.size
    while True:
        rows = _wrap(line, fS, max_w)
        if sz <= 30 or all(text_w(fS, r) <= max_w for r in rows):
            return rows, fS
        sz = max(30, sz - 4)
        fS = font(sz)

def _sub_row(d, s, n_sp, cx, y, fS):
    x0 = cx - text_w(fS, s) / 2
    for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3),
                   (-2, -2), (2, 2), (-2, 2), (2, -2)):
        d.text((x0 + dx, y + dy), s, font=fS, fill=(10, 10, 20))
    d.text((x0, y), s, font=fS, fill=INK)
    if n_sp > 0:
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
            d.text((x0 + dx, y + dy), s[:n_sp], font=fS, fill=(10, 10, 20))
        d.text((x0, y), s[:n_sp], font=fS, fill=YEL)

def subtitle(d, W, H, f, L):
    t = f / FPS
    for tr in TRACKS:
        if tr["start"] - 0.05 <= t <= tr["start"] + tr["dur"] + LINE_GAP * 0.6:
            fS = L["f_sub"]
            prog = max(0.0, min(1.0, (t - tr["start"]) / tr["dur"]))
            rows, fS = _fit_rows(tr["text"], fS, L["sub_max_w"])
            ci = int(len(tr["text"]) * prog)
            y = L["sub_y"]
            used = 0
            for s in rows:
                n_sp = max(0, min(len(s), ci - used))
                _sub_row(d, s, n_sp, W / 2, y, fS)
                used += len(s)
                y += fS.size + 18
            return

# ---------- 布局 ----------
def layout(name):
    if name == "9x16":
        W, H = 1080, 1920
        return dict(W=W, H=H,
                    content=(24, 40, W - 48, int(H * 0.60)),
                    avatar=(W - 320, 1240, 280),
                    sub_y=int(H * 0.82), sub_max_w=W - 80,
                    f_title=font(96), f_h2=font(56), f_body=font(42),
                    f_chip=font(38), f_warn=font(46), f_sub=font(46))
    W, H = 1920, 1080
    return dict(W=W, H=H,
                content=(60, 30, int(W * 0.70), int(H * 0.80)),
                avatar=(W - 460, H - 580, 380),
                sub_y=int(H * 0.84), sub_max_w=int(W * 0.72),
                f_title=font(88), f_h2=font(52), f_body=font(40),
                f_chip=font(36), f_warn=font(44), f_sub=font(44))

# ---------- 渲染 ----------
def render(name, outpath, with_avatar=True, with_sub=True):
    L = layout(name)
    W, H = L["W"], L["H"]
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-",
           "-i", os.path.join(OUT, "voice.mp3"),
           "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
           "-preset", "medium", "-c:a", "aac", "-b:a", "160k",
           "-shortest", outpath]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    bg = vgrad(W, H, BG_TOP, BG_BOT)
    for f in range(NF):
        global frame
        frame = bg.copy()
        t = f / FPS
        li = active_line(f)
        tr = TRACKS[li]
        lt = t - tr["start"]
        d = ImageDraw.Draw(frame)
        ctx = {"d": d, "content": L["content"], "L": L}
        SCENES[li](ctx, max(0, lt), f)
        if with_avatar:
            paste_avatar(frame, L["avatar"], f, t)
        if with_sub:
            subtitle(ImageDraw.Draw(frame), W, H, f, L)
        proc.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
        if f % 150 == 0:
            print(f"  {name} {f}/{NF}")
    proc.stdin.close()
    proc.wait()
    print("->", outpath, f"{os.path.getsize(outpath)/1e6:.1f}MB")

def render_broll():
    L = layout("16x9")
    W, H = L["W"], L["H"]
    dur = TRACKS[1]["dur"] + TRACKS[2]["dur"] + 1.0
    nf = int(dur * FPS)
    out = os.path.join(OUT, "素材_原理演示Broll.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
           "-preset", "medium", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    bg = vgrad(W, H, BG_TOP, BG_BOT)
    t2 = TRACKS[1]["dur"] + 0.5
    global frame
    for f in range(nf):
        frame = bg.copy()
        t = f / FPS
        d = ImageDraw.Draw(frame)
        ctx = {"d": d, "content": L["content"], "L": L}
        (scene1 if t < t2 else scene2)(ctx, t if t < t2 else t - t2, f)
        proc.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
    proc.stdin.close(); proc.wait()
    print("->", out)

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "broll"):
        render_broll()
    if which in ("all", "9x16"):
        render("9x16", os.path.join(OUT, "成品_抖音9x16.mp4"))
    if which in ("all", "16x9"):
        render("16x9", os.path.join(OUT, "成品_B站16x9.mp4"))
