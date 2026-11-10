import {initialData,validateData,changeData} from './data.js';
export const LEGACY_KEY='ttobak-mobile-v1';
const LOCAL_KEY='ttobak-guest-v1';
export class DataClient {
 constructor(fetcher=fetch,storage=localStorage){this.fetcher=fetcher.bind(globalThis);this.storage=storage;this.revision=0;this.data=initialData();this.cloud=false;}
 async request(path,body){
  let response;try{response=await this.fetcher(path,{cache:'no-store',credentials:'same-origin',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});}
  catch{throw new Error(globalThis.navigator?.onLine===false?'인터넷 연결이 끊겼어요. 입력은 유지됩니다. 연결 후 다시 시도해 주세요.':'서버 요청을 보내지 못했어요. 입력은 유지됩니다. 잠시 후 다시 시도해 주세요.');}
  let result;try{result=await response.json();}catch{throw new Error('서버 응답을 읽지 못했어요. 잠시 후 다시 시도해 주세요.');}
  if(!response.ok)throw new Error(result.error||'요청을 처리하지 못했어요.');return result;
 }
 async init(){
  const account=await this.request('/api/account');this.cloud=account.loggedIn;
  if(this.cloud)return this.reload();
  let raw;try{raw=this.storage.getItem(LOCAL_KEY)||this.storage.getItem(LEGACY_KEY);}catch{throw new Error('브라우저 저장 공간을 사용할 수 없어요. 일반 브라우저에서 열어 주세요.');}
  try{this.data=raw?validateData(JSON.parse(raw)):initialData();}catch{throw new Error('기존 자료를 읽지 못했어요. 저장 자료를 지우지 말고 백업 파일로 복구해 주세요.');}
  return this.data;
 }
 async reload(){if(!this.cloud)return this.data;const result=await this.request('/api/data');this.data=validateData(result.data);this.revision=result.revision;return this.data;}
 async change(action){
  if(this.cloud){const result=await this.request('/api/data',{revision:this.revision,action});this.data=validateData(result.data);this.revision=result.revision;return result.resultId;}
  const result=changeData(this.data,action);
  try{this.storage.setItem(LOCAL_KEY,JSON.stringify(result.data));}catch{throw new Error('기기에 저장하지 못했어요. 저장 공간을 확인해 주세요. 기존 기록은 유지됩니다.');}
  if(action.type==='account.clear'){try{this.storage.removeItem?.(LEGACY_KEY);this.storage.removeItem?.('ttobak-migrated');}catch{}}
  this.data=result.data;return result.resultId;
 }
 legacy(){try{const raw=this.storage.getItem(LOCAL_KEY)||this.storage.getItem(LEGACY_KEY);return raw?validateData(JSON.parse(raw)):null;}catch{return null;}}
}
