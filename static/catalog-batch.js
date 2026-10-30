// Request-size limits are measured in UTF-8 bytes, including JSON structure.
export function importFiles(files){
  return [...files].filter(f=>/\.(json|csv|html?)$/i.test(f.name)&&!/^report\.json$/i.test(f.name)).sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));
}
export function mergeCatalogRows(rows){
  const result=[],keys=new Set(),urls=new Set();
  for(const row of rows){const key=row.external_key||(row.sku?'sku:'+row.sku.toLowerCase():'url:'+row.url);if(keys.has(key)||(row.url&&urls.has(row.url)))continue;keys.add(key);if(row.url)urls.add(row.url);result.push(row)}
  return result;
}
export function importBatches(rows,supplier,jobId,limit=8_000_000){
 const encoder=new TextEncoder(),base=encoder.encode(JSON.stringify({supplier,job_id:jobId,rows:[]})).byteLength;
 let bytes=base,part=[];const batches=[];
 for(const row of rows){const size=encoder.encode(JSON.stringify(row)).byteLength;if(base+size>limit)throw Error('Один товар превышает допустимый размер запроса');const extra=size+(part.length?1:0);if(part.length&&(bytes+extra>limit||part.length>=4000)){batches.push(part);part=[];bytes=base}bytes+=size+(part.length?1:0);part.push(row)}
 if(part.length)batches.push(part);return batches;
}
