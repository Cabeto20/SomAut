import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analise.espectro import CENTROS  # noqa: E402


def sinal_com_curva(curva_db: np.ndarray, taxa: int = 48000, segundos: float = 8.0,
                    seed: int = 0, com_pausas: bool = True, periodo: float = 0.5) -> np.ndarray:
    """Ruído cuja potência por banda de 1/3 de oitava segue `curva_db` (simula uma voz)."""
    rng = np.random.default_rng(seed)
    n = int(taxa * segundos)
    espectro = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / taxa)
    f[0] = f[1]
    psd_db = np.interp(np.log2(f), np.log2(CENTROS), curva_db) - 10 * np.log10(f)
    x = np.fft.irfft(espectro * 10 ** (psd_db / 20), n)
    if com_pausas:  # "frases": 60% do período com voz, 40% de silêncio
        t = np.arange(n) / taxa
        x = x * ((t % periodo) < 0.6 * periodo) + 1e-5 * rng.standard_normal(n)
    return 0.5 * x / np.max(np.abs(x))


def voz_harmonica(f0: float, taxa: int = 48000, segundos: float = 4.0) -> np.ndarray:
    t = np.arange(int(taxa * segundos)) / taxa
    x = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 20) if f0 * k < taxa / 2)
    return 0.5 * x / np.max(np.abs(x))


def bump(freq: float, db: float, largura_bandas: float = 1.0) -> np.ndarray:
    distancia = np.log2(CENTROS / freq) * 3
    return db * np.exp(-0.5 * (distancia / largura_bandas) ** 2)


@pytest.fixture
def helpers():
    class H:
        pass
    H.sinal_com_curva = staticmethod(sinal_com_curva)
    H.voz_harmonica = staticmethod(voz_harmonica)
    H.bump = staticmethod(bump)
    return H
