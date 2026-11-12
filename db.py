"""New pseudonym-only schema. Legacy databases are never silently reused."""
import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 'rg-2-pseudonym-only'
FIELDS = {'patient_id','patient_name','study_token','exam_type','modality','region','study_desc',
          'study_month','patient_group','ctdivol_mgy','dlp_total_mgycm','phantom_cm','kvp','nrd',
          'screening','_dose_source','warnings','ctdivol_pct_nrd','dlp_pct_nrd','ctdivol_summary',
          'ssde_mgy','dw_cm','ssde_factor','ssde_method','ssde_reason','series'}


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if names and 'metadata' not in names:
            raise ValueError('Banco antigo detectado. Use migrate_legacy.py para criar cópia pseudonimizada; o original não será alterado.')
        if 'metadata' in names:
            version = conn.execute('SELECT version FROM metadata').fetchone()
            if not version or version[0] != SCHEMA_VERSION: raise ValueError('Versão de banco incompatível.')
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS metadata(version TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS exams(
            id INTEGER PRIMARY KEY, patient_id TEXT NOT NULL,
            study_token TEXT UNIQUE NOT NULL, study_month TEXT, region TEXT, data_json TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS by_patient ON exams(patient_id);
        ''')
        if not conn.execute('SELECT 1 FROM metadata').fetchone():
            conn.execute('INSERT INTO metadata VALUES (?)',(SCHEMA_VERSION,))


def save(path, record):
    # Records arrive from the parser + HMAC boundary, never from a browser payload.
    clean = {k:v for k,v in record.items() if k in FIELDS}
    if not clean.get('patient_id','').startswith('P-'): raise ValueError('Pseudônimo ausente.')
    with connect(path) as conn:
        conn.execute('''INSERT INTO exams(patient_id,study_token,study_month,region,data_json)
                        VALUES(?,?,?,?,?) ON CONFLICT(study_token) DO UPDATE SET
                        data_json=excluded.data_json, study_month=excluded.study_month, region=excluded.region''',
                     (clean['patient_id'],clean['study_token'],clean.get('study_month'),clean['region'],
                      json.dumps(clean,ensure_ascii=False,allow_nan=False)))
        eid=conn.execute('SELECT id FROM exams WHERE study_token=?',(clean['study_token'],)).fetchone()[0]
    return eid


def records(path, patient_id=None):
    with connect(path) as conn:
        rows = conn.execute('SELECT id,data_json FROM exams '+('WHERE patient_id=? ' if patient_id else '')+
                            'ORDER BY study_month DESC,id DESC LIMIT 500', (patient_id,) if patient_id else ()).fetchall()
    return [dict(json.loads(r['data_json']),exam_db_id=r['id']) for r in rows]


def get(path, eid):
    with connect(path) as conn:
        row=conn.execute('SELECT data_json FROM exams WHERE id=?',(eid,)).fetchone()
    return dict(json.loads(row[0]),exam_db_id=eid) if row else None
