import {readFile,mkdir,writeFile,rm,copyFile} from 'node:fs/promises';
const root=new URL('../',import.meta.url);
const files=['index.html','app.js','app.css','data.js','player.js','client.js','manifest.webmanifest','icon.svg','LICENSE'];
const assets={};
for(const file of files)assets['/'+file]=await readFile(new URL('web/'+file,root),'utf8');
let data=await readFile(new URL('web/data.js',root),'utf8');
let api=await readFile(new URL('worker/api.js',root),'utf8');
api=api.replace(/^import .*;\n/,'');
const code=`${data}\n${api}\nconst assets=${JSON.stringify(assets)};\n`+`
const types={html:'text/html; charset=utf-8',js:'text/javascript; charset=utf-8',css:'text/css; charset=utf-8',svg:'image/svg+xml',webmanifest:'application/manifest+json'};
export default {async fetch(request,env){
 const path=new URL(request.url).pathname;
 if(path.startsWith('/api/'))return api(request,env);
 if(!['GET','HEAD'].includes(request.method))return json({error:'지원하지 않는 요청입니다.'},405);
 if(path==='/health')return json({ok:true,version:'1.2.0'});
 const key=path==='/'?'/index.html':path;
 if(!Object.hasOwn(assets,key))return new Response('요청한 화면이 없습니다.',{status:404,headers:{'Content-Type':'text/plain; charset=utf-8'}});
 return new Response(request.method==='HEAD'?null:assets[key],{headers:{'Content-Type':types[key.split('.').pop()]||'text/plain; charset=utf-8','Cache-Control':'no-cache','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin','Permissions-Policy':'camera=(), microphone=()','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"}});
}};
`;
await rm(new URL('dist',root),{recursive:true,force:true});
await mkdir(new URL('dist/server',root),{recursive:true});
await mkdir(new URL('dist/.openai',root),{recursive:true});
await writeFile(new URL('dist/server/index.js',root),code);
await copyFile(new URL('.openai/hosting.json',root),new URL('dist/.openai/hosting.json',root));
console.log('Worker 빌드 완료');
