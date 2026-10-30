"""Supplier catalogue import. No remote requests, code execution, or credential collection."""
import base64
import csv
import hashlib
from html.parser import HTMLParser
import io
import json
import math
import re
from urllib.parse import urlparse, urlunparse, urljoin, parse_qsl, urlencode

SUPPLIERS={'Maxi':'https://www.maxi.rs','Moja Pijaca':'https://www.mojapijaca.rs','Coca-Cola':'https://cchbcshop.com'}
PAGES={**SUPPLIERS,'Maxi':'https://www.maxi.rs/Mlechni-proizvodi-i-jaja/c/02?q=%3Arelevance&sort=relevance','Coca-Cola':'https://cchbcshop.com/websiteRS/sr/c/Products?query=:relevance:allCategories:Products:'}
HOSTS={'Maxi':{'maxi.rs','www.maxi.rs'},'Moja Pijaca':{'mojapijaca.rs','www.mojapijaca.rs'},'Coca-Cola':{'cchbcshop.com'}}

def url(value,supplier,product=False):
    if not value:return ''
    value=str(value).strip()
    value=urljoin(SUPPLIERS[supplier],value)
    p=urlparse(value)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('URL must be HTTPS without credentials')
    if product and p.hostname.lower() not in HOSTS[supplier]:raise ValueError('Product URL must belong to the selected supplier')
    query=urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')])
    return urlunparse((p.scheme,p.netloc,p.path,p.params,query,''))

class StructuredHTML(HTMLParser):
    def __init__(self):super().__init__();self.capture=False;self.text=[];self.blocks=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script':self.capture=dict(attrs).get('type','').lower()=='application/ld+json';self.text=[]
    def handle_data(self,data):
        if self.capture:self.text.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.capture:
            try:self.blocks.append(json.loads(''.join(self.text)))
            except ValueError:pass
            self.capture=False

def walk(value):
    if isinstance(value,list):
        for item in value:yield from walk(item)
    elif isinstance(value,dict):
        kind=value.get('@type',[]);kind=[kind] if isinstance(kind,str) else kind
        if 'Product' in kind:yield value
        else:
            for v in value.values():yield from walk(v)

def normalise(row,supplier):
    if not isinstance(row.get('name'),str):raise ValueError('Invalid product name')
    name=row['name'].strip()
    if not name or len(name)>500:raise ValueError('Product name is missing or too long')
    # Supplier titles remain unchanged. A translated legacy name is never an official SKU.
    if any(ord(c)<32 for c in name):raise ValueError('Invalid product name')
    sku=str(row.get('sku',row.get('productID','')) or '').strip()[:150]
    href=url(row.get('url',''),supplier,True)
    if not sku and not href:raise ValueError('A supplier SKU or product URL is required')
    image=row.get('image','') or ''
    if isinstance(image,list):image=image[0] if image else ''
    if isinstance(image,dict):image=image.get('url',image.get('contentUrl',''))
    if isinstance(image,str) and image.startswith('data:'):
        match=re.fullmatch(r'data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)',image)
        if not match or len(image)>1_400_000:raise ValueError('Invalid embedded product photo')
        try:raw=base64.b64decode(match[2],validate=True)
        except ValueError:raise ValueError('Invalid embedded product photo')
        signatures={'image/png':raw.startswith(b'\x89PNG\r\n\x1a\n'),'image/jpeg':raw.startswith(b'\xff\xd8\xff'),'image/webp':raw.startswith(b'RIFF') and raw[8:12]==b'WEBP'}
        if not signatures[match[1]]:raise ValueError('Invalid embedded product photo')
    else:image=url(image,supplier)
    offer=row.get('offers',{})
    if isinstance(offer,list):offer=offer[0] if offer else {}
    if not isinstance(offer,dict):offer={}
    price=row.get('price',offer.get('price'))
    currency=str(row.get('currency',offer.get('priceCurrency','')) or '').upper()
    if price not in ('',None):
        try:price=float(str(price).replace(',','.'))
        except ValueError:raise ValueError('Invalid unit price')
        if not math.isfinite(price) or price<0 or price>1e9:raise ValueError('Invalid unit price')
        if currency not in ('','RSD'):raise ValueError('Only RSD prices are supported')
    else:price=None
    unit=str(row.get('unit','kom') or 'kom').strip()[:30]
    key=('sku:'+sku.casefold()) if sku else 'url:'+href
    return dict(supplier=supplier,name=name,sku=sku,url=href,image=image,price=price,currency='RSD' if price is not None else '',unit=unit,category=str(row.get('category') or 'Прочее')[:150],external_key=key)

def preview(content,format,supplier):
    if supplier not in SUPPLIERS:raise ValueError('Unknown supplier')
    if not isinstance(content,str) or len(content)>12_000_000:raise ValueError('Import file is too large')
    content=content.lstrip('\ufeff')
    if not content.strip():raise ValueError('No products found. Use a supplier CSV/JSON export or a page with Product JSON-LD.')
    if format=='csv':
        reader=csv.DictReader(io.StringIO(content),delimiter=';' if ';' in content.splitlines()[0] else ',')
        rows=list(reader)
    elif format=='json':
        data=json.loads(content)
        if isinstance(data,dict) and 'products' in data:rows=data['products']
        elif isinstance(data,list) and all(isinstance(x,dict) and 'name' in x and '@type' not in x for x in data):rows=data
        else:rows=list(walk(data))
    elif format=='html':
        parser=StructuredHTML();parser.feed(content);rows=list(walk(parser.blocks))
    else:raise ValueError('Use CSV, JSON or saved HTML with Product JSON-LD')
    if not isinstance(rows,list) or not rows:raise ValueError('No products found. Use a supplier CSV/JSON export or a page with Product JSON-LD.')
    if len(rows)>5000:raise ValueError('Import at most 5000 products at a time')
    result=[];errors=[];seen=set();seen_urls=set()
    for i,row in enumerate(rows,1):
        try:
            if not isinstance(row,dict):raise ValueError('Invalid product row')
            p=normalise(row,supplier)
            if p['external_key'] in seen or (p['url'] and p['url'] in seen_urls):continue
            seen.add(p['external_key']);seen_urls.add(p['url']);result.append(p)
        except (ValueError,TypeError) as e:errors.append(dict(row=i,error=str(e)))
    return dict(rows=result,errors=errors,total=len(rows))

def upsert(c,supplier,rows,stamp,log):
    if supplier not in SUPPLIERS:raise ValueError('Unknown supplier')
    if not isinstance(rows,list) or not 1<=len(rows)<=5000:raise ValueError('Select between 1 and 5000 products')
    normalised=[normalise(r,supplier) for r in rows];ids=[]
    for p in normalised:
        old=c.execute('SELECT id,data FROM supplier_catalog WHERE supplier=? AND external_key=?',(supplier,p['external_key'])).fetchone()
        if not old and p['url']:
            for candidate in c.execute('SELECT id,data FROM supplier_catalog WHERE supplier=?',(supplier,)):
                if json.loads(candidate['data']).get('url')==p['url']:
                    old=candidate
                    prior=json.loads(candidate['data'])
                    if not p['sku'] and prior.get('sku'):p['sku']=prior['sku'];p['external_key']=prior['external_key']
                    break
        p['imported_at']=stamp;p['source']='supplier_import'
        if old:
            id=old['id'];c.execute('UPDATE supplier_catalog SET external_key=?,data=? WHERE id=?',(p['external_key'],json.dumps(p,ensure_ascii=False),id))
        else:id=c.execute('INSERT INTO supplier_catalog(supplier,external_key,data) VALUES(?,?,?)',(supplier,p['external_key'],json.dumps(p,ensure_ascii=False))).lastrowid
        log(c,'update' if old else 'create','supplier_catalog',id,json.loads(old['data']) if old else None,p);ids.append(id)
    return ids
