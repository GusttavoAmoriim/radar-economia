import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import coletor

def test_bcb_e_sidra(tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "DB", tmp_path / "t.db")
    resp = {
        "bcdata.sgs.433": [{"data": "01/09/2026", "valor": "0.48"}, {"data": "01/10/2026", "valor": "0.52"}],
        "apisidra": [{"D3C": "Período"}, {"D3C": "202602", "V": "0.4"}, {"D3C": "202603", "V": "-"}],
    }
    monkeypatch.setattr(coletor, "_get", lambda url, *a: resp["apisidra" if "sidra" in url else "bcdata.sgs.433"])
    con = coletor.conectar()
    b = {"id": "ipca", "nome": "x", "fonte": "bcb", "codigo": 433}
    s = {"id": "pib", "nome": "y", "fonte": "sidra", "caminho": "/t/1"}
    assert coletor.coletar_serie(con, b) == (2, None)
    assert coletor.coletar_serie(con, b) == (0, None)          # repetir não duplica
    assert coletor.coletar_serie(con, s) == (2, None)
    assert con.execute("SELECT valor FROM observacoes WHERE serie='pib' AND periodo='202603'").fetchone()[0] is None
    assert con.execute("SELECT periodo FROM observacoes WHERE serie='ipca' ORDER BY periodo").fetchall()[0][0] == "2026-09-01"
    resp["bcdata.sgs.433"][1]["valor"] = "0.55"                 # revisão da fonte atualiza
    assert coletor.coletar_serie(con, b)[0] == 1

def test_yaml_atual():
    assert len(coletor.carregar_series()) == 10
