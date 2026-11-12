import io
import json
import math
import zipfile
from pathlib import Path
import pytest
from pydicom.dataset import Dataset,FileDataset,FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian,generate_uid
from pydicom.sequence import Sequence
from pypdf import PdfReader
from dosimetry import reference_for,ssde,screening,region_of
from dicom_parser import parse_dicom_zip_many,age_at_exam,NonCTExamError,SOP_DOSE_SR
from privacy import pseudonymize,load_key
import db

CT='1.2.840.10008.5.1.4.1.1.2'

def image(study=None,pid='SYNTHETIC_PATIENT_123',series=None,event=None):
    meta=FileMetaDataset();meta.TransferSyntaxUID=ExplicitVRLittleEndian
    d=FileDataset(None,{},file_meta=meta,preamble=b'\0'*128)
    d.SOPClassUID=CT;d.SOPInstanceUID=generate_uid()
    meta.MediaStorageSOPClassUID=d.SOPClassUID;meta.MediaStorageSOPInstanceUID=d.SOPInstanceUID
    d.Modality='CT';d.StudyInstanceUID=study or generate_uid();d.SeriesInstanceUID=series or generate_uid()
    d.PatientID=pid;d.PatientName='SYNTHETIC^SECRET_NAME';d.PatientBirthDate='19800101'
    d.PatientAge='046Y';d.PatientSex='F';d.StudyDate='20261112';d.PatientWeight=70;d.PatientSize=1.7
    d.BodyPartExamined='ABDOMEN';d.StudyDescription='SYNTHETIC SECRET FREE TEXT'
    d.CTDIvol=10;d.KVP=120;d.ImageType=['ORIGINAL','PRIMARY','AXIAL']
    d.WaterEquivalentDiameter=300
    c=Dataset();c.CodingSchemeDesignator='DCM';c.CodeValue='113691';c.CodeMeaning='IEC Body Dosimetry Phantom'
    d.CTDIPhantomTypeCodeSequence=Sequence([c])
    if event: d.IrradiationEventUID=event
    return d

def num(code,value,unit):
    d=Dataset();d.ValueType='NUM';c=Dataset();c.CodingSchemeDesignator='DCM';c.CodeValue=code;c.CodeMeaning='Test'
    d.ConceptNameCodeSequence=Sequence([c]);m=Dataset();m.NumericValue=value
    u=Dataset();u.CodingSchemeDesignator='UCUM';u.CodeValue=unit;u.CodeMeaning=unit
    m.MeasurementUnitsCodeSequence=Sequence([u]);d.MeasuredValueSequence=Sequence([m]);return d

def rdsr(ref,ctdi=10,unit='mGy',dlp=300,event=None):
    d=image(study=ref.StudyInstanceUID,pid=str(ref.PatientID));d.SOPClassUID=SOP_DOSE_SR;d.Modality='SR'
    d.file_meta.MediaStorageSOPClassUID=SOP_DOSE_SR
    acq=Dataset();acq.ValueType='CONTAINER';c=Dataset();c.CodeValue='113819';c.CodingSchemeDesignator='DCM';c.CodeMeaning='CT Acquisition'
    acq.ConceptNameCodeSequence=Sequence([c]);children=[num('113830',ctdi,unit),num('113838',dlp,'mGy.cm'),num('113733',120,'kV')]
    if event:
        e=Dataset();e.ValueType='UIDREF';e.UID=event;c=Dataset();c.CodeValue='113769';c.CodingSchemeDesignator='DCM';c.CodeMeaning='Irradiation Event UID';e.ConceptNameCodeSequence=Sequence([c]);children.append(e)
    acq.ContentSequence=Sequence(children);d.ContentSequence=Sequence([num('113813',dlp,'mGy.cm'),acq]);return d

def zipped(tmp,objects):
    p=tmp/'exam.zip'
    with zipfile.ZipFile(p,'w') as z:
        for i,d in enumerate(objects):
            b=io.BytesIO();d.save_as(b,enforce_file_format=True);z.writestr(f'{i}.dcm',b.getvalue())
    return p

def test_rdsr_rejects_other_concept_scheme(tmp_path):
    a=image();s=rdsr(a)
    for n in s.ContentSequence:
        n.ConceptNameCodeSequence[0].CodingSchemeDesignator='99LOCAL'
    result=parse_dicom_zip_many(zipped(tmp_path,[a,s]))[0]
    assert result['ctdivol_mgy'] is None
    assert result['dlp_total_mgycm'] is None

def test_rdsr_rejects_unrecognized_unit_scheme(tmp_path):
    a=image();s=rdsr(a)
    for node in s.iterall():
        if node.keyword=='MeasurementUnitsCodeSequence':
            node.value[0].CodingSchemeDesignator='99LOCAL'
    result=parse_dicom_zip_many(zipped(tmp_path,[a,s]))[0]
    assert result['ctdivol_mgy'] is None
    assert result['dlp_total_mgycm'] is None

@pytest.mark.parametrize('args,expected',[(('cranio',46,70,1.7),70),(('abdome',46,70,1.7),25),(('torax',46,70,1.7),None),(('abdome',5,20,1.1),None),(('cranio',None,70,1.7),None),(('cranio',46,None,None),None)])
def test_reference_population(args,expected):
    r=reference_for(*args);assert r['ctdivol']==expected;assert r['dlp'] is None

@pytest.mark.parametrize('percent,level',[(79.99,'routine'),(80,'attention'),(99.99,'attention'),(100,'review'),(101,'review')])
def test_threshold_boundaries(percent,level): assert screening(percent,100)['level']==level

@pytest.mark.parametrize('v',[None,0,-1,float('nan'),float('inf')])
def test_invalid_measurements_never_normal(v): assert screening(v,70)['level']=='unavailable'

@pytest.mark.parametrize('phantom,a,b',[(16,1.874799,.03871313),(32,3.704369,.03671937)])
def test_ssde_published_body_equation(phantom,a,b):
    r=ssde(10,30,phantom,'abdome',120);assert r['ssde_mgy']==pytest.approx(10*a*math.exp(-b*30),abs=.00051)

def test_ssde_published_head_equation():
    assert ssde(42.9,16,16,'cranio',120)['ssde_mgy']==pytest.approx(42.9*1.9852*math.exp(-.0486*16),abs=.00051)

@pytest.mark.parametrize('args',[(10,None,32,'abdome',120),(10,30,None,'abdome',120),(10,16,32,'cranio',120),(10,16,16,'cranio',70),(None,30,32,'abdome',120),(10,90,32,'abdome',120)])
def test_ssde_no_extrapolation(args): assert ssde(*args)['ssde_mgy'] is None

def test_fallback_no_dlp_from_duplicate_reconstructions(tmp_path):
    a=image();b=image(study=a.StudyInstanceUID,series=a.SeriesInstanceUID)
    a.ImagePositionPatient=[0,0,0];b.ImagePositionPatient=[0,0,300]
    r=parse_dicom_zip_many(zipped(tmp_path,[a,b,a]))[0]
    assert r['dlp_total_mgycm'] is None;assert r['ctdivol_mgy']==10;assert len(r['series'])==1
    assert r['dw_cm']==30;assert r['ssde_mgy'] is not None

def test_no_weight_diameter_not_zero(tmp_path):
    a=image();del a.PatientWeight;del a.WaterEquivalentDiameter
    r=parse_dicom_zip_many(zipped(tmp_path,[a]))[0]
    assert r['ssde_mgy'] is None and r['dw_cm'] is None and r['ssde_factor'] is None

def test_no_weight_but_valid_dw_calculates(tmp_path):
    a=image();del a.PatientWeight
    assert parse_dicom_zip_many(zipped(tmp_path,[a]))[0]['ssde_mgy'] is not None

def test_rdsr_preferred_and_units_converted(tmp_path):
    a=image(event=generate_uid());report=rdsr(a,.01,'Gy',300,a.IrradiationEventUID)
    r=parse_dicom_zip_many(zipped(tmp_path,[a,report,report]))[0]
    assert r['_dose_source']=='RDSR';assert r['ctdivol_mgy']==10;assert r['dlp_total_mgycm']==300;assert r['ssde_mgy'] is not None

def test_unknown_unit_not_assumed(tmp_path):
    a=image();r=parse_dicom_zip_many(zipped(tmp_path,[a,rdsr(a,10,'mSv')]))[0]
    assert r['ctdivol_mgy'] is None;assert r['ssde_mgy'] is None

def test_multi_study_not_mixed(tmp_path):
    a,b=image(),image(pid='OTHER_SYNTHETIC_ID')
    assert len(parse_dicom_zip_many(zipped(tmp_path,[a,b])))==2

def test_same_study_different_patient_refused(tmp_path):
    a=image();b=image(study=a.StudyInstanceUID,pid='OTHER')
    with pytest.raises(ValueError,match='pacientes distintos'):parse_dicom_zip_many(zipped(tmp_path,[a,b]))

def test_age_at_scan_not_today():
    a=image();a.PatientBirthDate='20200101';a.StudyDate='20210101';assert age_at_exam(a)==1
    del a.PatientBirthDate;a.PatientAge='006M';assert age_at_exam(a)==0

def test_combined_region_has_no_head_reference():
    assert region_of('HEADNECK')=='pescoco';assert region_of('ABDOMENPELVIS')=='combinado'

def test_patient_pseudonyms_and_database(tmp_path):
    raw=parse_dicom_zip_many(zipped(tmp_path,[image()]))[0];key=load_key(tmp_path/'private')
    r=pseudonymize(raw,key);assert r['patient_id']==pseudonymize(raw,key)['patient_id']
    assert r['patient_id']!=pseudonymize(raw,b'x'*32)['patient_id']
    encoded=json.dumps(r);assert 'SECRET' not in encoded and '19800101' not in encoded and 'PATIENT_123' not in encoded
    path=tmp_path/'new.db';db.init_db(path);eid=db.save(path,r);assert db.save(path,r)==eid
    assert len(db.records(path))==1
    assert 'SECRET' not in path.read_bytes().decode(errors='ignore')

def test_legacy_db_refused_without_mutation(tmp_path):
    import sqlite3
    path=tmp_path/'old.db'
    with sqlite3.connect(path) as conn: conn.execute('create table pacientes(nome text)')
    original=path.read_bytes()
    with pytest.raises(ValueError,match='Banco antigo'):db.init_db(path)
    assert path.read_bytes()==original

def test_pdf_missingness_and_no_organs(tmp_path):
    from pdf_report import generate_pdf
    a=image();del a.WaterEquivalentDiameter;r=pseudonymize(parse_dicom_zip_many(zipped(tmp_path,[a]))[0],b'x'*32)
    out=io.BytesIO();generate_pdf(r,out);out.seek(0);reader=PdfReader(out)
    text='\n'.join(p.extract_text() for p in reader.pages)
    assert 'não calculado' in text;assert 'Triagem operacional' in text
    assert 'SECRET' not in text and 'dose por órgão' in text  # explicit scope note, never estimates
    assert '1.7 mGy' not in text and 'Dose efetiva (est.)' not in text

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('GUIARAD_RUNTIME',str(tmp_path/'runtime'))
    import app
    monkeypatch.setattr(app,'DB_PATH',tmp_path/'test_app.db');db.init_db(app.DB_PATH)
    monkeypatch.setattr(app,'UPLOAD_DIR',tmp_path/'uploads');app.UPLOAD_DIR.mkdir()
    monkeypatch.setattr(app,'KEY',b'y'*32)
    return app,app.app.test_client()

def test_api_pipeline_privacy_csrf_cleanup_and_pdf(client,tmp_path):
    app,c=client;p=zipped(tmp_path,[image()]);headers={'X-RG-Token':app.TOKEN}
    assert c.post('/api/analyze').status_code==403
    with p.open('rb') as f:response=c.post('/api/analyze',headers=headers,data={'file':(f,'SECRET_FILENAME.zip')})
    assert response.status_code==200
    record=response.json['exams'][0]
    assert 'SECRET' not in response.get_data(as_text=True)
    assert not list(app.UPLOAD_DIR.iterdir())
    assert c.get('/api/pdf/'+str(record['exam_db_id'])).status_code==200
    assert c.post('/api/ai_summary',headers=headers,json={'patient_name':'SECRET'}).status_code==410
    assert c.get('/api/recent').json['exams'][0]['patient_id'].startswith('P-')
    assert c.get('/api/info',headers={'Host':'evil.example'}).status_code==403
    assert 'SECRET' not in app.DB_PATH.read_bytes().decode(errors='ignore')

def test_error_cleanup(client):
    app,c=client
    r=c.post('/api/analyze',headers={'X-RG-Token':app.TOKEN},data={'file':(io.BytesIO(b'invalid'),'PRIVATE_NAME.dcm')})
    assert r.status_code in (400,500);assert not list(app.UPLOAD_DIR.iterdir())
    assert 'PRIVATE_NAME' not in r.get_data(as_text=True)

def test_legacy_migration_preserves_original_and_invalidates_ssde(tmp_path):
    import sqlite3
    from migrate_legacy import migrate
    source=tmp_path/'legacy.db';dest=tmp_path/'v2'/'new.db'
    with sqlite3.connect(source) as conn:
        conn.execute('create table exames(id integer,id_paciente text,data_exame text,regiao text,ctdivol_mgy real,dlp_mgycm real,ssde_mgy real,dados_json text)')
        conn.execute('insert into exames values(1,?,?,?,?,?,?,?)',('SECRET_ID','12/11/2026','cranio',42.9,797,42.9,json.dumps({'patient_name':'SECRET_NAME'})))
    before=source.read_bytes();assert migrate(source,dest)==1;assert source.read_bytes()==before
    rec=db.records(dest)[0];assert rec['ssde_mgy'] is None;assert rec['screening']['level']=='unavailable'
    assert 'SECRET' not in dest.read_bytes().decode(errors='ignore')
    with pytest.raises(ValueError):migrate(source,dest)
