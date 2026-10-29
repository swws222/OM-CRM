import base64
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import server as s

class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=s.DATA;s.DATA=Path(self.tmp.name);s.init()
        self.http=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.url=f'http://127.0.0.1:{self.http.server_port}'
    def tearDown(self):
        self.http.shutdown();self.http.server_close();s.DATA=self.old;self.tmp.cleanup();os.environ.pop('PANTRY_PASSWORD',None)
    def request(self,path,body=None,headers=None):
        h={'Content-Type':'application/json',**(headers or {})}
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_language_files_are_served_as_json(self):
        for lang in ('ru','sr','en'):
            code,data=self.request('/locales/'+lang+'.json')
            self.assertEqual(code,200);self.assertIsInstance(data,dict)

    def test_mutations_persist_and_backup_has_history(self):
        code,d=self.request('/api/observation',dict(product_id=1,date='2026-10-22',kind='level',level=0))
        self.assertEqual(code,200)
        _,state=self.request('/api/state');self.assertEqual(state['products'][0]['estimated_stock'],0)
        _,backup=self.request('/api/backup');self.assertTrue(backup['tables']['audit']);self.assertIn('files',backup)
    def test_cross_origin_blocked_and_auth_required_when_configured(self):
        code,_=self.request('/api/attendance',dict(office='Белград',date='2026-10-22',count=1),{'Origin':'https://external.example'})
        self.assertEqual(code,403)
        os.environ['PANTRY_PASSWORD']='test-password'
        self.assertEqual(self.request('/api/state')[0],401)
        auth='Basic '+base64.b64encode(b'admin:test-password').decode()
        self.assertEqual(self.request('/api/state',headers={'Authorization':auth})[0],200)
    def test_invalid_import_rolls_back_entire_batch(self):
        code,_=self.request('/api/attendance',{'records':[dict(office='Белград',date='2026-10-22',count=5),dict(office='Белград',date='2026-10-23',count=-1)]})
        self.assertEqual(code,400)
        with s.connect() as c:self.assertFalse(c.execute("SELECT 1 FROM attendance WHERE date='2026-10-22'").fetchone())
    def test_backup_restores_to_new_directory(self):
        from scripts.restore_backup import restore
        _,backup=self.request('/api/backup');path=Path(self.tmp.name)/'backup.json';path.write_text(json.dumps(backup))
        old=s.DATA
        try:
            restore(path,Path(self.tmp.name)/'restored')
            with s.connect() as c:self.assertEqual(len(s.state(c)['products']),35)
        finally:s.DATA=old
