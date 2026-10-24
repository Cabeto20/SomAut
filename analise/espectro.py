"""Análise da voz: nível, trechos com voz, espectro médio em 1/3 de oitava e fundamental (F0)."""
import numpy as np
from scipy import signal

# Centros das bandas de 1/3 de oitava de 63 Hz a 12,5 kHz (24 bandas).
CENTROS = 1000.0 * 2.0 ** (np.arange(-12, 12) / 3.0)
NOMINAIS = (63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800,
            1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500)
FAIXA_REFERENCIA = (500.0, 4000.0)


def normalizar(db: np.ndarray) -> np.ndarray:
    """Coloca a média das bandas de 500 Hz a 4 kHz em 0 dB (só a forma do espectro importa)."""
    ref = (CENTROS >= FAIXA_REFERENCIA[0]) & (CENTROS <= FAIXA_REFERENCIA[1])
    return db - db[ref].mean()


def avisos_nivel(sinal: np.ndarray) -> list[str]:
    avisos = []
    pico = np.max(np.abs(sinal)) if len(sinal) else 0.0
    if np.mean(np.abs(sinal) >= 0.99) > 0.001:
        avisos.append("Clipping (sinal estourando): abaixe o GAIN do canal na mesa (ou o volume do "
                      "microfone no Windows) e grave de novo.")
    if pico < 10 ** (-30 / 20):
        avisos.append(f"Sinal fraco (pico {20 * np.log10(pico + 1e-12):.0f} dBFS): aumente o GAIN na mesa "
                      "(ou o volume do microfone no Windows), ou fale mais perto do microfone.")
    return avisos


def _tamanho_janela(taxa: int) -> int:
    return 4096 if taxa >= 44100 else 2048  # ~85 ms: separa bem as pausas da fala


def espectro_voz(sinal: np.ndarray, taxa: int, faixa_db: float = 30.0) -> tuple[np.ndarray, float]:
    """Espectro médio só dos trechos com voz.

    Devolve (nível por banda de 1/3 de oitava normalizado, segundos de voz usados).
    Trechos mais de `faixa_db` abaixo das partes mais fortes são tratados como silêncio.
    """
    n = _tamanho_janela(taxa)
    if len(sinal) < n:
        raise ValueError("Gravação curta demais para analisar.")
    f, _, z = signal.stft(sinal, fs=taxa, window="hann", nperseg=n, noverlap=n // 2,
                          boundary=None, padded=False)
    potencia = np.abs(z) ** 2
    energia = 10 * np.log10(potencia.sum(axis=0) + 1e-20)
    com_voz = energia >= np.percentile(energia, 95) - faixa_db
    psd = potencia[:, com_voz].mean(axis=1)

    db = np.empty(len(CENTROS))
    for i, fc in enumerate(CENTROS):
        faixa = (f >= fc * 2 ** (-1 / 6)) & (f < fc * 2 ** (1 / 6))
        db[i] = 10 * np.log10(psd[faixa].sum() + 1e-20)
    segundos_voz = com_voz.sum() * (n // 2) / taxa
    return normalizar(db), float(segundos_voz)


def estimar_f0(sinal: np.ndarray, taxa: int, fmin: float = 60.0, fmax: float = 500.0,
               limiar: float = 0.6) -> np.ndarray:
    """Estimativa da frequência fundamental (Hz) em cada trecho com voz, por autocorrelação."""
    fator = int(taxa // 16000) if taxa >= 32000 else 1
    x = signal.decimate(sinal, fator) if fator > 1 else np.asarray(sinal, dtype=float)
    fs = taxa / fator
    n = int(0.04 * fs)
    passo = n // 2
    if len(x) < n:
        return np.array([])
    quadros = np.lib.stride_tricks.sliding_window_view(x, n)[::passo]
    rms_db = 10 * np.log10(np.mean(quadros ** 2, axis=1) + 1e-20)
    quadros = quadros[rms_db >= np.percentile(rms_db, 95) - 25]

    lag_min, lag_max = int(fs / fmax), int(fs / fmin)
    janela = np.hanning(n)
    f0s = []
    for q in quadros:
        w = (q - q.mean()) * janela
        espectro = np.fft.rfft(w, 2 * n)
        ac = np.fft.irfft(np.abs(espectro) ** 2)[:n]
        if ac[0] <= 0:
            continue
        ac /= ac[0]
        trecho = ac[lag_min:lag_max]
        k = int(np.argmax(trecho))
        if trecho[k] >= limiar and 0 < k < len(trecho) - 1:
            a, b, c = trecho[k - 1], trecho[k], trecho[k + 1]
            ajuste = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
            f0s.append(fs / (lag_min + k + ajuste))
    return np.array(f0s)
