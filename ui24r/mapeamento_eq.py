"""Conversão entre valores reais do EQ (Hz, dB, Q) e os valores 0..1 do protocolo da Ui24R.

ATENÇÃO: os caminhos e as escalas abaixo são a melhor estimativa e ainda precisam ser
confirmados na mesa real com `python autoeq.py espiar --canal N`: mexa no EQ pela interface
web e compare o valor mostrado na tela com a interpretação impressa pelo script. Se não
bater, ajuste só este arquivo.
"""
import math
import re

NUM_BANDAS = 4

FREQ_MIN, FREQ_MAX = 20.0, 22000.0   # frequência das bandas (escala logarítmica)
HPF_MIN, HPF_MAX = 20.0, 1000.0      # corta-graves (escala logarítmica)
GANHO_MIN, GANHO_MAX = -20.0, 20.0   # ganho das bandas (escala linear em dB)
Q_MIN, Q_MAX = 0.05, 15.0            # largura das bandas (escala logarítmica)

PARAMS_BANDA = ("freq", "gain", "q")


def caminho_hpf(canal: int) -> str:
    """Canal começa em 1 (como escrito na mesa); no protocolo começa em 0."""
    return f"i.{canal - 1}.eq.hpf.freq"


def caminho_banda(canal: int, banda: int, param: str) -> str:
    return f"i.{canal - 1}.eq.b{banda}.{param}"


def caminhos_eq(canal: int) -> list[str]:
    caminhos = [caminho_hpf(canal)]
    for banda in range(1, NUM_BANDAS + 1):
        caminhos += [caminho_banda(canal, banda, p) for p in PARAMS_BANDA]
    return caminhos


def _limitar(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _log_para_valor(x: float, lo: float, hi: float) -> float:
    return math.log(_limitar(x, lo, hi) / lo) / math.log(hi / lo)


def _valor_para_log(v: float, lo: float, hi: float) -> float:
    return lo * (hi / lo) ** _limitar(v, 0.0, 1.0)


def freq_para_valor(hz: float) -> float:
    return _log_para_valor(hz, FREQ_MIN, FREQ_MAX)


def valor_para_freq(v: float) -> float:
    return _valor_para_log(v, FREQ_MIN, FREQ_MAX)


def hpf_para_valor(hz: float) -> float:
    return _log_para_valor(hz, HPF_MIN, HPF_MAX)


def valor_para_hpf(v: float) -> float:
    return _valor_para_log(v, HPF_MIN, HPF_MAX)


def ganho_para_valor(db: float) -> float:
    return (_limitar(db, GANHO_MIN, GANHO_MAX) - GANHO_MIN) / (GANHO_MAX - GANHO_MIN)


def valor_para_ganho(v: float) -> float:
    return GANHO_MIN + _limitar(v, 0.0, 1.0) * (GANHO_MAX - GANHO_MIN)


def q_para_valor(q: float) -> float:
    return _log_para_valor(q, Q_MIN, Q_MAX)


def valor_para_q(v: float) -> float:
    return _valor_para_log(v, Q_MIN, Q_MAX)


_RE_EQ = re.compile(r"^i\.(\d+)\.eq\.(?:(hpf)\.freq|b(\d)\.(freq|gain|q))$")


def interpretar(caminho: str, valor: str) -> str | None:
    """Traduz uma mensagem de EQ para texto legível, usando o mapeamento atual."""
    m = _RE_EQ.match(caminho)
    if not m:
        return None
    try:
        v = float(valor)
    except ValueError:
        return None
    canal = int(m.group(1)) + 1
    if m.group(2):
        return f"canal {canal} HPF = {valor_para_hpf(v):.0f} Hz"
    banda, param = m.group(3), m.group(4)
    if param == "freq":
        texto = f"{valor_para_freq(v):.0f} Hz"
    elif param == "gain":
        texto = f"{valor_para_ganho(v):+.1f} dB"
    else:
        texto = f"Q {valor_para_q(v):.2f}"
    return f"canal {canal} banda {banda} {param} = {texto}"
