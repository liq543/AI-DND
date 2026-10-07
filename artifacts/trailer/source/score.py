# Original trailer score: "The Hollow Crown" — D minor, 120 BPM (beat = 0.5 s, bar = 2 s), 88 s.
# Pure numpy synthesis: string ensemble, brass, choir, celesta, taiko, timpani, cymbals, risers, impacts,
# plus the sound-design cues (dice, fireball, typing, rewind) listed in sfx.json by the editor.
import json, sys
import numpy as np
from scipy import signal

SR = 44100
DUR = 88.0
N = int(SR * DUR)
rng = np.random.default_rng(7)
BEAT = 0.5
BAR = 2.0

def t_of(bar, beat=0.0): return bar * BAR + beat * BEAT
def hz(n): return 440.0 * 2 ** ((n - 69) / 12)
NOTE = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
def m(name):  # "D4" -> midi
    p, o = name[:-1], int(name[-1]); return 12 * (o + 1) + NOTE[p]

class Bus:
    def __init__(self, name, rev=0.2, pan=0.0):
        self.name, self.rev, self.L, self.R = name, rev, np.zeros(N), np.zeros(N)
    def add(self, x, t, pan=0.0, gain=1.0):
        i = int(t * SR)
        if i >= N or i + len(x) <= 0: return
        if i < 0: x = x[-i:]; i = 0
        x = x[: N - i] * gain
        a = np.sqrt((1 - pan) / 2); b = np.sqrt((1 + pan) / 2)
        self.L[i:i + len(x)] += x * a; self.R[i:i + len(x)] += x * b

def env_adsr(n, a, d, s, r, sr=SR):
    a, d, r = int(a * sr), int(d * sr), int(r * sr)
    e = np.ones(n) * s
    if a: e[:min(a, n)] = np.linspace(0, 1, a)[:min(a, n)]
    if d and a < n: k = min(d, n - a); e[a:a + k] = np.linspace(1, s, d)[:k]
    if r: rr = min(r, n); e[n - rr:] *= np.linspace(1, 0, rr)
    return e

def saw(f, n, detune_cents=0.0, vib=0.0, vibrate=5.0, phase=None, maxh=None):
    t = np.arange(n) / SR
    f = f * 2 ** (detune_cents / 1200)
    inst = f * (1 + vib * np.sin(2 * np.pi * vibrate * t + rng.uniform(0, 6.28)))
    ph = 2 * np.pi * np.cumsum(inst) / SR + (rng.uniform(0, 6.28) if phase is None else phase)
    H = int(min(maxh or 60, 9000 / f))
    out = np.zeros(n)
    for k in range(1, H + 1):
        out += np.sin(k * ph) / k
    return out * 0.55

def lowpass(x, fc, order=2):
    sos = signal.butter(order, min(fc, SR / 2 * 0.95), 'low', fs=SR, output='sos'); return signal.sosfilt(sos, x)
def highpass(x, fc, order=2):
    sos = signal.butter(order, fc, 'high', fs=SR, output='sos'); return signal.sosfilt(sos, x)
def bandpass(x, lo, hi, order=2):
    sos = signal.butter(order, [lo, min(hi, SR / 2 * .95)], 'band', fs=SR, output='sos'); return signal.sosfilt(sos, x)

# ------------------------------------------------------------------ instruments
def strings(midi, dur, vel=0.5, att=0.08, rel=0.25, bright=3500, voices=3, vib=0.004):
    n = int((dur + rel) * SR); x = np.zeros(n)
    for v in range(voices):
        x += saw(hz(midi), n, detune_cents=(v - (voices - 1) / 2) * 7, vib=vib)
    x = lowpass(x / voices, bright)
    return x * env_adsr(n, att, 0.1, 0.85, rel) * vel

def stacc(midi, dur, vel=0.5, bright=2800):
    n = int((dur + 0.06) * SR); x = saw(hz(midi), n, 0) + saw(hz(midi), n, 9)
    x = lowpass(x * 0.5, bright)
    e = np.exp(-np.arange(n) / SR / max(0.05, dur * 0.55)); e[:int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
    return x * e * vel

def brass(midi, dur, vel=0.5, att=0.06, rel=0.3, growl=1.0):
    n = int((dur + rel) * SR); t = np.arange(n) / SR
    f = hz(midi)
    ph = 2 * np.pi * np.cumsum(f * (1 + 0.003 * np.sin(2 * np.pi * 5.2 * t))) / SR
    # brightness rises through the attack, then settles
    cut = (2.5 + 9 * growl * (1 - np.exp(-t / 0.12))) * np.exp(-t / 3.0) + 2.5
    H = int(min(40, 7000 / f)); x = np.zeros(n)
    for k in range(1, H + 1):
        x += np.sin(k * ph) / k * np.exp(-k / cut)
    x = np.tanh(1.6 * x) * 0.7
    return x * env_adsr(n, att, 0.25, 0.75, rel) * vel

def choir(midi, dur, vel=0.4, att=0.6, rel=0.8):
    n = int((dur + rel) * SR); x = np.zeros(n)
    for v in range(4):
        x += saw(hz(midi), n, detune_cents=(v - 1.5) * 9, vib=0.006, vibrate=4.6 + v * 0.3)
    y = 0.9 * bandpass(x, 600, 900) + 0.6 * bandpass(x, 1000, 1300) + 0.25 * bandpass(x, 2400, 2900) + 0.2 * lowpass(x, 400)
    return y * env_adsr(n, att, 0.3, 0.9, rel) * vel * 0.8

def celesta(midi, vel=0.4, dec=1.6):
    n = int((dec * 1.5) * SR); t = np.arange(n) / SR; f = hz(midi)
    x = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.4)
         + 0.18 * np.sin(2 * np.pi * 4.07 * f * t) * np.exp(-t / 0.15) + 0.08 * np.sin(2 * np.pi * 6.8 * f * t) * np.exp(-t / 0.06))
    e = np.exp(-t / dec); e[:40] *= np.linspace(0, 1, 40)
    return x * e * vel * 0.5

def bass_pad(midi, dur, vel=0.4):
    n = int((dur + 0.6) * SR); x = saw(hz(midi), n, 0) + saw(hz(midi), n, 6) + 0.6 * np.sin(2 * np.pi * hz(midi) * np.arange(n) / SR)
    return lowpass(x, 600) * env_adsr(n, 0.4, 0.2, 0.9, 0.6) * vel * 0.6

def taiko(vel=1.0, pitch=1.0, dec=0.55):
    n = int(1.4 * SR); t = np.arange(n) / SR
    f = (55 + 120 * np.exp(-t / 0.035)) * pitch
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / dec)
    skin = lowpass(rng.standard_normal(n), 1800) * np.exp(-t / 0.03) * 0.5
    over = np.sin(2 * np.pi * 1.6 * np.cumsum(f) / SR) * np.exp(-t / 0.12) * 0.25
    return np.tanh(1.5 * (body + skin + over)) * vel

def tom(vel=0.6, pitch=1.0):
    n = int(0.6 * SR); t = np.arange(n) / SR
    f = (110 + 90 * np.exp(-t / 0.03)) * pitch
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.22) + lowpass(rng.standard_normal(n), 3000) * np.exp(-t / 0.02) * 0.3) * vel

def snare(vel=0.5):
    n = int(0.45 * SR); t = np.arange(n) / SR
    nz = bandpass(rng.standard_normal(n), 1500, 9000) * np.exp(-t / 0.09)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)
    return (nz * 0.8 + tone * 0.5) * vel

def tick(vel=0.25):
    n = int(0.08 * SR); t = np.arange(n) / SR
    return highpass(rng.standard_normal(n), 6000) * np.exp(-t / 0.012) * vel

def crash(vel=0.5, dec=2.6):
    n = int(dec * 2 * SR); t = np.arange(n) / SR
    x = highpass(rng.standard_normal(n), 4200, 4) * np.exp(-t / dec)
    x += 0.3 * bandpass(rng.standard_normal(n), 3000, 7000) * np.exp(-t / 0.3)
    return x * vel

def sub_boom(vel=1.0, dec=2.2, f0=58, f1=28):
    n = int(dec * 2.2 * SR); t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.5)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / dec) * vel

def noise_sweep(dur, f_lo, f_hi, vel=0.4, curve=2.0, reverse=False):
    n = int(dur * SR); x = rng.standard_normal(n); out = np.zeros(n); blk = 1024
    for i in range(0, n, blk):
        p = (i / n) ** curve; fc = f_lo * (f_hi / f_lo) ** p
        seg = x[max(0, i - 2048):i + blk]
        y = bandpass(seg, fc * 0.7, fc * 1.4)[-min(blk, n - i):]
        out[i:i + len(y)] = y
    e = np.linspace(0, 1, n) ** 2.2
    if reverse: out = out[::-1]; e = e
    return out * e * vel

def riser(dur, vel=0.35, f0=110, f1=880):
    n = int(dur * SR); t = np.arange(n) / SR; p = t / dur
    f = f0 * (f1 / f0) ** (p ** 1.5)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.5 * np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR)
    return (tone * 0.4 + noise_sweep(dur, 300, 8000, 1.0)) * (p ** 2.0) * vel

def rev_crash(dur=2.0, vel=0.5):
    x = crash(1.0, dur / 2.2)[: int(dur * SR)][::-1]
    return x * vel

def braam(root_midi, vel=1.0, dur=3.0):
    x = 0
    for k, iv in enumerate([0, 12, 19, 24]):
        x = x + brass(root_midi + iv, dur, vel=[0.9, 0.7, 0.45, 0.35][k], att=0.02, rel=1.0, growl=1.6)
    return np.tanh(1.3 * x) * vel * 0.8

# ------------------------------------------------------------------ harmony
CH = {  # chord -> (root midi in octave 2, tones as semitones)
    'Dm': (m('D2'), [0, 3, 7]), 'Bb': (m('A#1'), [0, 4, 7]), 'F': (m('F2'), [0, 4, 7]), 'C': (m('C2'), [0, 4, 7]),
    'Gm': (m('G1'), [0, 3, 7]), 'A': (m('A1'), [0, 4, 7]), 'Em': (m('E2'), [0, 3, 7]), 'Am': (m('A1'), [0, 3, 7]),
    'B': (m('B1'), [0, 4, 7]), 'G': (m('G1'), [0, 4, 7]), 'D': (m('D2'), [0, 4, 7]),
}
strB, celB, brassB, choirB, drumB, fxB, bassB = (Bus('strings', .32), Bus('celesta', .45), Bus('brass', .3), Bus('choir', .5),
                                                   Bus('drums', .18), Bus('fx', .25), Bus('bass', .12))
brkB, sfxB = Bus('brk', .35), Bus('sfx', .15)

def pad_bar(ch, t0, dur, vel=0.35, octs=(3, 4), choir_on=False, choir_vel=0.3):
    r, iv = CH[ch]
    bassB.add(bass_pad(r, dur, vel * 0.9), t0)
    for o in octs:
        for k, s in enumerate(iv):
            strB.add(strings(r + 12 * (o - 2) + s, dur, vel * 0.32, att=0.25, rel=0.5, bright=2600), t0, pan=(k - 1) * 0.4)
    if choir_on:
        for k, s in enumerate(iv):
            choirB.add(choir(r + 24 + s, dur, choir_vel), t0, pan=(k - 1) * 0.5)

OST8 = [0, 0, 7, 0, 3, 0, 7, 0]
def ostinato(ch, t0, sixteenths=False, vel=0.32, octave=3, bright=2600):
    r, iv = CH[ch]; third = iv[1]
    pat = [0, 0, 7, 0, third, 0, 7, 12]
    steps = 16 if sixteenths else 8; d = BAR / steps
    for i in range(steps):
        s = pat[i % 8]; acc = 1.0 if i % 4 == 0 else 0.75
        strB.add(stacc(r + 12 * (octave - 2) + s, d * 0.9, vel * acc, bright), t0 + i * d, pan=-0.35)
        if sixteenths and i % 2 == 0:
            strB.add(stacc(r + 12 * (octave - 1) + s, d * 0.9, vel * 0.55 * acc, bright + 800), t0 + i * d, pan=0.35)

# the Crown theme: (midi name, beats)
THEME = [[('D4', 1.5), ('E4', .5), ('F4', 1), ('A4', 1)], [('G4', 1.5), ('F4', .5), ('E4', 1), ('C4', 1)],
         [('D4', 1.5), ('E4', .5), ('F4', 1), ('A4', 1)], [('D5', 2), ('C#5', 2)],
         [('D5', 2), ('C5', 1), ('A#4', 1)], [('A4', 3), ('C5', 1)],
         [('A#4', 1.5), ('A4', .5), ('G4', 1), ('A#4', 1)], [('A4', 2), ('E4', 1), ('C#5', 1)]]
def theme(bars, t0, inst, shift=0, vel=0.4, bus=None, pan=0.0, legato=1.0):
    t = t0
    for bi in bars:
        for name, b in THEME[bi % 8]:
            d = b * BEAT
            if inst == 'cel': celB.add(celesta(m(name) + shift, vel), t, pan=pan)
            elif inst == 'str': strB.add(strings(m(name) + shift, d * legato, vel, att=0.07, rel=0.35, bright=5200, vib=0.006), t, pan=pan)
            elif inst == 'brass': brassB.add(brass(m(name) + shift, d * legato, vel), t, pan=pan)
            elif inst == 'choir': choirB.add(choir(m(name) + shift, d, vel, att=0.15, rel=0.4), t, pan=pan)
            t += d

def hit(t, big=1.0, root='D1'):
    drumB.add(taiko(1.0 * big, 0.9), t); drumB.add(taiko(0.8 * big, 0.7, 0.9), t + 0.003)
    fxB.add(sub_boom(0.9 * big), t); fxB.add(crash(0.45 * big), t, pan=0.2)
    brassB.add(braam(m(root), 0.75 * big, 2.6 * big), t)

# ------------------------------------------------------------------ the arrangement
# A. intro 0-8: drone, heartbeat, celesta motif, reverse swell
bassB.add(bass_pad(m('D1'), 8.0, 0.5), 0.0)
strB.add(strings(m('D3'), 7.5, 0.12, att=2.5, rel=1.5, bright=900), 0.2)
strB.add(strings(m('A3'), 7.0, 0.08, att=3.0, rel=1.5, bright=900), 0.8)
for k, tt in enumerate([0.4, 2.4, 4.4, 6.4]):
    drumB.add(taiko(0.35 + 0.08 * k, 0.75, 0.7), tt); drumB.add(taiko(0.22 + 0.06 * k, 0.75, 0.6), tt + 0.28)
theme([0, 1, 2, 3], 0.0, 'cel', shift=12, vel=0.32, pan=0.15)
fxB.add(rev_crash(2.0, 0.55), 6.0); fxB.add(riser(2.0, 0.25, 80, 600), 6.0)

# B. title 8-12
hit(8.0, 1.25, 'D1')
pad_bar('Dm', 8.0, 4.0, 0.42, choir_on=True, choir_vel=0.35)
fxB.add(riser(1.0, 0.18), 11.0)

# C. act I 12-28: 8ths ostinato, light drums, horn calls, celesta answers
P1 = ['Dm', 'Bb', 'F', 'C', 'Dm', 'Bb', 'Gm', 'A']
for i, ch in enumerate(P1):
    t0 = 12.0 + i * BAR
    pad_bar(ch, t0, BAR, 0.3)
    ostinato(ch, t0, False, 0.28)
    drumB.add(taiko(0.55, 0.8), t0); drumB.add(taiko(0.35, 0.95), t0 + 3.5 * BEAT)
    if i % 2 == 1: drumB.add(tom(0.35, 1.2), t0 + 3.0 * BEAT); drumB.add(tom(0.3, 1.0), t0 + 3.25 * BEAT)
theme([0, 1, 2, 3], 16.0, 'brass', shift=-12, vel=0.32, pan=-0.1)
theme([4, 5, 6, 7], 20.0, 'brass', shift=-12, vel=0.34, pan=-0.1)
theme([4, 5, 6, 7], 20.0, 'cel', shift=12, vel=0.16, pan=0.4)
fxB.add(riser(2.0, 0.3), 26.0)

# D. act II 28-44: 16ths, choir, theme in strings, drums build
hit(28.0, 0.8, 'D1')
P2 = ['Dm', 'C', 'Dm', 'A', 'Bb', 'F', 'Gm', 'A']
for i, ch in enumerate(P2):
    t0 = 28.0 + i * BAR
    pad_bar(ch, t0, BAR, 0.33, choir_on=True, choir_vel=0.22)
    ostinato(ch, t0, True, 0.27)
    drumB.add(taiko(0.75, 0.85), t0); drumB.add(taiko(0.45, 0.85), t0 + 1.5 * BEAT); drumB.add(taiko(0.6, 0.95), t0 + 2 * BEAT)
    for k in range(8): drumB.add(tick(0.10 + 0.06 * (k % 2 == 0)), t0 + k * BEAT / 2, pan=0.3)
    if i % 2 == 1:
        for k in range(4): drumB.add(tom(0.35 + 0.08 * k, 1.3 - 0.1 * k), t0 + (3 + k * 0.25) * BEAT)
theme([0, 1, 2, 3, 4, 5, 6, 7], 28.0, 'str', shift=12, vel=0.26, pan=0.2)
theme([0, 1, 2, 3, 4, 5, 6, 7], 28.0, 'brass', shift=0, vel=0.22, pan=-0.2)
fxB.add(riser(2.0, 0.4), 42.0); fxB.add(rev_crash(1.0, 0.5), 43.0)

# E. act III 44-60: full battle
hit(44.0, 1.2, 'D1')
P3 = ['Dm', 'Bb', 'Gm', 'A', 'Dm', 'Bb', 'C', 'A']
for i, ch in enumerate(P3):
    t0 = 44.0 + i * BAR
    pad_bar(ch, t0, BAR, 0.36, choir_on=True, choir_vel=0.3)
    ostinato(ch, t0, True, 0.3)
    r, iv = CH[ch]
    for b in range(4):
        drumB.add(taiko(0.85 if b % 2 == 0 else 0.65, 0.85), t0 + b * BEAT)
        drumB.add(taiko(0.4, 1.05), t0 + (b + 0.5) * BEAT)
    drumB.add(snare(0.35), t0 + 1 * BEAT); drumB.add(snare(0.4), t0 + 3 * BEAT)
    for k in range(16): drumB.add(tick(0.08 + 0.05 * (k % 4 == 0)), t0 + k * BEAT / 4, pan=0.35)
    brassB.add(brass(r + 12, 0.35, 0.45, growl=1.4), t0); brassB.add(brass(r + 19, 0.35, 0.3, growl=1.4), t0)
    if i % 2 == 1:
        for k in range(8): drumB.add(tom(0.3 + 0.05 * k, 1.5 - 0.08 * k), t0 + (2 + k * 0.25) * BEAT)
    if i % 4 == 0: fxB.add(crash(0.35), t0, pan=-0.2)
theme([0, 1, 2, 3, 4, 5, 6, 7], 44.0, 'brass', shift=0, vel=0.4, pan=0.0)
theme([0, 1, 2, 3, 4, 5, 6, 7], 44.0, 'brass', shift=-12, vel=0.3, pan=-0.3)
theme([0, 1, 2, 3, 4, 5, 6, 7], 44.0, 'str', shift=12, vel=0.24, pan=0.3)
fxB.add(riser(1.5, 0.35), 58.5)

# F. break 60-64: silence (the editor's ticks / rewind live in sfx), a low pulse, riser into 64
brkB.add(bass_pad(m('D1'), 3.6, 0.25), 60.3)
brkB.add(rev_crash(1.5, 0.6), 62.5); brkB.add(riser(2.0, 0.45, 90, 1200), 62.0)

# G. montage 64-76: up a tone to E minor, every beat a hit
hit(64.0, 1.3, 'E1')
P4 = ['Em', 'C', 'Am', 'B', 'Em', 'C']
for i, ch in enumerate(P4):
    t0 = 64.0 + i * BAR
    pad_bar(ch, t0, BAR, 0.38, choir_on=True, choir_vel=0.34)
    ostinato(ch, t0, True, 0.32)
    r, iv = CH[ch]
    for b in range(4):
        drumB.add(taiko(0.95, 0.85), t0 + b * BEAT); drumB.add(taiko(0.45, 1.05), t0 + (b + 0.5) * BEAT)
        brassB.add(brass(r + 12, 0.28, 0.32 if b else 0.5, growl=1.5), t0 + b * BEAT)
    drumB.add(snare(0.45), t0 + 1 * BEAT); drumB.add(snare(0.5), t0 + 3 * BEAT)
    for k in range(16): drumB.add(tick(0.1), t0 + k * BEAT / 4, pan=0.35)
    if i % 2 == 0: fxB.add(crash(0.3), t0, pan=0.25)
theme([0, 1, 2, 3, 4, 5], 64.0, 'brass', shift=2, vel=0.42)
theme([0, 1, 2, 3, 4, 5], 64.0, 'str', shift=14, vel=0.26, pan=0.3)
theme([0, 1, 2, 3, 4, 5], 64.0, 'choir', shift=2, vel=0.22)
for k in range(8): drumB.add(tom(0.45 + 0.06 * k, 1.5 - 0.08 * k), 74.0 + k * 0.25)
fxB.add(riser(2.0, 0.45), 74.0); fxB.add(rev_crash(1.2, 0.6), 74.8)

# H. end 76-88: final hit, sustained chord under the logo, last sting at 84
hit(76.0, 1.4, 'E1')
for k, s in enumerate([0, 7, 12, 15, 19]):
    strB.add(strings(m('E2') + s, 7.0, 0.22, att=0.05, rel=2.5, bright=3000), 76.0, pan=(k - 2) * 0.25)
    choirB.add(choir(m('E3') + s, 7.0, 0.22, att=0.3, rel=2.5), 76.0, pan=(k - 2) * 0.3)
bassB.add(bass_pad(m('E1'), 7.0, 0.5), 76.0)
theme([0], 79.0, 'cel', shift=14, vel=0.3, pan=0.2)
theme([3], 81.0, 'cel', shift=14, vel=0.22, pan=-0.2)
fxB.add(rev_crash(1.0, 0.45), 83.0)
drumB.add(taiko(1.0, 0.7, 1.0), 84.0); drumB.add(taiko(0.9, 0.55, 1.2), 84.01)
fxB.add(sub_boom(1.0, 3.0, 50, 24), 84.0)
brassB.add(braam(m('E1'), 0.9, 3.5), 84.0)

# ------------------------------------------------------------------ sound design cues from the editor
def dice_rattle(vel=0.5):
    n = int(0.7 * SR); out = np.zeros(n); tt = 0.0
    while tt < 0.55:
        k = int(tt * SR); L = int(0.03 * SR)
        f = rng.uniform(1800, 4200); seg = np.arange(L) / SR
        click = (np.sin(2 * np.pi * f * seg) * 0.6 + rng.standard_normal(L) * 0.5) * np.exp(-seg / 0.006)
        out[k:k + L] += click[: n - k] * (1 - tt / 0.7); tt += rng.uniform(0.025, 0.09) * (1 + tt * 2)
    return bandpass(out, 900, 9000) * vel

def keyclick(vel=0.18):
    L = int(0.03 * SR); seg = np.arange(L) / SR
    return bandpass(rng.standard_normal(L), 1500, 7000) * np.exp(-seg / 0.004) * vel

def whoosh(dur=0.7, vel=0.4):
    return noise_sweep(dur, 200, 3000, vel, 1.0) * np.hanning(int(dur * SR)) * 2

def explosion(vel=0.9):
    n = int(2.5 * SR); t = np.arange(n) / SR
    rumble = lowpass(rng.standard_normal(n), 900, 4) * np.exp(-t / 0.7) * 1.4
    crack = bandpass(rng.standard_normal(n), 600, 6000) * np.exp(-t / 0.08)
    sb = np.zeros(n); b_ = sub_boom(1.0, 0.9, 70, 30)[:n]; sb[:len(b_)] = b_
    return np.tanh(rumble + crack + sb) * vel

def clang(vel=0.5):
    n = int(1.2 * SR); t = np.arange(n) / SR; x = 0
    for f, a, d in [(523, 1, .5), (1347, .6, .3), (2210, .4, .2), (3120, .3, .12), (4415, .2, .08)]:
        x = x + a * np.sin(2 * np.pi * f * t) * np.exp(-t / d)
    return (x * 0.5 + highpass(rng.standard_normal(n), 3000) * np.exp(-t / 0.02)) * vel

def arrow(vel=0.4):
    n = int(0.35 * SR); t = np.arange(n) / SR
    return (bandpass(rng.standard_normal(n), 2500, 8000) * np.exp(-((t - 0.12) / 0.07) ** 2) + np.sin(2 * np.pi * 160 * t) * np.exp(-((t - .3) / .01) ** 2)) * vel

def buzz(vel=0.4):
    n = int(0.35 * SR); t = np.arange(n) / SR
    return lowpass(np.sign(np.sin(2 * np.pi * 92 * t)), 1200) * np.exp(-t / 0.18) * vel

def clock(vel=0.35, tock=False):
    L = int(0.05 * SR); seg = np.arange(L) / SR; f = 2200 if not tock else 1600
    return (np.sin(2 * np.pi * f * seg) * 0.6 + bandpass(rng.standard_normal(L), 2000, 8000)) * np.exp(-seg / 0.008) * vel

def swell(vel=0.3, dur=1.0):
    return noise_sweep(dur, 300, 5000, vel, 1.5)

try:
    cues = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else []
except FileNotFoundError:
    cues = []
for c in cues:
    k, t, v = c['k'], c['t'], c.get('v', 1.0)
    if k == 'dice': sfxB.add(dice_rattle(0.55 * v), t, pan=0.1)
    elif k == 'type':
        for j in range(int(c.get('n', 20))): sfxB.add(keyclick(0.16 * v * rng.uniform(.7, 1)), t + j * c.get('gap', 0.06) + rng.uniform(0, .02), pan=-0.2)
    elif k == 'whoosh': sfxB.add(whoosh(c.get('d', 0.6), 0.35 * v), t)
    elif k == 'boom': sfxB.add(explosion(0.85 * v), t)
    elif k == 'clang': sfxB.add(clang(0.5 * v), t, pan=-0.15)
    elif k == 'arrow': sfxB.add(arrow(0.45 * v), t, pan=0.2)
    elif k == 'buzz': sfxB.add(buzz(0.45 * v), t)
    elif k == 'tick':
        for j in range(int(c.get('n', 4))): sfxB.add(clock(0.35 * v, j % 2 == 1), t + j * 0.5)
    elif k == 'swell': sfxB.add(swell(0.3 * v, c.get('d', 1.0)), t)
    elif k == 'thump': sfxB.add(taiko(0.5 * v, 1.2, 0.3), t)

# ------------------------------------------------------------------ mix
def make_ir(sec, decay, sr=SR, seed=1):
    r = np.random.default_rng(seed); n = int(sec * sr); t = np.arange(n) / sr
    L = r.standard_normal(n) * np.exp(-t / decay); R = r.standard_normal(n) * np.exp(-t / decay)
    L = lowpass(L, 6000); R = lowpass(R, 6000); L[:int(.012 * sr)] = 0; R[:int(.017 * sr)] = 0
    return L / np.abs(L).sum() * 30, R / np.abs(R).sum() * 30
IRL, IRR = make_ir(3.2, 0.75)
GAIN = {'brk': 1.0, 'sfx': 1.0, 'strings': 1.0, 'celesta': 0.9, 'brass': 0.85, 'choir': 0.7, 'drums': 1.0, 'fx': 0.9, 'bass': 0.8}
L = np.zeros(N); R = np.zeros(N)
gate = np.ones(N); a0, a1, b0 = int(60.0 * SR), int(60.04 * SR), int(63.97 * SR)
gate[a0:a1] = np.linspace(1, 0, a1 - a0); gate[a1:b0] = 0
for b in (strB, celB, brassB, choirB, drumB, fxB, bassB, brkB, sfxB):
    g = GAIN[b.name]
    wl = signal.fftconvolve(b.L, IRL)[:N]; wr = signal.fftconvolve(b.R, IRR)[:N]
    gl = gate if b.name not in ('brk', 'sfx') else 1.0
    L += g * gl * ((1 - b.rev) * b.L + b.rev * wl); R += g * gl * ((1 - b.rev) * b.R + b.rev * wr)
# hard stop of the music at the break (60.0 → 60.25), keep only the post-break layers
# (the break's own sounds were added after 60.25 so they survive)
# gentle bus compression
def compress(x, thr=0.35, ratio=3.0, att=0.005, rel=0.15):
    env = np.abs(x); a = np.exp(-1 / (att * SR)); r_ = np.exp(-1 / (rel * SR))
    e = signal.lfilter([1 - r_], [1, -r_], env)
    g = np.where(e > thr, (thr + (e - thr) / ratio) / np.maximum(e, 1e-9), 1.0)
    return x * g
mono = (L + R) / 2
g = compress(mono) / np.where(np.abs(mono) > 1e-9, mono, 1)
gain_env = np.clip(np.nan_to_num(g, nan=1.0, posinf=1.0, neginf=1.0), 0, 1)
gain_env = signal.lfilter([0.002], [1, -0.998], gain_env) / signal.lfilter([0.002], [1, -0.998], np.ones(N))
L *= gain_env; R *= gain_env
out = np.stack([L, R], 1)
out = np.tanh(out / np.max(np.abs(out)) * 1.4) / np.tanh(1.4)
# fades
fi = int(0.05 * SR); out[:fi] *= np.linspace(0, 1, fi)[:, None]
fo = int(2.5 * SR); out[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
out *= 0.93
from scipy.io import wavfile
wavfile.write(sys.argv[2] if len(sys.argv) > 2 else 'score.wav', SR, (out * 32767).astype(np.int16))
print('wrote', out.shape[0] / SR, 's')
