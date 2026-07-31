"""GET /vagas e GET /vagas/{id}."""

from __future__ import annotations


def test_lista_todas_as_vagas(client):
    resposta = client.get("/vagas")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 4
    assert corpo["limit"] == 50
    assert corpo["offset"] == 0
    assert len(corpo["items"]) == 4


def test_lista_ordena_por_data_mais_recente_e_nulos_no_fim(client):
    items = client.get("/vagas").json()["items"]
    assert [i["external_id"] for i in items] == ["2001", "1001", "1002", "2002"]


def test_filtra_por_area(client):
    corpo = client.get("/vagas", params={"area": "Data"}).json()
    assert corpo["total"] == 2
    assert {i["area"] for i in corpo["items"]} == {"Data"}


def test_filtra_por_tecnologia(client):
    corpo = client.get("/vagas", params={"tecnologia": "Python"}).json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["external_id"] == "1001"


def test_filtro_de_tecnologia_ignora_maiusculas(client):
    assert client.get("/vagas", params={"tecnologia": "python"}).json()["total"] == 1


def test_filtra_por_modalidade(client):
    corpo = client.get("/vagas", params={"modalidade": "Remoto"}).json()
    assert corpo["total"] == 2
    assert {i["workplace_type"] for i in corpo["items"]} == {"Remoto"}


def test_filtra_por_fonte(client):
    corpo = client.get("/vagas", params={"fonte": "vagas"}).json()
    assert corpo["total"] == 2
    assert {i["source"] for i in corpo["items"]} == {"vagas"}


def test_filtros_combinam_em_and(client):
    corpo = client.get("/vagas", params={"area": "Data", "modalidade": "Remoto"}).json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["external_id"] == "1001"


def test_busca_livre_no_titulo(client):
    corpo = client.get("/vagas", params={"q": "Front"}).json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["external_id"] == "2001"


def test_combinacao_sem_resultado_devolve_lista_vazia(client):
    corpo = client.get("/vagas", params={"area": "Mobile", "fonte": "gupy"}).json()
    assert corpo["total"] == 0
    assert corpo["items"] == []


def test_paginacao(client):
    pagina = client.get("/vagas", params={"limit": 2, "offset": 0}).json()
    assert pagina["total"] == 4 and len(pagina["items"]) == 2

    seguinte = client.get("/vagas", params={"limit": 2, "offset": 2}).json()
    assert seguinte["total"] == 4 and len(seguinte["items"]) == 2

    ids_primeira = {i["id"] for i in pagina["items"]}
    ids_segunda = {i["id"] for i in seguinte["items"]}
    assert ids_primeira.isdisjoint(ids_segunda)


def test_tecnologias_vem_como_lista_de_nomes(client):
    corpo = client.get("/vagas", params={"tecnologia": "SQL"}).json()
    vaga = next(i for i in corpo["items"] if i["external_id"] == "1001")
    assert vaga["tecnologias"] == ["Python", "SQL"]


def test_detalhe_da_vaga(client):
    vaga_id = client.get("/vagas").json()["items"][0]["id"]
    resposta = client.get(f"/vagas/{vaga_id}")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["id"] == vaga_id
    # O detalhe traz a descricao, que a listagem omite.
    assert "description" in corpo


def test_detalhe_de_vaga_inexistente_da_404(client):
    resposta = client.get("/vagas/99999")
    assert resposta.status_code == 404
    assert "não encontrada" in resposta.json()["detail"]


def test_area_invalida_da_422(client):
    resposta = client.get("/vagas", params={"area": "Inexistente"})
    assert resposta.status_code == 422
    assert "detail" in resposta.json()


def test_modalidade_invalida_da_422(client):
    assert client.get("/vagas", params={"modalidade": "Meio Remoto"}).status_code == 422


def test_fonte_invalida_da_422(client):
    assert client.get("/vagas", params={"fonte": "linkedin"}).status_code == 422


def test_tecnologia_desconhecida_da_422_com_dica(client):
    resposta = client.get("/vagas", params={"tecnologia": "COBOL-2000"})
    assert resposta.status_code == 422
    assert "/tecnologias" in resposta.json()["detail"]


def test_limit_fora_do_intervalo_da_422(client):
    assert client.get("/vagas", params={"limit": 0}).status_code == 422
    assert client.get("/vagas", params={"limit": 500}).status_code == 422
    assert client.get("/vagas", params={"offset": -1}).status_code == 422


def test_id_nao_numerico_da_422(client):
    assert client.get("/vagas/abc").status_code == 422


def test_api_nao_expoe_escrita(client):
    """A API e somente leitura: sem POST, PUT ou DELETE."""
    assert client.post("/vagas", json={"title": "x"}).status_code == 405
    assert client.put("/vagas/1", json={"title": "x"}).status_code == 405
    assert client.delete("/vagas/1").status_code == 405
