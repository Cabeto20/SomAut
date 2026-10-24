"""Cliente WebSocket para mesas Soundcraft Ui (Ui12/Ui16/Ui24R).

Protocolo (baseado na biblioteca github.com/fmalcher/soundcraft-ui):
- conexão em ws://IP_DA_MESA
- cada mensagem vai prefixada com "3:::" (ex.: "3:::SETD^i.0.mix^0.5")
- o cliente envia "ALIVE" a cada 1 s para manter a conexão aberta
- logo após conectar, a mesa envia o estado completo (muitas linhas SETD/SETS)
"""
import threading
import time
from typing import Callable

import websocket

PREFIXO = "3:::"


class ErroConexao(Exception):
    pass


def formatar_valor(valor: float) -> str:
    texto = f"{valor:.6f}".rstrip("0").rstrip(".")
    return texto or "0"


def separar_mensagens(quadro: str) -> list[str]:
    """Um quadro WebSocket pode trazer várias mensagens separadas por quebra de linha."""
    mensagens = []
    for linha in quadro.splitlines():
        linha = linha.strip()
        if linha.startswith(PREFIXO):
            linha = linha[len(PREFIXO):]
        elif len(linha) >= 3 and linha[0].isdigit() and linha[1:3] == "::":
            continue  # quadros de controle do socket.io
        if linha:
            mensagens.append(linha)
    return mensagens


def interpretar_set(msg: str) -> tuple[str, str] | None:
    partes = msg.split("^", 2)
    if len(partes) == 3 and partes[0] in ("SETD", "SETS"):
        return partes[1], partes[2]
    return None


class Mesa:
    def __init__(self, ip: str, timeout: float = 5.0):
        self.ip = ip
        self.timeout = timeout
        self.estado: dict[str, str] = {}
        self._ws = None
        self._ouvintes: list[Callable[[str], None]] = []
        self._rodando = False
        self._lock = threading.Lock()
        self._ultimo_set = 0.0
        self._threads: list[threading.Thread] = []

    def conectar(self) -> "Mesa":
        url = f"ws://{self.ip}"
        try:
            self._ws = websocket.create_connection(url, timeout=self.timeout)
        except (OSError, websocket.WebSocketException) as e:
            raise ErroConexao(f"Não consegui conectar em {url}: {e}") from e
        self._ws.settimeout(1.0)
        self._rodando = True
        for alvo in (self._ler, self._manter_viva):
            t = threading.Thread(target=alvo, daemon=True)
            t.start()
            self._threads.append(t)
        return self

    def __enter__(self) -> "Mesa":
        return self.conectar()

    def __exit__(self, *_):
        self.fechar()

    def fechar(self):
        self._rodando = False
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
        for t in self._threads:
            t.join(timeout=2)
        self._threads.clear()

    def ouvir(self, callback: Callable[[str], None]):
        """Registra uma função chamada a cada mensagem recebida (já sem o prefixo)."""
        self._ouvintes.append(callback)

    def enviar(self, msg: str):
        with self._lock:
            if self._ws is None or not self._rodando:
                raise ErroConexao("Conexão com a mesa não está aberta.")
            self._ws.send(PREFIXO + msg)

    def setd(self, caminho: str, valor: float):
        texto = formatar_valor(valor)
        self.enviar(f"SETD^{caminho}^{texto}")
        self.estado[caminho] = texto

    def obter(self, caminho: str) -> str | None:
        return self.estado.get(caminho)

    def aguardar_estado(self, timeout: float = 8.0, silencio: float = 0.7) -> int:
        """Espera o 'dump' inicial terminar (nenhum SETD novo por `silencio` segundos)."""
        inicio = time.monotonic()
        while time.monotonic() - inicio < timeout:
            if self.estado and time.monotonic() - self._ultimo_set > silencio:
                break
            time.sleep(0.1)
        return len(self.estado)

    def _ler(self):
        while self._rodando:
            try:
                quadro = self._ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                self._rodando = False
                break
            if isinstance(quadro, bytes):
                quadro = quadro.decode("utf-8", "replace")
            for msg in separar_mensagens(quadro):
                par = interpretar_set(msg)
                if par:
                    self.estado[par[0]] = par[1]
                    self._ultimo_set = time.monotonic()
                for callback in self._ouvintes:
                    callback(msg)

    def _manter_viva(self):
        while self._rodando:
            try:
                self.enviar("ALIVE")
            except Exception:
                pass
            time.sleep(1.0)
