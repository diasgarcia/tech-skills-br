from scraper.dedupe import deduplicate
from scraper.models import Job


def test_remove_mesma_vaga_do_mesmo_portal():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="ACME"),
        Job(source="gupy", external_id="1", title="Dev Júnior", company="ACME"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 1
    assert removed == 1


def test_mantem_a_versao_com_descricao_mais_longa():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior",
            company="ACME", description="curta"),
        Job(source="gupy", external_id="1", title="Dev Júnior",
            company="ACME", description="uma descricao bem mais longa da vaga"),
    ]
    unique, _ = deduplicate(jobs)
    assert unique[0].description == "uma descricao bem mais longa da vaga"


def test_cruza_portais_por_titulo_e_empresa():
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company="ACME"),
        Job(source="vagas", external_id="99", title="desenvolvedor junior", company="Acme"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 1
    assert removed == 1


def test_nao_cruza_vagas_de_empresas_diferentes():
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company="ACME"),
        Job(source="gupy", external_id="2", title="Desenvolvedor Júnior", company="Globex"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 2
    assert removed == 0


def test_vagas_sem_empresa_nao_sao_agrupadas():
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company=""),
        Job(source="gupy", external_id="2", title="Desenvolvedor Júnior", company=""),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 2
    assert removed == 0


def test_funde_mesma_vaga_com_nome_de_empresa_diferente():
    """Casos reais: a Gupy escreve o nome completo, o LinkedIn o curto."""
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Fullstack Jr",
            company="Minsait an Indra Company", description="descricao longa"),
        Job(source="linkedin", external_id="9", title="Desenvolvedor Fullstack Jr",
            company="Minsait"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 1 and removed == 1
    # Fica a versão com mais informação.
    assert unique[0].description == "descricao longa"


def test_funde_quando_o_nome_curto_esta_contido_no_longo():
    jobs = [
        Job(source="gupy", external_id="1", title="Analista de Sistemas Júnior",
            company="Centro Universitário FEI"),
        Job(source="linkedin", external_id="9", title="Analista de Sistemas Júnior",
            company="FEI"),
    ]
    assert len(deduplicate(jobs)[0]) == 1


def test_titulo_generico_em_empresas_diferentes_nao_funde():
    """'Analista de Sistemas Júnior' existe em dezenas de empresas."""
    jobs = [
        Job(source="gupy", external_id="1", title="Analista de Sistemas Júnior",
            company="Techne"),
        Job(source="linkedin", external_id="9", title="Analista de Sistemas Júnior",
            company="Globoaves"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 2 and removed == 0


def test_confidencial_nao_identifica_empresa():
    """Duas vagas confidenciais com o mesmo título não são a mesma vaga."""
    jobs = [
        Job(source="gupy", external_id="1", title="Analista Júnior de TI",
            company="Confidencial"),
        Job(source="vagas", external_id="9", title="Analista Júnior de TI",
            company="Confidencial"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


def test_sufixo_societario_nao_impede_a_fusao():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="ACME"),
        Job(source="linkedin", external_id="9", title="Dev Júnior",
            company="ACME Soluções em Tecnologia LTDA"),
    ]
    assert len(deduplicate(jobs)[0]) == 1


def test_titulos_diferentes_da_mesma_empresa_nao_fundem():
    """Duas vagas distintas na mesma empresa continuam sendo duas."""
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior",
            company="ACME"),
        Job(source="linkedin", external_id="9", title="Analista de Testes Júnior",
            company="ACME"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


def test_lista_vazia():
    unique, removed = deduplicate([])
    assert unique == []
    assert removed == 0
