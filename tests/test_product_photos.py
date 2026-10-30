import base64
import json
import unittest
import test_http
import server as s

IMAGE='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aSc8AAAAASUVORK5CYII='
class ProductPhotoTest(unittest.TestCase):
 setUp=test_http.HTTPTest.setUp
 tearDown=test_http.HTTPTest.tearDown
 request=test_http.HTTPTest.request
 def product(self,id):return next(p for p in self.request('/api/state')[1]['products'] if p['id']==id)
 def import_photo(self):
  row=dict(name='Grekos jagoda 150g',sku='G-1',url='https://www.maxi.rs/p/G-1',image=IMAGE)
  self.request('/api/catalog/import',dict(supplier='Maxi',rows=[row]));return self.request('/api/supplier-catalog?supplier=Maxi')[1]['rows'][0]['id']
 def test_photo_only_changes_do_not_transfer_sku_or_stock(self):
  cid=self.import_photo();target=5
  self.request('/api/observation',dict(product_id=target,date='2026-10-30',kind='level',level=2))
  with s.connect() as c:
   p=json.loads(c.execute('SELECT data FROM products WHERE id=?',(target,)).fetchone()[0]);p['archived']=True;c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p),target))
  before=self.product(target);self.assertEqual(before['photo_status'],'none')
  _,choices=self.request(f'/api/photo-candidates?product_id={target}&q=Grekos');self.assertEqual(choices['total'],1)
  code,_=self.request('/api/product-photo',dict(product_id=target,source_type='supplier_catalog',source_id=cid));self.assertEqual(code,200)
  after=self.product(target)
  for field in ('name','supplier_sku','category','rate','thresholds','estimated_stock','observation','in_pantry','archived'):self.assertEqual(after.get(field),before.get(field),field)
  self.assertEqual(after['photo_status'],'local');self.assertTrue(after['image_source']['illustrative'])
 def test_missing_image_file_is_reported_without_erasing_its_reference(self):
  cid=self.import_photo();self.request('/api/product-photo',dict(product_id=5,source_type='supplier_catalog',source_id=cid))
  p=self.product(5);(s.DATA/'catalog-images'/p['image'].rsplit('/',1)[-1]).unlink()
  after=self.product(5);self.assertEqual(after['photo_status'],'missing');self.assertEqual(after['image'],p['image'])
  self.assertEqual(self.request('/api/product-photo',dict(product_id=5,source_type='supplier_catalog',source_id=cid))[0],400)
  self.import_photo();self.assertEqual(self.product(5)['photo_status'],'local')
 def test_archive_is_not_reenrolled_by_legacy_migration(self):
  with s.connect() as c:
   p=json.loads(c.execute('SELECT data FROM products WHERE id=5').fetchone()[0]);p['archived']=True;p.pop('in_pantry',None);p.pop('purchase_policy',None);c.execute('UPDATE products SET data=? WHERE id=5',(json.dumps(p),))
  s.init();self.assertFalse(self.product(5)['in_pantry'])
  self.request('/api/product-flags',dict(product_id=5,in_pantry=True));s.init();self.assertTrue(self.product(5)['in_pantry'])
