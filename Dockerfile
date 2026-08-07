# Imagem da API. O scraper nao roda aqui: portais de vaga costumam bloquear IP
# de nuvem, entao a coleta continua sendo feita na maquina de quem desenvolve e
# chega ao container pelo snapshot em seed/.
FROM python:3.11-slim

# PYTHONUNBUFFERED: sem isso o log do uvicorn fica preso no buffer e o
# `docker compose logs` so mostra as mensagens quando o processo termina.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# As dependencias entram antes do codigo para o cache de camadas do Docker
# sobreviver a cada alteracao em .py -- sem isso todo build reinstalaria tudo.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# So o que a API precisa. `scraper/` entra porque a API le os YAMLs de regras
# (areas e tecnologias) de la, e `scripts/` porque o compose importa o snapshot
# no boot.
COPY api/ ./api/
COPY scraper/ ./scraper/
COPY scripts/ ./scripts/
COPY seed/ ./seed/

# Usuario sem privilegios: um processo que so le dados nao precisa de root.
RUN useradd --create-home --uid 1000 vagas \
    && mkdir -p /app/data \
    && chown -R vagas:vagas /app
USER vagas

EXPOSE 8000

# Sem DATABASE_URL a imagem sobe em SQLite, igual ao comportamento local.
# O docker-compose sobrescreve isso para apontar ao Postgres.
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
