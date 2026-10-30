import json
import unittest
import test_http
import server as s
import taxonomy

class CategoriesTest(unittest.TestCase):
 def test_serbian_product_names_get_useful_categories(self):
  examples={'Mleko dugotrajno 2.8% 1l':'Молочные','Jogurt sa ukusom kafe 330g':'Молочные','Čokoladno mleko 250ml':'Молочные','Mlečni hleb tost 500g':'Хлеб и выпечка','Banane 1kg':'Фрукты и овощи','Šargarepa štapići 80g':'Фрукты и овощи','Sok od jabuke 1l':'Напитки','Coca-Cola limenka 330ml':'Напитки','Fuze Tea breskva':'Напитки','Čaj zeleni 20 kesica':'Кофе и чай','Kafa mlevena 200g':'Кофе и чай','Maslac od kikirikija 250g':'Соусы и намазки','Smrznuta malina 300g':'Замороженные продукты','Čokolada sa mlekom':'Сладости','Jaja 10 kom':'Яйца','Tunjevina Rio Mare 80g':'Мясо и рыба','Kreker slani':'Снеки','Palenta 500g':'Бакалея','Mleko za telo 250ml':'Бытовые товары','Nepoznat artikal 123':'Прочее'}
  for name,expected in examples.items():
   with self.subTest(name=name):self.assertEqual(taxonomy.suggest_category(name),expected)
 def test_manual_other_and_custom_categories_are_not_overwritten(self):
  self.assertEqual(taxonomy.category_fields('Mleko 1l','Прочее','manual')['category'],'Прочее')
  self.assertEqual(taxonomy.category_fields('Mleko 1l','Для переговорных','manual')['category'],'Для переговорных')
  self.assertEqual(taxonomy.canonical_supplier('mojapijaca'),'Moja Pijaca');self.assertEqual(taxonomy.canonical_supplier('denmark'),'Denmark')

class ProductListsTest(unittest.TestCase):
 setUp=test_http.HTTPTest.setUp
 tearDown=test_http.HTTPTest.tearDown
 request=test_http.HTTPTest.request
 def imported(self):
  item=dict(name='Mleko test 1l',sku='LISTS-1',url='https://www.maxi.rs/p/LISTS-1')
  self.request('/api/catalog/import',dict(supplier='Maxi',rows=[item]))
  row=self.request('/api/supplier-catalog?supplier=Maxi')[1]['rows'][0]
  code,result=self.request('/api/catalog/select',dict(catalog_id=row['id'],office='Белград'));self.assertEqual(code,200);return result['id']
 def product(self,id):return next(p for p in self.request('/api/state')[1]['products'] if p['id']==id)
 def test_import_favorite_and_pantry_are_separate_persistent_lists(self):
  pid=self.imported();p=self.product(pid);self.assertFalse(p['in_pantry']);self.assertFalse(p['favorite']);self.assertEqual(p['category'],'Молочные')
  self.assertEqual(self.request('/api/product-flags',dict(product_id=pid,favorite=True))[0],200)
  self.assertTrue(self.product(pid)['favorite']);self.assertFalse(self.product(pid)['in_pantry'])
  self.request('/api/product-flags',dict(product_id=pid,in_pantry=True));self.assertIsNone(self.product(pid)['estimated_stock'])
  self.request('/api/product-flags',dict(product_id=pid,in_pantry=False));s.init()
  p=self.product(pid);self.assertTrue(p['favorite']);self.assertFalse(p['in_pantry'])
 def test_manual_category_and_favorite_survive_editor_and_reimport(self):
  pid=self.imported();p=self.product(pid)
  self.request('/api/product-flags',dict(product_id=pid,favorite=True))
  p.update(category='Для кухни',category_source='manual')
  self.assertEqual(self.request('/api/product',dict(p,id=pid))[0],200);self.assertTrue(self.product(pid)['favorite'])
  job=self.request('/api/catalog/import-start',dict(supplier='Maxi',office='Белград',mode='add'))[1]['job_id']
  self.request('/api/catalog/import',dict(supplier='Maxi',job_id=job,rows=[dict(name='Mleko test 1l',sku='LISTS-1',url='https://www.maxi.rs/p/LISTS-1')]))
  self.request('/api/catalog/import-finish',dict(job_id=job,expected_count=1));s.init()
  p=self.product(pid);self.assertEqual(p['category'],'Для кухни');self.assertTrue(p['favorite']);self.assertFalse(p['in_pantry'])
 def test_old_assortment_is_migrated_without_inventing_inventory(self):
  pid=self.imported()
  with s.connect() as c:
   p=json.loads(c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone()[0]);p.pop('in_pantry');p.pop('favorite');p['category']='Прочее';p.pop('category_source',None);c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p),pid))
  s.init();self.assertFalse(self.product(pid)['in_pantry']);self.assertEqual(self.product(pid)['category'],'Молочные');self.assertTrue(self.product(1)['in_pantry'])
 def test_real_stock_observation_enrolls_but_unenrolling_keeps_history(self):
  pid=self.imported();self.request('/api/observation',dict(product_id=pid,date='2026-10-29',kind='exact',qty=4));self.assertTrue(self.product(pid)['in_pantry'])
  self.request('/api/product-flags',dict(product_id=pid,in_pantry=False));s.init();p=self.product(pid);self.assertFalse(p['in_pantry']);self.assertEqual(p['estimated_stock'],4)
 def test_flag_validation_and_office_scope(self):
  self.assertEqual(self.request('/api/product-flags',dict(product_id=1,favorite='false'))[0],400)
  self.request('/api/product-flags',dict(product_id=1,favorite=True))
  st=self.request('/api/state')[1];self.assertFalse(any(p['favorite'] for p in st['products'] if p['office']=='Нови-Сад'))
