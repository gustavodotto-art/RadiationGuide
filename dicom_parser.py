"""CT metadata only. RDSR preferred; header fallback never guesses DLP from reconstructions."""
import math
import zipfile
from collections import defaultdict
from datetime import datetime
from statistics import median
import pydicom
from dosimetry import positive, region_of, reference_for, screening, ssde
from _sr_parser import parse_dose_sr

SOP_DOSE_SR = '1.2.840.10008.5.1.4.1.1.88.67'
CT_SOPS = {'1.2.840.10008.5.1.4.1.1.2', '1.2.840.10008.5.1.4.1.1.2.1', '1.2.840.10008.5.1.4.1.1.2.2'}
class NonCTExamError(ValueError): pass


def text(ds, key): return str(getattr(ds, key, '') or '').strip()

def age_at_exam(ds):
    try:
        b = datetime.strptime(text(ds, 'PatientBirthDate'), '%Y%m%d')
        e = datetime.strptime(text(ds, 'StudyDate'), '%Y%m%d')
        if e < b: return None
        return e.year-b.year-((e.month,e.day)<(b.month,b.day))
    except ValueError: pass
    a = text(ds, 'PatientAge')
    if len(a) != 4 or not a[:3].isdigit(): return None
    value = int(a[:3])
    return {'Y': value, 'M': value//12, 'W': value//52, 'D': value//365}.get(a[-1])


def phantom(ds):
    seq = getattr(ds, 'CTDIPhantomTypeCodeSequence', [])
    if seq:
        code = text(seq[0], 'CodeValue')
        scheme = text(seq[0], 'CodingSchemeDesignator')
        if scheme == 'DCM': return {'113690':16, '113691':32}.get(code)
    return None


def dw(ds):
    # DICOM (0018,1271) is millimetres. Never use reconstruction FOV as patient size.
    v = positive(getattr(ds, 'WaterEquivalentDiameter', None))
    return v / 10 if v else None


def numeric(raw, quantity):
    if not isinstance(raw, tuple): return None
    value, unit = raw
    value = positive(value)
    factors = {'ctdi': {'mGy': 1, 'Gy':1000},
               'dlp': {'mGy.cm':1, 'mGy*cm':1, 'Gy.cm':1000},
               'kvp': {'kV':1}, 'length': {'mm':1, 'cm':10}}
    factor = factors[quantity].get(unit)
    return value * factor if value and factor else None


def _sr_events(reports):
    events, totals, warnings = [], [], []
    for ds in reports:
        parsed = parse_dose_sr(ds)
        total = numeric(parsed['summary'].get('dlp_total'), 'dlp')
        if total is not None: totals.append(total)
        for i, acq in enumerate(parsed['acquisitions']):
            typ = str(acq.get('acquisition_type','')).lower()
            ph = str(acq.get('phantom_type','')).lower()
            events.append({'event':acq.get('event_uid'), 'protocol':'TC',
                           'is_localizer':any(s in typ for s in ('localizer','scout','constant angle')),
                           'ctdivol_mgy': numeric(acq.get('ctdivol'),'ctdi'),
                           'dlp_mgycm': numeric(acq.get('dlp'),'dlp'),
                           'phantom_cm':16 if '16' in ph or 'head' in ph else 32 if '32' in ph or 'body' in ph else None,
                           'kvp': numeric(acq.get('kvp'),'kvp')})
    # Deduplicate only with a proven irradiation event UID, never by equal dose.
    unique, seen = [], set()
    for event in events:
        uid = event['event']
        if uid and uid in seen: continue
        if uid: seen.add(uid)
        unique.append(event)
    if len(reports) > 1 and any(not e['event'] for e in events):
        warnings.append('Múltiplos RDSR sem UID de evento; DLP total não agregado.')
        total = None
    elif len(reports) == 1 and len(totals) == 1:
        total = totals[0]
    elif unique and all(e['event'] and e['dlp_mgycm'] is not None for e in unique):
        total = sum(e['dlp_mgycm'] for e in unique)
    else: total = None
    if total is None and len(reports)==1 and unique and all(e['dlp_mgycm'] is not None for e in unique):
        total = sum(e['dlp_mgycm'] for e in unique)
    return unique, total, warnings


def _process_group(images, reports):
    ref = images[0]
    age = age_at_exam(ref)
    # BodyPartExamined only: free text is ambiguous and can contain names.
    region = region_of(text(ref, 'BodyPartExamined'))
    weight = positive(getattr(ref, 'PatientWeight', None))
    height = positive(getattr(ref, 'PatientSize', None))
    nrd = reference_for(region, age, weight, height)
    warnings = []
    if reports:
        series, dlp, warnings = _sr_events(reports)
        source = 'RDSR'
        candidates = [e for e in series if not e['is_localizer'] and e['ctdivol_mgy'] is not None]
        selected = max(candidates,key=lambda e:e['ctdivol_mgy']) if candidates else None
        ctdi = selected['ctdivol_mgy'] if selected else None
        matches = [ds for ds in images if selected and selected['event'] and text(ds,'IrradiationEventUID')==selected['event']]
        meta = matches[0] if matches else None
        size = dw(meta) if meta is not None else None
        ph = selected.get('phantom_cm') if selected else None
        ph = ph or (phantom(meta) if meta is not None else None)
        kvp = selected.get('kvp') if selected else None
    else:
        grouped = defaultdict(list)
        for ds in images:
            uid = text(ds,'IrradiationEventUID') or text(ds,'SeriesInstanceUID')
            if not uid: raise ValueError('TC sem UID de série/evento; agrupamento não seguro.')
            grouped[uid].append(ds)
        series = []
        metadata = {}
        for uid, items in grouped.items():
            clinical = [ds for ds in items if 'LOCALIZER' not in text(ds,'ImageType').upper() and 'SCOUT' not in text(ds,'ImageType').upper()]
            pairs = [(positive(getattr(ds,'CTDIvol',None)), ds) for ds in clinical]
            pairs = [(v,ds) for v,ds in pairs if v is not None]
            values = [v for v,_ in pairs]
            value = median(values) if values else None
            meta_ds = min(pairs,key=lambda pair:abs(pair[0]-value))[1] if pairs else None
            metadata[uid] = meta_ds
            series.append({'event':uid, 'protocol':'TC', 'is_localizer':not bool(clinical),
                           'ctdivol_mgy':value, 'dlp_mgycm':None,
                           'phantom_cm':phantom(meta_ds) if meta_ds is not None else None,
                           'kvp':positive(getattr(meta_ds,'KVP',None)) if meta_ds is not None else None})
        candidates = [e for e in series if not e['is_localizer'] and e['ctdivol_mgy'] is not None]
        selected = max(candidates,key=lambda e:e['ctdivol_mgy']) if candidates else None
        ctdi = selected['ctdivol_mgy'] if selected else None
        meta = metadata.get(selected['event']) if selected else None
        size = dw(meta) if meta is not None else None
        ph = selected['phantom_cm'] if selected else None
        kvp = selected['kvp'] if selected else None
        dlp, source = None, 'Cabeçalhos CT (fallback)'
        warnings.append('Sem RDSR: DLP não calculado a partir de comprimentos reconstruídos; não representa dose zero.')
    if age is None: warnings.append('Idade não disponível; referência de população não selecionada.')
    if ctdi is None: warnings.append('CTDIvol não disponível em unidades reconhecidas.')
    # Persist only an HMAC input privately in memory; app removes it before storage/response.
    raw_id = text(ref,'PatientID')
    issuer = text(ref,'IssuerOfPatientID')
    study = text(ref,'StudyInstanceUID')
    if raw_id:
        identity = f'id:{issuer}:{raw_id}'
    else:
        if not study: raise ValueError('Sem PatientID e StudyInstanceUID; identificação não segura.')
        identity = 'study:' + study
        warnings.append('Sem PatientID; pseudônimo limitado a este estudo, sem vínculo entre exames.')
    date = text(ref,'StudyDate')
    month = date[:4]+'-'+date[4:6] if len(date)==8 and date.isdigit() else None
    screen = screening(ctdi, nrd.get('ctdivol'))
    result = {'_identity':identity, '_study_uid':study, 'exam_type':'CT', 'modality':'CT',
              'region':region, 'study_desc':'TC '+region, 'study_month':month,
              'patient_group':'pediátrico' if age is not None and age<18 else 'adulto' if age is not None else 'não definido',
              'ctdivol_mgy':ctdi, 'dlp_total_mgycm':round(dlp,3) if dlp is not None else None,
              'phantom_cm':ph, 'kvp':kvp, 'nrd':nrd, 'screening':screen,
              '_dose_source':source, 'warnings':warnings,
              'ctdivol_pct_nrd':screen['percent'], 'dlp_pct_nrd':None,
              'ctdivol_summary':'Maior CTDIvol representativo das aquisições não localizadoras; não é dose somada.'}
    result.update(ssde(ctdi,size,ph,region,kvp))
    # No event UID, free-text protocol or DICOM UID crosses the privacy boundary.
    result['series'] = [{k:v for k,v in e.items() if k!='event'} for e in series]
    return result


def parse_dicom_zip_many(zip_path):
    groups = defaultdict(lambda: {'images':[], 'reports':[]})
    seen_sop = set()
    with zipfile.ZipFile(zip_path) as z:
        entries = [i for i in z.infolist() if not i.is_dir() and not any(p.startswith('.') or p=='__MACOSX' for p in i.filename.split('/'))]
        if len(entries)>20000 or sum(i.file_size for i in entries)>8*1024**3:
            raise ValueError('Pacote excede os limites de 20.000 arquivos ou 8 GiB descompactados.')
        for info in entries:
            try:
                with z.open(info) as f:
                    ds = pydicom.dcmread(f, stop_before_pixels=True, force=False)
            except pydicom.errors.InvalidDicomError: continue
            sop = text(ds,'SOPClassUID')
            if sop not in CT_SOPS and sop != SOP_DOSE_SR: continue
            uid = text(ds,'SOPInstanceUID')
            if uid and uid in seen_sop: continue
            if uid: seen_sop.add(uid)
            study = text(ds,'StudyInstanceUID')
            if not study: raise ValueError('Objeto DICOM sem StudyInstanceUID.')
            groups[study]['reports' if sop==SOP_DOSE_SR else 'images'].append(ds)
    if not any(g['images'] for g in groups.values()):
        raise NonCTExamError('Pacote sem imagens clínicas de TC suportadas.')
    results = []
    for group in groups.values():
        if not group['images']: continue
        ids = {(text(ds,'PatientID'),text(ds,'IssuerOfPatientID')) for ds in group['images']+group['reports'] if text(ds,'PatientID')}
        if len(ids)>1: raise ValueError('StudyInstanceUID associado a pacientes distintos; pacote recusado.')
        results.append(_process_group(group['images'],group['reports']))
    return results


def parse_dicom_zip(path):
    results = parse_dicom_zip_many(path)
    if len(results)!=1: raise ValueError('Use a leitura multiestudo para este pacote.')
    return results[0]
