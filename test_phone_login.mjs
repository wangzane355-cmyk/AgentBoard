/* Browser-flow regressions using a fake DOM and fetch. No network or account is used. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('./static/phone-login.js',import.meta.url),'utf8');
const response=(status,body)=>({status,ok:status>=200&&status<300,json:async()=>body});

function browserFixture({language='zh-CN',fetch:fakeFetch}={}) {
  const nodes=new Map(),requests=[],destinations=[],storageWrites=[],timers=new Map();
  for(const id of ['pair-code','pair-device-name','pair-form','pair-error','pair-submit','pair-status','pair-language']) {
    nodes.set('#'+id,{
      value:'',disabled:false,hidden:false,textContent:'',dataset:{},
      addEventListener(type,handler){this[type]=handler;},
      focus(){this.focused=true;},setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}
    });
  }
  const get=id=>nodes.get('#'+id);
  const copied=['title','codeHelp','nameLabel','submit'].map(key=>key==='submit'?get('pair-submit'):{dataset:{pairCopy:key},textContent:''});
  get('pair-submit').dataset.pairCopy='submit';
  const document={documentElement:{},querySelector:selector=>nodes.get(selector),querySelectorAll:()=>copied};
  const context={
    document,navigator:{language},location:{replace:path=>destinations.push(path)},
    localStorage:{getItem:()=>null,setItem:(...args)=>storageWrites.push(args)},
    fetch:async(path,options)=>{requests.push({path,options});return fakeFetch(path,options,{get,requests});},
    AbortController,TypeError,
    setTimeout:(handler,ms)=>{timers.set(1,{handler,ms});return 1;},clearTimeout:id=>timers.delete(id)
  };
  vm.runInNewContext(source,context,{filename:'phone-login.js'});
  return {
    get,requests,destinations,storageWrites,timers,
    submit:()=>get('pair-form').onsubmit({preventDefault(){}}),
    expire:()=>{const pending=[...timers.values()];assert.equal(pending.length,1);assert.equal(pending[0].ms,15000);pending[0].handler();}
  };
}

function ready(fixture,code='1234 5678',name='My Android phone') {
  fixture.get('pair-code').value=code;fixture.get('pair-device-name').value=name;return fixture;
}
function assertRecovered(fixture) {
  for(const id of ['pair-submit','pair-code','pair-device-name'])assert.equal(fixture.get(id).disabled,false,id);
  assert.equal(fixture.timers.size,0);
}
function assertOnlySafeStorage(fixture) {
  assert.ok(fixture.storageWrites.every(([key])=>key==='agentboard.language'));
  assert.ok(fixture.requests.every(({path})=>!/[?]|1234|5678/.test(path)));
}

test('a consumed pairing code with no saved cookie stays on login and explains the remedy',async()=>{
  const f=ready(browserFixture({fetch:async path=>path==='/phone/pair'?response(200,{ok:true}):response(401,{error:'unauthorized'})}));
  await f.submit();
  assert.deepEqual(f.requests.map(item=>item.path),['/phone/pair','/phone/client']);
  assert.deepEqual(f.destinations,[]);
  assert.equal(f.get('pair-code').value,'');
  assert.equal(f.get('pair-device-name').value,'My Android phone');
  assert.equal(f.get('pair-error').hidden,false);
  assert.match(f.get('pair-error').textContent,/Cookie/);
  assert.match(f.get('pair-error').textContent,/Chrome/);
  assert.match(f.get('pair-error').textContent,/换新码/);
  assert.equal(f.get('pair-status').textContent,'');assertRecovered(f);assertOnlySafeStorage(f);
});

for(const envelope of [false,true])test('only a fresh 200 remote session redirects'+(envelope?' (data envelope)':''),async()=>{
  let pairSignal;
  const f=ready(browserFixture({fetch:async(path,options,{get})=>{
    assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');
    if(path==='/phone/pair'){
      pairSignal=options.signal;assert.equal(options.method,'POST');
      assert.deepEqual(JSON.parse(options.body),{code:'12345678',device_name:'My Android phone'});
      return response(200,{ok:true});
    }
    assert.equal(path,'/phone/client');assert.equal(options.method,'GET');assert.equal(options.signal,pairSignal);
    assert.equal(get('pair-code').value,'');assert.equal(get('pair-submit').disabled,true);
    assert.match(get('pair-status').textContent,/检查浏览器登录状态/);
    assert.match(get('pair-submit').textContent,/检查连接/);
    return response(200,envelope?{ok:true,data:{remote:true,device_id:'fixture'}}:{remote:true,device_id:'fixture'});
  }}));
  await f.submit();assert.deepEqual(f.destinations,['/']);assert.equal(f.get('pair-code').value,'');
  assert.match(f.get('pair-status').textContent,/连接已确认/);assertRecovered(f);assertOnlySafeStorage(f);
});

for(const client of [{remote:false},{remote:'true'},{data:{remote:false}}])test('an unconfirmed session cannot redirect: '+JSON.stringify(client),async()=>{
  const f=ready(browserFixture({fetch:async path=>path==='/phone/pair'?response(200,{ok:true}):response(200,client)}));
  await f.submit();assert.deepEqual(f.destinations,[]);assert.equal(f.get('pair-code').value,'');
  assert.match(f.get('pair-error').textContent,/Cookie/);assertRecovered(f);
});

test('a server verification failure does not claim that a cookie was saved or navigate',async()=>{
  const f=ready(browserFixture({fetch:async path=>path==='/phone/pair'?response(200,{ok:true}):response(503,{error:'temporary'})}));
  await f.submit();assert.deepEqual(f.destinations,[]);assert.equal(f.get('pair-code').value,'');
  assert.match(f.get('pair-error').textContent,/无法检查登录状态/);assertRecovered(f);
});

for(const failingStage of ['pair','client'])test('network failure during '+failingStage+' never reports success',async()=>{
  const f=ready(browserFixture({fetch:async path=>{
    if(path==='/phone/pair'&&failingStage==='client')return response(200,{ok:true});
    throw new TypeError('offline fixture');
  }}));
  await f.submit();assert.deepEqual(f.destinations,[]);assert.equal(f.get('pair-error').hidden,false);
  assert.match(f.get('pair-error').textContent,/连接中断或超时/);
  assert.equal(f.get('pair-code').value,failingStage==='client'?'':'1234 5678');
  if(failingStage==='client')assert.match(f.get('pair-error').textContent,/配对码可能已使用/);
  assertRecovered(f);
});

test('the shared deadline aborts session verification and restores the form',async()=>{
  const f=ready(browserFixture({fetch:async(path,options)=>{
    if(path==='/phone/pair')return response(200,{ok:true});
    return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{
      const error=new Error('deadline fixture');error.name='AbortError';reject(error);
    },{once:true}));
  }}));
  const pending=f.submit();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(f.requests.length,2);f.expire();await pending;
  assert.deepEqual(f.destinations,[]);assert.equal(f.get('pair-code').value,'');
  assert.match(f.get('pair-error').textContent,/超时/);assertRecovered(f);
});

for(const [language,expected] of [['zh-CN','我的手机'],['en','My phone']])test('blank device name falls back without modifying the input ('+language+')',async()=>{
  const f=ready(browserFixture({language,fetch:async path=>path==='/phone/pair'?response(200,{ok:true}):response(200,{remote:true})}),'1234 5678','  ');
  await f.submit();assert.equal(JSON.parse(f.requests[0].options.body).device_name,expected);
  assert.equal(f.get('pair-device-name').value,'  ');assert.deepEqual(f.destinations,['/']);assertOnlySafeStorage(f);
});

test('invalid codes and rejected pairing requests do not attempt a session check',async()=>{
  const invalid=ready(browserFixture({fetch:async()=>{throw Error('must not fetch');}}),'123');
  await invalid.submit();assert.equal(invalid.requests.length,0);assert.deepEqual(invalid.destinations,[]);
  const rejected=ready(browserFixture({fetch:async()=>response(400,{error:'EXPIRED_CODE'})}));
  await rejected.submit();assert.equal(rejected.requests.length,1);assert.deepEqual(rejected.destinations,[]);
  assert.equal(rejected.get('pair-code').value,'1234 5678');assert.equal(rejected.get('pair-error').textContent,'EXPIRED_CODE');assertRecovered(rejected);
});

test('language changes preserve code and device-name drafts without a network call',()=>{
  const f=ready(browserFixture({fetch:async()=>{throw Error('must not fetch');}}));
  f.get('pair-code').value='12345678';f.get('pair-code').selectionStart=8;
  f.get('pair-code').input({target:f.get('pair-code')});
  assert.equal(f.get('pair-code').value,'1234 5678');
  f.get('pair-language').onchange({target:{value:'en'}});
  assert.equal(f.get('pair-code').value,'1234 5678');assert.equal(f.get('pair-device-name').value,'My Android phone');
  assert.equal(f.requests.length,0);assertOnlySafeStorage(f);
});
