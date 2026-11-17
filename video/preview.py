# -*- coding: utf-8 -*-
# 抽帧预览：python preview.py <layout> <t秒> <out.png>
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import ImageDraw
import render as R

name, t, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
L = R.layout(name)
R.frame = R.vgrad(L["W"], L["H"], R.BG_TOP, R.BG_BOT)
f = int(t * R.FPS)
li = R.active_line(f)
tr = R.TRACKS[li]
d = ImageDraw.Draw(R.frame)
ctx = {"d": d, "content": L["content"], "L": L}
R.SCENES[li](ctx, t - tr["start"], f)
R.paste_avatar(R.frame, L["avatar"], f, t)
R.subtitle(ImageDraw.Draw(R.frame), L["W"], L["H"], f, L)
R.frame.save(out)
print("scene", li, "->", out)
