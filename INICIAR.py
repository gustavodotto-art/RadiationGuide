"""Instalação inicial em ambiente isolado e abertura local da versão de teste."""
import hashlib
import os
from pathlib import Path
import subprocess
import socket
import sys
import threading
import time
import urllib.request
import venv
import webbrowser

BASE=Path(__file__).resolve().parent

def main():
    if not (3,10) <= sys.version_info[:2] < (3,14):
        print('Instale Python 3.10 a 3.13 de python.org e tente novamente.')
        return 1
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',5050))==0:
            print('A porta 5050 já está em uso. Encerre a outra instância do app e tente novamente.')
            return 1
    runtime=BASE/'_runtime_v2'
    envdir=runtime/'venv'
    python=envdir/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    requirements=BASE/'requirements.txt'
    marker=envdir/'.requirements.sha256'
    digest=hashlib.sha256(requirements.read_bytes()).hexdigest()
    try:
        if not python.exists():
            print('Criando ambiente Python local…',flush=True)
            venv.EnvBuilder(with_pip=True).create(envdir)
        if not marker.exists() or marker.read_text()!=digest:
            print('Instalando dependências: esta etapa precisa de internet.',flush=True)
            subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],check=True)
            subprocess.run([str(python),'-m','pip','check'],check=True)
            marker.write_text(digest)
        env=os.environ.copy()
        env['GUIARAD_RUNTIME']=str(runtime)
        env['GUIARAD_PORT']='5050'
        url='http://127.0.0.1:5050'
        # Open only when this version answers locally; all processing stays local.
        def open_when_ready():
            for _ in range(60):
                try:
                    with urllib.request.urlopen(url+'/api/info',timeout=1) as r:
                        import json
                        if json.load(r).get('version')=='2.0.0-rc1':
                            webbrowser.open(url)
                            return
                except Exception:
                    time.sleep(.5)
        thread=threading.Thread(target=open_when_ready,daemon=True)
        thread.start()
        print('Radiation Guide 2.0.0-rc1 — versão experimental para teste técnico.',flush=True)
        print('Abra '+url+' no navegador. Para encerrar, pressione Ctrl+C.',flush=True)
        return subprocess.call([str(python),str(BASE/'app.py')],cwd=BASE,env=env)
    except KeyboardInterrupt:
        return 0
    except (OSError,subprocess.CalledProcessError) as exc:
        print('Não foi possível iniciar. Verifique Python, internet na instalação e as mensagens acima.')
        return 1

if __name__=='__main__':
    raise SystemExit(main())
