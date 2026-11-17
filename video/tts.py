# -*- coding: utf-8 -*-
# 逐句 edge-tts 配音：产出 out/voice/lineN.mp3、timing.json（词边界）、voice.mp3、subtitles.srt
import asyncio, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
VDIR = os.path.join(OUT, "voice")
os.makedirs(VDIR, exist_ok=True)
sys.path.insert(0, HERE)
from script import LINES, VOICE, RATE, LINE_GAP

import edge_tts

async def synth_line(i, text):
    mp3 = os.path.join(VDIR, f"line{i}.mp3")
    words = []   # [(text, offset_s, dur_s)] 相对本句
    comm = edge_tts.Communicate(text, VOICE, rate=RATE)
    with open(mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append([chunk["text"],
                              chunk["offset"] / 1e7,
                              chunk["duration"] / 1e7])
    return mp3, words

def mp3_dur(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                        "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())

async def main():
    tracks, t = [], 0.0
    for i, text in enumerate(LINES):
        mp3, words = await synth_line(i, text)
        dur = mp3_dur(mp3)
        tracks.append({"i": i, "text": text, "mp3": mp3, "start": t,
                       "dur": dur, "words": words})
        t += dur + LINE_GAP
        print(f"line{i}: {dur:.2f}s  {text[:24]}...")

    total = t
    # 拼一条完整音轨：各句 mp3 按时间点 delay 后 mix
    fc = "".join(f"[{i}:a]adelay={int(tr['start']*1000)}|{int(tr['start']*1000)}[d{i}];"
                 for i, tr in enumerate(tracks))
    mix = "".join(f"[d{i}]" for i in range(len(tracks)))
    voice = os.path.join(OUT, "voice.mp3")
    subprocess.run(["ffmpeg", "-y", "-v", "error"]
                   + sum([["-i", tr["mp3"]] for tr in tracks], [])
                   + ["-filter_complex",
                      fc + mix + f"amix=inputs={len(tracks)}:normalize=0,volume=1.4[a]",
                      "-map", "[a]", "-c:a", "libmp3lame", "-q:a", "2", voice],
                   check=True)

    # SRT（句级）
    def ts(s):
        ms = int(round(s * 1000))
        return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
    with open(os.path.join(OUT, "subtitles.srt"), "w", encoding="utf-8") as f:
        for i, tr in enumerate(tracks):
            f.write(f"{i+1}\n{ts(tr['start'])} --> {ts(tr['start']+tr['dur'])}\n"
                    f"{tr['text']}\n\n")

    with open(os.path.join(OUT, "timing.json"), "w", encoding="utf-8") as f:
        json.dump({"total": total, "tracks": tracks}, f, ensure_ascii=False, indent=1)
    print(f"total {total:.1f}s -> voice.mp3, subtitles.srt, timing.json")

asyncio.run(main())
