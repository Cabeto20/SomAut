import numpy as np

from analise import espectro as esp
from analise import solver_eq
from analise.espectro import CENTROS


def test_ruido_rosa_fica_plano(helpers):
    sinal = helpers.sinal_com_curva(np.zeros(len(CENTROS)), com_pausas=False)
    db, _ = esp.espectro_voz(sinal, 48000)
    faixa = (CENTROS >= 100) & (CENTROS <= 10000)
    assert np.max(np.abs(db[faixa])) < 1.5


def test_gate_ignora_silencio(helpers):
    sinal = helpers.sinal_com_curva(np.zeros(len(CENTROS)), segundos=10, periodo=2.0)
    _, segundos_voz = esp.espectro_voz(sinal, 48000)
    assert 5.0 < segundos_voz < 7.5


def test_f0(helpers):
    for f0 in (110.0, 220.0):
        f0s = esp.estimar_f0(helpers.voz_harmonica(f0), 48000)
        assert len(f0s) > 20
        assert abs(np.median(f0s) - f0) < 3


def test_f0_ignora_ressonancia_em_ruido(helpers):
    sinal = helpers.sinal_com_curva(solver_eq.curva_alvo("fala") + helpers.bump(315, 6), segundos=12)
    assert len(esp.estimar_f0(sinal, 48000)) < 10


def test_avisos_de_nivel():
    assert any("Clipping" in a for a in esp.avisos_nivel(np.ones(48000)))
    assert any("fraco" in a for a in esp.avisos_nivel(0.001 * np.ones(48000)))
    assert esp.avisos_nivel(0.5 * np.sin(np.arange(48000) / 10)) == []


def _sugerir(helpers, curva, perfil="fala", **kw):
    db, _ = esp.espectro_voz(helpers.sinal_com_curva(curva), 48000)
    return solver_eq.sugerir(db, perfil, **kw)


def test_voz_no_alvo_nao_precisa_de_bandas(helpers):
    sug = _sugerir(helpers, solver_eq.curva_alvo("fala"))
    assert all(abs(b.ganho_db) <= 1.5 for b in sug.bandas)


def test_embolado_em_315hz_gera_corte(helpers):
    sug = _sugerir(helpers, solver_eq.curva_alvo("fala") + helpers.bump(315, 6))
    cortes = [b for b in sug.bandas if 250 <= b.freq <= 400]
    assert len(cortes) == 1 and -7 <= cortes[0].ganho_db <= -2.5
    assert all(abs(b.ganho_db) <= 1.5 for b in sug.bandas if b not in cortes)


def test_falta_de_presenca_gera_reforco_limitado(helpers):
    sug = _sugerir(helpers, solver_eq.curva_alvo("fala") + helpers.bump(3150, -8, 1.5))
    reforcos = [b for b in sug.bandas if 2000 <= b.freq <= 5000 and b.ganho_db > 0]
    assert reforcos and all(b.ganho_db <= 4 for b in reforcos)


def test_ganho_respeita_limite_de_corte(helpers):
    sug = _sugerir(helpers, solver_eq.curva_alvo("fala") + helpers.bump(500, 18))
    assert sug.bandas and min(b.ganho_db for b in sug.bandas) >= -8


def test_nunca_reforca_graves(helpers):
    sug = _sugerir(helpers, solver_eq.curva_alvo("canto") + helpers.bump(160, -10), perfil="canto")
    assert all(b.ganho_db <= 0 for b in sug.bandas if b.freq < 250)


def test_hpf_pela_fundamental():
    hpf_grave, f0 = solver_eq._calcular_hpf("fala", np.full(50, 100.0))
    assert hpf_grave == 80 and f0 == 100
    hpf_aguda, _ = solver_eq._calcular_hpf("fala", np.full(50, 200.0))
    assert hpf_aguda == 140
    assert solver_eq._calcular_hpf("canto", None) == (80.0, None)


def test_eq_existente_e_descontado(helpers):
    eq = [solver_eq.Banda(315, 6, 1.4)]
    medido = solver_eq.curva_alvo("fala") + solver_eq.resposta_eq(eq)
    sug = solver_eq.sugerir(medido, "fala", eq_existente=(None, eq))
    assert all(abs(b.ganho_db) <= 1.5 for b in sug.bandas)
