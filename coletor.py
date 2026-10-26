"""Radar Economia: coleta séries de APIs oficiais (BCB/SGS e IBGE/SIDRA) para SQLite.

Uso:
  python coletor.py coletar            # busca todas as séries ativas
  python coletor.py ultimos [id] [n]   # mostra os últimos valores guardados
  python coletor.py agendar [horas]    # coleta em loop (padrão: a cada 6 h)
  python coletor.py painel [--sem-abrir]  # gera (e abre) dados/painel.html
  python coletor.py testar-telegram    # envia mensagem de teste
  python coletor.py resumo             # envia o resumo diário ao Telegram
  python coletor.py telegram-chat-id   # descobre o chat id do seu bot
  python coletor.py sidra /t/..        # confere o que um caminho SIDRA devolve
"""
import re
import sqlite3
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

import requests
import yaml

BASE = Path(__file__).parent
DB = BASE / "dados" / "economia.db"
UA = "radar-economia/0.1 (uso pessoal)"
BCB = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{n}?formato=json"
BCB_INTERVALO = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={ini}&dataFinal={fim}"
OLINDA = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoMoedaPeriodo("
          "moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
          "?@moeda='{moeda}'&@dataInicial='{ini}'&@dataFinalCotacao='{fim}'&$top=10000&$format=json"
          "&$select=cotacaoVenda,dataHoraCotacao,tipoBoletim")
SIDRA = "https://apisidra.ibge.gov.br/values{caminho}"


def conectar():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS observacoes(
      serie TEXT NOT NULL, periodo TEXT NOT NULL, valor REAL,
      coletado_em TEXT NOT NULL, PRIMARY KEY(serie, periodo));
    CREATE TABLE IF NOT EXISTS coletas(
      id INTEGER PRIMARY KEY, serie TEXT, em TEXT, ok INTEGER, novos INTEGER, erro TEXT);
    """)
    return con


def carregar_series(arquivo=BASE / "series.yaml"):
    dados = yaml.safe_load(Path(arquivo).read_text(encoding="utf-8"))
    vistos, saida = set(), []
    for i, s in enumerate(dados.get("series", []), 1):
        for campo in ("id", "nome", "fonte"):
            if not s.get(campo):
                raise ValueError(f"series.yaml: item {i} sem '{campo}'")
        if s["fonte"] not in ("bcb", "sidra", "ptax"):
            raise ValueError(f"series.yaml: '{s['id']}' com fonte inválida '{s['fonte']}'")
        if s["fonte"] == "bcb" and not s.get("codigo"):
            raise ValueError(f"series.yaml: '{s['id']}' precisa de 'codigo'")
        if s["fonte"] == "ptax" and not s.get("moeda"):
            raise ValueError(f"series.yaml: '{s['id']}' precisa de 'moeda' (ex.: EUR)")
        if s["fonte"] == "sidra" and not s.get("caminho"):
            raise ValueError(f"series.yaml: '{s['id']}' precisa de 'caminho'")
        if s["id"] in vistos:
            raise ValueError(f"series.yaml: id repetido '{s['id']}'")
        vistos.add(s["id"])
        if s.get("enabled", True):
            saida.append(s)
    return saida


def _get(url, tentativas=3):
    """GET que devolve JSON; em caso de falha, o erro diz status e início da resposta."""
    ultimo = None
    for t in range(tentativas):
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            ultimo = f"HTTP {r.status_code}"
            time.sleep(5 * (t + 1))
            continue
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} em {url} -> {r.text[:150]!r}")
        try:
            return r.json()
        except ValueError:
            texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)).strip()[:300]
            ultimo = f"resposta não-JSON (HTTP 200, {len(r.content)} bytes) em {url} -> texto da página: {texto!r}"
            time.sleep(5 * (t + 1))  # pode ser instabilidade momentânea do servidor
            continue
    raise RuntimeError(f"{ultimo} (após {tentativas} tentativas)")


def _num(txt):
    try:
        return float(str(txt).replace(",", "."))
    except ValueError:
        return None  # SIDRA usa "-", "..", "X" para ausente


def buscar_bcb(s, desde=None):
    """Sempre por intervalo de datas (o BCB limita 'ultimos/N' a 20 registros).
    desde: data ISO da última observação guardada; se houver, busca só a partir de 60 dias antes dela."""
    fim = date.today()
    if desde:
        ini = date.fromisoformat(desde) - timedelta(days=60)  # margem para revisões
    else:
        ini = date(fim.year - int(s.get("anos", 9)), fim.month, 1)
    linhas = _get(BCB_INTERVALO.format(codigo=s["codigo"], ini=ini.strftime("%d/%m/%Y"), fim=fim.strftime("%d/%m/%Y")))
    # data vem como dd/mm/aaaa -> guardamos ISO aaaa-mm-dd
    return [(datetime.strptime(l["data"], "%d/%m/%Y").date().isoformat(), _num(l["valor"])) for l in linhas]


def buscar_ptax(s, desde=None):
    """Cotação de venda no boletim de fechamento da PTAX (API Olinda do BCB) para a moeda indicada."""
    fim = date.today()
    ini = (date.fromisoformat(desde) - timedelta(days=30)) if desde else date(fim.year - int(s.get("anos", 3)), fim.month, 1)
    url = OLINDA.format(moeda=s["moeda"], ini=ini.strftime("%m-%d-%Y"), fim=fim.strftime("%m-%d-%Y"))
    saida = {}
    for l in _get(url).get("value", []):
        if l.get("tipoBoletim") == "Fechamento":
            saida[l["dataHoraCotacao"][:10]] = _num(l["cotacaoVenda"])
    return sorted(saida.items())


def buscar_sidra(s):
    linhas = _get(SIDRA.format(caminho=s["caminho"]))
    # primeira linha é o cabeçalho; D3C = período (AAAAMM mensal, AAAAQQ trimestral), V = valor
    return [(l["D3C"], _num(l["V"])) for l in linhas[1:]]


def coletar_serie(con, s):
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        if s["fonte"] in ("bcb", "ptax"):
            ult = con.execute("SELECT MAX(periodo) FROM observacoes WHERE serie=?", (s["id"],)).fetchone()[0]
            obs = (buscar_bcb if s["fonte"] == "bcb" else buscar_ptax)(s, ult)
        else:
            obs = buscar_sidra(s)
        antes = con.total_changes
        for periodo, valor in obs:
            # só insere o que é novo; se o valor foi revisado pela fonte, atualiza
            con.execute("""INSERT INTO observacoes(serie,periodo,valor,coletado_em) VALUES(?,?,?,?)
                           ON CONFLICT(serie,periodo) DO UPDATE SET valor=excluded.valor,
                           coletado_em=excluded.coletado_em WHERE valor IS NOT excluded.valor""",
                        (s["id"], periodo, valor, agora))
        novos = con.total_changes - antes
        con.execute("INSERT INTO coletas(serie,em,ok,novos) VALUES(?,?,1,?)", (s["id"], agora, novos))
        con.commit()
        return novos, None
    except Exception as e:  # uma série com erro não derruba as outras
        con.execute("INSERT INTO coletas(serie,em,ok,erro) VALUES(?,?,0,?)", (s["id"], agora, str(e)[:300]))
        con.commit()
        return 0, str(e)


def coletar():
    con = conectar()
    for s in carregar_series():
        print(f"... buscando {s['id']}", flush=True)
        novos, erro = coletar_serie(con, s)
        print(f"{'ERRO' if erro else 'ok  '} {s['id']:<16} {erro or str(novos) + ' novos/atualizados'}", flush=True)
        time.sleep(3)  # cortesia com as APIs (o BCB recusa pedidos em sequência rápida)


def ultimos(serie=None, n=5):
    con = conectar()
    ids = [serie] if serie else [s["id"] for s in carregar_series()]
    nomes = {s["id"]: s["nome"] for s in carregar_series()}
    for i in ids:
        rows = con.execute("SELECT periodo,valor FROM observacoes WHERE serie=? ORDER BY periodo DESC LIMIT ?", (i, n)).fetchall()
        print(f"\n{nomes.get(i, i)}")
        for p, v in rows:
            print(f"  {p}  {v}")


def ciclo():
    coletar()
    try:
        import alertas
        alertas.verificar()
    except Exception as e:  # alerta com problema não pode derrubar a coleta
        print("aviso: alertas falharam:", e)


def sidra_raw(caminho):
    """Mostra o que a SIDRA devolve (nome da variável, período, valor) para conferir um caminho."""
    for l in _get(SIDRA.format(caminho=caminho))[1:6]:
        print(l.get("D2N", ""), "|", l.get("D3C"), "|", l.get("V"))


def agendar(horas=6):
    while True:
        print(datetime.now().isoformat(timespec="seconds"), "coletando...")
        ciclo()
        time.sleep(horas * 3600)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "coletar"
    if cmd == "coletar":
        ciclo()
    elif cmd == "ultimos":
        ultimos(sys.argv[2] if len(sys.argv) > 2 else None, int(sys.argv[3]) if len(sys.argv) > 3 else 5)
    elif cmd == "agendar":
        agendar(float(sys.argv[2]) if len(sys.argv) > 2 else 6)
    elif cmd == "painel":
        import painel
        painel.gerar(abrir="--sem-abrir" not in sys.argv)
    elif cmd == "testar-telegram":
        import alertas
        alertas.testar()
    elif cmd == "resumo":
        import alertas
        alertas.enviar_resumo()
    elif cmd == "telegram-chat-id":
        import alertas
        alertas.descobrir_chat_id()
    elif cmd == "sidra":
        sidra_raw(sys.argv[2])
    else:
        print(__doc__)
