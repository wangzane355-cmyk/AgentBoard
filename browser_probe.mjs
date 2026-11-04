/* Exact local viewport evidence. Node 22+ built-ins and an installed Chromium browser. */
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const [browser,url,widthValue,heightValue,outputValue,profileValue]=process.argv.slice(2);
const width=Number(widthValue),height=Number(heightValue),output=resolve(outputValue),profile=resolve(profileValue);
if(typeof WebSocket!=='function')throw Error('Web checks require Node 22+ with built-in WebSocket');
if(new URL(url).hostname!=='127.0.0.1'||![width,height].every(n=>Number.isInteger(n)&&n>=320&&n<=2560))throw Error('Invalid local viewport request');
await mkdir(profile,{recursive:true});
const child=spawn(browser,['--headless=new','--no-first-run','--no-default-browser-check',
  '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],
  {windowsHide:true,stdio:['ignore','ignore','ignore']});
let socket,sequence=0;
const pending=new Map();
const abortPending=message=>{for(const entry of pending.values()){clearTimeout(entry.timer);entry.reject(Error(message));}pending.clear();};
child.on('error',error=>abortPending(error.message));
child.on('exit',()=>abortPending('Owned browser exited'));
async function call(method,params={}){
  const id=++sequence;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error(`Browser command timed out: ${method}`));},12000);
    pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));
  });
}
try{
  let port;
  for(let count=0;count<150;count++){
    try{port=Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);if(port)break;}catch{}
    if(child.exitCode!==null)throw Error('Owned browser failed to start');
    await delay(100);
  }
  if(!port)throw Error('Browser did not expose its owned local diagnostic port');
  const tabs=await (await fetch(`http://127.0.0.1:${port}/json/list`,{signal:AbortSignal.timeout(3000)})).json();
  const target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');
  if(!target)throw Error('Owned browser page unavailable');
  socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=()=>reject(Error('Cannot connect to owned browser'));});
  socket.onmessage=event=>{
    const message=JSON.parse(event.data),entry=pending.get(message.id);if(!entry)return;
    pending.delete(message.id);clearTimeout(entry.timer);
    if(message.error)entry.reject(Error(message.error.message));else entry.resolve(message.result);
  };
  socket.onclose=()=>abortPending('Browser connection closed');
  await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url});
  for(let count=0;count<100;count++){
    const ready=await call('Runtime.evaluate',{expression:'location.href === '+JSON.stringify(url)+' && document.readyState === "complete"',returnByValue:true});
    if(ready.result?.value)break;
    if(count===99)throw Error('Local page did not finish loading');
    await delay(100);
  }
  await call('Runtime.evaluate',{expression:'document.fonts.ready.then(()=>true)',awaitPromise:true,returnByValue:true});
  await delay(250);
  const evidence=await call('Runtime.evaluate',{expression:'JSON.stringify({width:innerWidth,height:innerHeight,scrollWidth:Math.max(document.documentElement.scrollWidth,document.body.scrollWidth),text:document.body.innerText})',returnByValue:true});
  if(evidence.exceptionDetails)throw Error('Cannot read rendered page evidence');
  const measurement=JSON.parse(evidence.result.value);
  const capture=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false,fromSurface:true});
  await writeFile(output,Buffer.from(capture.data,'base64'));
  await writeFile(output+'.json',JSON.stringify(measurement,null,2));
  console.log(JSON.stringify({width:measurement.width,height:measurement.height,scrollWidth:measurement.scrollWidth}));
}finally{
  if(socket?.readyState===WebSocket.OPEN){try{await call('Browser.close');}catch{}socket.close();}
  if(child.exitCode===null){await Promise.race([new Promise(resolve=>child.once('exit',resolve)),delay(1500)]);if(child.exitCode===null)child.kill();}
  abortPending('Browser probe completed');
}
