import base64
import json
import unittest
import test_http
import catalog
import server as s

PRODUCT=dict(name='Mleko test 1 l',sku='TEST-1',url='https://www.maxi.rs/p/TEST-1',image='https://images.example.org/milk.jpg',price=199.99,currency='RSD',unit='kom')
class ParseTest(unittest.TestCase):
 def test_jsonld_nested_and_official_text_preserved(self):
  p=dict(PRODUCT,**{'@type':'Product'})
  text='<html><script type="application/ld+json">'+json.dumps({'@graph':[p]})+'</script><script>throw Error("never execute")</script></html>'
  r=catalog.preview(text,'html','Maxi');self.assertEqual(r['rows'][0]['name'],PRODUCT['name']);self.assertFalse(r['errors'])
 def test_csv_duplicates_and_tracking_parameters(self):
  text='name;sku;url;price;currency\nMleko;1;https://www.maxi.rs/p/1?utm_source=x;200;RSD\nMleko;1;https://www.maxi.rs/p/1;200;RSD\n'
  r=catalog.preview(text,'csv','Maxi');self.assertEqual(len(r['rows']),1);self.assertEqual(r['rows'][0]['url'],'https://www.maxi.rs/p/1')
 def test_invalid_rows_are_explained_and_not_silently_saved(self):
  rows=[PRODUCT,{**PRODUCT,'sku':'bad','url':'https://example.com/p/1'},{'name':'no identity'},{**PRODUCT,'price':'NaN'}]
  r=catalog.preview(json.dumps(rows),'json','Maxi');self.assertEqual(len(r['rows']),1);self.assertEqual(len(r['errors']),3)
 def test_empty_and_unstructured_pages_fail_explicitly(self):
  for fmt,content in [('csv',''),('html','<html>no products</html>'),('json','[]')]:
   with self.assertRaises(ValueError):catalog.preview(content,fmt,'Maxi')
 def test_portable_photos_are_validated(self):
  image='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
  self.assertEqual(catalog.normalise({**PRODUCT,'image':image},'Maxi')['image'],image)
  for bad in ['data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,bm90YW5pbWFnZQ==']:
   with self.assertRaises(ValueError):catalog.normalise({**PRODUCT,'image':bad},'Maxi')

 def test_non_rsd_and_embedded_credentials_rejected(self):
  for row in [{**PRODUCT,'currency':'EUR'},{**PRODUCT,'url':'https://user:secret@www.maxi.rs/p/1'}]:
   with self.assertRaises(ValueError):catalog.normalise(row,'Maxi')

class CatalogHTTPTest(unittest.TestCase):
 setUp=test_http.HTTPTest.setUp
 tearDown=test_http.HTTPTest.tearDown
 request=test_http.HTTPTest.request
 def test_catalogue_is_separate_and_links_preserve_inventory(self):
  code,r=self.request('/api/catalog/preview',dict(supplier='Maxi',format='json',content=json.dumps([PRODUCT])))
  self.assertEqual(code,200)
  code,r=self.request('/api/catalog/import',dict(supplier='Maxi',rows=r['rows']));self.assertEqual(code,200)
  self.assertEqual(self.request('/api/catalog/import',dict(supplier='Maxi',rows=[PRODUCT]))[0],200)
  _,r=self.request('/api/supplier-catalog?supplier=Maxi');self.assertEqual(r['total'],1);cid=r['rows'][0]['id']
  _,before=self.request('/api/state');self.assertEqual(len(before['products']),35);p=before['products'][0]
  code,_=self.request('/api/catalog/select',dict(catalog_id=cid,office='Белград',product_id=1));self.assertEqual(code,200)
  _,after=self.request('/api/state');p2=after['products'][0]
  self.assertEqual(p2['name'],PRODUCT['name']);self.assertEqual(p2['rate'],p['rate']);self.assertEqual(p2['estimated_stock'],p['estimated_stock']);self.assertEqual(after['observations'],before['observations'])
  self.assertEqual(self.request('/api/catalog/select',dict(catalog_id=cid,office='Белград'))[0],400)
 def test_catalogue_new_product_has_no_invented_rate_or_stock(self):
  self.request('/api/catalog/import',dict(supplier='Maxi',rows=[PRODUCT]));_,r=self.request('/api/supplier-catalog?supplier=Maxi');cid=r['rows'][0]['id']
  code,result=self.request('/api/catalog/select',dict(catalog_id=cid,office='Нови-Сад'));self.assertEqual(code,200)
  _,st=self.request('/api/state');p=next(p for p in st['products'] if p['id']==result['id']);self.assertIsNone(p['rate']);self.assertIsNone(p['estimated_stock']);self.assertEqual(p['office'],'Нови-Сад')
 def test_import_batch_failure_rolls_back(self):
  code,_=self.request('/api/catalog/import',dict(supplier='Maxi',rows=[PRODUCT,{'name':'invalid'}]));self.assertEqual(code,400)
  self.assertEqual(self.request('/api/supplier-catalog?supplier=Maxi')[1]['total'],0)
 def test_name_migration_is_idempotent_and_preserves_history(self):
  _,st=self.request('/api/state');self.assertEqual(st['products'][0]['name'],'Argeta pašteta');self.assertEqual(st['products'][0]['legacy_name'],'Argeta (паштет)');self.assertEqual(st['products'][0]['name_status'],'provisional')
  with s.connect() as c:before=c.execute('SELECT count(*) FROM audit').fetchone()[0]
  s.init()
  with s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM audit').fetchone()[0],before)
