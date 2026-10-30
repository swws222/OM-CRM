import json
from pathlib import Path
import tempfile
import unittest
from scripts.collect_catalog import Collector,STORES,extract_products,write_export,next_links,options,choose_proxy

class CollectorTest(unittest.TestCase):
 def test_sap_records_preserve_names_codes_images_and_price(self):
  data={'products':[{'code':'123','name':'Mleko original 1L','url':'/Mleko/p/123','images':[{'url':'/milk.jpg','format':'product'}],'price':{'value':155.99,'currencyIso':'RSD'}}]}
  p=extract_products(data,'https://www.maxi.rs/api/search',STORES['maxi'])[0]
  self.assertEqual((p['sku'],p['name'],p['price']),('123','Mleko original 1L',155.99));self.assertEqual(p['image'],'https://www.maxi.rs/milk.jpg')
 def test_woo_prices_and_schema_products(self):
  data={'products':[{'id':91,'name':'Paradajz čeri 250g','permalink':'https://www.mojapijaca.rs/product/ceri','images':[{'src':'/ceri.jpg'}],'prices':{'price':'30420','currency_code':'RSD','currency_minor_unit':2}}]}
  p=extract_products(data['products'],'https://www.mojapijaca.rs/',STORES['moja'])[0];self.assertEqual(p['price'],304.2);self.assertEqual(p['sku'],'91')
  p=extract_products({'@type':'Product','name':'Coca-Cola','sku':'55','image':'/cola.jpg'},STORES['coca']['start'],STORES['coca'])[0];self.assertEqual(p['sku'],'55')
 def test_non_products_and_foreign_links_are_not_catalogue_entries(self):
  self.assertEqual(extract_products({'regions':[{'name':'Beograd','code':'BG'}]},'https://www.maxi.rs/',STORES['maxi']),[])
  self.assertEqual(extract_products({'@type':'Product','name':'Fake','url':'https://example.com/p/1'},'https://www.maxi.rs/',STORES['maxi']),[])
 def test_merging_uses_canonical_product_name_not_list_caption(self):
  c=Collector(STORES['maxi']);c.add([dict(name='Image caption',sku='',url='https://www.maxi.rs/p/1',image='',price=None)],'dom')
  c.add([dict(name='Official name',sku='1',url='https://www.maxi.rs/p/1',image='https://www.maxi.rs/1.jpg',price=10)],'network')
  c.add([dict(name='Caption again',sku='',url='https://www.maxi.rs/p/1',image='',price=None)],'dom')
  self.assertEqual(len(c.products),1);self.assertEqual(next(iter(c.products.values()))['name'],'Official name')
 def test_queue_is_supplier_scoped_and_does_not_expand_filters(self):
  snap={'links':[{'url':'/c/02','text':'Milk'},{'url':'/c/02?filter=x','text':'Filter'},{'url':'/c/02?page=1','text':'Next','next':True},{'url':'https://evil.example/p/1','text':'X'},{'url':'/p/1','text':'Product'}]}
  links=next_links(snap,'https://www.maxi.rs/',STORES['maxi']);self.assertEqual(len(links),3);self.assertNotIn('https://evil.example/p/1',links)
 def test_export_is_checkpointed_and_reports_incompleteness(self):
  c=Collector(STORES['maxi'],max_pages=1);c.add([dict(name='Mleko',sku='1',url='',image='',price=None)],'network');c.queue=['https://www.maxi.rs/c/02'];c.page_records=[{'status':'visited'}]
  with tempfile.TemporaryDirectory() as tmp:
   report=write_export(c,Path(tmp),'page_limit');self.assertTrue(report['page_limit_reached']);self.assertFalse(report['live_store_verified']);self.assertEqual(len(json.loads((Path(tmp)/report['import_files'][0]).read_text())['products']),1)
 def test_url_scope_and_inherited_proxy(self):
  import contextlib,io
  with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):options(['--supplier','maxi','--url','https://example.com'])
  self.assertEqual(choose_proxy({'HTTPS_PROXY':'http://proxy:8080'}),{'server':'http://proxy:8080'})
  self.assertIsNone(choose_proxy({}))
