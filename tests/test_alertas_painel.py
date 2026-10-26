import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import coletor, alertas, painel

def prep(tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "DB", tmp_path / "t.db")
    con = coletor.conectar()
    def ins(serie, per, v): con.execute("INSERT OR REPLACE INTO observacoes VALUES(?,?,?,'x')", (serie, per, v)); con.commit()
    return con, ins

def test_alertas(tmp_path, monkeypatch):
    con, ins = prep(tmp_path, monkeypatch)
    cfg = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c"}
    msgs = []
    envio = lambda m, c: msgs.append(m)
    ins("selic_meta", "2026-10-26", 13.75); ins("dolar_venda", "2026-10-23", 5.0)
    ins("ipca_mensal", "2026-09-01", 0.8)
    assert alertas.verificar(con, cfg, envio) == 0          # 1ª vez: só registra, não avisa
    ins("selic_meta", "2026-10-27", 13.25)                  # mudou
    ins("ipca_mensal", "2026-10-01", 0.4)                   # novo
    ins("dolar_venda", "2026-10-26", 5.6)                   # cruzou 5,50 pra cima
    assert alertas.verificar(con, cfg, envio) == 3, msgs
    assert alertas.verificar(con, cfg, envio) == 0          # sem repetir
    ins("dolar_venda", "2026-10-27", 5.7)                   # continua acima: não repete
    assert alertas.verificar(con, cfg, envio) == 0
    ins("dolar_venda", "2026-10-28", 4.7)                   # cruzou 4,80 pra baixo
    assert alertas.verificar(con, cfg, envio) == 1

def test_sem_telegram_nao_perde_aviso(tmp_path, monkeypatch):
    con, ins = prep(tmp_path, monkeypatch)
    ins("selic_meta", "2026-10-26", 13.75)
    alertas.verificar(con, {}, None)
    ins("selic_meta", "2026-10-27", 13.0)
    assert alertas.verificar(con, {}, None) == 0            # não configurado: só imprime
    msgs = []
    assert alertas.verificar(con, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c"}, lambda m, c: msgs.append(m)) == 1

def test_painel(tmp_path, monkeypatch):
    con, ins = prep(tmp_path, monkeypatch)
    for i in range(5): ins("selic_meta", f"2026-10-2{i}", 13 + i / 10)
    ins("pib_trim_anterior", "202602", 0.5); ins("pib_trim_anterior", "202601", 1.1)
    h = painel.montar(con)
    assert "<polyline" in h and "2026-T2" in h and "sem dados ainda" in h

def test_erro_telegram_sem_token(monkeypatch):
    class R:
        status_code = 400
        def json(self): return {"ok": False, "description": "Bad Request: chat not found"}
    monkeypatch.setattr(alertas.requests, "post", lambda *a, **k: R())
    try:
        alertas.enviar("x", {"TELEGRAM_BOT_TOKEN": "SEGREDO123", "TELEGRAM_CHAT_ID": ""})
    except RuntimeError as e:
        assert "chat not found" in str(e) and "SEGREDO123" not in str(e)
    else:
        raise AssertionError("deveria falhar")

def test_painel_mostra_atualizacao(tmp_path, monkeypatch):
    con, _ = prep(tmp_path, monkeypatch)
    assert "atualizado em" in painel.montar(con) and "{{" not in painel.montar(con)
