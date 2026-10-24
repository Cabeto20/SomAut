"""Leitura de gravações WAV (ex.: gravação multitrack da Ui24R no pendrive)."""
from pathlib import Path

import numpy as np
from scipy.io import wavfile


def ler_wav(caminho, canal: int = 1) -> tuple[np.ndarray, int]:
    """Devolve (sinal mono em -1..1, taxa). `caminho` pode ser um arquivo aberto.
    `canal` começa em 1 (para WAV com vários canais)."""
    taxa, dados = wavfile.read(caminho if hasattr(caminho, "read") else str(caminho))
    if dados.dtype.kind == "i":
        dados = dados.astype(np.float64) / (np.iinfo(dados.dtype).max + 1.0)
    elif dados.dtype.kind == "u":
        dados = (dados.astype(np.float64) - 128.0) / 128.0
    else:
        dados = dados.astype(np.float64)
    if dados.ndim == 2:
        if not 1 <= canal <= dados.shape[1]:
            raise ValueError(f"O arquivo tem {dados.shape[1]} canais; canal {canal} não existe.")
        dados = dados[:, canal - 1]
    return dados, int(taxa)


def salvar_wav(caminho: str | Path, sinal: np.ndarray, taxa: int):
    wavfile.write(str(caminho), taxa, (np.clip(sinal, -1, 1) * 32767).astype(np.int16))
