"""A interface deve dar exatamente o mesmo resultado do terminal."""
import numpy as np
import pytest
from scipy.io import wavfile

import autoeq
import interface
from analise import relatorio, solver_eq
from analise.solver_eq import Banda
from audio.captura import ErroAudio, configurar_canal


@pytest.fixture
def projeto(tmp_path, monkeypatch, helpers):
    (tmp_path / "config.yaml").write_text(
        "perfil: fala\nfonte: arquivo\naudio:\n  pos_eq: true\n", encoding="utf-8")
    monkeypatch.setattr(interface, "PASTA", tmp_path)
    curva = solver_eq.curva_alvo("fala") + helpers.bump(315, 7) + helpers.bump(3150, -5, 1.5)
    voz = helpers.sinal_com_curva(curva)
    ruido = 0.01 * np.random.default_rng(1).standard_normal(len(voz))
    wav = tmp_path / "voz.wav"
    wavfile.write(wav, 48000, (np.column_stack([ruido, voz]) * 32767).astype(np.int16))  # voz no canal 2
    return tmp_path, wav


def _linhas_eq(texto: str) -> list[str]:
    """Linhas do EQ sugerido, sem a parte '(antes: ...)' / '[antes: ...]' que só o terminal mostra em texto."""
    return [l.split("   [antes")[0].split("   (antes")[0].rstrip()
            for l in texto.splitlines() if l.strip().startswith(("HPF", "Banda"))]


def test_interface_igual_ao_terminal_com_pos_eq(projeto, capsys):
    pasta, wav = projeto
    config = ["--config", str(pasta / "config.yaml")]
    # Coloca um EQ na mesa simulada, para o pos_eq ter o que descontar.
    assert autoeq.main(config + ["calibrar", "--wav", str(wav), "--canal-wav", "2", "--canal", "3",
                                 "--simular", "--aplicar"]) == 0
    capsys.readouterr()

    assert autoeq.main(config + ["calibrar", "--wav", str(wav), "--canal-wav", "2", "--canal", "3",
                                 "--simular"]) == 0
    terminal = _linhas_eq(capsys.readouterr().out)
    assert len(terminal) == 5  # HPF + 4 bandas

    estudio = interface.Estudio()
    estudio.carregar_wav(wav.read_bytes(), "voz.wav", canal=2)
    estudio.ler_eq_da_mesa("simulada", "", 3)
    r = estudio.analisar("fala", 0.8, 3)
    sug = estudio.resultado.sugestao
    texto = relatorio.relatorio(sug)
    assert _linhas_eq(texto) == terminal
    assert r["antes"] is not None and len(r["antes"]["bandas_eq"]) == 4
    assert not any("pos_eq" in a for a in r["avisos"])


def test_interface_avisa_quando_pos_eq_sem_ler_eq(projeto):
    _, wav = projeto
    estudio = interface.Estudio()
    estudio.carregar_wav(wav.read_bytes(), "voz.wav", canal=2)
    r = estudio.analisar("fala", 0.8, 3)
    assert r["antes"] is None
    assert any("pos_eq" in a for a in r["avisos"])


def test_aplicar_e_desfazer_atualizam_eq_atual(projeto):
    _, wav = projeto
    estudio = interface.Estudio()
    estudio.carregar_wav(wav.read_bytes(), "voz.wav", canal=2)
    estudio.analisar("fala", 0.8, 5)
    r = estudio.aplicar_na_mesa("simulada", "", 5)
    ganhos = [b["ganho"] for b in r["antes"]["bandas_eq"]]
    assert min(ganhos) < -2
    r = estudio.desfazer("simulada", "", 5)
    assert all(abs(b["ganho"]) < 0.1 for b in r["antes"]["bandas_eq"])


def test_wav_canal_inexistente(projeto):
    _, wav = projeto
    with pytest.raises(ValueError):
        interface.Estudio().carregar_wav(wav.read_bytes(), "voz.wav", canal=3)


@pytest.mark.parametrize("hostapi,canal,entradas,esperado", [
    ("Windows WASAPI", 1, 2, (2, 0)),      # fone: abre 2, lê o 1º
    ("Windows WASAPI", 1, 1, (1, 0)),
    ("MME", 11, 32, (11, 10)),             # Ui24R: entrada 1 da mesa = canal USB 11
])
def test_configurar_canal(hostapi, canal, entradas, esperado):
    canais, coluna, extra = configurar_canal(hostapi, canal, entradas, "teste")
    assert (canais, coluna) == esperado and extra == {}


def test_configurar_canal_asio_abre_so_o_canal_pedido():
    canais, coluna, extra = configurar_canal("ASIO", 11, 32, "Ui24R")
    assert (canais, coluna) == (1, 0) and "extra_settings" in extra


def test_configurar_canal_fora_da_faixa():
    with pytest.raises(ErroAudio):
        configurar_canal("Windows WASAPI", 11, 2, "fone")


def test_eq_json_vazio():
    assert interface._eq_json(None) is None
    assert interface._eq_json((100.0, [Banda(300, -3, 1)]))["hpf"] == 100
