"""Mesa falsa, em memória, com a mesma interface de `conexao.Mesa`.

Permite testar o fluxo completo (calibrar --aplicar, desfazer) sem estar na rede da mesa.
O estado é guardado em um arquivo JSON para sobreviver entre execuções.
"""
import json
from pathlib import Path

from .conexao import formatar_valor, interpretar_set
from . import mapeamento_eq as m

FREQS_PADRAO = (100.0, 400.0, 1600.0, 6400.0)


def estado_inicial(canais: int = 24) -> dict[str, str]:
    estado = {}
    for canal in range(1, canais + 1):
        estado[m.caminho_hpf(canal)] = formatar_valor(m.hpf_para_valor(20.0))
        for banda, freq in enumerate(FREQS_PADRAO, start=1):
            estado[m.caminho_banda(canal, banda, "freq")] = formatar_valor(m.freq_para_valor(freq))
            estado[m.caminho_banda(canal, banda, "gain")] = formatar_valor(m.ganho_para_valor(0.0))
            estado[m.caminho_banda(canal, banda, "q")] = formatar_valor(m.q_para_valor(1.0))
    return estado


class MesaSimulada:
    ip = "simulada"

    def __init__(self, arquivo_estado: Path | None = None, canais: int = 24):
        self.arquivo_estado = Path(arquivo_estado) if arquivo_estado else None
        self.canais = canais
        self.estado: dict[str, str] = {}
        self.enviados: list[str] = []
        self._ouvintes = []

    def conectar(self) -> "MesaSimulada":
        if self.arquivo_estado and self.arquivo_estado.exists():
            self.estado = json.loads(self.arquivo_estado.read_text(encoding="utf-8"))
        else:
            self.estado = estado_inicial(self.canais)
        return self

    def __enter__(self) -> "MesaSimulada":
        return self.conectar()

    def __exit__(self, *_):
        self.fechar()

    def fechar(self):
        if self.arquivo_estado:
            self.arquivo_estado.parent.mkdir(parents=True, exist_ok=True)
            self.arquivo_estado.write_text(json.dumps(self.estado, indent=1), encoding="utf-8")

    def ouvir(self, callback):
        self._ouvintes.append(callback)

    def enviar(self, msg: str):
        self.enviados.append(msg)
        par = interpretar_set(msg)
        if par:
            self.estado[par[0]] = par[1]
        for callback in self._ouvintes:
            callback(msg)

    def setd(self, caminho: str, valor: float):
        self.enviar(f"SETD^{caminho}^{formatar_valor(valor)}")

    def obter(self, caminho: str) -> str | None:
        return self.estado.get(caminho)

    def aguardar_estado(self, timeout: float = 0, silencio: float = 0) -> int:
        return len(self.estado)
