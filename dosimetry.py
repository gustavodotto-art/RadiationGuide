"""Explicitly scoped CT quantities; no organ or effective-dose estimates.

SSDE: AAPM 220 appendix (body), AAPM 293 eq. 1 (routine head).
Reference values: ANVISA IN 93/2021, Annex II, republication 07/07/2022.
See SOURCES.md for populations, units and limitations.
"""
import math

SOURCE = 'ANVISA IN 93/2021, Anexo II, republicação 07/07/2022'
REFERENCES = [
    {'region': 'cranio', 'population': 'adulto típico', 'ctdivol': 70.0},
    {'region': 'abdome', 'population': 'adulto típico', 'ctdivol': 25.0},
    {'region': 'abdome', 'population': '5 anos, aproximadamente 20 kg', 'ctdivol': 20.0},
]

def positive(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (TypeError, ValueError):
        return None

def region_of(text):
    t = str(text).lower()
    # Combined, facial and cervical protocols must not inherit a head/abdomen reference.
    for terms, region in [
        (('chest abdomen', 'torax_abdom', 'toracoab', 'thoracoab', 'abdomen pelvis', 'abdomenpelvis', 'abdomepelve'), 'combinado'),
        (('face', 'sinus', 'dental', 'mandib', 'maxil'), 'face'),
        (('cerv', 'neck', 'pesco'), 'pescoco'),
        (('head', 'brain', 'skull', 'cranio', 'crânio', 'cerebro'), 'cranio'),
        (('abdomen', 'abdome'), 'abdome'),
        (('chest', 'thorax', 'torax', 'tórax', 'lung'), 'torax'),
        (('pelv',), 'pelve'),
    ]:
        if any(s in t for s in terms): return region
    return 'desconhecida'

def reference_for(region, age, weight, height):
    """No adult fallback for a child or missing demographics.

    Pediatric reference is catalogued but not auto-selected: 'approximately 20 kg'
    has no validated numerical interval here. No DLP reference is invented.
    """
    base = {'ctdivol': None, 'dlp': None, 'source': SOURCE,
            'population': None, 'reason': 'Sem referência aplicável validada.'}
    if age is None: return {**base, 'reason': 'Idade ausente; população não definida.'}
    if age < 18:
        return {**base, 'reason': 'Referência pediátrica requer população e protocolo validados; sem alerta automático.'}
    if region not in ('cranio', 'abdome'): return base
    if not (weight and height and 60 <= weight <= 75 and 1.60 <= height <= 1.75):
        return {**base, 'reason': 'Referência para adulto típico: 60–75 kg e 1,60–1,75 m; aplicabilidade não confirmada.'}
    return {**base, 'ctdivol': 70.0 if region == 'cranio' else 25.0,
            'population': 'adulto típico (60–75 kg; 1,60–1,75 m)', 'reason': ''}

def screening(value, reference):
    """Operational internal screen; never a regulatory compliance verdict."""
    value, reference = positive(value), positive(reference)
    if value is None or reference is None:
        return {'percent': None, 'level': 'unavailable', 'label': 'Triagem não realizada'}
    pct = value / reference * 100
    level = 'review' if pct >= 100 else 'attention' if pct >= 80 else 'routine'
    return {'percent': round(pct, 1), 'level': level,
            'label': {'review': 'Revisão operacional (≥100%)',
                      'attention': 'Atenção operacional (≥80%)',
                      'routine': 'Abaixo do gatilho operacional de 80%'}[level]}

def ssde(ctdi, dw_cm, phantom_cm, region, kvp=None):
    result = {'ssde_mgy': None, 'dw_cm': positive(dw_cm), 'ssde_factor': None,
              'ssde_method': None, 'ssde_reason': 'Diâmetro equivalente em água ou fantoma ausente.'}
    ctdi, dw = positive(ctdi), positive(dw_cm)
    if ctdi is None or dw is None or phantom_cm not in (16, 32): return result
    if region == 'cranio':
        # Conservative supported interval around the report's tabulated phantom sizes.
        if phantom_cm != 16 or not 12 <= dw <= 18 or kvp not in (80, 100, 120, 140):
            return {**result, 'ssde_reason': 'Crânio: requer Dw 12–18 cm, fantoma 16 cm e 80/100/120/140 kV.'}
        a, b, method = 1.9852, 0.0486, 'AAPM 293, eq. 1 (H16; Dw)'
    elif region in ('torax', 'abdome', 'pelve') and 8 <= dw <= 40:
        a, b = (3.704369, 0.03671937) if phantom_cm == 32 else (1.874799, 0.03871313)
        method = f'AAPM 220, apêndice, eq. A-1 (B{phantom_cm}; Dw)'
    else:
        return {**result, 'ssde_reason': 'Região ou Dw fora do escopo implementado; sem extrapolação.'}
    factor = a * math.exp(-b * dw)
    return {**result, 'ssde_mgy': round(ctdi * factor, 3), 'ssde_factor': round(factor, 6),
            'ssde_method': method, 'ssde_reason': ''}
