# 手动 UI 测试用的假"游戏"窗口：独立进程、内容持续动。
# 启动后把顶层 hwnd 写到 _uitarget_hwnd.txt，位置 (5,5) 大小 600x430。
import os, sys, time, tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
root = tk.Tk()
root.title("UI_TEST_TARGET")
root.geometry("600x430+5+5")
cv = tk.Canvas(root, bg="#203040", highlightthickness=0)
cv.pack(fill="both", expand=True)

COLORS = ["#dc3c3c", "#3c8c46", "#3c64dc", "#dcdc3c", "#c83cc8", "#3cc8c8",
          "#e08c28", "#8c3cdc", "#64c832", "#c86464", "#6464c8", "#64c864"]
W, H = 600, 430
cell = 90
for i, col in enumerate(COLORS):
    x = 30 + (i % 4) * (cell + 30)
    y = 30 + (i // 4) * (cell + 30)
    cv.create_rectangle(x, y, x + cell, y + cell, fill=col, outline="white", width=2)
cv.create_text(300, 340, text="MAKETPL TARGET", fill="white",
               font=("Arial", 28, "bold"))
cv.create_text(300, 380, text="STATIC-TEXT-12345", fill="#a0e0a0",
               font=("Courier", 18, "bold"))

box = cv.create_rectangle(0, 0, 60, 60, fill="#ffffff", outline="#ff0000", width=3)
num = cv.create_text(560, 20, text="0", fill="#ffff80", font=("Courier", 14, "bold"))

root.update_idletasks()
with open(os.path.join(HERE, "_uitarget_hwnd.txt"), "w") as f:
    f.write(str(root.winfo_id()))

t0 = time.time()
i = 0
while True:
    t = time.time() - t0
    x = 30 + (480 - 60) * abs((t * 0.35) % 2 - 1)
    y = 390 + 20 * (1 if int(t * 2) % 2 else -1) * 0.5
    cv.coords(box, x, y, x + 60, y + 60)
    i += 1
    cv.itemconfigure(num, text=str(i % 1000))
    root.update()
    time.sleep(0.03)
