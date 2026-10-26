"""Gera dados/painel.html: página única com um gráfico (SVG) por série. Sem dependências externas."""
import html
import webbrowser
from datetime import datetime, timedelta, timezone

import coletor

W, H, PAD = 320, 90, 6


def _rotulo(periodo, trimestral):
    if trimestral and len(periodo) == 6:
        return f"{periodo[:4]}-T{int(periodo[4:])}"
    if len(periodo) == 6:
        return f"{periodo[:4]}-{periodo[4:]}"
    return periodo


def _svg(valores, cor="var(--linha)"):
    pts = [(i, v) for i, v in enumerate(valores) if v is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    span = (hi - lo) or 1
    n = len(valores) - 1
    xy = [(PAD + i / n * (W - 2 * PAD), H - PAD - (v - lo) / span * (H - 2 * PAD)) for i, v in pts]
    linha = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    x, y = xy[-1]
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="gráfico da série">'
            f'<polyline points="{linha}" fill="none" stroke="{cor}" stroke-width="2" stroke-linejoin="round"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{cor}"/></svg>')


def montar(con=None, pontos=60):
    con = con or coletor.conectar()
    cartoes = []
    for s in coletor.carregar_series():
        rows = con.execute("SELECT periodo,valor FROM observacoes WHERE serie=? ORDER BY periodo DESC LIMIT ?",
                           (s["id"], pontos)).fetchall()[::-1]
        if not rows:
            corpo = '<p class="vazio">sem dados ainda</p>'
        else:
            per, val = rows[-1]
            ant = next((v for _, v in reversed(rows[:-1]) if v is not None), None)
            delta, cor = "", "var(--linha)"
            if val is not None and ant is not None:
                d = val - ant
                classe = "sobe" if d > 0 else "desce" if d < 0 else ""
                cor = "var(--alta)" if d > 0 else "var(--queda)" if d < 0 else cor
                delta = f'<span class="delta {classe}">{"▲" if d > 0 else "▼" if d < 0 else "="} {abs(d):.4g} vs. anterior</span>'
            tri = bool(s.get("trimestral"))
            corpo = (f'<div class="valor">{"—" if val is None else f"{val:g}"}</div>'
                     f'<div class="meta">{_rotulo(per, tri)} {delta}</div>{_svg([v for _, v in rows], cor)}'
                     f'<div class="meta">{len(rows)} observações · {_rotulo(rows[0][0], tri)} → {_rotulo(per, tri)}</div>')
        cartoes.append(f'<section class="card"><h2>{html.escape(s["nome"])}</h2>{corpo}</section>')
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
    return PAGINA.replace("{{CARTOES}}", "\n".join(cartoes)).replace("{{ATUALIZADO}}", agora)


def gerar(abrir=False):
    destino = coletor.DB.parent / "painel.html"
    destino.write_text(montar(), encoding="utf-8")
    print("Painel gerado em", destino)
    if abrir:
        webbrowser.open(destino.as_uri())
    return destino


PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Radar Economia</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--txt:#1b2430;--mut:#667085;--linha:#1f6feb;--alta:#1a7f37;--queda:#cf222e;--borda:#e3e6ea}
@media (prefers-color-scheme:dark){:root{--bg:#10151c;--card:#18202a;--txt:#e8ecf1;--mut:#97a3b2;--linha:#5aa2ff;--alta:#3fb950;--queda:#f85149;--borda:#27313d}}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.4 system-ui,sans-serif}
header{padding:20px 16px 4px;max-width:1100px;margin:auto}h1{margin:0;font-size:22px}
main{max-width:1100px;margin:auto;padding:12px 16px 32px;display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.card{background:var(--card);border:1px solid var(--borda);border-radius:12px;padding:14px}
h2{font-size:14px;margin:0 0 6px;color:var(--mut);font-weight:600}.valor{font-size:30px;font-weight:700}
.meta{color:var(--mut);font-size:12.5px}.delta{margin-left:6px}.sobe{color:var(--alta);font-weight:600}.desce{color:var(--queda);font-weight:600}svg{width:100%;height:auto;margin:6px 0}
</style></head><body><header><h1>Radar Economia</h1><div class="meta">Fontes: Banco Central (SGS) e IBGE (SIDRA) · atualizado em {{ATUALIZADO}} (Brasília)</div></header>
<main>
{{CARTOES}}
</main></body></html>"""
