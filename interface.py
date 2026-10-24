"""Interface de testes no navegador: grava a voz, mostra o EQ sugerido e toca antes/depois no fone.

Uso:  .\\.venv\\Scripts\\python.exe interface.py      (abre o navegador sozinho; Ctrl+C para sair)
"""
import io
import json
import os
import queue
import sys
import threading
import time
import traceback
import webbrowser
from concurrent.futures import Future
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

os.environ.setdefault("SD_ENABLE_ASIO", "1")

import numpy as np
import sounddevice as sd
from scipy import signal

from analise import pipeline, solver_eq
from analise.espectro import NOMINAIS
from analise.processar import aplicar_eq, igualar_volume
from audio.arquivo import ler_wav, salvar_wav
from audio.captura import ErroAudio, configurar_canal
from autoeq import PASTA, carregar_config
from ui24r import aplicar
from ui24r.conexao import ErroConexao, Mesa
from ui24r.simulador import MesaSimulada

PORTA = 8765
HOSTAPIS_PREFERIDAS = ("ASIO", "Windows WASAPI", "MME")
FREQS_CURVA = np.geomspace(20, 20000, 160)


def listar(tipo: str) -> list[dict]:
    """Entradas ou saídas, só da melhor API de áudio disponível (evita a lista repetida)."""
    hostapis = sd.query_hostapis()
    chave = "max_input_channels" if tipo == "entrada" else "max_output_channels"
    todos = [(i, d, hostapis[d["hostapi"]]["name"]) for i, d in enumerate(sd.query_devices()) if d[chave] > 0]
    presentes = {h for _, _, h in todos}
    comuns = [api for api in HOSTAPIS_PREFERIDAS[1:] if api in presentes]
    usar = {"ASIO", comuns[0]} if comuns else presentes
    return [{"indice": i, "nome": d["name"], "api": h, "taxa": int(d["default_samplerate"]), "canais": d[chave]}
            for i, d, h in todos if h in usar]


def _nome_padrao(tipo: str) -> str | None:
    padrao = sd.default.device[0 if tipo == "entrada" else 1]
    return sd.query_devices(padrao)["name"] if padrao is not None and padrao >= 0 else None


def _aparelho(nome: str) -> str:
    """'Microfone (H2015 Pro)' -> 'h2015 pro' (nome do aparelho, sem o tipo da porta)."""
    return nome[nome.find("(") + 1:].rstrip(")").strip().lower() if "(" in nome else nome.lower()


def indice_padrao(tipo: str, lista: list[dict]) -> int | None:
    """Escolhe o dispositivo inicial. Para o microfone, prefere o do mesmo aparelho da saída
    padrão (ex.: o fone-microfone); senão, o padrão do Windows (nomes do MME vêm cortados)."""
    if not lista:
        return None
    if tipo == "entrada" and (saida := _nome_padrao("saida")):
        for d in lista:
            if _aparelho(d["nome"])[:20] == _aparelho(saida)[:20]:
                return d["indice"]
    if nome := _nome_padrao(tipo):
        for d in lista:
            if d["nome"].startswith(nome[:31]) or nome.startswith(d["nome"][:31]):
                return d["indice"]
    return lista[0]["indice"]


def _eq_json(eq) -> dict | None:
    """(hpf, bandas) -> JSON com a curva, para mostrar o EQ que está na mesa."""
    if eq is None:
        return None
    hpf, bandas = eq
    curva = solver_eq.resposta_eq(bandas, hpf, FREQS_CURVA)
    return {
        "hpf": round(hpf) if hpf is not None else None,
        "bandas_eq": [{"freq": round(b.freq), "ganho": round(b.ganho_db, 1), "q": round(b.q, 2)} for b in bandas],
        "curva": [[round(float(f), 1), round(float(g), 2)] for f, g in zip(FREQS_CURVA, curva)],
    }


class Estudio:
    """Estado da sessão de testes (uma gravação por vez)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.eq_atual: dict[str, float] | None = None  # EQ lido da mesa (valores 0..1)
        self.eq_atual_canal = 0
        self.sinal: np.ndarray | None = None
        self.taxa = 48000
        self.origem = ""
        self.resultado = None
        self.gravando = False
        self.fim_gravacao = 0.0
        self.nivel_db = -90.0
        self.pico_max = 0.0
        self._blocos: list[np.ndarray] = []
        self._stream = None

    @property
    def cfg(self) -> dict:
        """Relido a cada uso, como no terminal (mudanças no config.yaml valem na hora)."""
        return carregar_config(PASTA / "config.yaml")

    # --- gravação -------------------------------------------------------------------------
    def gravar(self, entrada: int, segundos: float, canal: int):
        if self.gravando:
            raise ValueError("Já está gravando.")
        if self._stream is not None:
            self._stream.close()
        info = sd.query_devices(entrada)
        hostapi = sd.query_hostapis(info["hostapi"])["name"]
        canais, coluna, extra = configurar_canal(hostapi, canal, int(info["max_input_channels"]), info["name"])
        taxa = int(info["default_samplerate"])
        total = int(segundos * taxa)
        self._blocos, self.pico_max, self.nivel_db = [], 0.0, -90.0
        contagem = {"n": 0}

        def ao_receber(dados, frames, _tempo, _status):
            bloco = dados[:, coluna].astype(np.float64)
            self._blocos.append(bloco.copy())
            pico = float(np.max(np.abs(bloco))) if frames else 0.0
            self.nivel_db = 20 * np.log10(pico + 1e-9)
            self.pico_max = max(self.pico_max, pico)
            contagem["n"] += frames
            if contagem["n"] >= total:
                raise sd.CallbackStop

        def ao_terminar():
            with self.lock:
                self.sinal = np.concatenate(self._blocos)[:total] if self._blocos else None
                self.taxa = taxa
                self.origem = f"gravação ({info['name']}, canal {canal})"
                self.resultado = None
                self.gravando = False

        self._stream = sd.InputStream(device=entrada, channels=canais, samplerate=taxa, dtype="float32",
                                      callback=ao_receber, finished_callback=ao_terminar, **extra)
        self._stream.start()
        self.gravando = True
        self.fim_gravacao = time.monotonic() + segundos

    def parar_gravacao(self):
        if self._stream is not None and self.gravando:
            self._stream.stop()
            self._stream.close()

    def carregar_wav(self, dados: bytes, nome: str, canal: int = 1):
        sinal, taxa = ler_wav(io.BytesIO(dados), canal)
        with self.lock:
            self.sinal, self.taxa, self.resultado = sinal, taxa, None
            self.origem = f"arquivo {nome}, canal {canal}"

    # --- análise e audição ----------------------------------------------------------------
    def analisar(self, perfil: str, intensidade: float, canal_mesa: int) -> dict:
        """Mesmo cálculo do `autoeq.py calibrar` (limites e pos_eq do config.yaml)."""
        if self.sinal is None:
            raise ValueError("Grave sua voz (ou abra um WAV) primeiro.")
        cfg = self.cfg
        antes = self._eq_atual_legivel(canal_mesa)
        avisos = []
        existente = None
        if cfg["audio"].get("pos_eq"):
            if antes is None:
                avisos.append(f"pos_eq ligado mas o EQ atual do canal {canal_mesa} não foi lido: "
                              "clique em \"Ler EQ atual\" na parte da mesa e analise de novo.")
            else:
                existente = antes
        lim = cfg["limites"]
        self.resultado = pipeline.analisar(self.sinal, self.taxa, perfil, intensidade,
                                           float(lim["ganho_min_db"]), float(lim["ganho_max_db"]),
                                           eq_existente=existente)
        self.resultado.avisos += avisos
        return self.resultado_json(antes)

    def _eq_atual_legivel(self, canal: int):
        if self.eq_atual and self.eq_atual_canal == canal:
            return aplicar.eq_legivel(self.eq_atual, canal)
        return None

    def resultado_json(self, antes=None) -> dict:
        r = self.resultado
        s = r.sugestao
        curva = solver_eq.resposta_eq(s.bandas, s.hpf_hz, FREQS_CURVA)
        return {
            "antes": _eq_json(antes),
            "avisos": r.avisos,
            "segundos_voz": round(r.segundos_voz, 1),
            "taxa": r.taxa,
            "f0": round(s.f0_mediana) if s.f0_mediana else None,
            "hpf": s.hpf_hz,
            "bandas_eq": [{"freq": b.freq, "ganho": b.ganho_db, "q": b.q, "rotulo": b.rotulo} for b in s.bandas],
            "bandas": [{"nominal": n, "antes": round(float(a), 2), "depois": round(float(d), 2), "valido": bool(v)}
                       for n, a, d, v in zip(NOMINAIS, s.desvio, s.depois, s.validos)],
            "curva": [[round(float(f), 1), round(float(g), 2)] for f, g in zip(FREQS_CURVA, curva)],
        }

    def ouvir(self, saida: int, versao: str):
        if self.sinal is None:
            raise ValueError("Não há gravação.")
        audio = self.sinal
        if versao == "eq":
            if self.resultado is None:
                raise ValueError("Analise primeiro para ouvir com EQ.")
            audio = igualar_volume(aplicar_eq(self.sinal, self.taxa, self.resultado.sugestao), self.sinal)
        info = sd.query_devices(saida)
        taxa_saida = int(info["default_samplerate"])
        if taxa_saida != self.taxa:
            divisor = np.gcd(taxa_saida, self.taxa)
            audio = signal.resample_poly(audio, taxa_saida // divisor, self.taxa // divisor)
        audio = np.clip(audio, -1, 1).astype(np.float32)
        if info["max_output_channels"] >= 2:
            audio = np.column_stack([audio, audio])  # mesmo som nos dois lados do fone
        sd.stop()
        sd.play(audio, taxa_saida, device=saida)

    def salvar(self) -> str:
        if self.sinal is None:
            raise ValueError("Não há gravação para salvar.")
        pasta = PASTA / "gravacoes"
        pasta.mkdir(exist_ok=True)
        arquivo = pasta / f"voz_{datetime.now():%Y%m%d_%H%M%S}.wav"
        salvar_wav(arquivo, self.sinal, self.taxa)
        return str(arquivo.relative_to(PASTA))

    # --- mesa -----------------------------------------------------------------------------
    def _mesa(self, destino: str, ip: str):
        if destino == "simulada":
            return MesaSimulada(PASTA / "backups" / "mesa_simulada.json").conectar()
        mesa = Mesa(ip).conectar()
        if mesa.aguardar_estado() == 0:
            mesa.fechar()
            raise ValueError("A mesa conectou mas não enviou o estado. Confira o IP.")
        return mesa

    def _guardar_eq_atual(self, mesa, canal: int) -> dict:
        self.eq_atual, self.eq_atual_canal = aplicar.ler_eq(mesa, canal), canal
        return _eq_json(self._eq_atual_legivel(canal))

    def ler_eq_da_mesa(self, destino: str, ip: str, canal: int) -> dict:
        mesa = self._mesa(destino, ip)
        try:
            atual = self._guardar_eq_atual(mesa, canal)
        finally:
            mesa.fechar()
        if atual is None:
            raise ValueError(f"A mesa não informou o EQ do canal {canal}.")
        return {"mensagem": f"EQ atual do canal {canal} lido da mesa {destino}.", "antes": atual}

    def aplicar_na_mesa(self, destino: str, ip: str, canal: int) -> dict:
        if self.resultado is None:
            raise ValueError("Analise primeiro.")
        mesa = self._mesa(destino, ip)
        try:
            backup = aplicar.aplicar_sugestao(mesa, canal, self.resultado.sugestao, PASTA / "backups")
            atual = self._guardar_eq_atual(mesa, canal)
        finally:
            mesa.fechar()
        return {"mensagem": f"EQ aplicado no canal {canal} da mesa {destino}. Backup: {backup.name}",
                "antes": atual}

    def desfazer(self, destino: str, ip: str, canal: int) -> dict:
        mesa = self._mesa(destino, ip)
        try:
            arquivo = aplicar.restaurar_ultimo(mesa, canal, PASTA / "backups")
            atual = self._guardar_eq_atual(mesa, canal)
        finally:
            mesa.fechar()
        if not arquivo:
            return {"mensagem": f"Nenhum backup para o canal {canal}.", "antes": atual}
        return {"mensagem": f"Canal {canal} restaurado a partir de {arquivo.name}.", "antes": atual}

    def estado_json(self) -> dict:
        return {
            "gravando": self.gravando,
            "restante": max(0.0, round(self.fim_gravacao - time.monotonic(), 1)) if self.gravando else 0,
            "nivel_db": round(self.nivel_db, 1),
            "clipou": self.pico_max >= 0.99,
            "tem_audio": self.sinal is not None,
            "duracao": round(len(self.sinal) / self.taxa, 1) if self.sinal is not None else 0,
            "origem": self.origem,
        }


class FilaPrincipal:
    """Executa funções na thread principal. Neste Windows o PortAudio só consegue iniciar
    gravação/reprodução na thread em que foi carregado; o servidor web roda em outras threads."""

    def __init__(self):
        self._fila: queue.Queue = queue.Queue()

    def executar(self, funcao, *args):
        futuro: Future = Future()
        self._fila.put((futuro, funcao, args))
        return futuro.result(timeout=30)

    def rodar(self):
        while True:
            try:
                futuro, funcao, args = self._fila.get(timeout=0.2)  # timeout: deixa o Ctrl+C funcionar
            except queue.Empty:
                continue
            try:
                futuro.set_result(funcao(*args))
            except Exception as e:
                futuro.set_exception(e)


ESTUDIO = Estudio()
FILA = FilaPrincipal()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _responder(self, codigo: int, corpo: bytes, tipo: str = "application/json; charset=utf-8"):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, dados, codigo: int = 200):
        self._responder(codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._responder(200, (PASTA / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/inicio":
            entradas, saidas = FILA.executar(listar, "entrada"), FILA.executar(listar, "saida")
            cfg = ESTUDIO.cfg
            self._json({
                "entradas": entradas, "saidas": saidas,
                "entrada_padrao": FILA.executar(indice_padrao, "entrada", entradas),
                "saida_padrao": FILA.executar(indice_padrao, "saida", saidas),
                "perfil": cfg["perfil"], "intensidade": cfg["intensidade"],
                "ip": cfg["ip_mesa"], "canal": cfg["canal_mesa"],
                "dispositivo_mesa": str(cfg["audio"]["dispositivo"]), "offset_usb": int(cfg["audio"]["offset_usb"]),
                "pos_eq": bool(cfg["audio"].get("pos_eq")),
                "perfis": {k: v["descricao"] for k, v in solver_eq.PERFIS.items()},
            })
        elif self.path == "/api/estado":
            self._json(ESTUDIO.estado_json())
        else:
            self._json({"erro": "não encontrado"}, 404)

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(tamanho) if tamanho else b""
        try:
            if self.path.startswith("/api/carregar_wav"):
                nome = unquote(self.headers.get("X-Nome-Arquivo", "arquivo.wav"))
                ESTUDIO.carregar_wav(corpo, nome, int(self.headers.get("X-Canal", "1")))
                self._json({"ok": True, **ESTUDIO.estado_json()})
                return
            p = json.loads(corpo or b"{}")
            acoes = {
                "/api/gravar": lambda: FILA.executar(ESTUDIO.gravar, int(p["entrada"]), float(p["segundos"]),
                                                     int(p["canal"])),
                "/api/parar_gravacao": lambda: FILA.executar(ESTUDIO.parar_gravacao),
                "/api/analisar": lambda: ESTUDIO.analisar(p["perfil"], float(p["intensidade"]), int(p["canal_mesa"])),
                "/api/ouvir": lambda: FILA.executar(ESTUDIO.ouvir, int(p["saida"]), p["versao"]),
                "/api/parar_audio": lambda: FILA.executar(sd.stop),
                "/api/salvar": lambda: {"mensagem": f"Gravação salva em {ESTUDIO.salvar()}"},
                "/api/ler_eq": lambda: ESTUDIO.ler_eq_da_mesa(p["destino"], p["ip"], int(p["canal"])),
                "/api/aplicar": lambda: ESTUDIO.aplicar_na_mesa(p["destino"], p["ip"], int(p["canal"])),
                "/api/desfazer": lambda: ESTUDIO.desfazer(p["destino"], p["ip"], int(p["canal"])),
            }
            if self.path not in acoes:
                self._json({"erro": "ação desconhecida"}, 404)
                return
            resposta = acoes[self.path]()
            self._json(resposta if isinstance(resposta, dict) else {"ok": True})
        except Exception as e:  # o erro aparece na tela, em vez de derrubar o servidor
            if not isinstance(e, (ValueError, sd.PortAudioError, OSError, ErroAudio, ErroConexao)):
                traceback.print_exc()
            self._json({"erro": str(e) or type(e).__name__}, 400)


def main():
    for porta in range(PORTA, PORTA + 10):
        try:
            servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit("Nenhuma porta livre entre 8765 e 8774.")
    url = f"http://127.0.0.1:{porta}/"
    print(f"Interface de testes aberta em {url}  (Ctrl+C aqui para encerrar)", flush=True)
    if "--sem-navegador" not in sys.argv:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        FILA.rodar()
    except KeyboardInterrupt:
        pass
    finally:
        sd.stop()
        servidor.shutdown()
        servidor.server_close()


if __name__ == "__main__":
    main()
