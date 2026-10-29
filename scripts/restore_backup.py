"""Restore a trusted downloaded backup into a NEW data directory only."""
import base64
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

def restore(backup_path,target):
    target=Path(target)
    if target.exists() and any(target.iterdir()): raise ValueError('Target must be an empty/new directory. Stop the server before switching data directories.')
    backup=json.loads(Path(backup_path).read_text())
    if backup.get('version')!=1: raise ValueError('Unsupported backup version')
    tables=('products','observations','deliveries','attendance','audit','meta','orders','supplier_catalog')
    if set(backup['tables']) not in (set(tables),set(tables)-{'supplier_catalog'}): raise ValueError('Incomplete backup')
    files={}
    for name,encoded in backup.get('files',{}).items():
        raw=base64.b64decode(encoded,validate=True)
        if name!=hashlib.sha256(raw).hexdigest()+'.pdf': raise ValueError('Invalid attachment hash')
        files[name]=raw
    server.DATA=target;server.init()
    with server.connect() as c:
        for table in ('supplier_catalog','observations','orders','audit','deliveries','attendance','products','meta'): c.execute(f'DELETE FROM {table}')
        for table in tables:
            columns=[r[1] for r in c.execute(f'PRAGMA table_info({table})')]
            for row in backup['tables'].get(table,[]):
                if set(row)!=set(columns): raise ValueError(f'Unexpected columns: {table}')
                c.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",[row[col] for col in columns])
    (target/'files').mkdir(exist_ok=True)
    for name,raw in files.items(): (target/'files'/name).write_bytes(raw)
    print('Restored. Start the server with PANTRY_DATA_DIR set to the target directory.')
if __name__=='__main__': restore(sys.argv[1],sys.argv[2])
