"""Gera um wordmark ASCII 3D animado (SVG) para o README do perfil.

Texto extrudado em voxels, girado em 18 quadros (balanço lateral), cada quadro
convertido em ASCII por ray casting. O SVG imita uma janela de terminal com
revelação da esquerda para a direita e cursor.

Uso (na raiz do repo, Python 3 sem dependências):
    python scripts/wordmark.py "RYAN ADRIAN" assets/wordmark.svg
    python scripts/wordmark.py "RYAN ADRIAN" assets/wordmark.svg "titulo da janela" --preview

Letras disponíveis: as que estão em FONT. Para outro texto, desenhe as letras que faltarem.
"""
import math
import sys
from xml.sax.saxutils import escape

# Fonte bitmap 7x9 desenhada à mão (só as letras usadas + espaço).
FONT = {
    "R": ["######.", "#.....#", "#.....#", "#.....#", "######.", "#...#..", "#....#.", "#.....#", "#.....#"],
    "Y": ["#.....#", "#.....#", ".#...#.", "..#.#..", "...#...", "...#...", "...#...", "...#...", "...#..."],
    "A": [".#####.", "#.....#", "#.....#", "#.....#", "#######", "#.....#", "#.....#", "#.....#", "#.....#"],
    "N": ["#.....#", "##....#", "#.#...#", "#..#..#", "#...#.#", "#....##", "#.....#", "#.....#", "#.....#"],
    "D": ["######.", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", "######."],
    "I": ["#######", "...#...", "...#...", "...#...", "...#...", "...#...", "...#...", "...#...", "#######"],
    " ": ["....."] * 9,
}
LETTER_GAP = 2

# Geometria e animação
DEPTH = 2            # profundidade da extrusão (voxels)
FRAMES = 18
LOOP_SECONDS = 5
BASE_YAW = -12       # giro fixo: mostra a lateral esquerda das letras
YAW_AMPLITUDE = 20   # graus de balanço lateral
BASE_PITCH = 16      # inclinação fixa: mostra o topo das letras
PITCH_WOBBLE = 4
CELL_H = 0.92        # altura da célula de texto em unidades de voxel
CHAR_ASPECT = 0.6    # largura/altura de um caractere monoespaçado
SUB = 3              # subamostras por eixo em cada célula
ROWS = 12            # linhas fixas por quadro
LIGHT = (-0.45, -0.65, -1.0)  # luz vinda de cima/esquerda/frente

# SVG
FONT_SIZE = 14.3
CHAR_W = 8.6
LINE_H = 15.5
PAD_X = 18
TITLE_BAR = 34
TOP = 41.2
BOTTOM_PAD = 18
MONO = "ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"


def build_bitmap(text):
    rows = [""] * 9
    for i, ch in enumerate(text.upper()):
        glyph = FONT[ch]
        for r in range(9):
            rows[r] += glyph[r] + ("." * LETTER_GAP if i < len(text) - 1 else "")
    return [[c == "#" for c in row] for row in rows]


def normalize(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def rot_matrix(yaw, pitch):
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    ry = ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy))
    rx = ((1, 0, 0), (0, cp, -sp), (0, sp, cp))
    # inclina primeiro (X) e gira depois (Y): o giro não entorta a linha de base
    return tuple(tuple(sum(ry[i][k] * rx[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mat_vec(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


def transpose(m):
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))


def cast(bitmap, w, h, origin, direction):
    """Ray casting em grade de voxels (DDA). Retorna normal da face atingida ou None."""
    size = (w, h, DEPTH)
    tmin, tmax, axis_in = -math.inf, math.inf, 0
    for a in range(3):
        if abs(direction[a]) < 1e-12:
            if not 0 <= origin[a] <= size[a]:
                return None
            continue
        t1 = (0 - origin[a]) / direction[a]
        t2 = (size[a] - origin[a]) / direction[a]
        lo, hi = min(t1, t2), max(t1, t2)
        if lo > tmin:
            tmin, axis_in = lo, a
        tmax = min(tmax, hi)
    if tmin > tmax:
        return None
    p = [origin[a] + direction[a] * (tmin + 1e-7) for a in range(3)]
    cell = [min(max(int(math.floor(p[a])), 0), size[a] - 1) for a in range(3)]
    step = [1 if direction[a] > 0 else -1 for a in range(3)]
    t_max, t_delta = [], []
    for a in range(3):
        if abs(direction[a]) < 1e-12:
            t_max.append(math.inf)
            t_delta.append(math.inf)
        else:
            boundary = cell[a] + (1 if step[a] > 0 else 0)
            t_max.append((boundary - p[a]) / direction[a])
            t_delta.append(abs(1 / direction[a]))
    axis = axis_in
    while True:
        x, y, _ = cell
        if bitmap[y][x]:
            n = [0, 0, 0]
            n[axis] = -step[axis]
            return tuple(n)
        a = min(range(3), key=lambda i: t_max[i])
        cell[a] += step[a]
        if not 0 <= cell[a] < size[a]:
            return None
        t_max[a] += t_delta[a]
        axis = a


def render_frame(bitmap, yaw, pitch, cols):
    h, w = len(bitmap), len(bitmap[0])
    rot = rot_matrix(yaw, pitch)
    inv = transpose(rot)
    center = (w / 2, h / 2, DEPTH / 2)
    light = normalize(LIGHT)
    d_model = mat_vec(inv, (0, 0, 1))
    cell_w = CELL_H * CHAR_ASPECT
    u0 = -cols * cell_w / 2
    v0 = -ROWS * CELL_H / 2
    lines = []
    for r in range(ROWS):
        line = []
        for c in range(cols):
            hits, front, bright = 0, 0, 0.0
            for sy in range(SUB):
                for sx in range(SUB):
                    u = u0 + (c + (sx + 0.5) / SUB) * cell_w
                    v = v0 + (r + (sy + 0.5) / SUB) * CELL_H
                    o = mat_vec(inv, (u, v, -1000))
                    o = (o[0] + center[0], o[1] + center[1], o[2] + center[2])
                    n = cast(bitmap, w, h, o, d_model)
                    if n is None:
                        continue
                    hits += 1
                    if n == (0, 0, -1):
                        front += 1
                    nw = mat_vec(rot, n)
                    bright += max(0.0, sum(nw[i] * light[i] for i in range(3)))
            line.append(pick_char(hits / SUB ** 2, front, hits, bright))
        lines.append("".join(line))
    return lines


def pick_char(coverage, front, hits, bright):
    if coverage < 0.15:
        return " "
    if front * 2 >= hits:  # face da frente domina
        return "S" if coverage > 0.55 else "s" if coverage > 0.3 else "`"
    b = bright / hits
    ramp = "`:-=+*"
    if coverage < 0.4:
        return ramp[0] if b < 0.5 else ramp[1]
    return ramp[min(len(ramp) - 1, int(b * len(ramp)))]


def trim_columns(frames):
    """Corta colunas vazias nas bordas comuns a todos os quadros."""
    width = len(frames[0][0])
    used = [any(f[r][c] != " " for f in frames for r in range(ROWS)) for c in range(width)]
    first = used.index(True)
    last = width - 1 - used[::-1].index(True)
    return [[row[max(0, first - 2): last + 3] for row in f] for f in frames]


def svg(frames, title, label):
    cols = len(frames[0][0])
    text_w = cols * CHAR_W
    width = round(text_w + PAD_X * 2)
    body_h = ROWS * LINE_H
    height = round(TOP + body_h + BOTTOM_PAD)
    first_baseline = TOP + LINE_H * 0.8
    reveal_begin, reveal_dur = 0.2, 2.2
    ease = 'calcMode="spline" keyTimes="0;1" keySplines="0.25 0.1 0.25 1"'
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">',
        f"<title>{escape(label)}</title>",
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#111722"/><stop offset="1" stop-color="#0b0e14"/></linearGradient>',
        f'<clipPath id="reveal"><rect x="{PAD_X}" y="{TOP}" height="{body_h}" width="0">'
        f'<animate attributeName="width" from="0" to="{text_w:.1f}" begin="{reveal_begin}s" '
        f'dur="{reveal_dur}s" fill="freeze" {ease}/></rect></clipPath>',
        "</defs>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="url(#bg)" stroke="#2a3038"/>',
        f'<path d="M0.5 12.5a12 12 0 0 1 12-12h{width - 25}a12 12 0 0 1 12 12v{TITLE_BAR - 12}h-{width - 1}z" fill="#161b22"/>',
        f'<rect x="0.5" y="{TITLE_BAR}" width="{width - 1}" height="1" fill="#2a3038"/>',
        '<circle cx="22" cy="17.5" r="6" fill="#ff5f56"/>'
        '<circle cx="42" cy="17.5" r="6" fill="#ffbd2e"/>'
        '<circle cx="62" cy="17.5" r="6" fill="#27c93f"/>',
        f'<text x="{width / 2}" y="22" text-anchor="middle" font-family="{MONO}" font-size="12.5" '
        f'fill="#8b949e">{escape(title)}</text>',
        '<g clip-path="url(#reveal)">',
    ]
    n = len(frames)
    for i, frame in enumerate(frames):
        a, b = i / n, (i + 1) / n
        if i == 0:
            anim = f'values="1;0" keyTimes="0;{b:.4f}"'
        elif i == n - 1:
            anim = f'values="0;1" keyTimes="0;{a:.4f}"'
        else:
            anim = f'values="0;1;0" keyTimes="0;{a:.4f};{b:.4f}"'
        out.append(f'<g opacity="{1 if i == 0 else 0}">')
        out.append(
            f'<animate attributeName="opacity" calcMode="discrete" {anim} '
            f'dur="{LOOP_SECONDS}s" repeatCount="indefinite"/>'
        )
        for r, row in enumerate(frame):
            if not row.strip():
                continue
            y = first_baseline + r * LINE_H
            out.append(
                f'<text xml:space="preserve" x="{PAD_X}" y="{y:.1f}" textLength="{text_w:.1f}" '
                f'lengthAdjust="spacing" font-family="{MONO}" font-size="{FONT_SIZE}" '
                f'fill="#c9d1d9">{escape(row)}</text>'
            )
        out.append("</g>")
    out.append("</g>")
    # cursor que acompanha a revelação
    out.append(
        f'<rect y="{TOP}" width="3" height="{body_h}" fill="#c9d1d9" opacity="0">'
        f'<set attributeName="opacity" to="0.9" begin="{reveal_begin}s"/>'
        f'<set attributeName="opacity" to="0" begin="{reveal_begin + reveal_dur}s" fill="freeze"/>'
        f'<animate attributeName="x" from="{PAD_X}" to="{PAD_X + text_w:.1f}" begin="{reveal_begin}s" '
        f'dur="{reveal_dur}s" fill="freeze" {ease}/></rect>'
    )
    out.append("</svg>")
    return "\n".join(out)


def main():
    text = sys.argv[1]
    dest = sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else "1kibe@github: ~$ ./wordmark.sh --name"
    bitmap = build_bitmap(text)
    w = len(bitmap[0])
    cols = int(w / (CELL_H * CHAR_ASPECT)) + 30
    frames = []
    for i in range(FRAMES):
        phase = 2 * math.pi * i / FRAMES
        yaw = math.radians(BASE_YAW + YAW_AMPLITUDE * math.sin(phase))
        pitch = math.radians(BASE_PITCH + PITCH_WOBBLE * math.cos(phase))
        frames.append(render_frame(bitmap, yaw, pitch, cols))
    frames = trim_columns(frames)
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg(frames, title, f"{text} em ASCII 3D"))
    print(f"ok: {len(frames)} quadros, {len(frames[0][0])} colunas -> {dest}")
    if "--preview" in sys.argv:
        for i in (0, 4, 13):
            print(f"--- quadro {i}")
            print("\n".join(frames[i]))


if __name__ == "__main__":
    main()
