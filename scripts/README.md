# Arte do README

Os SVGs em `assets/` são gerados por `build.py`. Cada um é autossuficiente
(fontes em subconjunto e imagens embutidas), porque o GitHub mostra SVG dentro
de `<img>` e bloqueia recursos externos. As animações são só CSS e param com
`prefers-reduced-motion`.

```bash
pip install fonttools brotli pillow
python3 scripts/build.py
```

- Paleta e tipografia seguem o manual de identidade do portfólio (café, creme, marrom, laranja; Outfit, Fraunces itálico, JetBrains Mono).
- Textos, funções digitadas, stack e projetos ficam no próprio `build.py`.
- `images/`: retrato recortado e capturas dos projetos. `fonts/`: fontes OFL (veja `fonts/LICENSE.md`). `icons.json`: ícones do Simple Icons (CC0).
