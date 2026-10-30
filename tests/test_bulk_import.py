import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
import test_http
import server as s

PHOTO=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aSc8AAAAASUVORK5CYII=')
IMAGE='data:image/png;base64,'+base64.b64encode(PHOTO).decode()
def row(i):return dict(name=f'Maxi proizvod {i}',sku=str(i),url=f'https://www.maxi.rs/p/{i}',image=IMAGE,unit='kom')
class BulkImportTest(unittest.TestCase):
 setUp=test_http.HTTPTest.setUp
 tearDown=test_http.HTTPTest.tearDown
 request=test_http.HTTPTest.request
 def start(self,mode='replace',o='Белград'):
  code,result=self.request('/api/catalog/import-start',dict(supplier='Maxi',office=o,mode=mode));self.assertEqual(code,200);return result['job_id']
 def upload(self,job,rows):return self.request('/api/catalog/import',dict(supplier='Maxi',job_id=job,rows=rows))
 def finish(self,job,count):return self.request('/api/catalog/import-finish',dict(job_id=job,expected_count=count))
 def test_replacement_is_staged_then_archives_originals_and_keeps_history(self):
  job=self.start();self.assertEqual(self.upload(job,[row(1),row(2)])[0],200)
  _,before=self.request('/api/state');self.assertEqual(len(before['products']),35)
  self.assertEqual(self.finish(job,3)[0],400)
  self.assertFalse(any(p.get('archived') for p in self.request('/api/state')[1]['products']))
  code,result=self.finish(job,2);self.assertEqual(code,200);self.assertEqual(result['archived'],35);self.assertEqual(result['created'],2)
  _,after=self.request('/api/state');current=[p for p in after['products'] if not p.get('archived')];self.assertEqual(len(current),2)
  self.assertEqual(before['observations'],after['observations']);self.assertEqual(before['deliveries'],after['deliveries'])
  self.assertTrue(all(p['rate'] is None and p['estimated_stock'] is None for p in current))
  path=current[0]['image'];self.assertTrue(path.startswith('/assets/catalog/'))
  import urllib.request
  with urllib.request.urlopen(self.url+path) as response:self.assertEqual(response.read(),PHOTO);self.assertIn('immutable',response.headers['Cache-Control'])
  self.assertEqual(self.finish(job,2)[1],result)
  self.assertEqual(len(self.request('/api/state')[1]['products']),37)
 def test_failed_batch_and_retry_do_not_replace_or_duplicate(self):
  job=self.start();self.upload(job,[row(1)])
  self.assertEqual(self.upload(job,[row(2),{'name':'bad'}])[0],400)
  self.assertEqual(len(self.request('/api/state')[1]['products']),35)
  self.assertEqual(self.upload(job,[row(1),row(2)])[0],200)
  self.assertEqual(self.finish(job,2)[0],200)
  job2=self.start();self.upload(job2,[row(1),row(2)]);self.assertEqual(self.finish(job2,2)[1]['created'],0)
  self.assertEqual(len(self.request('/api/state')[1]['products']),37)
 def test_existing_catalogue_schema_migrates_without_losing_products(self):
  import catalog
  with s.connect() as c:
   c.execute('DROP TABLE supplier_catalog')
   c.execute('CREATE TABLE supplier_catalog(id INTEGER PRIMARY KEY,supplier TEXT NOT NULL,external_key TEXT NOT NULL,data TEXT NOT NULL,UNIQUE(supplier,external_key))')
   item=catalog.normalise(row(1),'Maxi')
   c.execute('INSERT INTO supplier_catalog(supplier,external_key,data) VALUES(?,?,?)',('Maxi',item['external_key'],json.dumps(item)))
  s.init();s.init()
  result=self.request('/api/supplier-catalog?supplier=Maxi&q=proizvod')[1]
  self.assertEqual(result['total'],1);self.assertEqual(result['rows'][0]['name'],item['name'])

 def test_other_office_and_supplier_only_mode_leave_products_untouched(self):
  job=self.start('supplier');self.upload(job,[row(1)]);self.finish(job,1)
  self.assertEqual(len(self.request('/api/state')[1]['products']),35)
  job=self.start(o='Нови-Сад');self.upload(job,[row(1)]);self.finish(job,1)
  st=self.request('/api/state')[1];self.assertEqual(len([p for p in st['products'] if p['office']=='Белград' and not p.get('archived')]),35)
 def test_photo_backup_restores_files_and_supports_previous_schema(self):
  from scripts.restore_backup import restore
  job=self.start();self.upload(job,[row(1)]);self.finish(job,1)
  _,backup=self.request('/api/backup');self.assertEqual(len(backup['images']),1)
  # Simulate the previous catalogue schema in a portable backup.
  for item in backup['tables']['supplier_catalog']:item.pop('url');item.pop('name_search')
  path=Path(self.tmp.name)/'backup.json';path.write_text(json.dumps(backup));old=s.DATA
  try:
   restore(path,Path(self.tmp.name)/'restored')
   with s.connect() as c:
    self.assertEqual(c.execute('SELECT count(*) FROM supplier_catalog WHERE url<>? AND name_search<>?',('','')).fetchone()[0],1)
   self.assertEqual(next((s.DATA/'catalog-images').iterdir()).read_bytes(),PHOTO)
  finally:s.DATA=old
