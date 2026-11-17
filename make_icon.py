# -*- coding: utf-8 -*-
"""生成应用图标 icon.ico / icon.png —— 卡通魔法棒。"""
import math

from PIL import Image, ImageDraw

S = 1024  # 超采样画布，最后缩到 256


def star(cx, cy, r_out, r_in, n=5, rot=-90.0):
    pts = []
    for i in range(n * 2):
        ang = math.radians(rot + i * 180.0 / n)
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def sparkle(d, cx, cy, r, fill, outline):
    d.polygon(star(cx, cy, r * 1.08, r * 0.40, 4), fill=outline)
    d.polygon(star(cx, cy, r, r * 0.34, 4), fill=fill)


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ---- 背景：圆角徽章，竖向紫色渐变 ----
    R = 480
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    top, bot = (196, 181, 253), (124, 92, 231)  # 浅薰衣草 -> 紫
    for y in range(S):
        t = y / S
        gd.line([(0, y), (S, y)],
                fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([S//2 - R, S//2 - R, S//2 + R, S//2 + R],
                         radius=210, fill=255)
    img.paste(grad, (0, 0), mask)

    # 徽章内圈白色细环 + 左上高光，提立体感
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([S//2 - R + 26, S//2 - R + 26, S//2 + R - 26, S//2 + R - 26],
                        radius=190, outline=(255, 255, 255, 70), width=16)
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([170, 120, 620, 420], fill=(255, 255, 255, 46))
    img = Image.alpha_composite(img, hl)
    d = ImageDraw.Draw(img)

    # ---- 魔法棒：左下 -> 右上，粗描边卡通风 ----
    x1, y1, x2, y2 = 268, 776, 592, 452       # 棒身两端
    dx, dy = x2 - x1, y2 - y1
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux                          # 法向

    def band(t0, t1, w, color):
        ax, ay = x1 + dx * t0, y1 + dy * t0
        bx, by = x1 + dx * t1, y1 + dy * t1
        d.line([(ax, ay), (bx, by)], fill=color, width=w)

    W = 104
    band(0.0, 1.0, W + 20, (52, 40, 96, 255))            # 描边
    band(0.0, 1.0, W, (120, 92, 220, 255))               # 棒身紫
    # 棒身两条白色饰环
    for t in (0.30, 0.55):
        cxm, cym = x1 + dx * t, y1 + dy * t
        hw = 20
        d.polygon([(cxm + px * (W // 2 - 6), cym + py * (W // 2 - 6)),
                   (cxm - px * (W // 2 - 6), cym - py * (W // 2 - 6)),
                   (cxm - px * (W // 2 - 6) - ux * hw * 2, cym - py * (W // 2 - 6) - uy * hw * 2),
                   (cxm + px * (W // 2 - 6) - ux * hw * 2, cym + py * (W // 2 - 6) - uy * hw * 2)],
                  fill=(240, 236, 255, 255))
    # 底端圆帽
    d.ellipse([x1 - 62, y1 - 62, x1 + 62, y1 + 62], fill=(52, 40, 96, 255))
    d.ellipse([x1 - 48, y1 - 48, x1 + 48, y1 + 48], fill=(255, 214, 102, 255))
    # 白色棒尖（在星星底下露一点）
    band(0.82, 1.04, W, (245, 242, 255, 255))

    # ---- 顶端星星：大黄星 + 笑脸 ----
    scx, scy, sr = 648, 372, 205
    d.polygon(star(scx, scy, sr * 1.10, sr * 0.55), fill=(230, 120, 30, 255))  # 橙描边
    d.polygon(star(scx, scy, sr, sr * 0.50), fill=(255, 213, 79, 255))         # 星身
    # 星星左上的白色小高光
    d.polygon(star(scx - 52, scy - 60, 42, 18, 5), fill=(255, 246, 210, 200))
    # 笑脸：两眼 + 腮红 + 嘴
    eye = (74, 62)
    for ex in (scx - 62, scx + 62):
        d.ellipse([ex - 21, scy - 8 - 21, ex + 21, scy - 8 + 21], fill=(84, 52, 20, 255))
        d.ellipse([ex - 8, scy - 8 - 15, ex + 6, scy - 8 - 1], fill=(255, 255, 255, 235))
    for ex in (scx - 108, scx + 108):
        d.ellipse([ex - 20, scy + 22, ex + 20, scy + 44], fill=(255, 140, 140, 120))
    d.arc([scx - 46, scy + 4, scx + 46, scy + 78], start=25, end=155,
          fill=(84, 52, 20, 255), width=13)

    # ---- 周围小闪光 ----
    sparkle(d, 300, 300, 74, (255, 255, 255, 255), (255, 200, 90, 255))
    sparkle(d, 822, 640, 58, (255, 255, 255, 255), (255, 200, 90, 255))
    sparkle(d, 770, 210, 40, (255, 236, 170, 255), (255, 200, 90, 255))

    img256 = img.resize((256, 256), Image.LANCZOS)
    img256.save("icon.png")
    img256.save("icon.ico",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                       (64, 64), (128, 128), (256, 256)])
    print("icon.ico / icon.png done")


if __name__ == "__main__":
    main()
