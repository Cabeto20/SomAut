"""Análise completa de uma gravação: nível, trechos com voz, espectro, F0 e EQ sugerido."""
from dataclasses import dataclass, field

import numpy as np

from . import espectro as esp
from . import solver_eq


@dataclass
class ResultadoAnalise:
    sugestao: solver_eq.SugestaoEQ
    segundos_voz: float
    taxa: int
    avisos: list[str] = field(default_factory=list)


def analisar(sinal: np.ndarray, taxa: int, perfil: str, intensidade: float = 0.8,
             ganho_min: float = -8.0, ganho_max: float = 4.0, eq_existente=None) -> ResultadoAnalise:
    avisos = esp.avisos_nivel(sinal)
    espectro, segundos_voz = esp.espectro_voz(sinal, taxa)
    if segundos_voz < 1:
        raise ValueError("Quase nenhuma voz detectada; confira o microfone e o nível e grave de novo.")
    if segundos_voz < 3:
        avisos.append("Pouca voz na gravação; o resultado pode ficar impreciso.")
    sugestao = solver_eq.sugerir(
        espectro, perfil, esp.estimar_f0(sinal, taxa), intensidade=intensidade,
        ganho_min=ganho_min, ganho_max=ganho_max, eq_existente=eq_existente,
        freq_max=solver_eq.freq_max_para(taxa),
    )
    return ResultadoAnalise(sugestao, segundos_voz, taxa, avisos)
