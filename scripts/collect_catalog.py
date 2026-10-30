#!/usr/bin/env python3
"""Local, read-only browser catalogue collector. Site-specific coverage is unverified.

Requires the optional collector venv. The CRM itself still needs only Python.
Browser login stays in a separate local profile; no passwords/cookies are exported.
"""
import argparse
import asyncio
import base64
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

ROOT=Path(__file__).resolve().parents[1]
STORES={
 'maxi':dict(name='Maxi',host='maxi.rs',start='https://www.maxi.rs/'),
 'moja':dict(name='Moja Pijaca',host='mojapijaca.rs',start='https://www.mojapijaca.rs/'),
 'coca':dict(name='Coca-Cola',host='cchbcshop.com',start='https://cchbcshop.com/websiteRS/sr/c/Products?query=:relevance:allCategories:Products:')}
SENSITIVE=re.compile(r'^(utm_.*|fbclid|gclid|token|access_token|auth|session|sessionid|key)$',re.I)

def clean_url(value,base):
 try:
  p=urlparse(urljoin(base,str(value or '')))
  if p.scheme!='https' or not p.hostname or p.username or p.password:return ''
  query=urlencode([(k,v) for k,v in parse_qsl(p.query) if not SENSITIVE.match(k)])
  return urlunparse((p.scheme,p.netloc,p.path,p.params,query,''))
 except ValueError:return ''

def own_url(value,store):
 try:
  host=urlparse(value).hostname or ''
  return urlparse(value).scheme=='https' and (host==store['host'] or host.endswith('.'+store['host']))
 except ValueError:return False

def text(value):
 if isinstance(value,dict):value=value.get('rendered','')
 return html.unescape(re.sub(r'<[^>]+>','',str(value or ''))).strip()

def image_url(value,base):
 if isinstance(value,list):
  # SAP Commerce commonly exposes a zoom image alongside thumbnail variants.
  value=sorted(value,key=lambda x:0 if isinstance(x,dict) and x.get('format') in ('zoom','superZoom','product') else 1)
  value=value[0] if value else ''
 if isinstance(value,dict):value=value.get('url') or value.get('src') or value.get('contentUrl') or ''
 return clean_url(value,base) if value else ''

def product_from_object(obj,base,store,product_context=False):
 """Recognise Schema.org, SAP Commerce and WooCommerce-like product records."""
 if not isinstance(obj,dict):return None
 kind=obj.get('@type') or [];kind=[kind] if isinstance(kind,str) else kind
 href=clean_url(obj.get('url') or obj.get('permalink') or '',base)
 sku=str(obj.get('sku') or obj.get('code') or obj.get('productID') or '').strip()
 name=text(obj.get('name') or obj.get('title'))
 markers=any(k in obj for k in ('images','image','price','offers','prices'))
 explicit='Product' in kind or bool(obj.get('sku')) or (markers and bool(obj.get('permalink') or re.search(r'/(p|product|proizvod)/',href)))
 if not name or len(name)>500 or not (explicit or (product_context and markers)):return None
 if not sku and obj.get('id') is not None and (product_context or explicit):sku=str(obj['id'])
 # A code alone is valid; never substitute a category/page URL as a product URL.
 if href==clean_url(base,base) and not re.search(r'/(p|product|proizvod)/',urlparse(href).path):href=''
 if href and not own_url(href,store):href=''
 if not sku and not href:return None
 image=image_url(obj.get('image') or obj.get('images') or '',base)
 offers=obj.get('offers') or {}
 if isinstance(offers,list):offers=offers[0] if offers else {}
 price=obj.get('price');currency=obj.get('currency') or (offers.get('priceCurrency') if isinstance(offers,dict) else '') or ''
 if isinstance(price,dict):currency=price.get('currencyIso') or price.get('currency') or currency;price=price.get('value')
 if price is None and isinstance(offers,dict):price=offers.get('price')
 prices=obj.get('prices')
 if price is None and isinstance(prices,dict):
  try:price=float(prices['price'])/(10**int(prices.get('currency_minor_unit',2)));currency=prices.get('currency_code','')
  except (ValueError,TypeError,KeyError):price=None
 try:
  price=float(price) if price is not None else None
  if price is not None and (not 0<=price<=1e9 or str(currency).upper() not in ('','RSD')):price=None
 except (TypeError,ValueError):price=None
 # Unit and packaging need confirmation; no rate or stock is inferred here.
 return dict(name=name,sku=sku,url=href,image=image,price=price,currency='RSD' if price is not None else '',unit='kom',category='Прочее')

def extract_products(data,base,store):
 result=[];budget=100000
 def walk(v,context=False,depth=0):
  nonlocal budget
  budget-=1
  if budget<0 or depth>25:return
  if isinstance(v,list):
   for item in v:walk(item,context,depth+1)
  elif isinstance(v,dict):
   p=product_from_object(v,base,store,context)
   if p:result.append(p)
   else:
    for k,item in v.items():walk(item,context or k.lower() in ('products','product','results','items','itemlistelement','item'),depth+1)
 walk(data)
 return result

# This function executes in the browser, reads the DOM, and never clicks purchasing controls.
DOM_SCRIPT=r'''() => {
 const blocks=[];
 document.querySelectorAll('script[type="application/ld+json"]').forEach(el=>{try{blocks.push(JSON.parse(el.textContent))}catch{}});
 const cards=[];const links=[];
 document.querySelectorAll('a[href]').forEach(a=>{
  const href=a.href;const title=(a.getAttribute('aria-label')||a.textContent||'').trim();
  links.push({url:href,text:title.slice(0,150),next:a.rel==='next'});
  if(!/\/(p|product|proizvod)\//.test(a.pathname))return;
  const box=a.closest('[itemtype*="Product"],[data-product-id],article,li,.product-item')||a;
  const img=box.querySelector('img');const head=box.querySelector('[itemprop="name"],h2,h3,h4');
  const name=(head?.textContent||a.getAttribute('title')||img?.alt||a.textContent||'').trim();
  if(name&&name.length<500)cards.push({'@type':'Product',name,url:href,image:img?.currentSrc||img?.src||'',sku:box.getAttribute('data-product-id')||box.querySelector('[itemprop="sku"]')?.textContent||''});
 });
 const buttons=[...document.querySelectorAll('button,[role="button"]')].map((b,i)=>({i,text:(b.getAttribute('aria-label')||b.textContent||'').trim(),disabled:b.disabled||b.getAttribute('aria-disabled')==='true'}));
 return {blocks,cards,links,buttons};
}'''
NEXT_TEXT=re.compile(r'^(next(?: page)?|slede[ćc]a(?: stranica)?|naredna(?: stranica)?|load more|show more|prika[žz]i jo[šs]|u[čc]itaj jo[šs]|следующая(?: страница)?|далее|показать ещё|[›»→])$',re.I)
CATEGORY=re.compile(r'/(c|category|categories|kategorija|kategorije|product-category)/',re.I)
DETAIL=re.compile(r'/(p|product|proizvod)/',re.I)

def next_links(snapshot,base,store):
 categories=[];details=[];pagination=[]
 for item in snapshot['links']:
  u=clean_url(item['url'],base)
  if not own_url(u,store):continue
  if item.get('next') or NEXT_TEXT.match(item.get('text','')):pagination.append(u)
  elif CATEGORY.search(urlparse(u).path):
   # Do not expand a site's combinatorial filter URLs.
   parts=urlparse(u);params=parse_qsl(parts.query)
   if any(k.lower() in ('filter','facet') or (k=='q' and v not in ('',':relevance','relevance')) for k,v in params):continue
   params=[(k,v) for k,v in params if k.lower()!='sort']
   categories.append(urlunparse((parts.scheme,parts.netloc,parts.path,parts.params,urlencode(params),'')))
  elif DETAIL.search(urlparse(u).path):details.append(u)
 return list(dict.fromkeys(pagination+categories+details))

def choose_proxy(environ):
 # Preserve the managed environment's supported proxy route if present.
 value=environ.get('HTTPS_PROXY') or environ.get('https_proxy') or environ.get('HTTP_PROXY') or environ.get('http_proxy')
 if not value:return None
 p=urlparse(value)
 result={'server':f'{p.scheme}://{p.hostname}:{p.port or 80}'}
 if p.username:result['username']=p.username
 if p.password:result['password']=p.password
 return result

class Collector:
 def __init__(self,store,max_pages=100,scroll_rounds=6,delay=1.5):
  self.store=store;self.max_pages=max_pages;self.scroll_rounds=scroll_rounds;self.delay=delay
  self.products={};self.url_keys={};self.page_records=[];self.tasks=set();self.seen=set();self.queue=[];self.interrupted=False
 def add(self,products,source):
  for p in products:
   key='sku:'+p['sku'].casefold() if p['sku'] else 'url:'+p['url']
   old_key=key if key in self.products else self.url_keys.get(p['url']) if p['url'] else None
   old=self.products.get(old_key)
   if old:
    # JSON/product responses are stronger sources than a label on a list card.
    if {'dom':1,'jsonld':2,'network':3}.get(source,0)>={'dom':1,'jsonld':2,'network':3}.get(old.get('source'),0):merged={**old,**{k:v for k,v in p.items() if v not in ('',None)}}
    else:merged={**p,**{k:v for k,v in old.items() if v not in ('',None)}}
    p=merged
    if old_key!=key:self.products.pop(old_key,None)
   p={**p,'source':source if not old or {'dom':1,'jsonld':2,'network':3}.get(source,0)>={'dom':1,'jsonld':2,'network':3}.get(old.get('source'),0) else old.get('source',source)}
   key='sku:'+p['sku'].casefold() if p['sku'] else 'url:'+p['url'];self.products[key]=p
   if p['url']:self.url_keys[p['url']]=key
 async def response(self,response):
  try:
   if response.status!=200 or not own_url(response.url,self.store):return
   if 'json' not in response.headers.get('content-type','').lower():return
   size=response.headers.get('content-length')
   if size and int(size)>15_000_000:return
   data=await response.json();self.add(extract_products(data,response.url,self.store),'network')
  except Exception:pass # A response failing to parse does not establish collection success.
 def listen(self,page):
  def callback(r):
   task=asyncio.create_task(self.response(r));self.tasks.add(task);task.add_done_callback(self.tasks.discard)
  page.on('response',callback)
 async def snapshot(self,page):
  for _ in range(self.scroll_rounds):
   await page.evaluate('window.scrollTo(0,document.documentElement.scrollHeight)');await page.wait_for_timeout(int(self.delay*1000))
  snap=await page.evaluate(DOM_SCRIPT)
  self.add(extract_products(snap['blocks'],page.url,self.store),'jsonld')
  self.add(extract_products(snap['cards'],page.url,self.store),'dom')
  if self.tasks:await asyncio.gather(*list(self.tasks),return_exceptions=True)
  return snap
 async def crawl(self,page,starts,checkpoint):
  self.queue=list(starts)
  while self.queue and len(self.page_records)<self.max_pages:
   target=self.queue.pop(0)
   if target in self.seen or not own_url(target,self.store):continue
   self.seen.add(target);before=len(self.products);record={'url':target,'status':'pending'}
   try:
    response=await page.goto(target,wait_until='domcontentloaded',timeout=45000)
    if response and response.status>=400:
     record.update(status='http_error',http_status=response.status)
    elif not own_url(page.url,self.store):record.update(status='redirected_outside_store')
    else:
     await page.wait_for_timeout(int(self.delay*1000));snap=await self.snapshot(page)
     record.update(status='visited',added=len(self.products)-before)
     for link in next_links(snap,page.url,self.store):
      if link not in self.seen and link not in self.queue:self.queue.append(link)
     # SPA pagination may be a button rather than an anchor. Only explicitly labelled next buttons are used.
     fingerprints=set()
     while len(self.page_records)+1<self.max_pages:
      nxt=next((b for b in snap['buttons'] if not b['disabled'] and NEXT_TEXT.match(b['text'])),None)
      if not nxt:break
      signature=hashlib.sha256(json.dumps([p.get('url') for p in snap['cards']],sort_keys=True).encode()).hexdigest()+str(len(self.products))
      if signature in fingerprints:break
      fingerprints.add(signature);count=len(self.products)
      await page.locator('button,[role="button"]').nth(nxt['i']).click(timeout=8000)
      await page.wait_for_timeout(int(self.delay*1000));snap=await self.snapshot(page)
      self.page_records.append(dict(url=clean_url(page.url,page.url),status='next_button',added=len(self.products)-count))
      for link in next_links(snap,page.url,self.store):
       if link not in self.seen and link not in self.queue:self.queue.append(link)
   except Exception as e:record.update(status='error',error=type(e).__name__)
   self.page_records.append(record);checkpoint(self)
   print(f'Страниц: {len(self.page_records)} / {self.max_pages}; товаров: {len(self.products)}; в очереди: {len(self.queue)}',flush=True)
   await page.wait_for_timeout(int(self.delay*1000))
  if self.tasks:await asyncio.gather(*list(self.tasks),return_exceptions=True)

def write_export(collector,out,status='partial',image_overrides=None):
 out.mkdir(parents=True,exist_ok=True)
 products=[dict(p,**({'image':image_overrides[p['image']]} if image_overrides and p['image'] in image_overrides else {})) for p in collector.products.values()]
 timestamp=dt.datetime.now(dt.timezone.utc).isoformat()
 # Keep each import below the CRM's request limit even when photos are embedded.
 chunks=[];chunk=[];size=0
 for p in products:
  item_size=len(json.dumps(p,ensure_ascii=False).encode())
  if chunk and (size+item_size>6_000_000 or len(chunk)>=4000):chunks.append(chunk);chunk=[];size=0
  chunk.append(p);size+=item_size
 if chunk:chunks.append(chunk)
 names=[]
 for i,part in enumerate(chunks,1):
  name=f'products-{i:03d}.json';temp=out/(name+'.tmp')
  temp.write_text(json.dumps(dict(supplier=collector.store['name'],collected_at=timestamp,products=part),ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(out/name);names.append(name)
 manifest=dict(supplier=collector.store['name'],status=status,live_store_verified=False,products=len(products),with_sku=sum(bool(p['sku']) for p in products),with_image=sum(bool(p['image']) for p in products),embedded_images=sum(p['image'].startswith('data:') for p in products),pages=collector.page_records,remaining_urls=len(collector.queue),page_limit_reached=bool(collector.queue and len(collector.page_records)>=collector.max_pages),import_files=names,updated_at=timestamp)
 (out/'report.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 return manifest

async def download_images(context,collector,out):
 images={};folder=out/'images';folder.mkdir(exist_ok=True)
 for index,p in enumerate(collector.products.values(),1):
  href=p['image']
  if not href or href in images:continue
  try:
   # Use browser requests for the same signed-in session. Redirects are bounded; credentials are not exported.
   response=await context.request.get(href,timeout=20000,max_redirects=3)
   if not response.ok:continue
   raw=await response.body()
   if len(raw)>1_000_000:continue
   if raw.startswith(b'\xff\xd8\xff'):mime,extension='image/jpeg','jpg'
   elif raw.startswith(b'\x89PNG\r\n\x1a\n'):mime,extension='image/png','png'
   elif raw.startswith(b'RIFF') and raw[8:12]==b'WEBP':mime,extension='image/webp','webp'
   else:continue
   digest=hashlib.sha256(raw).hexdigest();(folder/f'{digest}.{extension}').write_bytes(raw)
   images[href]='data:'+mime+';base64,'+base64.b64encode(raw).decode()
  except Exception:continue
  if index%20==0:print(f'Фото: сохранено {len(images)}',flush=True)
 return images

def options(argv=None):
 p=argparse.ArgumentParser(description='Read-only supplier catalogue collector. No full-coverage claim; inspect report.json.')
 p.add_argument('--supplier',choices=STORES,required=True);p.add_argument('--url',action='append',help='Category URL; repeat for several categories')
 p.add_argument('--max-pages',type=int,default=100);p.add_argument('--scroll-rounds',type=int,default=6);p.add_argument('--delay',type=float,default=1.5)
 p.add_argument('--images',action='store_true',help='Download and embed photos up to 1 MB each')
 p.add_argument('--no-pause',action='store_true',help='Do not wait for manual sign-in/consent');p.add_argument('--headless',action='store_true')
 p.add_argument('--output',type=Path);p.add_argument('--browser',help='Installed Chromium/Chrome executable')
 a=p.parse_args(argv)
 if not 1<=a.max_pages<=2000 or not 0<=a.scroll_rounds<=30 or not .5<=a.delay<=30:p.error('Use 1–2000 pages, 0–30 scroll rounds, delay 0.5–30 seconds')
 store=STORES[a.supplier]
 a.urls=[clean_url(u,u) for u in a.url] if a.url else [store['start']]
 if any(not own_url(u,store) for u in a.urls):p.error('Start URLs must use HTTPS and belong to the selected supplier')
 return a

async def main(argv=None):
 args=options(argv);store=STORES[args.supplier]
 try:from playwright.async_api import async_playwright
 except ImportError:raise SystemExit('Запустите scripts/collect_catalog.command или установите scripts/collector-requirements.txt в отдельное venv.')
 runtime=Path(os.environ.get('PANTRY_DATA_DIR',ROOT/'.runtime'))
 output=args.output or runtime/'collections'/f"{args.supplier}-{dt.datetime.now():%Y%m%d-%H%M%S}"
 profile=runtime/'collector-profiles'/args.supplier;profile.mkdir(parents=True,exist_ok=True,mode=0o700)
 if output.exists() and any(output.iterdir()):raise SystemExit('Папка результата не пуста. Выберите новую папку через --output.')
 collector=Collector(store,args.max_pages,args.scroll_rounds,args.delay)
 launch=dict(headless=args.headless,accept_downloads=False)
 proxy=choose_proxy(os.environ)
 if proxy:launch['proxy']=proxy
 if args.browser:launch['executable_path']=args.browser
 else:
  chrome=next((p/'Contents/MacOS/Google Chrome' for p in (Path('/Applications/Google Chrome.app'),Path.home()/'Applications/Google Chrome.app') if (p/'Contents/MacOS/Google Chrome').exists()),None)
  if chrome:launch['executable_path']=str(chrome)
 async with async_playwright() as playwright:
  try:context=await playwright.chromium.launch_persistent_context(str(profile),**launch)
  except Exception:raise SystemExit('Не удалось открыть браузер. Укажите --browser /путь/к/Chrome или установите Chromium командой python -m playwright install chromium в venv сборщика.')
  page=context.pages[0] if context.pages else await context.new_page();collector.listen(page)
  try:
   if not args.no_pause:
    await page.goto(args.urls[0],wait_until='domcontentloaded',timeout=45000)
    print('В браузере выберите адрес доставки, примите cookies и войдите в магазин, если нужно. Откройте нужную категорию.\nСкрипт не оформляет заказы. Пароль вводите только на сайте магазина.')
    await asyncio.to_thread(input,'Когда товары видны в браузере, нажмите Enter здесь: ')
    matching=[p for p in context.pages if own_url(p.url,store)]
    if matching and matching[-1]!=page:page=matching[-1];collector.listen(page)
    if re.search(r'/(?:cart|checkout|basket|login|signin|sign-in|my-account|account|order)(?:/|$)',urlparse(page.url).path,re.I):raise SystemExit('Открыта страница входа, аккаунта или корзины. Запустите сбор ещё раз и откройте категорию товаров перед Enter.')
    if own_url(page.url,store):args.urls=[clean_url(page.url,page.url),*args.urls[1:]]
   if collector.tasks:await asyncio.gather(*list(collector.tasks),return_exceptions=True)
   collector.products.clear();collector.url_keys.clear()
   await collector.crawl(page,args.urls,lambda c:write_export(c,output))
   images=await download_images(context,collector,output) if args.images else {}
   status='errors' if any(r['status'] in ('error','http_error','redirected_outside_store') for r in collector.page_records) else 'page_limit' if collector.queue else 'queue_exhausted'
   report=write_export(collector,output,status,images)
   if not report['products']:raise SystemExit('Товары не найдены. Сохранён report.json. Нужна настройка адаптера по фактической странице магазина.')
   print(f"Собрано {report['products']} товаров; фото: {report['with_image']}, скачано: {report['embedded_images']}.\nРезультат: {output}\nВ CRM импортируйте только products-*.json, не report.json. Полнота каталога автоматически не подтверждена.")
  except (KeyboardInterrupt,asyncio.CancelledError):
   write_export(collector,output,'interrupted');print(f'Сбор остановлен. Частичный результат: {output}')
  finally:await context.close()

if __name__=='__main__':
 try:asyncio.run(main())
 except KeyboardInterrupt:pass
