"""Cálculo do EQ sugerido: corta-graves (HPF) + até 4 bandas paramétricas."""
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

from .espectro import CENTROS, NOMINAIS, normalizar

FS_MODELO = 48000

# Espectro médio de longo prazo da fala em 1/3 de oitava (dB), aprox. Byrne et al. (1994).
LTASS = np.array([38.6, 43.5, 54.4, 57.7, 56.8, 58.2, 59.7, 60.0, 62.1, 62.1, 60.5, 56.8,
                  53.7, 53.0, 52.0, 48.7, 48.1, 46.8, 45.6, 44.5, 44.3, 43.7, 43.4, 41.3])

PERFIS = {
    "fala": {
        "descricao": "fala/pregação: menos embolado, mais presença e inteligibilidade",
        "ajustes": {200: -1, 250: -2, 315: -2.5, 400: -2.5, 500: -1.5, 630: -0.5,
                    1600: 0.5, 2000: 1.5, 2500: 2.5, 3150: 3, 4000: 2.5, 5000: 1.5, 6300: 0.5},
        "hpf": (80.0, 150.0),
        "hpf_padrao": 100.0,
    },
    "canto": {
        "descricao": "canto: som mais cheio e natural, cortes suaves",
        "ajustes": {250: -0.5, 315: -1, 400: -1, 2500: 1, 3150: 1.5, 4000: 1, 8000: 1, 10000: 1},
        "hpf": (70.0, 120.0),
        "hpf_padrao": 80.0,
    },
}

REGIOES = (
    (250, "graves / efeito de proximidade"),
    (600, "embolado (médio-grave)"),
    (1500, "som de caixa / nasal"),
    (5000, "presença / inteligibilidade"),
    (8000, "sibilância (s, x, ch)"),
    (float("inf"), "brilho / ar"),
)

FREQ_MAX_CORRECAO = 10500.0
SEM_REFORCO_ABAIXO = 250.0      # nunca reforçar graves (realimentação e embolado)
DESVIO_MINIMO_DB = 1.5          # desvios menores que isso não valem uma banda
GANHO_MINIMO_DB = 1.0           # bandas com ganho final menor que isso são descartadas
DISTANCIA_MINIMA_OITAVAS = 0.5  # duas bandas não ficam mais perto que isso
Q_MIN, Q_MAX = 0.7, 3.0


@dataclass
class Banda:
    freq: float
    ganho_db: float
    q: float

    @property
    def rotulo(self) -> str:
        regiao = next(nome for limite, nome in REGIOES if self.freq < limite)
        return f"{regiao} - {'corte' if self.ganho_db < 0 else 'reforço'}"


@dataclass
class SugestaoEQ:
    perfil: str
    hpf_hz: float
    bandas: list[Banda]
    f0_mediana: float | None
    desvio: np.ndarray            # medido - alvo (dB por banda; + = sobrando)
    depois: np.ndarray            # desvio previsto depois do EQ
    validos: np.ndarray = field(repr=False)  # bandas consideradas na correção


def freq_max_para(taxa: int) -> float:
    """Maior frequência confiável para uma taxa de amostragem (margem abaixo de Nyquist)."""
    return min(FREQ_MAX_CORRECAO, 0.42 * taxa)


def curva_alvo(perfil: str) -> np.ndarray:
    ajustes = PERFIS[perfil]["ajustes"]
    alvo = LTASS + np.array([ajustes.get(n, 0.0) for n in NOMINAIS])
    return normalizar(alvo)


def coeficientes_peaking(banda: Banda, fs: float = FS_MODELO):
    """Filtro peaking do 'Audio EQ Cookbook' (R. Bristow-Johnson)."""
    a = 10 ** (banda.ganho_db / 40)
    w0 = 2 * np.pi * banda.freq / fs
    alpha = np.sin(w0) / (2 * banda.q)
    b = [1 + alpha * a, -2 * np.cos(w0), 1 - alpha * a]
    den = [1 + alpha / a, -2 * np.cos(w0), 1 - alpha / a]
    return b, den


def resposta_eq(bandas: list[Banda], hpf_hz: float | None = None,
                freqs: np.ndarray = CENTROS) -> np.ndarray:
    """Resposta em dB do EQ nas frequências pedidas."""
    total = np.zeros(len(freqs))
    for banda in bandas:
        if abs(banda.ganho_db) < 1e-6:
            continue
        b, a = coeficientes_peaking(banda)
        _, h = signal.freqz(b, a, worN=freqs, fs=FS_MODELO)
        total += 20 * np.log10(np.abs(h) + 1e-12)
    if hpf_hz:
        b, a = signal.butter(2, hpf_hz, "highpass", fs=FS_MODELO)
        _, h = signal.freqz(b, a, worN=freqs, fs=FS_MODELO)
        total += 20 * np.log10(np.abs(h) + 1e-12)
    return total


def _suavizar(d: np.ndarray) -> np.ndarray:
    p = np.pad(d, 1, mode="edge")
    return 0.25 * p[:-2] + 0.5 * p[1:-1] + 0.25 * p[2:]


def _calcular_hpf(perfil: str, f0s: np.ndarray | None) -> tuple[float, float | None]:
    cfg = PERFIS[perfil]
    if f0s is None or len(f0s) < 10:
        return cfg["hpf_padrao"], None
    f0_baixo = float(np.percentile(f0s, 10))
    hpf = min(max(0.7 * f0_baixo, cfg["hpf"][0]), cfg["hpf"][1])
    return round(hpf / 5) * 5, float(np.median(f0s))


def _q_pela_largura(r: np.ndarray, i: int, validos: np.ndarray) -> float:
    meio, sinal = abs(r[i]) / 2, np.sign(r[i])
    n = 1
    for passo in (-1, 1):
        j = i + passo
        while 0 <= j < len(r) and validos[j] and np.sign(r[j]) == sinal and abs(r[j]) >= meio:
            n += 1
            j += passo
    oitavas = n / 3
    q = np.sqrt(2 ** oitavas) / (2 ** oitavas - 1)
    return float(np.clip(q, Q_MIN, Q_MAX))


def _freq_refinada(r: np.ndarray, i: int) -> float:
    if 0 < i < len(r) - 1:
        a, b, c = r[i - 1], r[i], r[i + 1]
        den = a - 2 * b + c
        ajuste = float(np.clip(0.5 * (a - c) / den, -0.5, 0.5)) if den != 0 else 0.0
        return float(CENTROS[i] * 2 ** (ajuste / 3))
    return float(CENTROS[i])


def _residuo_em(r: np.ndarray, freq: float) -> float:
    return float(np.interp(np.log2(freq), np.log2(CENTROS), r))


def _limites(freq: float, ganho_min: float, ganho_max: float) -> tuple[float, float]:
    return ganho_min, (ganho_max if freq >= SEM_REFORCO_ABAIXO else 0.0)


def _arredondar(banda: Banda) -> Banda:
    passo = 5 if banda.freq < 1000 else 50
    return Banda(freq=round(banda.freq / passo) * passo,
                 ganho_db=round(banda.ganho_db * 2) / 2,
                 q=round(banda.q, 1))


def sugerir(espectro_db: np.ndarray, perfil: str = "fala", f0s: np.ndarray | None = None,
            intensidade: float = 0.8, ganho_min: float = -8.0, ganho_max: float = 4.0,
            num_bandas: int = 4, eq_existente: tuple[float | None, list[Banda]] | None = None,
            freq_max: float = FREQ_MAX_CORRECAO) -> SugestaoEQ:
    """Compara o espectro medido com a curva-alvo do perfil e escolhe HPF + bandas.

    `eq_existente` (hpf, bandas): EQ que já estava atuando no áudio analisado; é descontado.
    `freq_max`: acima disso o áudio não é confiável (ex.: gravação com taxa baixa) e é ignorado.
    """
    if perfil not in PERFIS:
        raise ValueError(f"Perfil desconhecido: {perfil}. Use: {', '.join(PERFIS)}")
    medido = np.asarray(espectro_db, dtype=float)
    if eq_existente:
        medido = normalizar(medido - resposta_eq(eq_existente[1], eq_existente[0]))

    hpf, f0_mediana = _calcular_hpf(perfil, f0s)
    bruto = normalizar(medido) - curva_alvo(perfil)
    acima = CENTROS > freq_max
    if acima.any() and not acima.all():  # não deixa bandas sem áudio "vazarem" na suavização
        bruto[acima] = bruto[~acima][-1]
    desvio = _suavizar(bruto)
    alvo_corr = desvio * intensidade
    validos = (CENTROS >= max(hpf * 1.5, 120.0)) & ~acima

    bandas: list[Banda] = []
    for _ in range(num_bandas):
        r = alvo_corr + resposta_eq(bandas)
        candidatos = np.where(validos, np.abs(r), 0.0)
        candidatos[(CENTROS < SEM_REFORCO_ABAIXO) & (r < 0)] = 0.0
        for b in bandas:
            candidatos[np.abs(np.log2(CENTROS / b.freq)) < DISTANCIA_MINIMA_OITAVAS] = 0.0
        i = int(np.argmax(candidatos))
        if candidatos[i] < DESVIO_MINIMO_DB:
            break
        freq = _freq_refinada(r, i)
        lo, hi = _limites(freq, ganho_min, ganho_max)
        bandas.append(Banda(freq=freq, ganho_db=float(np.clip(-r[i], lo, hi)),
                            q=_q_pela_largura(r, i, validos)))

    # Reajuste fino dos ganhos considerando a soma de todas as bandas.
    for _ in range(4):
        for b in bandas:
            r = alvo_corr + resposta_eq(bandas)
            lo, hi = _limites(b.freq, ganho_min, ganho_max)
            b.ganho_db = float(np.clip(b.ganho_db - _residuo_em(r, b.freq), lo, hi))

    bandas = sorted((_arredondar(b) for b in bandas if abs(b.ganho_db) >= GANHO_MINIMO_DB),
                    key=lambda b: b.freq)
    depois = desvio + resposta_eq(bandas)
    return SugestaoEQ(perfil=perfil, hpf_hz=hpf, bandas=bandas, f0_mediana=f0_mediana,
                      desvio=desvio, depois=depois, validos=validos)
