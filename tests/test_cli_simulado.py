import json

import numpy as np
from scipy.io import wavfile

import autoeq
from analise import solver_eq
from ui24r import mapeamento_eq as m


def test_calibrar_aplicar_e_desfazer_na_mesa_simulada(tmp_path, helpers, capsys):
    (tmp_path / "config.yaml").write_text("canal_mesa: 3\nfonte: arquivo\n", encoding="utf-8")
    curva = solver_eq.curva_alvo("fala") + helpers.bump(315, 7)
    wav = tmp_path / "voz.wav"
    wavfile.write(wav, 48000, (helpers.sinal_com_curva(curva) * 32767).astype(np.int16))
    config = ["--config", str(tmp_path / "config.yaml")]
    estado_arq = tmp_path / "backups" / "mesa_simulada.json"

    assert autoeq.main(config + ["calibrar", "--wav", str(wav)]) == 0
    assert "PRÉVIA" in capsys.readouterr().out
    assert not estado_arq.exists()

    assert autoeq.main(config + ["calibrar", "--wav", str(wav), "--simular", "--aplicar"]) == 0
    saida = capsys.readouterr().out
    assert "EQ aplicado no canal 3" in saida
    estado = json.loads(estado_arq.read_text(encoding="utf-8"))
    ganhos = [m.valor_para_ganho(float(estado[m.caminho_banda(3, k, "gain")])) for k in range(1, 5)]
    assert min(ganhos) < -2
    assert m.valor_para_hpf(float(estado[m.caminho_hpf(3)])) > 70
    assert len(list((tmp_path / "backups").glob("canal_03_*.json"))) == 1

    assert autoeq.main(config + ["desfazer", "--simular"]) == 0
    estado = json.loads(estado_arq.read_text(encoding="utf-8"))
    ganhos = [m.valor_para_ganho(float(estado[m.caminho_banda(3, k, "gain")])) for k in range(1, 5)]
    assert all(abs(g) < 1e-3 for g in ganhos)
    assert m.valor_para_hpf(float(estado[m.caminho_hpf(3)])) < 21


def test_fonte_rede_explica_que_falta_capturar_rta(tmp_path, capsys):
    (tmp_path / "config.yaml").write_text("fonte: rede\n", encoding="utf-8")
    assert autoeq.main(["--config", str(tmp_path / "config.yaml"), "calibrar", "--simular"]) == 2
    assert "espiar --rta" in capsys.readouterr().out
