export function supplierName(value){
 const s=String(value||'').trim(),key=s.toLowerCase().replace(/\s*\(чек\)$/i,'').replace(/[\s_.-]+/g,'');
 return ({maxi:'Maxi',mojapijaca:'Moja Pijaca',denmark:'Denmark','денмарк':'Denmark',cocacola:'Coca-Cola'})[key]||s;
}
export function filterProducts(products,{supplier='',category='Все товары',search='',favorites=false,low=false}={}){
 const query=search.trim().toLocaleLowerCase();
 return products.filter(p=>(!supplier||supplierName(p.supplier)===supplierName(supplier))&&(category==='Все товары'||p.category===category)&&(!favorites||p.favorite)&&(!low||(p.observation?.kind==='level'&&p.observation.level<=2))&&[p.name,p.legacy_name,p.supplier_sku].some(v=>String(v||'').toLocaleLowerCase().includes(query)));
}
export function suppliersFor(products,presets=[]){return [...new Set([...presets,...products.map(p=>supplierName(p.supplier))])].filter(Boolean)}
export function categoriesFor(products,presets=[]){return [...new Set([...presets,...products.map(p=>p.category)])].filter(Boolean)}
