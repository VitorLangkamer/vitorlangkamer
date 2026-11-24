#!/usr/bin/env python3
"""Gera os SVGs animados do README (tema café de desenvolvedor).

Uso:  pip install fonttools brotli pillow && python3 scripts/build.py

Cada SVG é autossuficiente: as fontes entram como subconjunto em base64 e as
imagens como data URI, porque o GitHub exibe o SVG dentro de <img> e bloqueia
qualquer recurso externo. Todas as animações são CSS e respeitam
prefers-reduced-motion: sem animação, cada SVG mostra o estado final.
"""

import base64
import io
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "scripts" / "fonts"
IMAGES = ROOT / "scripts" / "images"
OUT = ROOT / "assets"
ICONS = json.loads((ROOT / "scripts" / "icons.json").read_text())

# Paleta do manual de identidade (DESIGN.md do portfólio, seção 5)
CAFE = "#1C110D"
CREME = "#F3E8DA"
MARROM = "#4A2A1E"
LARANJA = "#E33A0A"
LARANJA_CLARO = "#EA3C0A"
TIJOLO = "#6E1407"
CINZA = "#8C827A"
SURFACE = "#2E1B14"
LATTE = "#D9B48F"  # strings no editor: creme tostado

# ---------------------------------------------------------------- fontes ----

FONT_SPECS = {
    # chave: (arquivo, peso da instância ou None)
    "thin": ("Outfit-Variable.woff2", 200),
    "reg": ("Outfit-Variable.woff2", 400),
    "med": ("Outfit-Variable.woff2", 500),
    "bold": ("Outfit-Variable.woff2", 750),
    "serif": ("Fraunces-Italic-Variable.woff2", 500),
    "mono": ("JetBrainsMono-400.woff2", None),
    "monom": ("JetBrainsMono-500.woff2", None),
    "monob": ("JetBrainsMono-700.woff2", None),
}
_font_cache = {}


def font(key):
    if key not in _font_cache:
        file, wght = FONT_SPECS[key]
        f = TTFont(FONTS / file)
        if wght is not None:
            f = instancer.instantiateVariableFont(f, {"wght": wght})
        _font_cache[key] = f
    return _font_cache[key]


def measure(key, text, size, spacing=0.0):
    """Largura do texto em px (avanços da fonte + letter-spacing)."""
    f = font(key)
    cmap = f.getBestCmap()
    hmtx = f["hmtx"]
    upm = f["head"].unitsPerEm
    total = 0
    for ch in text:
        gid = cmap.get(ord(ch))
        if gid is None:
            raise ValueError(f"glifo ausente em {key}: {ch!r}")
        total += hmtx[gid][0]
    return total / upm * size + spacing * len(text)


def font_face(key, chars):
    f = font(key)
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    src = TTFont(buf)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga"]
    opts.name_IDs = []
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars)))
    sub.subset(src)
    out = io.BytesIO()
    src.flavor = "woff2"
    src.save(out)
    b64 = base64.b64encode(out.getvalue()).decode()
    return f"@font-face{{font-family:'vl-{key}';src:url(data:font/woff2;base64,{b64}) format('woff2');}}"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------- builder -----


class SVG:
    def __init__(self, w, h, title, desc):
        self.w, self.h = w, h
        self.title, self.desc = title, desc
        self.used = {}
        self.defs = []
        self.css = []
        self.body = []

    def use(self, key, text):
        self.used.setdefault(key, set()).update(text)

    def add(self, s):
        self.body.append(s)

    def text(self, x, y, s, key, size, fill=CREME, spacing=0, anchor=None, cls=None, extra=""):
        self.use(key, s)
        a = f' text-anchor="{anchor}"' if anchor else ""
        c = f' class="{cls}"' if cls else ""
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        return (f'<text x="{x:.2f}" y="{y:.2f}" font-family="vl-{key}" font-size="{size}" '
                f'fill="{fill}"{ls}{a}{c}{extra}>{esc(s)}</text>')

    def runs(self, x, y, parts, size):
        """Uma linha com trechos em fontes diferentes. parts = [(key, texto, cor)]."""
        out = [f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}">']
        width = 0
        for key, s, fill in parts:
            self.use(key, s)
            out.append(f'<tspan font-family="vl-{key}" fill="{fill}">{esc(s)}</tspan>')
            width += measure(key, s, size)
        out.append("</text>")
        return "".join(out), width

    def render(self):
        faces = "".join(font_face(k, v) for k, v in self.used.items())
        css = (
            faces
            + "text{white-space:pre;}"
            + "".join(self.css)
            + "@media (prefers-reduced-motion: reduce){*{animation:none!important;}}"
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" role="img" '
            f'aria-labelledby="t d"><title id="t">{esc(self.title)}</title><desc id="d">{esc(self.desc)}</desc>'
            f"<defs><style>{css}</style>{''.join(self.defs)}</defs>{''.join(self.body)}</svg>"
        )

    def save(self, name):
        OUT.mkdir(exist_ok=True)
        data = self.render()
        (OUT / name).write_text(data, encoding="utf-8")
        print(f"{name}: {len(data) / 1024:.1f} KB")


def image_uri(path, max_w=None, max_h=None, quality=80):
    im = Image.open(path)
    has_alpha = im.mode in ("RGBA", "LA")
    im = im.convert("RGBA" if has_alpha else "RGB")
    if max_w or max_h:
        im.thumbnail((max_w or 10_000, max_h or 10_000), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode(), im.size


def logo(x, y, scale, color=CREME):
    """Símbolo VL (reconstrução do DESIGN.md, seção 4.5)."""
    return (f'<g transform="translate({x} {y}) scale({scale})">'
            f'<polygon points="0,0 50,0 130,148 82,148" fill="{color}"/>'
            f'<rect x="124" y="0" width="51" height="108" fill="{color}"/>'
            f'<rect x="175" y="108" width="40" height="40" fill="{LARANJA}"/></g>')


def icon(slug, x, y, size, fill=CREME, extra=""):
    s = size / 24
    return f'<path transform="translate({x} {y}) scale({s:.4f})" d="{ICONS[slug]}" fill="{fill}"{extra}/>'


def card_bg(svg, rx=22, glow=True):
    svg.defs.append(
        f'<clipPath id="card"><rect width="{svg.w}" height="{svg.h}" rx="{rx}"/></clipPath>'
        f'<radialGradient id="glow" cx="50%" cy="0%" r="60%">'
        f'<stop offset="0" stop-color="{CREME}" stop-opacity=".28"/>'
        f'<stop offset="1" stop-color="{CREME}" stop-opacity="0"/></radialGradient>'
    )
    svg.add(f'<rect width="{svg.w}" height="{svg.h}" rx="{rx}" fill="{CAFE}"/>')
    if glow:
        svg.add(f'<ellipse cx="{svg.w * 0.55}" cy="0" rx="{svg.w * 0.42}" ry="{svg.h * 0.5}" '
                f'fill="url(#glow)" class="glow"/>')
        svg.css.append(".glow{animation:breathe 7s ease-in-out infinite;transform-origin:55% 0;transform-box:view-box;}"
                       "@keyframes breathe{50%{opacity:.6;transform:scale(1.06);}}")


def ticker(svg, y, h, words, size=13, key="monom", speed=40, fill=CREME, bg=MARROM, sep=LARANJA, spacing=1.6):
    """Faixa que corre sem fim. Separadores são quadrados laranja (assinatura da marca)."""
    gap = 22
    sq = 6
    items = []
    x = 0
    for w in words:
        items.append(svg.text(x, y + h / 2 + size * 0.36, w, key, size, fill, spacing=spacing))
        x += measure(key, w, size, spacing) + gap
        items.append(f'<rect x="{x:.2f}" y="{y + h / 2 - sq / 2:.2f}" width="{sq}" height="{sq}" fill="{sep}"/>')
        x += sq + gap
    period = x
    reps = int(svg.w // period) + 2
    groups = "".join(f'<g transform="translate({i * period:.2f} 0)">{"".join(items)}</g>' for i in range(reps))
    svg.add(f'<rect x="0" y="{y}" width="{svg.w}" height="{h}" fill="{bg}"/>')
    svg.add(f'<g clip-path="url(#card)"><g class="tick">{groups}</g></g>')
    svg.css.append(f".tick{{animation:tick {period / speed:.2f}s linear infinite;}}"
                   f"@keyframes tick{{to{{transform:translateX(-{period:.2f}px);}}}}")


def steam(svg, cx, base, height, n=3, spread=16, stroke=CREME, width=3, cls="st"):
    """Fumaça de café: linhas onduladas que sobem e somem."""
    out = []
    for i in range(n):
        x = cx + (i - (n - 1) / 2) * spread
        d = (f"M{x} {base} c-8 -{height * .18} 8 -{height * .32} 0 -{height * .5} "
             f"s8 -{height * .32} 0 -{height * .5}")
        out.append(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{width}" '
                   f'stroke-linecap="round" class="{cls}" style="animation-delay:{i * .7:.1f}s"/>')
    svg.css.append(f".{cls}{{opacity:.55;stroke-dasharray:{height * 1.25:.0f};animation:{cls} 2.4s ease-in-out infinite both;}}"
                   f"@keyframes {cls}{{0%{{stroke-dashoffset:{height * 1.25:.0f};opacity:0;transform:translateY(6px);}}"
                   f"40%{{opacity:.6;}}100%{{stroke-dashoffset:-{height * 1.25:.0f};opacity:0;transform:translateY(-10px);}}}}")
    return "".join(out)


# --------------------------------------------------------------- header ----


def build_header():
    W, H = 1000, 460
    svg = SVG(W, H, "Victor Langkamer · Dev Front-end, Web Designer e UI/UX Designer",
              "Cabeçalho em tons de café com o retrato de Victor, o símbolo VL e as funções digitadas em sequência.")
    card_bg(svg)

    # Nome gigante ao fundo, como no hero do portfólio
    svg.add(f'<g clip-path="url(#card)" opacity=".05">'
            + svg.text(W - 18, 330, "LANGKAMER", "bold", 150, CREME, anchor="end", spacing=-2) + "</g>")

    # Retrato recortado
    uri, (iw, ih) = image_uri(IMAGES / "profile_nobg.webp", max_h=760, quality=78)
    ph = 372
    pw = iw / ih * ph
    px = W - pw + 34
    svg.add(f'<g clip-path="url(#card)"><image class="photo" href="{uri}" x="{px:.1f}" y="{H - 44 - ph}" '
            f'width="{pw:.1f}" height="{ph}" preserveAspectRatio="xMidYMax meet"/></g>')
    svg.css.append(".photo{animation:rise 1.2s cubic-bezier(.2,.7,.2,1) both;}"
                   "@keyframes rise{from{opacity:0;transform:translateY(24px);}}")

    # Topo: logo + nome em minúsculas, tagline mono
    svg.add(logo(40, 36, 0.2))
    svg.add(svg.text(92, 50, "victor", "bold", 17, CREME))
    svg.add(svg.text(92, 68, "langkamer", "bold", 17, CREME))
    tag = ["WEB DESIGN", "INTERFACES", "TECNOLOGIA"]
    x = W - 40
    parts = []
    for i, t in enumerate(reversed(tag)):
        wdt = measure("mono", t, 11, 2)
        x -= wdt
        parts.append(svg.text(x, 58, t, "mono", 11, CREME, spacing=2))
        if i < len(tag) - 1:
            x -= 14
            parts.append(f'<rect x="{x:.1f}" y="51" width="5" height="5" fill="{LARANJA}"/>')
            x -= 9
    svg.add("".join(parts))

    # Etiqueta da formação
    lx, ly = 40, 150
    label = "ANÁLISE E DESENVOLVIMENTO DE SISTEMAS · FORMADO"
    lw = measure("mono", label, 11, 1.4) + 40
    svg.add(f'<g class="badge"><rect x="{lx}" y="{ly - 18}" width="{lw:.1f}" height="28" rx="14" fill="none" '
            f'stroke="{CREME}" stroke-opacity=".28"/>'
            f'<circle cx="{lx + 16}" cy="{ly - 4}" r="4" fill="{LARANJA}" class="dot"/>'
            + svg.text(lx + 28, ly, label, "mono", 11, CREME, spacing=1.4) + "</g>")
    svg.css.append(".badge{animation:fade .8s .2s both;}.dot{animation:pulse 1.8s ease-in-out infinite;transform-box:fill-box;transform-origin:center;}"
                   "@keyframes pulse{50%{opacity:.35;transform:scale(.7);}}"
                   "@keyframes fade{from{opacity:0;transform:translateY(10px);}}")

    # "Eu sou" + funções digitadas
    svg.add(f'<g class="hi">' + svg.text(38, 222, "Eu sou", "thin", 52, CREME) + "</g>")
    svg.css.append(".hi{animation:fade .8s .35s both;}")
    roles = ["Dev Front-end", "Web Designer", "UI/UX Designer"]
    size = 64
    rx0, ry = 40, 292
    t_char, hold, t_del, gap = 0.075, 2.6, 0.03, 0.4
    timeline = []  # (role, start, n)
    t = 0
    for r in roles:
        n = len(r)
        timeline.append((r, t, n))
        t += n * t_char + hold + n * t_del + gap
    D = t

    def pct(v):
        return f"{v / D * 100:.3f}%"

    cursor_frames = []
    for i, (r, start, n) in enumerate(timeline):
        widths = [measure("bold", r[:k], size) for k in range(n + 1)]
        frames = []
        # antes do início: escondido
        if start > 0:
            frames.append(f"0%{{transform:translateX(0px);}}")
        for k in range(n + 1):
            frames.append(f"{pct(start + k * t_char)}{{transform:translateX({widths[k]:.2f}px);}}")
        del_start = start + n * t_char + hold
        for k in range(n + 1):
            frames.append(f"{pct(del_start + k * t_del)}{{transform:translateX({widths[n - k]:.2f}px);}}")
        frames.append("100%{transform:translateX(0px);}")
        cursor_frames.extend((start + k * t_char, widths[k]) for k in range(n + 1))
        cursor_frames.extend((del_start + k * t_del, widths[n - k]) for k in range(n + 1))
        Wmax = widths[-1] + 10
        svg.defs.append(f'<clipPath id="cr{i}"><rect class="cr{i}" x="{rx0 - Wmax - 4:.2f}" y="{ry - size}" '
                        f'width="{Wmax:.2f}" height="{size * 1.4}"/></clipPath>')
        svg.add(f'<g clip-path="url(#cr{i})">' + svg.text(rx0, ry, r, "bold", size, CREME) + "</g>")
        static = widths[-1] + 4 if i == 0 else 0
        svg.css.append(f".cr{i}{{transform:translateX({static:.2f}px);animation:cr{i} {D:.2f}s steps(1,end) infinite;}}"
                       f"@keyframes cr{i}{{{''.join(frames)}}}")
    cframes = "".join(f"{pct(t0)}{{transform:translateX({w:.2f}px);}}" for t0, w in cursor_frames)
    w0 = measure("bold", roles[0], size)
    svg.add(f'<g class="cur"><rect class="blink" x="{rx0 + 6}" y="{ry - 6}" width="30" height="7" fill="{LARANJA}"/></g>')
    svg.css.append(f".cur{{transform:translateX({w0:.2f}px);animation:cur {D:.2f}s steps(1,end) infinite;}}"
                   f"@keyframes cur{{{cframes}100%{{transform:translateX(0px);}}}}"
                   ".blink{animation:blink 1s steps(1,end) infinite;}@keyframes blink{50%{opacity:0;}}")

    # Assinatura
    line, _ = svg.runs(40, 352, [("reg", "Sites feitos com ", CREME), ("serif", "intenção.", LARANJA)], 30)
    svg.add(f'<g class="sig">{line}</g>')
    svg.add(f'<g class="sig2">' + svg.text(40, 384, "Tecnologia com critério. Café com código.", "reg", 16, CINZA) + "</g>")
    svg.css.append(".sig{animation:fade .8s .6s both;}.sig2{animation:fade .8s .8s both;}")

    ticker(svg, H - 44, 44, ["HTML", "CSS", "JAVASCRIPT", "TYPESCRIPT", "REACT", "ASTRO",
                             "TAILWIND CSS", "GSAP", "NODE.JS", "GIT", "VERCEL", "CAFÉ"])
    svg.save("header.svg")


# -------------------------------------------------------------- títulos ----


def build_title(name, eyebrow, before, accent, after=""):
    W, H = 1000, 124
    svg = SVG(W, H, f"{before}{accent}{after}", f"Título de seção: {eyebrow}")
    card_bg(svg, rx=18, glow=False)
    svg.add(f'<rect x="40" y="34" width="9" height="9" fill="{LARANJA}" class="sq"/>')
    svg.add(svg.text(60, 43, eyebrow, "mono", 12, CINZA, spacing=2.4))
    parts = [("bold", before, CREME), ("serif", accent, LARANJA)]
    if after:
        parts.append(("bold", after, CREME))
    line, w = svg.runs(38, 94, parts, 40)
    svg.add(f'<g class="ttl">{line}</g>')
    svg.add(f'<rect x="{40 + w + 18:.1f}" y="83" width="{W - 80 - w - 18:.1f}" height="2" fill="{MARROM}"/>')
    svg.add(f'<rect x="{40 + w + 18:.1f}" y="83" width="{W - 80 - w - 18:.1f}" height="2" fill="{LARANJA}" class="bar"/>')
    svg.css.append(".ttl{animation:fade .7s both;}@keyframes fade{from{opacity:0;transform:translateY(10px);}}"
                   ".sq{animation:spin 6s cubic-bezier(.7,0,.3,1) infinite;transform-box:fill-box;transform-origin:center;}"
                   "@keyframes spin{0%,70%{transform:rotate(0);}85%,100%{transform:rotate(180deg);}}"
                   ".bar{transform-box:fill-box;transform-origin:left;animation:bar 5s cubic-bezier(.6,0,.2,1) infinite;}"
                   "@keyframes bar{0%{transform:scaleX(0);}40%,60%{transform:scaleX(1);transform-origin:left;}"
                   "60.01%{transform-origin:right;}100%{transform:scaleX(0);transform-origin:right;}}")
    svg.save(name)


# ---------------------------------------------------------------- sobre ----


def build_about():
    W, H = 1000, 452
    svg = SVG(W, H, "victor.ts: quem é Victor Langkamer",
              "Janela de editor com um objeto TypeScript descrevendo Victor: formado em Análise e Desenvolvimento "
              "de Sistemas, Dev Front-end, Web Designer e UI/UX Designer, focado em sites para pequenos negócios "
              "e autônomos. Ao lado, uma xícara de café com fumaça animada.")
    card_bg(svg, glow=False)
    # Barra de título
    svg.add(f'<path d="M0 22a22 22 0 0 1 22-22h956a22 22 0 0 1 22 22v26H0z" fill="{MARROM}"/>')
    for i, c in enumerate([CREME, CINZA, LARANJA]):
        svg.add(f'<circle cx="{28 + i * 20}" cy="24" r="6" fill="{c}" opacity="{.9 if i != 1 else .7}"/>')
    tab = "victor.ts"
    tw = measure("mono", tab, 13) + 36
    svg.add(f'<path d="M100 48v-30a8 8 0 0 1 8-8h{tw - 16:.1f}a8 8 0 0 1 8 8v30z" fill="{CAFE}"/>')
    svg.add(f'<rect x="112" y="24" width="7" height="7" fill="{LARANJA}"/>')
    svg.add(svg.text(126, 32, tab, "mono", 13, CREME))
    svg.add(svg.text(W - 24, 32, "CAFÉ COM CÓDIGO 01/06", "mono", 11, CREME, spacing=2, anchor="end", extra=' opacity=".7"'))

    K, P, S, C, N, PU = LARANJA_CLARO, CREME, LATTE, CINZA, CREME, "#B9A99A"
    lines = [
        [("mono", "// café com código: quem escreve este perfil", C)],
        [("monob", "const ", K), ("mono", "victor", P), ("mono", " = {", PU)],
        [("mono", "  nome", P), ("mono", ": ", PU), ("mono", '"Victor Soares Langkamer"', S), ("mono", ",", PU)],
        [("mono", "  formacao", P), ("mono", ": ", PU), ("mono", '"Análise e Desenv. de Sistemas"', S), ("mono", ",", PU)],
        [("mono", "  status", P), ("mono", ": ", PU), ("mono", '"formado"', S), ("mono", ",  ", PU), ("mono", "// fase concluída", C)],
        [("mono", "  funcoes", P), ("mono", ": [", PU), ("mono", '"Dev Front-end"', S), ("mono", ", ", PU),
         ("mono", '"Web Designer"', S), ("mono", ", ", PU), ("mono", '"UI/UX"', S), ("mono", "],", PU)],
        [("mono", "  foco", P), ("mono", ": ", PU), ("mono", '"sites p/ pequenos negócios"', S), ("mono", ",", PU)],
        [("mono", "  mantra", P), ("mono", ": ", PU), ("mono", '"menos efeito, mais intenção"', S), ("mono", ",", PU)],
        [("mono", "  combustivel", P), ("mono", ": ", PU), ("mono", '"café"', S), ("mono", ",", PU)],
        [("mono", "};", PU)],
        [],
        [("monob", "export default ", K), ("mono", "victor", P), ("mono", ";", PU)],
    ]
    size, lh, x0, y0 = 15, 29, 70, 92
    for i, parts in enumerate(lines):
        y = y0 + i * lh
        svg.add(svg.text(44, y, f"{i + 1:>2}", "mono", 13, CINZA, anchor="end", extra=' opacity=".55"'))
        if parts:
            ln, w = svg.runs(x0, y, parts, size)
            svg.add(f'<g class="ln" style="animation-delay:{.25 + i * .16:.2f}s">{ln}</g>')
            last_w, last_y = w, y
    svg.add(f'<rect class="caret" x="{x0 + last_w + 4:.1f}" y="{last_y - 14}" width="9" height="18" fill="{LARANJA}"/>')
    svg.css.append(".ln{animation:type .5s cubic-bezier(.2,.7,.2,1) both;}"
                   "@keyframes type{from{opacity:0;transform:translateX(-12px);}}"
                   ".caret{animation:blink 1s steps(1,end) infinite;}@keyframes blink{50%{opacity:0;}}")
    svg.add(f'<rect x="{x0 - 8}" y="{y0 + 2 * lh - 21}" width="3" height="{lh * 7}" fill="{MARROM}"/>')

    # Xícara com o símbolo VL
    cx, cy = 840, 300
    cup = (f'<g class="cup">'
           f'<ellipse cx="{cx}" cy="{cy + 92}" rx="112" ry="16" fill="{MARROM}"/>'
           f'<ellipse cx="{cx}" cy="{cy + 86}" rx="92" ry="11" fill="{SURFACE}"/>'
           f'<path d="M{cx + 70} {cy - 30} h18 a34 34 0 0 1 0 68 h-26" fill="none" stroke="{CREME}" stroke-width="14"/>'
           f'<path d="M{cx - 84} {cy - 52} h168 v86 a58 52 0 0 1 -58 52 h-52 a58 52 0 0 1 -58 -52z" fill="{CREME}"/>'
           f'<ellipse cx="{cx}" cy="{cy - 52}" rx="84" ry="13" fill="{TIJOLO}"/>'
           f'<ellipse cx="{cx}" cy="{cy - 50}" rx="74" ry="9" fill="{MARROM}" class="coffee"/>'
           + logo(cx - 27, cy - 12, 0.25, CAFE) + "</g>")
    svg.add(cup)
    svg.add(steam(svg, cx, cy - 70, 110, n=3, spread=30, width=4))
    svg.css.append(".coffee{animation:swirl 4s ease-in-out infinite;transform-box:fill-box;transform-origin:center;}"
                   "@keyframes swirl{50%{transform:scaleX(.92);}}")
    svg.save("about.svg")


# ---------------------------------------------------------------- stack ----


def build_stack():
    W, H = 1000, 452
    svg = SVG(W, H, "Cardápio da stack",
              "Stack em formato de cardápio de cafeteria. Espresso (base): HTML, CSS, JavaScript e TypeScript. "
              "Cappuccino (interfaces): React, Astro, Tailwind CSS e GSAP. Cold brew (entrega): Node.js, Git e Vercel.")
    card_bg(svg)
    cols = [
        ("ESPRESSO", "Base", "o que sustenta", [
            ("html5", "HTML", "estrutura"), ("css", "CSS", "estilo"),
            ("javascript", "JavaScript", "interação"), ("typescript", "TypeScript", "tipagem")]),
        ("CAPPUCCINO", "Interfaces", "o que aparece", [
            ("react", "React", "componentes"), ("astro", "Astro", "sites rápidos"),
            ("tailwindcss", "Tailwind CSS", "utilitários"), ("gsap", "GSAP", "animação")]),
        ("COLD BREW", "Entrega", "o que leva ao ar", [
            ("nodedotjs", "Node.js", "runtime"), ("git", "Git", "versões"),
            ("vercel", "Vercel", "deploy")]),
    ]
    m, gap = 32, 22
    cw = (W - 2 * m - 2 * gap) / 3
    top = 36
    for ci, (kicker, name, sub, items) in enumerate(cols):
        x = m + ci * (cw + gap)
        d0 = ci * .25
        g = [f'<g class="col" style="animation-delay:{d0:.2f}s">',
             f'<rect x="{x:.1f}" y="{top}" width="{cw:.1f}" height="{H - top - 32}" rx="16" fill="{SURFACE}"/>',
             f'<rect x="{x:.1f}" y="{top}" width="{cw:.1f}" height="{H - top - 32}" rx="16" fill="none" stroke="{MARROM}"/>']
        g.append(f'<rect x="{x + 24:.1f}" y="{top + 30}" width="7" height="7" fill="{LARANJA}"/>')
        g.append(svg.text(x + 40, top + 38, kicker, "monom", 11, LARANJA_CLARO, spacing=2.2))
        g.append(svg.text(x + 24, top + 78, name, "bold", 30, CREME))
        g.append(svg.text(x + 24, top + 104, sub, "serif", 18, CINZA))
        # mini xícara com fumaça no canto
        mx, my = x + cw - 50, top + 72
        g.append(f'<path d="M{mx - 14} {my - 10} h28 v14 a10 10 0 0 1 -10 10 h-8 a10 10 0 0 1 -10 -10z" fill="{CREME}" opacity=".9"/>'
                 f'<path d="M{mx + 14} {my - 6} h4 a6 6 0 0 1 0 12 h-5" fill="none" stroke="{CREME}" stroke-width="3" opacity=".9"/>')
        g.append(steam(svg, mx, my - 16, 30, n=2, spread=10, width=2, cls=f"s{ci}"))
        g.append(f'<line x1="{x + 24:.1f}" x2="{x + cw - 24:.1f}" y1="{top + 128}" y2="{top + 128}" stroke="{MARROM}"/>')
        for ii, (slug, label, note) in enumerate(items):
            y = top + 168 + ii * 58
            nw = measure("med", label, 18)
            tw = measure("mono", note.upper(), 10, 1.2)
            dly = d0 + .35 + ii * .14
            g.append(f'<g class="item" style="animation-delay:{dly:.2f}s">')
            g.append(icon(slug, x + 24, y - 17, 22))
            g.append(svg.text(x + 58, y, label, "med", 18, CREME))
            g.append(f'<line x1="{x + 58 + nw + 8:.1f}" x2="{x + cw - 24 - tw - 8:.1f}" y1="{y - 1}" y2="{y - 1}" '
                     f'stroke="{CINZA}" stroke-width="1.6" stroke-dasharray="1.5 5" stroke-linecap="round" opacity=".7"/>')
            g.append(svg.text(x + cw - 24, y - 1, note.upper(), "mono", 10, CINZA, spacing=1.2, anchor="end"))
            g.append("</g>")
        if len(items) == 3:
            y = top + 168 + 3 * 58
            g.append(f'<g class="item" style="animation-delay:{d0 + .35 + 3 * .14:.2f}s">')
            line, _ = svg.runs(x + 24, y, [("serif", "+ café, ", LARANJA), ("serif", "sempre", LARANJA)], 20)
            g.append(line + "</g>")
        g.append("</g>")
        svg.add("".join(g))
    svg.css.append(".col{animation:up .8s cubic-bezier(.2,.7,.2,1) both;}"
                   "@keyframes up{from{opacity:0;transform:translateY(22px);}}"
                   ".item{animation:fade .6s both;}@keyframes fade{from{opacity:0;transform:translateX(-10px);}}")
    svg.save("stack.svg")


# ------------------------------------------------------------- projetos ----


def browser(svg, x, y, w, h, url, img_path, clip_id):
    uri, _ = image_uri(img_path, max_w=960, quality=76)
    bar = 34
    svg.defs.append(f'<clipPath id="{clip_id}"><rect x="{x}" y="{y + bar}" width="{w}" height="{h - bar}" rx="0"/></clipPath>')
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{MARROM}"/>']
    for i in range(3):
        out.append(f'<circle cx="{x + 18 + i * 15}" cy="{y + bar / 2}" r="4.5" fill="{CREME}" opacity="{.85 - i * .25:.2f}"/>')
    uw = w - 110
    out.append(f'<rect x="{x + 70}" y="{y + 8}" width="{uw}" height="{bar - 16}" rx="9" fill="{CAFE}"/>')
    out.append(svg.text(x + 84, y + bar / 2 + 4, url, "mono", 11, CREME, extra=' opacity=".8"'))
    ih = (h - bar)
    out.append(f'<g clip-path="url(#{clip_id})"><image class="shot" href="{uri}" x="{x}" y="{y + bar}" width="{w}" '
               f'height="{w * 600 / 960:.1f}" preserveAspectRatio="xMidYMin slice"/></g>')
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="none" stroke="{MARROM}" stroke-width="2"/>')
    _ = ih
    return "".join(out)


def chip(svg, x, y, label, fill, color=CREME):
    w = measure("monom", label, 10, 1.6) + 24
    return (f'<rect x="{x}" y="{y - 15}" width="{w:.1f}" height="22" rx="11" fill="{fill}"/>'
            + svg.text(x + 12, y, label, "monom", 10, color, spacing=1.6)), w


def build_project_feature():
    W, H = 1000, 400
    svg = SVG(W, H, "Portfólio Victor Langkamer",
              "Projeto em destaque: o portfólio de Victor, feito com Astro e GSAP. Sites feitos com intenção.")
    card_bg(svg)
    svg.add(f'<g class="win">' + browser(svg, 32, 36, 560, 328, "victor-langkamer-portfolio.vercel.app",
                                          IMAGES / "portfolio.webp", "pf") + "</g>")
    x = 628
    c, _ = chip(svg, x, 78, "EM DESTAQUE", LARANJA_CLARO, CAFE)
    svg.add(c)
    svg.add(svg.text(x, 132, "Meu portfólio", "bold", 38, CREME))
    line, _ = svg.runs(x, 170, [("reg", "Sites feitos com ", CINZA), ("serif", "intenção.", LARANJA)], 22)
    svg.add(line)
    desc = ["Hero em camadas, retrato recortado,",
            "funções digitadas e rolagem suave.",
            "Identidade própria em tons de café."]
    for i, d in enumerate(desc):
        svg.add(svg.text(x, 214 + i * 24, d, "reg", 16, CREME, extra=' opacity=".82"'))
    cx = x
    for slug, label in [("astro", "Astro"), ("gsap", "GSAP"), ("typescript", "TypeScript"), ("vercel", "Vercel")]:
        svg.add(icon(slug, cx, 300, 16) + svg.text(cx + 22, 313, label, "mono", 11, CREME))
        cx += 22 + measure("mono", label, 11) + 18
    svg.add(f'<g class="cta">' + svg.text(x, 352, "VER AO VIVO", "monob", 12, LARANJA_CLARO, spacing=2) +
            f'<path d="M{x + measure("monob", "VER AO VIVO", 12, 2) + 10:.1f} 352 l10 -10 m-8 0 h8 v8" fill="none" '
            f'stroke="{LARANJA_CLARO}" stroke-width="2" class="arr"/></g>')
    svg.css.append(".win{animation:up 1s cubic-bezier(.2,.7,.2,1) both;}@keyframes up{from{opacity:0;transform:translateY(20px);}}"
                   ".shot{animation:pan 12s ease-in-out infinite alternate;}@keyframes pan{to{transform:translateY(-14px) scale(1.04);}}"
                   ".arr{animation:nudge 1.6s ease-in-out infinite;}@keyframes nudge{50%{transform:translate(3px,-3px);}}")
    svg.save("project-portfolio.svg")


def build_project_card(name, file, title, kind, kind_fill, kind_color, kind_desc, url, img):
    W, H = 600, 540
    svg = SVG(W, H, f"{title}: {kind_desc}", f"{kind.capitalize()}: {kind_desc}. Publicado em {url}.")
    card_bg(svg)
    svg.add(f'<g class="win">' + browser(svg, 28, 30, W - 56, 360, url, img, "pc") + "</g>")
    c, _ = chip(svg, 30, 432, kind, kind_fill, kind_color)
    svg.add(c)
    svg.add(svg.text(28, 478, title, "bold", 32, CREME))
    svg.add(svg.text(28, 508, kind_desc, "serif", 19, CINZA))
    lbl = "VER PROJETO"
    lw = measure("monob", lbl, 12, 2)
    svg.add(svg.text(W - 28 - 22, 508, lbl, "monob", 12, LARANJA_CLARO, spacing=2, anchor="end"))
    svg.add(f'<path d="M{W - 40} 508 l10 -10 m-8 0 h8 v8" fill="none" stroke="{LARANJA_CLARO}" stroke-width="2" class="arr"/>')
    _ = lw
    svg.css.append(".win{animation:up 1s cubic-bezier(.2,.7,.2,1) both;}@keyframes up{from{opacity:0;transform:translateY(20px);}}"
                   ".shot{animation:pan 12s ease-in-out infinite alternate;}@keyframes pan{to{transform:translateY(-12px) scale(1.04);}}"
                   ".arr{animation:nudge 1.6s ease-in-out infinite;}@keyframes nudge{50%{transform:translate(3px,-3px);}}")
    svg.save(file)


# --------------------------------------------------------------- rodapé ----


def build_footer():
    W, H = 1000, 220
    svg = SVG(W, H, "Sites feitos com intenção. Tecnologia com critério. Café com código.",
              "Rodapé com as assinaturas da marca correndo em faixa e o fechamento: curiosidade para descobrir, "
              "cuidado para construir, intenção para comunicar.")
    card_bg(svg)
    # faixa grande com assinaturas
    size = 40
    segs = [("Sites feitos com ", "intenção."), ("Tecnologia com ", "critério."), ("Café com ", "código.")]
    items, x = [], 0
    for a, b in segs:
        ln, w = svg.runs(x, 92, [("bold", a, CREME), ("serif", b, LARANJA)], size)
        items.append(ln)
        x += w + 34
        items.append(f'<rect x="{x:.1f}" y="70" width="12" height="12" fill="{LARANJA}"/>')
        x += 12 + 34
    period = x
    reps = int(W // period) + 2
    svg.add('<g clip-path="url(#card)"><g class="big">' + "".join(
        f'<g transform="translate({i * period:.1f} 0)">{"".join(items)}</g>' for i in range(reps)) + "</g></g>")
    svg.css.append(f".big{{animation:tick {period / 55:.2f}s linear infinite;}}"
                   f"@keyframes tick{{to{{transform:translateX(-{period:.1f}px);}}}}")
    svg.add(f'<line x1="40" x2="{W - 40}" y1="132" y2="132" stroke="{MARROM}"/>')
    svg.add(logo(40, 158, 0.14))
    closing = "Curiosidade para descobrir. Cuidado para construir. Intenção para comunicar."
    svg.add(svg.text(80, 176, closing, "reg", 15, CREME, extra=' opacity=".85"'))
    svg.add(svg.text(W - 40, 176, "VICTOR LANGKAMER", "mono", 11, CINZA, spacing=2, anchor="end"))
    svg.save("footer.svg")


if __name__ == "__main__":
    build_header()
    build_title("title-about.svg", "01 / SOBRE", "Prazer, ", "Victor.")
    build_title("title-stack.svg", "02 / STACK", "O que vai na ", "xícara")
    build_title("title-projects.svg", "03 / PROJETOS", "Do conceito ", "ao ar.")
    build_title("title-contact.svg", "04 / CONTATO", "Vamos ", "conversar?")
    build_about()
    build_stack()
    build_project_feature()
    build_project_card("brunno", "project-brunno.svg", "Brunno Rodrigues", "CASO REAL", LARANJA_CLARO, CAFE,
                       "portfólio de social media", "brunnocorreia.vercel.app", IMAGES / "brunno.webp")
    build_project_card("neriva", "project-neriva.svg", "Neriva", "PROJETO CONCEITO", MARROM, CREME,
                       "site para estúdio de tatuagem", "neriva-delta.vercel.app", IMAGES / "neriva.webp")
    build_footer()
