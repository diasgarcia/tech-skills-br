"""Apresentacao de progresso e captura limitada dos logs da coleta."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time as _time
from collections import deque

RESUMO_INTERVALO_S = 45.0

# Cores ANSI para o viewer do Actions (renderiza SGR; "clear" nao existe).
_ANSI = {
    "verde": "\033[32m",
    "vermelho": "\033[31m",
    "amarelo": "\033[33m",
    "ciano": "\033[36m",
    "cinza": "\033[90m",
    "negrito": "\033[1m",
}

_STATUS_COR = {
    "Concluido": _ANSI["verde"],
    "Erro": _ANSI["vermelho"],
    "Coletando": _ANSI["amarelo"],
    "Iniciando": _ANSI["cinza"],
}


def _cor(estilo: str, texto: str) -> str:
    return f"{estilo}{texto}\033[0m"


class _CapturaHandler(logging.Handler):
    """Captura apenas logs do pacote, com limites de linhas e de caracteres."""

    def __init__(self, destino: deque[str], max_chars: int = 4000) -> None:
        super().__init__()
        self._destino = destino
        self.max_chars = max_chars
        self.omitidas = 0
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        if len(self._destino) == self._destino.maxlen:
            self.omitidas += 1
        line = self.format(record)
        self._destino.append(line[:self.max_chars])


class _SilenciarColeta(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.name == "scraper" or record.name.startswith("scraper."))


class _BufferLog:
    """Silencia o logging durante a coleta paralela e despeja no final.

    Na rodada padrao o monitor (tabela) e a unica saida durante a coleta:
    as linhas das fontes (sitemaps, warnings de 429/500 etc.) ficam
    guardadas e aparecem juntas no fim, como um log geral.
    """

    def __init__(self, max_lines: int = 1000) -> None:
        if max_lines < 1:
            raise ValueError("max_lines deve ser positivo")
        self.linhas: deque[str] = deque(maxlen=max_lines)
        self._handler: _CapturaHandler | None = None
        self._filtrados: list[logging.Handler] = []
        self._filtro = _SilenciarColeta()
        self.omitidas = 0

    def ativar(self) -> None:
        if self._handler is not None:
            return
        self._handler = _CapturaHandler(self.linhas)
        logging.getLogger("scraper").addHandler(self._handler)
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler) and handler.stream in (sys.stdout, sys.stderr):
                handler.addFilter(self._filtro)
                self._filtrados.append(handler)

    def desativar(self) -> None:
        if self._handler is not None:
            self.omitidas += self._handler.omitidas
            logging.getLogger("scraper").removeHandler(self._handler)
            self._handler.close()
            self._handler = None
        for handler in self._filtrados:
            handler.removeFilter(self._filtro)
        self._filtrados.clear()

    def despejar(self) -> None:
        if not self.linhas:
            return
        print("------  log geral da coleta  ------", flush=True)
        if self.omitidas:
            print(f"{self.omitidas} linhas antigas omitidas do resumo em memoria.", flush=True)
        for linha in self.linhas:
            print(linha, flush=True)


FONTES_LABELS = {
    "linkedin": "LinkedIn",
    "gupy": "Gupy",
    "vagas": "Vagas.com",
    "trampos": "Trampos.co",
    "solides": "Solides",
    "geekhunter": "GeekHunter",
    "infojobs": "InfoJobs",
    "abler": "Abler",
    "recrutei": "Recrutei",
}


class _TabelaParalela:
    """Monitor de progresso em tabela para coleta paralela entre fontes.

    - Em terminal interativo (TTY local): redesenha a tabela in-place sem rolar telas.
    - No GitHub Actions / nao-TTY: imprime snapshots da tabela como linhas
      planas (sempre visiveis; o Actions nao deixa controlar o estado
      inicial de um ::group:: e nao renderiza ANSI, entao nada de "clear").
    """

    def __init__(self, fontes: list[str], labels: dict[str, str] | None = None) -> None:
        self.fontes = list(fontes)
        self.labels = labels or {}
        self.is_ci = os.getenv("GITHUB_ACTIONS") == "true"
        self.is_tty = sys.stdout.isatty() and not self.is_ci

        if self.is_tty and sys.platform == "win32":
            os.system("")  # Ativa virtual terminal ANSI no conhost se necessario

        self.estado: dict[str, dict] = {
            f: {
                "label": self.labels.get(f, FONTES_LABELS.get(f, f.capitalize())),
                "status": "Iniciando",
                "vagas": 0,
                "requests": 0,
                "termo": "-",
                "progresso": 0.0,
            }
            for f in fontes
        }
        self.lock = threading.RLock()
        self.inicio = _time.time()
        self.linhas_impressas = 0
        self.ultimo_render = 0.0
        self.parar = threading.Event()
        self.thread_timer: threading.Thread | None = None

    def formatar(self) -> str:
        with self.lock:
            decorrido = _time.time() - self.inicio
            minutos, segundos = divmod(int(decorrido), 60)
            tempo_str = f"{minutos:02d}m{segundos:02d}s"

            total_vagas = sum(d["vagas"] for d in self.estado.values())
            total_reqs = sum(d["requests"] for d in self.estado.values())
            concluidas = sum(
                1 for d in self.estado.values()
                if d["status"] == "Concluido" or d["status"].startswith("Erro")
            )
            total_fontes = len(self.estado)

            cabecalho = (
                f"[Coleta Paralela: {total_fontes} fontes | "
                f"{concluidas}/{total_fontes} concluidas | "
                f"{self._percentual()}% | {tempo_str} decorridos]"
            )

            # A ultima coluna cresce conforme o conteudo (sem cortar o termo);
            # o log do Actions tem scroll horizontal para linhas longas.
            celulas_info = [d["termo"] or "-" for d in
                            (self.estado[n] for n in self.fontes)]
            celulas_info.append(f"{total_vagas} vagas brutas")
            larg_info = max(len("Ultimo Termo / Info"), *(len(c) for c in celulas_info))

            larguras = [20, 10, 7, 8, larg_info]
            borda = "+" + "+".join("-" * (w + 2) for w in larguras) + "+"
            cabecalhos = ["Fonte", "Status", "Vagas", "Requests", "Ultimo Termo / Info"]
            colorir = self.is_ci or self.is_tty

            def cel(c, w, cor=None):
                t = c.ljust(w)
                return _cor(cor, t) if (cor and colorir) else t

            linhas = [
                cabecalho,
                borda,
                "| " + " | ".join(cel(c, w, _ANSI["ciano"]) for c, w in zip(cabecalhos, larguras)) + " |",
                borda,
            ]

            for nome in self.fontes:
                d = self.estado[nome]
                lbl = d["label"][:20]
                st = d["status"][:10]
                vg = f"{d['vagas']:,}".replace(",", ".")
                rq = f"{d['requests']:,}".replace(",", ".")
                tm = d["termo"] or "-"
                linhas.append(
                    "| " + " | ".join([
                        cel(lbl, 20),
                        cel(st, 10, self._cor_status(d["status"])),
                        cel(vg.rjust(7), 7),
                        cel(rq.rjust(8), 8),
                        cel(tm, larg_info),
                    ]) + " |"
                )

            linhas.append(borda)
            resumo_st = f"{concluidas}/{total_fontes} conc."
            tot_vg = f"{total_vagas:,}".replace(",", ".")
            tot_rq = f"{total_reqs:,}".replace(",", ".")
            tot_info = f"{total_vagas} vagas brutas"
            linhas.append(
                "| " + " | ".join([
                    cel("TOTAL", 20, _ANSI["negrito"]),
                    cel(resumo_st, 10),
                    cel(tot_vg.rjust(7), 7),
                    cel(tot_rq.rjust(8), 8),
                    cel(tot_info, larg_info),
                ]) + " |"
            )
            linhas.append(borda)
            return "\n".join(linhas)

    def atualizar(
        self,
        nome: str,
        total: int | None = None,
        termo: str | None = None,
        requests: int | None = None,
        status: str | None = None,
        progresso: float | None = None,
    ) -> None:
        with self.lock:
            if nome in self.estado:
                if total is not None:
                    self.estado[nome]["vagas"] = total
                if termo is not None:
                    self.estado[nome]["termo"] = termo
                if requests is not None:
                    self.estado[nome]["requests"] = requests
                if progresso is not None:
                    self.estado[nome]["progresso"] = min(1.0, max(0.0, progresso))
                if status is not None:
                    self.estado[nome]["status"] = status
                elif self.estado[nome]["status"] == "Iniciando":
                    self.estado[nome]["status"] = "Coletando"

    @staticmethod
    def _cor_status(status: str) -> str | None:
        if status.startswith("Erro"):
            return _ANSI["vermelho"]
        return _STATUS_COR.get(status)

    def _percentual(self) -> int:
        with self.lock:
            if not self.estado:
                return 0
            return round(
                100 * sum(d["progresso"] for d in self.estado.values())
                / len(self.estado)
            )

    def finalizar_fonte(self, nome: str, total: int, requests: int) -> None:
        with self.lock:
            if nome in self.estado:
                self.estado[nome]["vagas"] = total
                self.estado[nome]["requests"] = requests
                self.estado[nome]["status"] = "Concluido"
                self.estado[nome]["termo"] = "finalizado"
                self.estado[nome]["progresso"] = 1.0
        if not self.is_tty:
            # Em CI/nao-TTY, renderiza se ja passou intervalo ou se todas terminaram
            concluidas = sum(
                1 for d in self.estado.values()
                if d["status"] == "Concluido" or d["status"].startswith("Erro")
            )
            if concluidas == len(self.estado):
                self.renderizar(forcar=True)
            else:
                self.renderizar(forcar=False)

    def erro_fonte(self, nome: str, erro: str = "", codigo: int | None = None) -> None:
        with self.lock:
            if nome in self.estado:
                self.estado[nome]["status"] = (
                    f"Erro {codigo}" if codigo else "Erro"
                )
                self.estado[nome]["termo"] = erro or "erro"
                self.estado[nome]["progresso"] = 1.0
        if not self.is_tty:
            self.renderizar(forcar=False)

    def renderizar(self, forcar: bool = False) -> None:
        agora = _time.time()
        if not self.is_tty and not forcar:
            # Em CI/nao-TTY, evita snapshots repetidos em menos de 15 segundos
            if agora - self.ultimo_render < 15.0:
                return

        texto = self.formatar()
        linhas = texto.splitlines()

        if self.is_ci:
            # Linhas planas, sem ::group::: o Actions decide sozinho se o
            # grupo nasce aberto ou fechado (hoje nasce fechado), e nao
            # existe parametro para forcar. A linha de titulo continua
            # permitindo um resumo de relance no meio do log.
            with self.lock:
                decorrido = agora - self.inicio
                minutos, segundos = divmod(int(decorrido), 60)
                tempo_str = f"{minutos:02d}m{segundos:02d}s"
                total_vagas = sum(d["vagas"] for d in self.estado.values())
                concluidas = sum(
                    1 for d in self.estado.values()
                    if d["status"] == "Concluido" or d["status"].startswith("Erro")
                )
                titulo = (
                    f"[resumo {_time.strftime('%H:%M:%S')}] {total_vagas} vagas | "
                    f"{concluidas}/{len(self.estado)} fontes ({tempo_str}) | "
                    f"{self._percentual()}%"
                )
            # "Respirar" entre snapshots: linha vazia nao renderiza no
            # viewer do Actions (HTML colapsa), mas uma linha com espacos
            # sobrevive e funciona como enter visual.
            print("  ", flush=True)
            print(_cor(_ANSI["negrito"], titulo), flush=True)
            print(texto, flush=True)
            # Separador visual entre um snapshot e o seguinte.
            print("-" * 144, flush=True)
            print("  ", flush=True)
            self.ultimo_render = agora
        elif self.is_tty:
            if self.linhas_impressas > 0:
                sys.stdout.write(f"\033[{self.linhas_impressas}F")
            sys.stdout.write(texto + "\n")
            sys.stdout.flush()
            self.linhas_impressas = len(linhas)
            self.ultimo_render = agora
        else:
            print(texto, flush=True)
            self.ultimo_render = agora

    def iniciar(self) -> None:
        intervalo = 1.0 if self.is_tty else RESUMO_INTERVALO_S

        def _loop():
            while not self.parar.wait(intervalo):
                self.renderizar()

        self.renderizar(forcar=True)
        self.thread_timer = threading.Thread(target=_loop, daemon=True)
        self.thread_timer.start()

    def encerrar(self) -> None:
        self.parar.set()
        if self.thread_timer is not None:
            self.thread_timer.join(timeout=2.0)
        if self.is_tty:
            self.renderizar(forcar=True)
            print("", flush=True)
        else:
            if _time.time() - self.ultimo_render > 1.0:
                self.renderizar(forcar=True)
