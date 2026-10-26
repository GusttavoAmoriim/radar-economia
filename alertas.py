"""Alertas por Telegram. Estado em SQLite: cada alerta avisa uma vez e não repete."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

import coletor

BASE = Path(__file__).parent


def ler_env(arquivo=BASE / ".env"):
    cfg = {}
    if Path(arquivo).exists():
        for linha in Path(arquivo).read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        cfg[k] = os.environ.get(k, cfg.get(k, ""))
    return cfg


def _api(cfg, metodo, **dados):
    """Chama a API do Telegram. Os erros nunca incluem o token."""
    url = f"https://api.telegram.org/bot{cfg['TELEGRAM_BOT_TOKEN']}/{metodo}"
    try:
        r = requests.post(url, json=dados, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"falha de rede ao falar com o Telegram ({type(e).__name__})") from None
    try:
        corpo = r.json()
    except ValueError:
        corpo = {}
    if not corpo.get("ok"):
        raise RuntimeError(f"Telegram recusou ({r.status_code}): {corpo.get('description', 'sem detalhe')}")
    return corpo["result"]


def enviar(texto, cfg):
    _api(cfg, "sendMessage", chat_id=cfg["TELEGRAM_CHAT_ID"], text=texto)


def descobrir_chat_id():
    """Lista os chats que já mandaram mensagem ao bot (mande um 'oi' ao bot antes)."""
    cfg = ler_env()
    if not cfg["TELEGRAM_BOT_TOKEN"]:
        print("Preencha TELEGRAM_BOT_TOKEN no arquivo .env")
        return
    vistos = {}
    for u in _api(cfg, "getUpdates"):
        chat = (u.get("message") or u.get("my_chat_member") or {}).get("chat")
        if chat:
            vistos[chat["id"]] = chat.get("first_name") or chat.get("title") or chat.get("username", "")
    if not vistos:
        print("Nenhuma mensagem encontrada. Abra o seu bot no Telegram, mande 'oi' e rode de novo.")
    for cid, nome in vistos.items():
        print(f"chat id: {cid}   ({nome})   -> coloque em TELEGRAM_CHAT_ID no .env")


def carregar_regras(arquivo=BASE / "alertas.yaml"):
    regras = yaml.safe_load(Path(arquivo).read_text(encoding="utf-8")).get("alertas", [])
    for i, r in enumerate(regras, 1):
        if r.get("tipo") not in ("novo", "mudou", "acima", "abaixo"):
            raise ValueError(f"alertas.yaml: item {i} com tipo inválido {r.get('tipo')!r}")
        if r["tipo"] in ("acima", "abaixo") and "valor" not in r:
            raise ValueError(f"alertas.yaml: item {i} ({r['tipo']}) precisa de 'valor'")
    return regras


def _fmt(v):
    return "sem valor" if v is None else f"{v:g}"


def avaliar(con, regra, nomes):
    """Devolve (mensagem|None, novo_estado). Na primeira vez só grava o estado, sem avisar."""
    serie = regra["serie"]
    ult = con.execute("SELECT periodo,valor FROM observacoes WHERE serie=? ORDER BY periodo DESC LIMIT 1", (serie,)).fetchone()
    if not ult:
        return None, None
    periodo, valor = ult
    nome = nomes.get(serie, serie)
    tipo = regra["tipo"]
    if tipo == "novo":
        return f"📊 {nome}\nNovo dado: {periodo} = {_fmt(valor)}", periodo
    if tipo == "mudou":
        return f"🔔 {nome} mudou para {_fmt(valor)} (dado de {periodo})", _fmt(valor)
    lim = float(regra["valor"])
    if valor is None:
        return None, None
    cond = valor > lim if tipo == "acima" else valor < lim
    est = "sim" if cond else "nao"
    return (f"⚠️ {nome}: {_fmt(valor)} está {'acima' if tipo == 'acima' else 'abaixo'} de {lim:g} ({periodo})", est)


def verificar(con=None, cfg=None, enviar_fn=enviar):
    con = con or coletor.conectar()
    con.execute("CREATE TABLE IF NOT EXISTS alertas_estado(chave TEXT PRIMARY KEY, estado TEXT)")
    cfg = cfg or ler_env()
    nomes = {s["id"]: s["nome"] for s in coletor.carregar_series()}
    pode_enviar = bool(cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID"))
    enviados = 0
    for regra in carregar_regras():
        chave = f"{regra['serie']}|{regra['tipo']}|{regra.get('valor', '')}"
        msg, novo = avaliar(con, regra, nomes)
        if novo is None:
            continue
        antigo = con.execute("SELECT estado FROM alertas_estado WHERE chave=?", (chave,)).fetchone()
        if antigo is None:                      # primeira vez: só registra
            con.execute("INSERT INTO alertas_estado VALUES(?,?)", (chave, novo))
            continue
        if novo == antigo[0]:
            continue
        deve_avisar = (novo != "nao") if regra["tipo"] in ("acima", "abaixo") else True
        if deve_avisar:
            if not pode_enviar:
                print("alerta pendente (Telegram não configurado):", msg.replace("\n", " | "))
                continue                         # mantém estado antigo: avisa quando configurar
            enviar_fn(msg, cfg)
            enviados += 1
            print("alerta enviado:", msg.replace("\n", " | "))
        con.execute("UPDATE alertas_estado SET estado=? WHERE chave=?", (novo, chave))
    con.commit()
    return enviados


def testar():
    cfg = ler_env()
    if not (cfg["TELEGRAM_BOT_TOKEN"] and cfg["TELEGRAM_CHAT_ID"]):
        print("Preencha TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no arquivo .env")
        return
    try:
        enviar("✅ Radar Economia: alerta de teste", cfg)
        print("Mensagem de teste enviada.")
    except RuntimeError as e:
        print("ERRO:", e)
        print("Dica: rode  python coletor.py telegram-chat-id  para descobrir o chat id certo.")


DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _pt(v):
    return "—" if v is None else f"{v:g}".replace(".", ",")


def _periodo(p):
    return f"{p[:4]}-{p[4:]}" if len(p) == 6 else p


def montar_resumo(con=None, agora=None):
    con = con or coletor.conectar()
    agora = agora or datetime.now(timezone(timedelta(hours=-3)))
    linhas = [f"📊 Radar Economia — {DIAS[agora.weekday()]}, {agora:%d/%m/%Y}", ""]
    for s in coletor.carregar_series():
        rows = con.execute("SELECT periodo,valor FROM observacoes WHERE serie=? ORDER BY periodo DESC LIMIT 2",
                           (s["id"],)).fetchall()
        if not rows:
            continue
        per, val = rows[0]
        sinal, extra = "⚪", ""
        if len(rows) > 1 and val is not None and rows[1][1] is not None:
            d = val - rows[1][1]
            sinal = "🟢" if d > 0 else "🔴" if d < 0 else "⚪"
            extra = f" ({'▲' if d > 0 else '▼' if d < 0 else '='} {_pt(abs(round(d, 4)))})"
        linhas.append(f"{sinal} {s['nome']}: {_pt(val)}{extra} · {_periodo(per)}")
    return "\n".join(linhas)


def enviar_resumo(cfg=None, enviar_fn=enviar):
    cfg = cfg or ler_env()
    texto = montar_resumo()
    if not (cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID")):
        print(texto)
        print("\n(Telegram não configurado: resumo só exibido na tela)")
        return
    enviar_fn(texto, cfg)
    print("Resumo diário enviado.")
