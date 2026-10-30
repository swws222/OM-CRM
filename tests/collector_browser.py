"""Offline integration: real Chromium, routed shop fixtures, no live supplier traffic."""
import asyncio
import base64
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.collect_catalog import Collector,STORES,write_export,download_images
import catalog

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aSc8AAAAASUVORK5CYII=')
class FixtureResponse:
 ok=True
 async def body(self):return PNG
class FixtureRequest:
 async def get(self,url,**kwargs):
  assert url=='https://www.maxi.rs/fixture.jpg'
  return FixtureResponse()
class ImageFixture:
 request=FixtureRequest()

async def main():
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  context=await browser.new_context()
  async def route(r):
   u=r.request.url
   if '/api/products' in u:
    body={'products':[{'code':'B2','name':'Original B 1L','url':'/p/B2','images':[{'url':'/fixture.jpg'}],'price':{'value':250,'currencyIso':'RSD'}}]}
    await r.fulfill(content_type='application/json',body=json.dumps(body))
   elif '/c/02?page=1' in u:
    await r.fulfill(content_type='text/html',body='<html><script>fetch("/api/products")</script><h1>Page two</h1></html>')
   elif '/c/02' in u:
    body='<html><script type="application/ld+json">'+json.dumps({'@type':'Product','sku':'A1','name':'Original A 250g','url':'https://www.maxi.rs/p/A1','image':'https://www.maxi.rs/fixture.jpg'})+'</script><a href="/c/02?page=1" rel="next">Next</a></html>'
    await r.fulfill(content_type='text/html',body=body)
   else:raise AssertionError('Unexpected fixture URL: '+u)
  await context.route('**/*',route)
  page=await context.new_page();collector=Collector(STORES['maxi'],max_pages=2,scroll_rounds=0,delay=.5);collector.listen(page)
  with tempfile.TemporaryDirectory() as temp:
   output=Path(temp)
   await collector.crawl(page,['https://www.maxi.rs/c/02'],lambda c:write_export(c,output))
   assert len(collector.products)==2,collector.products
   images=await download_images(ImageFixture(),collector,output)
   assert len(images)==1
   report=write_export(collector,output,'page_limit',images)
   imported=catalog.preview((output/report['import_files'][0]).read_text(),'json','Maxi')
   assert len(imported['rows'])==2 and not imported['errors'],imported
   assert all(p['image'].startswith('data:image/png;base64,') for p in imported['rows'])
   assert {p['sku'] for p in imported['rows']}=={'A1','B2'}
  await browser.close()
 print('Collector browser fixture passed: pagination, JSON-LD, product API, deduplication, downloaded portable photos, CRM import.')

asyncio.run(main())
