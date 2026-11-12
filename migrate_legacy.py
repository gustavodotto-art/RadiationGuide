"""Offline, non-destructive import of v1 technical history into a new v2 database.

Usage: python migrate_legacy.py --source old.db --dest _runtime_v2/data/radiation_guide_v2.db
Legacy calculations are not silently reused: SSDE and reference screening are invalidated.
The original database and old raw files remain at source and require local data governance.
"""
import argparse
import json
import sqlite3
from pathlib import Path
import db
from dosimetry import region_of,positive,reference_for,screening
from privacy import load_key,pseudonymize


def migrate(source,dest):
    source,dest=Path(source).resolve(),Path(dest).resolve()
    if source==dest or dest.exists(): raise ValueError('Destino deve ser um arquivo novo, diferente da origem.')
    conn=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    rows=conn.execute('SELECT * FROM exames ORDER BY id').fetchall()
    key=load_key(dest.parent);db.init_db(dest)
    imported=0
    for row in rows:
        data=dict(row)
        try: old=json.loads(data.get('dados_json') or '{}')
        except ValueError: old={}
        pid=str(data.get('id_paciente') or old.get('patient_id') or '')
        if not pid: raise ValueError('Registro sem identificador de origem; importação interrompida.')
        date=str(data.get('data_exame') or '')
        month=date[-4:]+'-'+date[3:5] if len(date)==10 and date[2]=='/' else None
        region=region_of(str(data.get('regiao') or old.get('region') or ''))
        record={'_identity':'id::'+pid, '_study_uid':'legacy:'+str(data['id']),
                'region':region,'study_desc':'TC '+region,'study_month':month,'exam_type':'CT','modality':'CT',
                'patient_group':'não definido', 'ctdivol_mgy':positive(data.get('ctdivol_mgy')),
                'dlp_total_mgycm':positive(data.get('dlp_mgycm')), 'dw_cm':None,'ssde_mgy':None,
                'ssde_factor':None,'ssde_method':None,'ssde_reason':'Valor legado invalidado; reprocesse o DICOM original.',
                'phantom_cm':None,'kvp':positive(data.get('kvp')),'series':[],
                'nrd':reference_for(region,None,None,None),'screening':screening(None,None),
                'ctdivol_pct_nrd':None,'dlp_pct_nrd':None,'_dose_source':'Legado não revalidado',
                'warnings':['Histórico importado da v1; CTDIvol/DLP não conferidos com o DICOM nesta importação.'],
                'ctdivol_summary':'Valor histórico; não somar CTDIvol entre exames.'}
        db.save(dest,pseudonymize(record,key));imported+=1
    conn.close()
    return imported

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',required=True);ap.add_argument('--dest',required=True)
    args=ap.parse_args();print('Registros importados:',migrate(args.source,args.dest))
