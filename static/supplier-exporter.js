/* Run locally as a bookmark on a store page. No cookies, passwords, or requests are read/sent. */
(()=>{
 const host=location.hostname;
 const supplier=/^(www\.)?maxi\.rs$/.test(host)?'Maxi':/^(www\.)?mojapijaca\.rs$/.test(host)?'Moja Pijaca':host==='cchbcshop.com'?'Coca-Cola':null;
 if(!supplier){alert('Open a Maxi, Moja Pijaca or Coca-Cola HBC product/category page first.');return;}
 const products=[],seen=new Set();
 function add(p){
  const name=String(p.name||'').trim();let href='';
  try{if(p.url)href=new URL(p.url,location.href).href;}catch{}
  const sku=String(p.sku||p.productID||'').trim();
  if(!name||(!sku&&!href))return;
  const key=sku||href;if(seen.has(key))return;seen.add(key);
  let image=p.image||'';if(Array.isArray(image))image=image[0]||'';if(typeof image==='object')image=image.url||image.contentUrl||'';
  if(image){try{image=new URL(image,location.href).href}catch{image=''}}
  let offer=p.offers||{};if(Array.isArray(offer))offer=offer[0]||{};
  products.push({name,sku,url:href,image,price:offer.price??null,currency:offer.priceCurrency||'',category:p.category||'',unit:p.unit||'kom'});
 }
 function walk(v){if(Array.isArray(v)){v.forEach(walk);return;}if(!v||typeof v!=='object')return;const types=[v['@type']].flat();if(types.includes('Product'))add(v);else Object.values(v).forEach(walk);}
 document.querySelectorAll('script[type="application/ld+json"]').forEach(el=>{try{walk(JSON.parse(el.textContent))}catch{}});
 // Conservative fallback: only explicit product links with visible product headings or image labels.
 if(!products.length)document.querySelectorAll('a[href]').forEach(a=>{
  let u;try{u=new URL(a.href)}catch{return;}
  if(u.hostname!==host||!(/\/(p|product|proizvod)\//.test(u.pathname)))return;
  const box=a.closest('[itemtype*="Product"],[data-product-id],article,li,.product-item')||a;
  const heading=box.querySelector('[itemprop="name"],h2,h3,h4');
  const image=box.querySelector('img');const name=(heading?.textContent||a.getAttribute('title')||image?.getAttribute('alt')||a.textContent).trim();
  if(!name||name.length>250)return;
  const sku=box.getAttribute('data-product-id')||box.querySelector('[itemprop="sku"]')?.textContent||(/\/p\/([^/]+)$/.exec(u.pathname)||[])[1]||'';
  add({name,sku,url:u.href,image:image?.currentSrc||image?.src||''});
 });
 if(!products.length){alert('No product records found on this page. The store may require a specific connector or a CSV export. No file was created.');return;}
 const result={schema:'office-pantry-supplier-v1',supplier,page:location.href,exported_at:new Date().toISOString(),products};
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));a.download=supplier.toLowerCase().replaceAll(' ','-')+'-products.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);
 alert(`Exported ${products.length} product records from this page. Import the JSON into Office Pantry and review the names, SKUs and quantities. This is not a full-store sync.`);
})();
