"""Gera a trilha e os efeitos sonoros do vídeo (síntese procedural) e mixa no MP4.

Uso: python3 video/audio.py [video_mudo.mp4] [saida.mp4]
Os instantes dos efeitos acompanham a linha do tempo de video/motions.html.
"""
import subprocess, sys, os
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 44100
DUR = 45.0
N = int(SR * DUR)
rng = np.random.default_rng(11)
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- linha do tempo (igual à do motions.html) ----------
SC = dict(intro=0.0, grid=3.8, flow=8.8, brick=13.8, sim=20.4, type=30.8, dash=34.8, ui=39.8)
BEAT = 60 / 110          # 110 bpm, grade ancorada em 8.8 s (entrada da bateria)
GRID0 = SC['flow']

# ---------- barramentos estéreo ----------
MUS = np.zeros((2, N)); SFX = np.zeros((2, N)); REV = np.zeros((2, N))

def put(bus, x, t, g=1.0, pan=0.0, send=0.0):
    i = int(t * SR)
    if i >= N or i + len(x) <= 0:
        return
    a, b = max(0, -i), min(len(x), N - i)
    seg = x[a:b] * g
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    bus[0, i + a:i + b] += seg * l
    bus[1, i + a:i + b] += seg * r
    if send:
        REV[0, i + a:i + b] += seg * l * send
        REV[1, i + a:i + b] += seg * r * send

def tt(d): return np.arange(int(d * SR)) / SR
def midi(n): return 440.0 * 2 ** ((n - 69) / 12)
def sos(x, kind, f, order=2):
    return signal.sosfilt(signal.butter(order, f, kind, fs=SR, output='sos'), x)
def lp(x, f, o=2): return sos(x, 'low', min(f, SR * .45), o)
def hp(x, f, o=2): return sos(x, 'high', f, o)
def bp(x, lo, hi, o=2): return sos(x, 'band', [lo, min(hi, SR * .45)], o)
def noise(d): return rng.standard_normal(int(d * SR))
def decay(d, a=.003, r=.1):
    t = tt(d); return np.minimum(t / a, 1) * np.exp(-t / r)
def swell(d, up=.5):
    t = tt(d) / d; return np.where(t < up, (t / up) ** 2, ((1 - t) / (1 - up)) ** 1.5)
def sine(f, d):
    f = np.broadcast_to(f, int(d * SR)) if np.ndim(f) == 0 else f
    return np.sin(2 * np.pi * np.cumsum(f) / SR)
def saw(f, d):
    f = np.broadcast_to(f, int(d * SR)) if np.ndim(f) == 0 else f
    return signal.sawtooth(2 * np.pi * np.cumsum(f) / SR)

# ---------- peças de efeito ----------
def whoosh(d, f0=300, f1=7000):
    n = noise(d); out = np.zeros_like(n); t = tt(d) / d
    cs = np.geomspace(f0, f1, 8)
    for k, c in enumerate(cs):
        band = bp(n, c * .7, c * 1.4)
        out += band * np.exp(-((t - k / 7) / .2) ** 2)
    return out * np.sin(np.pi * t) ** 1.2 * 1.6

def thump(f0=130, f1=48, d=.35, r=.09):
    fr = np.linspace(f0, f1, int(d * SR)) ** 1.0
    return sine(fr, d) * decay(d, .002, r)

def click(d=.02, f=3500):
    return hp(noise(d), f) * decay(d, .0005, d / 4)

def bell(f, d=1.2, r=.45):
    out = 0
    for ratio, amp in [(1, 1), (2.01, .5), (2.76, .35), (4.07, .2), (5.4, .12)]:
        out = out + amp * np.sin(2 * np.pi * f * ratio * tt(d)) * np.exp(-tt(d) / (r / (1 + .25 * (ratio - 1))))
    return out * np.minimum(tt(d) / .002, 1)

def pluck(f, d=.3, r=.12):
    return (saw(f, d) + .5 * saw(f * 1.004, d)) * decay(d, .002, r)

def crunch(d=.45):
    n = lp(noise(d), 1800) * decay(d, .002, .13)
    th = np.zeros_like(n); th[:int(.35 * SR)] = thump(95, 42, .35, .12)
    deb = np.zeros_like(n)
    for _ in range(14):
        p = int(rng.uniform(0, .3) * SR); c = click(.012, rng.uniform(1200, 4000))
        deb[p:p + len(c)] += c * rng.uniform(.3, 1)
    return n * .9 + th * 1.3 + deb * .8

def glitch(d=.22):
    out = np.zeros(int(d * SR)); pos = 0
    while pos < len(out):
        step = int(rng.uniform(.004, .014) * SR)
        f = rng.choice([220, 330, 440, 880, 1320, 1760])
        seg = np.sign(np.sin(2 * np.pi * f * np.arange(step) / SR)) * rng.uniform(.4, 1)
        out[pos:pos + step] = seg[:len(out) - pos]
        pos += step
    n = rng.standard_normal(len(out)) * (rng.random(len(out)) > .6)
    return (out * .5 + n * .35) * np.hanning(len(out)) ** .3

# ======================================================================
#  MÚSICA
# ======================================================================
CH = [(57, [57, 60, 64, 67]), (53, [53, 57, 60, 64]), (48, [48, 52, 55, 59]), (55, [55, 59, 62, 66])]  # Am(add9), F, C, G
bar = BEAT * 4
n_bars = int((DUR - GRID0) / bar) + 6
b0 = GRID0 - 6 * bar   # barras começam antes de 0 para cobrir o início

def level(t, pts):  # interpolação por pontos (tempo, ganho)
    return float(np.interp(t, [p[0] for p in pts], [p[1] for p in pts]))

PAD_G = [(0, .0), (1.5, .55), (30, .55), (34.8, .75), (44, .8), (45, 0)]
for k in range(n_bars):
    t0 = b0 + k * bar
    if t0 + bar < 0 or t0 > DUR: continue
    root, notes = CH[k % 4]
    d = bar + .9
    pad = np.zeros(int(d * SR))
    for nn in notes:
        f = midi(nn + 12)
        pad += saw(f * .997, d) + saw(f * 1.003, d) + .6 * np.sin(2 * np.pi * f * tt(d))
    pad = lp(pad, 1500) * np.minimum(tt(d) / .5, 1) * np.minimum((d - tt(d)) / .7, 1) * .07
    put(MUS, pad, t0, level(t0 + bar / 2, PAD_G), send=.35)
    # baixo
    if t0 >= GRID0 - .01:
        gb = level(t0, [(8.8, .5), (20.4, .35), (30.8, .8), (34.8, .6), (43.5, .6), (44.6, 0)])
        for s8 in range(8):
            ts = t0 + s8 * BEAT / 2
            if ts > 44.0: continue
            nb = root - 12 + (12 if s8 % 4 == 3 else 0)
            b = lp(saw(midi(nb), BEAT / 2 * .9) + sine(midi(nb - 12 if nb > 40 else nb), BEAT / 2 * .9), 400)
            put(MUS, b * decay(BEAT / 2 * .9, .004, .16) * .55, ts, gb)

# arpejo (a partir da grade)
arp_bus = np.zeros((2, N))
AG = [(3.8, .0), (4.6, .38), (20.4, .24), (30.8, .5), (34.8, .55), (43.8, .5), (44.4, 0)]
step = BEAT / 4
t = 3.8
k = 0
pat = [0, 2, 1, 3, 2, 3, 1, 2]
while t < 44.4:
    kb = int((t - b0) // bar)
    notes = CH[kb % 4][1]
    nn = notes[pat[k % 8]] + (24 if (k // 8) % 2 else 12)
    g = level(t, AG)
    if g > .01:
        put(arp_bus, pluck(midi(nn), .3, .13), t, g * .09, pan=(-.4 if k % 2 else .4), send=.4)
    t += step; k += 1
MUS += lp(arp_bus, 4500)

# bateria
t = GRID0 + BEAT
beat_i = 1
while t < 43.95:
    if t >= SC['sim'] and t < SC['type']:
        kg, hg = .55, .35
    elif t >= SC['type'] and t < SC['dash']:
        kg, hg = 1.0, .6
    else:
        kg, hg = .85, .5
    put(MUS, thump(160, 46, .34, .11) * 1.1, t, .55 * kg)
    # chimbal fechado fora do tempo e 16ths leves
    for off, gg in [(BEAT / 2, 1.0), (BEAT / 4 * 3, .35), (BEAT / 4, .35)]:
        h = hp(noise(.05), 7000) * decay(.05, .001, .012)
        put(MUS, h, t + off, .13 * hg * gg, pan=.25)
    if beat_i % 4 == 2 or beat_i % 4 == 0:   # tempos 2 e 4: palmas leves
        c = bp(noise(.18), 1000, 3200) * decay(.18, .002, .05)
        put(MUS, c, t, .09 * hg, send=.25)
    t += BEAT; beat_i += 1

# ======================================================================
#  EFEITOS
# ======================================================================
# transições entre cenas
for name in ['grid', 'flow', 'brick', 'sim', 'type', 'dash', 'ui']:
    a = SC[name]
    put(SFX, whoosh(.9), a - .5, .30, send=.3)
    put(SFX, thump(110, 40, .5, .14), a - .02, .5)

# abertura
t0 = SC['intro']
rise = (hp(noise(1.4), 1200) * swell(1.4, .85) * .35 + sine(np.linspace(180, 1500, int(1.4 * SR)), 1.4) * swell(1.4, .9) * .12)
put(SFX, rise, .2, 1, send=.3)
put(SFX, thump(70, 32, 1.2, .35), 1.0, 1.2)
put(SFX, bell(midi(81), 2.2, .9) * .25, 1.0, 1, send=.7)
put(SFX, bell(midi(88), 2.0, .8) * .18, 1.05, 1, send=.7)
for i in range(9):
    put(SFX, bell(midi(69 + [0, 3, 7, 10, 12, 10, 7, 3, 0][i]), .35, .1) * .14, 1.8 + i * .07 + .05, 1, pan=-.6 + i * .15, send=.3)
put(SFX, whoosh(.7, 800, 9000), 2.7, .18)

# grade 3D: 17 olarias aparecem com pings de pentatônica
PENT = [69, 72, 74, 76, 79, 81, 84]
for n in range(17):
    ts = SC['grid'] + 1.0 + n * .13
    put(SFX, bell(midi(PENT[n % 7] + 12 * (n // 7)), .9, .22) * .22, ts, 1, pan=((n * 37) % 20) / 10 - 1, send=.6)
    put(SFX, click(.01, 5000), ts, .1)
put(SFX, thump(100, 45, .4, .12), SC['grid'] + 1.0, .5)

# flow field: respiração de vento + sparkle
put(SFX, bp(noise(4.5), 400, 3000) * swell(4.5, .35) * .1, SC['flow'] + .2, 1, send=.5)
put(SFX, whoosh(1.0, 400, 6000), SC['flow'] + .3, .22)

# tijolos virando chamote
B = SC['brick']
BRICK_T = [1.7, 2.3, 2.9, 3.5]
for i in range(4):
    ts = B + .9 + i * .15
    put(SFX, thump(150, 55, .22, .06) * .9, ts, .75)
    put(SFX, click(.015, 2500), ts, .5, pan=-.3 + i * .2)
# motor/rotores a partir de 14.5 até o fim
d = BRICK_T[-1] + 2.4
mot = lp(saw(np.linspace(48, 62, int(d * SR)), d), 300) * .5 + bp(noise(d), 80, 420) * .5
mot *= np.minimum(tt(d) / .6, 1) * np.minimum((d - tt(d)) / 1.2, 1) * (1 + .3 * np.sin(2 * np.pi * 6.5 * tt(d)))
put(SFX, mot, B + .8, .35, send=.1)
for T in BRICK_T:
    put(SFX, whoosh(.45, 500, 5000), B + T - 1.0 + .3, .15)
    put(SFX, crunch(.5), B + T, .75, send=.2)
# grãos caindo
for e, T in enumerate(BRICK_T):
    for g in range(70):
        ts = B + T + .9 + rng.uniform(0, .7) + rng.uniform(.4, .8)
        put(SFX, click(.008, rng.uniform(2500, 7000)) * rng.uniform(.5, 1), ts, .09, pan=rng.uniform(-.5, .5))
hiss = bp(noise(3.6), 2500, 9000) * swell(3.6, .55) * .06
put(SFX, hiss, B + BRICK_T[0] + 1.5, 1, send=.1)
put(SFX, bell(midi(81), 1.8, .6) * .22, B + 4.0, 1, send=.6)
put(SFX, bell(midi(76), 1.6, .5) * .15, B + 4.1, 1, send=.6)
put(SFX, bell(midi(84), 1.6, .5) * .12, B + 5.2, 1, send=.7)

# simulação do protótipo
S = SC['sim']
d = 9.8
hum = lp(saw(np.linspace(55, 58, int(d * SR)), d), 250) * .55 + bp(noise(d), 100, 600) * .35
hum *= np.minimum(tt(d) / .8, 1) * np.minimum((d - tt(d)) / 1.0, 1) * (1 + .25 * np.sin(2 * np.pi * 5.5 * tt(d)))
put(SFX, hum, S + .5, .30, send=.1)
for i in range(4):
    put(SFX, bell(midi(76 + i * 3), .35, .12) * .14, S + .8 + i * .15, 1, pan=.3, send=.3)
for ts, nn in [(2.1, 79), (5.0, 83), (7.0, 88)]:
    put(SFX, bell(midi(nn), .8, .25) * .2, S + ts, 1, send=.5)
    put(SFX, click(.012, 4000), S + ts, .3)
# batidas graves enquanto tritura (passo 2)
tb = S + 2.3
while tb < S + 5.0:
    put(SFX, thump(85, 45, .3, .1), tb, .35)
    put(SFX, lp(noise(.12), 900) * decay(.12, .002, .04), tb + .01, .3)
    tb += .42

# tipografia com glitch
Tn = SC['type']
put(SFX, thump(90, 28, 1.0, .4), Tn + .2, 1.1)
put(SFX, whoosh(.8, 200, 3000), Tn - .1, .3)
put(SFX, hp(noise(1.0), 3000) * swell(1.0, .9) * .25, Tn - .8, 1, send=.4)
for ts in [1.6, 2.5, 3.2, 3.55]:
    put(SFX, glitch(.22), Tn + ts, .32, pan=rng.uniform(-.5, .5), send=.15)
    put(SFX, thump(70, 30, .3, .09), Tn + ts, .5)
put(SFX, bell(midi(81), 1.5, .5) * .12, Tn + 1.0, 1, send=.6)

# dashboard
D = SC['dash']
for a in [.3, 1.1, 1.3, 1.6]:
    put(SFX, whoosh(.5, 800, 6000), D + a - .1, .13)
for k in range(32):
    u = k / 31
    ts = D + .7 + 1.9 * (1 - (1 - u) ** .25)
    put(SFX, sine(midi(84 + int(u * 12)), .03) * decay(.03, .001, .01) * .5, ts, .14, pan=-.2, send=.2)
put(SFX, sine(np.linspace(300, 1800, int(1.7 * SR)), 1.7) * swell(1.7, .9) * .08, D + 1.5, 1, pan=.25, send=.3)
put(SFX, bell(midi(88), 1.4, .5) * .2, D + 2.7, 1, send=.5)
for i in range(2):
    ts = D + 1.7 + i * .35
    put(SFX, thump(220, 80, .25, .07), ts + .5, .55)
    put(SFX, bell(midi([76, 81][i]), .7, .2) * .18, ts + .6, 1, send=.4)

# interface e fechamento
U = SC['ui']
put(SFX, whoosh(.6, 600, 5000), U + .5, .12)
for i, ts in enumerate([2.0, 2.6, 3.2]):
    put(SFX, click(.015, 3000), U + ts, .55)
    put(SFX, sine(np.linspace(520, 780, int(.09 * SR)), .09) * decay(.09, .002, .035), U + ts + .01, .45)
    put(SFX, bell(midi(81 + i * 2), .5, .15) * .12, U + ts + .05, 1, send=.4)
    put(SFX, whoosh(.3, 1500, 6000), U + ts - .35, .08, pan=.4)
tb = U + 4.15
put(SFX, click(.02, 1800), tb, .8); put(SFX, thump(160, 70, .18, .05), tb, .6)
put(SFX, whoosh(.7, 400, 7000), tb + .05, .18)
for i, nn in enumerate([81, 85, 88, 93]):
    put(SFX, bell(midi(nn), 1.4, .55) * .22, U + 4.32 + i * .07, 1, pan=-.4 + i * .27, send=.6)
put(SFX, bell(midi(81), 3.0, 1.2) * .2, U + 4.6, 1, send=.8)
put(SFX, bell(midi(93), 2.6, 1.0) * .12, U + 4.65, 1, send=.8)
put(SFX, thump(60, 30, 1.5, .5), U + 4.6, .8)

# ======================================================================
#  MIXAGEM
# ======================================================================
ir_d = 1.8
ir = rng.standard_normal((2, int(ir_d * SR))) * np.exp(-tt(ir_d) * 3.2)
ir = hp(lp(ir, 5000), 180)
rev = np.stack([signal.fftconvolve(REV[c], ir[c])[:N] for c in range(2)]) * .06

# ducking da música sob os efeitos fortes
env = np.sqrt(np.maximum(signal.sosfilt(signal.butter(2, 6, 'low', fs=SR, output='sos'), SFX.mean(0) ** 2), 0))
duck = 1 - np.clip(env * 5, 0, .35)
mix = MUS * .55 * duck + SFX + rev
# fade in/out e limitador suave
fade = np.minimum(np.arange(N) / (.4 * SR), 1) * np.minimum((N - np.arange(N)) / (1.6 * SR), 1)
mix = mix * fade
mix = hp(mix, 28, 2)
peak = np.max(np.abs(mix))
mix = np.tanh(mix / peak * 1.9) / np.tanh(1.9) * .89
print(f'pico {np.max(np.abs(mix)):.2f}  rms {np.sqrt(np.mean(mix ** 2)):.3f}')

wav = os.path.join(HERE, '.cache', 'audio.wav')
os.makedirs(os.path.dirname(wav), exist_ok=True)
wavfile.write(wav, SR, (mix.T * 32767).astype(np.int16))

if len(sys.argv) > 1:
    silent = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'jubartech-motions.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', silent, '-i', wav, '-c:v', 'copy', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=9', '-ar', '44100', '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart', '-shortest', out], check=True)
    print('ok ->', out)
