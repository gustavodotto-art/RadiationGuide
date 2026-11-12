"""Radiation Guide 2.0 — local CT metadata review, without external AI calls."""
import io
import os
import secrets
import tempfile
import zipfile
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException
import db
from dicom_parser import parse_dicom_zip_many, NonCTExamError
from privacy import load_key, pseudonymize
from pdf_report import generate_pdf

APP_VERSION = '2.0.0-rc1'
BASE_DIR=Path(__file__).parent
# A new runtime prevents accidental use of legacy identifiable databases/reports.
RUNTIME_DIR=Path(os.environ.get('GUIARAD_RUNTIME',str(BASE_DIR/'_runtime_v2')))
DATA_DIR=RUNTIME_DIR/'data'
UPLOAD_DIR=RUNTIME_DIR/'uploads'
for d in (DATA_DIR,UPLOAD_DIR): d.mkdir(parents=True,exist_ok=True)
DB_PATH=DATA_DIR/'radiation_guide_v2.db'
KEY=load_key(DATA_DIR)
db.init_db(DB_PATH)
TOKEN=secrets.token_urlsafe(32)
app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=512*1024*1024

@app.before_request
def local_boundary():
    # Host and explicit token guard local browser requests against rebinding/CSRF.
    if request.host.split(':')[0] not in ('127.0.0.1','localhost','[::1]'):
        return jsonify(error='Use o endereço local 127.0.0.1.'),403
    if request.method not in ('GET','HEAD','OPTIONS'):
        if not secrets.compare_digest(request.headers.get('X-RG-Token',''),TOKEN):
            return jsonify(error='Reabra a página local antes de continuar.'),403

@app.after_request
def private_response(response):
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
    return response

@app.errorhandler(Exception)
def error(exc):
    if isinstance(exc, HTTPException): return jsonify(error=exc.name),exc.code
    # No DICOM names, paths, patient IDs or tracebacks in logs/API.
    return jsonify(error='Falha no processamento local. Confira o formato e as limitações documentadas.'),500

@app.get('/')
def index(): return render_template('index.html',token=TOKEN,version=APP_VERSION)

@app.post('/api/analyze')
def analyze():
    f=request.files.get('file')
    if f is None: return jsonify(error='Selecione um arquivo DICOM ou ZIP.'),400
    try:
        # Filenames are random, never the user-supplied original. Always cleaned,
        # including cache/error paths. No raw DICOM retained in the database.
        with tempfile.TemporaryDirectory(dir=UPLOAD_DIR,prefix='request_') as td:
            source=Path(td)/'input'
            f.save(source)
            if not zipfile.is_zipfile(source):
                wrapped=Path(td)/'input.zip'
                with zipfile.ZipFile(wrapped,'w') as z: z.write(source,'image.dcm')
                source=wrapped
            output=[]
            for raw in parse_dicom_zip_many(source):
                record=pseudonymize(raw,KEY)
                eid=db.save(DB_PATH,record)
                output.append(dict(record,exam_db_id=eid))
        return jsonify(exams=output,count=len(output))
    except (NonCTExamError,ValueError,zipfile.BadZipFile) as exc:
        # All expected exceptions have controlled, non-identifying messages.
        return jsonify(error=str(exc)),400

@app.get('/api/recent')
def recent(): return jsonify(exams=db.records(DB_PATH))

@app.get('/api/history/<patient_id>')
def history(patient_id): return jsonify(exams=db.records(DB_PATH,patient_id))

@app.get('/api/exam/<int:eid>')
def exam(eid):
    record=db.get(DB_PATH,eid)
    return (jsonify(record) if record else (jsonify(error='Exame não encontrado.'),404))

@app.get('/api/pdf/<int:eid>')
def pdf(eid):
    record=db.get(DB_PATH,eid)
    if not record: return jsonify(error='Exame não encontrado.'),404
    out=io.BytesIO()
    generate_pdf(record,out)
    out.seek(0)
    return send_file(out,mimetype='application/pdf',as_attachment=True,download_name=f'RG_exame_{eid}.pdf')

@app.post('/api/ai_summary')
def no_external_ai():
    return jsonify(error='Integração externa removida nesta versão; nenhum dado é enviado a LLM.'),410

@app.get('/api/info')
def info():
    return jsonify(version=APP_VERSION,external_ai=False,privacy='pseudonymized-local',
                   n_exames=len(db.records(DB_PATH)))

if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.environ.get('GUIARAD_PORT','5050')),debug=False)
