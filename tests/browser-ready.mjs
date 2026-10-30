import http from 'node:http';
export async function waitForServer(url){
 for(let i=0;i<60;i++){
  const ready=await new Promise(resolve=>{const request=http.get(url,{agent:false},response=>{let text='';response.setEncoding('utf8');response.on('data',chunk=>text+=chunk);response.on('end',()=>{try{resolve(response.statusCode===200&&Array.isArray(JSON.parse(text).products))}catch{resolve(false)}});response.on('error',()=>resolve(false))});request.setTimeout(1000,()=>{request.destroy();resolve(false)});request.on('error',()=>resolve(false))});
  if(ready)return;
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw Error('Development server did not become ready');
}
