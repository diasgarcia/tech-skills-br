# Execução local

Use Python 3.12 ou mais recente. Execute os comandos na raiz do repositório.
O [Manual de Uso](https://github.com/diasgarcia/tech-skills-br/wiki/Manual-de-Uso) descreve as opções de coleta.

## Preparar o ambiente

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,export,publish]"
```

Para coletar, basta instalar `python -m pip install -e .`. Os grupos opcionais são `dev` (testes e lint), `export` (Parquet) e `publish` (Kaggle). Os testes da interface também usam Node.js.

## Validar sem coleta real

```powershell
python -m ruff check .
python -m pytest -q
python -m pytest --cov --cov-report=term-missing --cov-report=html
```

O relatório de cobertura fica em `htmlcov/index.html`. Os testes usam bases temporárias e respostas simuladas. Cobertura não substitui a conferência dos resultados.

Para conferir a mesma versão de Python usada na CI sem substituir seu ambiente atual, crie um ambiente separado na pasta local ignorada `data`:

```powershell
py -3.12 -m venv data/venv-validacao-py312
.\data\venv-validacao-py312\Scripts\python.exe -m pip install -e ".[dev,export,publish]"
.\data\venv-validacao-py312\Scripts\python.exe -m ruff check .
.\data\venv-validacao-py312\Scripts\python.exe -m pytest -q --cov --cov-report=term --cov-report=html -W error::ResourceWarning
```

A instalação baixa dependências; os testes seguintes usam respostas simuladas. É necessário ter Python 3.12 e Node.js instalados. Se a criação do ambiente ou a instalação falhar, corrija essa etapa antes de continuar.

## Fazer uma coleta curta

```powershell
python main.py --sources gupy --terms "desenvolvedor junior" --max-pages 1 --page-size 20 --no-enrich --output output-teste-rapido
```

Este comando faz chamadas reais à Gupy. Limita a busca a um termo e uma página, mas não garante um tempo máximo. Os filtros podem remover parte dos resultados. A saída fica separada da coleta normal. O comando não importa vagas no SQLite nem publica arquivos. `--no-enrich` desativa os detalhes do LinkedIn; não é um bloqueio geral de rede.

## Baixar a base de trabalho

O banco não está no Git. `git pull` atualiza o código, não os dados. Antes de baixar a base, feche o DBeaver e preserve qualquer alteração local ainda não publicada: o download substitui o arquivo de destino.

```powershell
git pull --ff-only origin main
python scripts/release_snapshot.py download --allow-legacy
```

O script usa o GitHub CLI (`gh`), que deve estar autenticado. Ele valida o snapshot e registra seu hash de origem em `data/snapshot-base.json`. Use `--allow-legacy` apenas durante a transição de releases antigas sem manifesto. Se houver manifesto, ele é obrigatório e validado mesmo com essa opção.

Quantidade de vagas e maior ID ajudam a conferir a base, mas não provam que ela está atualizada. Uma correção de descrição ou skill pode manter ambos iguais.

## Coletar e consolidar

Uma coleta normal pode demorar. Execute somente quando quiser consultar os portais:

```powershell
python main.py --no-enrich
python scripts/import_csv.py
python scripts/enrich_outras_fontes.py --summary-json data/enrich-outras.json
python scripts/enrich_descriptions.py --summary-json data/enrich-linkedin.json
python scripts/reclassify_areas.py
```

O importador sem `--csv` usa o CSV mais recente em `output`. Para importar um arquivo específico, use `--csv caminho.csv`. Importação e enriquecimento aplicam as migrações internas quando necessário. Faça a primeira migração em uma cópia antes de adotá-la na base de trabalho. A importação não regenera os JSONs automaticamente; use o exportador explícito abaixo.

A reextração global continua sendo uma manutenção deliberada. Ela não foi adicionada à rotina diária. Para avaliar mudanças sem gravar:

```powershell
python scripts/reextract_all_skills.py --db data/vagas.db --dry-run
```

Quando a regra de modalidade do LinkedIn mudar, reavalie a base sem fazer chamadas:

```powershell
python scripts/reclassify_workplaces.py --db data/vagas.db
```

O workflow usa `--quality-gate`, compara `output/collection_metrics.json` com o
histórico da release e só registra a rodada depois das validações. Não use
`collection_health.py record` para uma correção manual: frescor representa uma
coleta real.

## Gerar saídas locais

```powershell
python scripts/export_seed.py
python scripts/report_db.py
python scripts/export_pages_data.py
python scripts/export_readme_charts.py --output-dir _site/assets
python scripts/build_pages.py
python scripts/export_kaggle.py --export-only
```

Estes comandos não publicam nada. Os leitores exigem um banco existente. Os comandos de banco aceitam `--db`; sem ele, usam `DATABASE_URL`, depois `VAGAS_DB` e, por fim, `data/vagas.db`.

## Publicar e recuperar falhas

Não publique localmente enquanto um Action estiver trabalhando sobre a mesma release. A trava dos workflows não bloqueia um comando iniciado no computador.

```powershell
python scripts/release_snapshot.py publish --allow-legacy
python scripts/export_kaggle.py
```

O primeiro comando prepara DB e CSV da mesma cópia consistente, verifica o hash da base remota e confirma os artefatos após o envio. Não use `gh release upload --clobber` no fluxo normal, pois ele ignora essas verificações. Para usar outra base, passe também um `--state` separado nos comandos de download e publicação.

Uma falha no Kaggle não desfaz a release. O workflow **Publicar Snapshot no Kaggle** repete somente essa entrega, sem nova coleta. A confirmação compara o Parquet de uma versão identificada, não apenas o número da versão.

Se o upload da release falhar, preserve `data/snapshots/<hash>/`. Nos Actions, os arquivos disponíveis são guardados no artefato de recuperação por sete dias. Uma publicação confirmada remove somente sua cópia temporária de recuperação.

O upload de vários assets não é atômico: uma interrupção pode deixar uma release incompleta. Nesse caso, não force uma nova coleta nem baixe por cima do banco de trabalho. Preserve a cópia de recuperação, pare os escritores e confira os hashes e a origem antes de restaurar os assets do mesmo snapshot. Se outro snapshot já foi publicado, reconcilie as mudanças; não restaure uma base antiga por cima dele.

Consulte também a [organização do código](arquitetura.md).
