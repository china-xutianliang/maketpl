
def make_music(total, path, hits, sr=44100):
    n = int((total + 1) * sr); out = np.zeros(n); rng = np.random.default_rng(7)
    def add(t0, sig):
        s0 = int(t0 * sr)
        if s0 < 0: sig = sig[-s0:]; s0 = 0
        if s0 >= n or len(sig) == 0: return
        e = min(n, s0 + len(sig)); out[s0:e] += sig[:e - s0]
    chords = [[220, 261.63, 329.63], [174.61, 220, 261.63], [261.63, 329.63, 392], [196, 246.94, 293.66]]
    beat = 0.5; bar = 4 * beat
    for k in range(int(total / bar) + 2):
        ch = chords[k % 4]
        L = int((bar + 0.3) * sr); tt = np.arange(L) / sr
        env = np.minimum(1, tt / 0.2) * np.exp(-tt * 0.8); sig = np.zeros(L)
        for f in ch: sig += 0.035 * env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt))
        add(k * bar, sig)
        for j in range(8):
            tb = np.arange(int(0.22 * sr)) / sr
            add(k * bar + j * beat / 2, 0.09 * np.exp(-tb * 9) * np.sin(np.pi * ch[0] * tb))
            tq = np.arange(int(0.2 * sr)) / sr
            f = ch[[0, 1, 2, 1][j % 4]] * 2
            add(k * bar + j * beat / 2 + beat / 4, 0.025 * np.exp(-tq * 12) * np.sin(2 * np.pi * f * tq))
    tk = np.arange(int(0.2 * sr)) / sr
    kick = 0.45 * np.exp(-tk * 14) * np.sin(2 * np.pi * (50 * tk + 90 * (1 - np.exp(-35 * tk)) / 35))
    Lh = int(0.05 * sr); hat = 0.06 * rng.standard_normal(Lh) * np.exp(-np.arange(Lh) / sr * 80); hat = np.diff(hat, prepend=0)
    for b in range(int(total / beat) + 2):
        add(b * beat, kick); add(b * beat + beat / 2, hat)
    Lw = int(0.45 * sr); tw = np.arange(Lw) / sr
    wn = np.convolve(rng.standard_normal(Lw), np.ones(6) / 6, 'same')
    whoosh = 0.25 * wn * (tw / tw[-1]) ** 2
    for h in hits:
        if h > 0.3: add(h - 0.45, whoosh); add(h, kick * 1.3)
    fi, fo, end = int(0.6 * sr), int(2.0 * sr), int(total * sr)
    out[:fi] *= np.linspace(0, 1, fi); out[end - fo:end] *= np.linspace(1, 0, fo); out[end:] = 0
    out = out / (np.abs(out).max() + 1e-9) * 0.8
    pcm = (np.stack([out, out], 1) * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

music = os.path.join(TMP, 'music.wav'); make_music(TOTAL, music, FLASH)
audio = os.path.join(TMP, 'audio.wav')
cmd = ['ffmpeg', '-y', '-v', 'error', '-i', music]
fc, mix = '[0:a]volume=0.28[m];', '[m]'
if HAS_VOICE:
    for i, s in enumerate(SCENES):
        cmd += ['-i', s['mp3']]; ms = int((s['start'] + LEAD) * 1000)
        fc += '[%d:a]aresample=44100,aformat=channel_layouts=stereo,adelay=%d|%d,volume=1.7[v%d];' % (i + 1, ms, ms, i)
        mix += '[v%d]' % i
n_in = len(SCENES) + 1 if HAS_VOICE else 1
fc += mix + 'amix=inputs=%d:normalize=0:duration=longest,alimiter=limit=0.95[a]' % n_in
cmd += ['-filter_complex', fc, '-map', '[a]', '-t', '%.3f' % TOTAL, audio]
subprocess.run(cmd, check=True)
