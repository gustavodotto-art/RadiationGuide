"""Local pseudonymization. No direct identifiers or free-text clinical fields persisted.

Pseudonyms are keyed HMACs, not anonymous data. Exam month and dose metrics remain
potentially identifying. Protect the device and key; see PRIVACY.md.
"""
import hashlib
import hmac
import os
from pathlib import Path


def load_key(data_dir):
    path = Path(data_dir) / '.pseudonym_key'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f: f.write(os.urandom(32))
    except FileExistsError:
        pass
    key = path.read_bytes()
    if len(key) != 32: raise ValueError('Chave local inválida; restaure a chave original.')
    return key


def token(key, namespace, value):
    return hmac.new(key, (namespace + '\0' + value).encode(), hashlib.sha256).hexdigest()[:32]


def pseudonymize(data, key):
    source = dict(data)
    identity = source.pop('_identity', None)
    if not identity:
        raise ValueError('Identidade de origem ausente; vínculo longitudinal não criado.')
    pid = 'P-' + token(key, 'patient', identity)
    study = source.pop('_study_uid', '')
    source.pop('_study_date', None)
    source['patient_id'] = pid
    source['patient_name'] = pid  # compatibility only: contains no name
    source['study_token'] = token(key, 'study', study or identity)
    return source
