import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
const main = await readFile(new URL('../code.js', import.meta.url),'utf8');
const html = await readFile(new URL('../ui.html', import.meta.url),'utf8');
const uiCode = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function harness(shared = new Map()) {
  const events = {}, intervals = [], timeouts = new Map(), calls = [], elements = new Map();
  const uploadWaiters = [];
  let timerId = 0, sequence = 0, revision = 0, offline = false, acknowledgedThenLost = false, pagesLoaded = false;
  const elem = id => {
    if (!elements.has(id)) elements.set(id,{hidden:false,dataset:{},value:'',textContent:'',disabled:false});
    return elements.get(id);
  };
  const root={id:'0:0',name:'Demo',type:'DOCUMENT',getPluginData:()=> 'local',setPluginData:()=>{}};
  const page={id:'0:1',name:'Page',type:'CANVAS',parent:root};
  const text={id:'1:1',name:'Label',type:'TEXT',characters:'Before',fontName:Symbol('mixed'),fontSize:14,x:1,y:2,width:100,height:20,parent:page,getStyledTextSegments:()=>[{characters:text.characters,fontSize:14}]};
  page.children=[text]; root.children=[page];
  const nodes=new Map([[root.id,root],[page.id,page],[text.id,text]]);
  let ui, editor;
  const sendUI=message => ui.window.onmessage({source:ui.parent,origin:'null',data:{pluginMessage:message}});
  const figma={root,fileKey:'FILE123',showUI:()=>{},loadAllPagesAsync:async()=>{pagesLoaded=true;},on:(name,fn)=>{assert.equal(pagesLoaded,true);events[name]=fn;},
    getNodeByIdAsync:async id=>nodes.get(id)||null,
    clientStorage:{getAsync:async key=>structuredClone(shared.get(key)),setAsync:async(key,value)=>shared.set(key,structuredClone(value)),deleteAsync:async key=>shared.delete(key)},
    ui:{postMessage:message=>queueMicrotask(()=>sendUI(message))}};
  editor=vm.createContext({figma,__html__:'',setTimeout,clearTimeout,console});
  vm.runInContext(main,editor);
  const parent={postMessage:message=>queueMicrotask(()=>figma.ui.onmessage(message.pluginMessage))}; parent.parent=parent;
  const window={onmessage:null,addEventListener:()=>{}};
  ui=vm.createContext({parent,window,document:{getElementById:elem},URL,Blob,Response,CompressionStream,AbortSignal,Intl,Date,Math,Map,Promise,console,
    setInterval:(fn,ms)=>intervals.push({fn,ms}),
    setTimeout:(fn,ms)=>{const id=++timerId;timeouts.set(id,{fn,ms});return id;}, clearTimeout:id=>timeouts.delete(id),
    fetch:async(url,options)=>{
      const path=new URL(url).pathname.replace('/api/figma-plugin','');
      const compressed=options.headers['Content-Type']==='application/gzip';
      const body=JSON.parse(compressed ? gunzipSync(new Uint8Array(await options.body.arrayBuffer())).toString('utf8') : options.body);
      calls.push({path,body,compressed});
      if (path === '/changes') for (const resolve of uploadWaiters.splice(0)) resolve(calls.at(-1));
      if(offline) throw new Error('offline');
      if(path==='/pair') return {ok:true,json:async()=>({token:'moeum_figma_plugin_test',project_name:'Demo'})};
      if(path==='/resume') return {ok:true,json:async()=>({last_sequence:sequence,revision})};
      const duplicate=body.sequence<=sequence;
      if(!duplicate){sequence=body.sequence;revision++;}
      if(acknowledgedThenLost){acknowledgedThenLost=false;throw new Error('response lost');}
      return {ok:true,json:async()=>({last_sequence:sequence,revision,duplicate,received_at:new Date().toISOString()})};
    }});
  vm.runInContext(uiCode,ui);
  const drain=async()=>{for(let i=0;i<30;i++) await new Promise(resolve=>setImmediate(resolve));};
  return {calls,elements,nodes,text,page,events,shared,intervals,timeouts,drain,
    nextUpload:()=>new Promise(resolve=>uploadWaiters.push(resolve)),
    async pair(){await drain();elem('code').value='pair-code';elem('file-url').value='https://www.figma.com/design/FILE123/Test';await elem('pair-form').onsubmit({preventDefault(){}});await drain();},
    async tick(){await intervals.find(i=>i.ms===5000).fn();await drain();},
    async retry(){const entry=[...timeouts].find(([,t])=>t.ms<10000);assert.ok(entry,'automatic retry scheduled');timeouts.delete(entry[0]);await entry[1].fn();await drain();},
    set offline(value){offline=value;},set loseResponse(value){acknowledgedThenLost=value;},
    change(changes=[{id:'1:1',type:'PROPERTY_CHANGE',properties:['characters']}]){events.documentchange({documentChanges:changes});}};
}

test('pair persists credentials; edits batch at five seconds, reopen resumes without pairing',async()=>{
  const h=harness();await h.pair();
  assert.equal(h.calls.filter(c=>c.path==='/snapshot').length,1);
  assert.equal(h.calls.find(c=>c.path==='/snapshot').body.document.children[0].children[0].style.segments[0].fontSize,14);
  const saved=[...h.shared.values()][0];assert.equal(saved.session.token,'moeum_figma_plugin_test');
  h.text.characters='After';h.change();await h.drain();
  assert.equal(h.calls.filter(c=>c.path==='/changes').length,0);
  await h.tick();
  const delta=h.calls.find(c=>c.path==='/changes');assert.ok(delta);
  assert.equal(delta.body.upserts.find(n=>n.id==='1:1').characters,'After');
  assert.equal(delta.body.document,undefined);
  const reopened=harness(h.shared);await reopened.drain();
  assert.equal(reopened.calls.filter(c=>c.path==='/pair').length,0);
  assert.ok(reopened.calls.some(c=>c.path==='/resume'));
  assert.ok(reopened.calls.some(c=>c.path==='/snapshot'));
});

test('frame creation/deletion, text, fills and size use node deltas without repeated snapshots',async()=>{
  const h=harness();await h.pair();
  const frame={id:'2:1',name:'Frame',type:'FRAME',children:[],parent:h.page,x:0,y:0,width:300,height:200};
  h.nodes.set(frame.id,frame);h.page.children.push(frame);h.change([{id:frame.id,type:'CREATE'}]);await h.tick();
  let batch=h.calls.filter(c=>c.path==='/changes').at(-1).body;
  assert.ok(batch.upserts.some(n=>n.id===frame.id));
  h.text.fills=[{type:'SOLID',color:{r:1,g:0,b:0}}];h.text.width=200;h.change();await h.tick();
  batch=h.calls.filter(c=>c.path==='/changes').at(-1).body;
  assert.deepEqual(batch.upserts.find(n=>n.id==='1:1').size,[200,20]);
  h.nodes.delete(frame.id);h.page.children.pop();h.change([{id:frame.id,type:'DELETE'}]);await h.tick();
  batch=h.calls.filter(c=>c.path==='/changes').at(-1).body;assert.ok(batch.deleted.includes(frame.id));
  assert.equal(h.calls.filter(c=>c.path==='/snapshot').length,1);
});

test('network failure retries the identical durable sequence, including a lost acknowledgement',async()=>{
  const h=harness();await h.pair();h.offline=true;h.text.characters='offline';h.change();await h.tick();
  const first=[...h.shared.values()][0].pending.body;
  assert.ok([...h.shared.values()][0].pending);
  h.offline=false;h.loseResponse=true;await h.retry();await h.retry();
  const sent=h.calls.filter(c=>c.path==='/changes');assert.equal(sent.length,2);
  assert.ok(sent.every(c=>c.body.sequence===first.sequence));
  assert.equal([...h.shared.values()][0].pending,null);
});

test('large Korean node batches retain their text through gzip',{timeout:10000},async()=>{
 const h=harness();await h.pair();const sent=h.nextUpload();h.text.characters='디자인 수정 '.repeat(20000);h.change();await h.tick();
 const call=await sent;assert.equal(call.compressed,true);
 assert.equal(call.body.upserts.find(n=>n.id==='1:1').characters,h.text.characters);
});
