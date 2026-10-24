"""Aplica o EQ sugerido no próprio áudio, para ouvir o resultado no fone antes de ir para a mesa."""
import numpy as np
from scipy import signal

from .solver_eq import SugestaoEQ, coeficientes_peaking


def aplicar_eq(sinal: np.ndarray, taxa: int, sugestao: SugestaoEQ) -> np.ndarray:
    secoes = [signal.butter(2, sugestao.hpf_hz, "highpass", fs=taxa, output="sos")]
    for banda in sugestao.bandas:
        if banda.freq < taxa / 2 and abs(banda.ganho_db) > 1e-6:
            b, a = coeficientes_peaking(banda, fs=taxa)
            secoes.append(signal.tf2sos(b, a))
    return signal.sosfilt(np.vstack(secoes), sinal)


def igualar_volume(sinal: np.ndarray, referencia: np.ndarray, pico_max: float = 0.9) -> np.ndarray:
    """Deixa `sinal` com o mesmo volume médio (RMS) da referência, para comparar de forma justa."""
    rms = np.sqrt(np.mean(sinal ** 2)) + 1e-12
    saida = sinal * (np.sqrt(np.mean(referencia ** 2)) / rms)
    pico = np.max(np.abs(saida)) if len(saida) else 0.0
    return saida * (pico_max / pico) if pico > pico_max else saida
