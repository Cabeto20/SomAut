import pytest

from ui24r import mapeamento_eq as m
from ui24r.conexao import formatar_valor, interpretar_set, separar_mensagens


@pytest.mark.parametrize("hz", [20, 100, 315, 1000, 3150, 12000, 22000])
def test_freq_ida_volta(hz):
    assert m.valor_para_freq(m.freq_para_valor(hz)) == pytest.approx(hz, rel=1e-6)


@pytest.mark.parametrize("db", [-20, -8, -0.5, 0, 4, 20])
def test_ganho_ida_volta(db):
    assert m.valor_para_ganho(m.ganho_para_valor(db)) == pytest.approx(db, abs=1e-9)


def test_ganho_zero_no_meio():
    assert m.ganho_para_valor(0) == pytest.approx(0.5)


@pytest.mark.parametrize("q", [0.7, 1.4, 3.0])
def test_q_e_hpf_ida_volta(q):
    assert m.valor_para_q(m.q_para_valor(q)) == pytest.approx(q, rel=1e-6)
    assert m.valor_para_hpf(m.hpf_para_valor(q * 100)) == pytest.approx(q * 100, rel=1e-6)


def test_valores_fora_da_faixa_sao_limitados():
    assert m.ganho_para_valor(50) == 1.0
    assert m.freq_para_valor(5) == 0.0


def test_caminhos_usam_canal_comecando_em_zero():
    assert m.caminho_hpf(1) == "i.0.eq.hpf.freq"
    assert m.caminho_banda(5, 2, "gain") == "i.4.eq.b2.gain"
    assert len(m.caminhos_eq(3)) == 1 + 4 * 3


def test_interpretar():
    assert m.interpretar("i.4.eq.b2.gain", "0.65") == "canal 5 banda 2 gain = +6.0 dB"
    assert "HPF" in m.interpretar("i.0.eq.hpf.freq", "0.5")
    assert m.interpretar("i.0.mix", "0.5") is None


def test_protocolo_mensagens():
    quadro = "3:::SETD^i.0.mix^0.5\n3:::SETS^i.0.name^Voz\n2::\nVU2^abc"
    assert separar_mensagens(quadro) == ["SETD^i.0.mix^0.5", "SETS^i.0.name^Voz", "VU2^abc"]
    assert interpretar_set("SETD^i.0.mix^0.5") == ("i.0.mix", "0.5")
    assert interpretar_set("SETS^i.0.name^A^B") == ("i.0.name", "A^B")
    assert interpretar_set("VU2^abc") is None
    assert formatar_valor(0.5) == "0.5"
    assert formatar_valor(0.0) == "0"
