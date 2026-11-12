import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir,mkdtemp,chmod} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const run=promisify(execFile), dir=await mkdtemp(tmpdir()+'/mo186-');
await mkdir(dir+'/.local/bin',{recursive:true});
const sha='a'.repeat(40), other='b'.repeat(40);
const good={state:'OPEN',isDraft:false,mergeable:'MERGEABLE',headRefOid:sha,statusCheckRollup:[]};
const review={thread:{activeRunId:null},recentRuns:[{runId:'r',ordinal:1,model:'claude-opus-5-5',status:'completed'}],items:[{type:'assistant_message',runId:'r',text:`CHECK: PASS ${sha}\nVERDICT: PASS`}]};
let fixture={head:good,review};
const fixturePath=dir+'/fixture.json', log=dir+'/calls.jsonl';
const stub=`#!/usr/bin/env node
const fs=require('fs'), a=process.argv.slice(2), f=JSON.parse(fs.readFileSync(process.env.MO_FIXTURE)), name=require('path').basename(process.argv[1]);
fs.appendFileSync(process.env.MO_LOG,JSON.stringify([name,...a])+'\\n');
if(name==='gh'){if(a[0]!=='pr'||a[1]!=='view')process.exit(90); console.log(JSON.stringify(f.head));}
else if(name==='empq'){if(a[0]!=='start')process.exit(91); if(f.queueError)process.exit(4); console.log(f.ambiguous?'unexpected reply':'queued #7');}
else {const t=a[1], q=JSON.parse(a[2]); if(t==='t3_thread_read')console.log(JSON.stringify(f.review)); else if(t==='t3_project_list')console.log(JSON.stringify({projects:f.noProject?[]:[{id:'p',title:'mac-ops',workspaceRoot:'/repos/mac-ops'}]})); else if(t==='t3_thread_list')console.log(JSON.stringify({threads:q.statuses.includes('running')?[{threadId:'one',title:'MO-186 work',projectId:'p',status:'running',updatedAt:new Date().toISOString(),createdAt:new Date().toISOString()},{threadId:'two',title:'MO-187 work',projectId:'p',status:'waiting',updatedAt:new Date().toISOString(),createdAt:new Date().toISOString()}]:[]})); else if(t==='t3_pending_request'){if(q.threadId==='one')process.exit(3);console.log(JSON.stringify(q.action==='list'?{requestIds:['q']}:{question:'Need answer'}));} else process.exit(92);}
`;
for(const name of ['gh','empq','.local/bin/t3mcp']){await writeFile(dir+'/'+name,stub);await chmod(dir+'/'+name,0o700);}
const calls=[];
globalThis.probe={home:()=>dir,readTextFile:async()=>null,exec:async(file,args)=>{calls.push([file,args]);try{return {code:0,...await run(file,args,{env:{...process.env,PATH:dir+':'+process.env.PATH,MO_FIXTURE:fixturePath,MO_LOG:log}})};}catch(e){return {code:e.code,stdout:e.stdout??'',stderr:e.stderr??''};}}};
const source=(await readFile('empryo/mods/cockpit/hub.js','utf8')).replace(/import \{[^}]+\} from "herdr";/,'const {exec,home,readTextFile}=globalThis.probe;');
const hub=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const card={key:'MO-186',task:'MO-186',info:{pr:{repo:'shyamsivakumar/mac-ops',number:131}},threads:[{key:'author'},{key:'review',review:true,kind:'done',at:1}]};
const save=()=>writeFile(fixturePath,JSON.stringify(fixture));await save();
const checks=[];
async function refuses(name,change,pattern,c=card){fixture=structuredClone({head:good,review});change(fixture);await save();const p=await hub.mergePlan(c);assert.match(p.refused,pattern);assert.equal((await hub.mergeThread(c,{sha})).queued,undefined);checks.push(name);}
await refuses('no PASS',f=>f.review.items[0].text='VERDICT: FAIL',/PASS/);
await refuses('non Opus',f=>f.review.recentRuns[0].model='gpt-6.1-sol',/claude-opus/);
await refuses('stale head',f=>f.head.headRefOid=other,/current head/);
await refuses('Ascend',()=>{},/Ascend/,{...card,info:{pr:{repo:'shyamsivakumar/omni',number:131}}});
await refuses('closed PR',f=>f.head.state='CLOSED',/open/);
await refuses('conflicting PR',f=>f.head.mergeable='CONFLICTING',/mergeable/);
await refuses('CHECK FAIL with PASS verdict',f=>f.review.items[0].text=`CHECK: FAIL ${sha}\nVERDICT: PASS`,/CHECK/);
await refuses('duplicate CHECK',f=>f.review.items[0].text=`CHECK: PASS ${sha}\nCHECK: PASS ${sha}\nVERDICT: PASS`,/CHECK/);
const newerReview = (f, status, text) => {
  f.review.recentRuns.unshift({runId:'new',ordinal:2,model:'claude-opus-5-5',status});
  f.review.items.push({type:'assistant_message',runId:'new',text});
};
await refuses('old PASS newest FAIL',f=>newerReview(f,'completed',`CHECK: FAIL ${sha}\nVERDICT: FAIL`),/VERDICT: PASS/);
await refuses('newest running with old PASS',f=>newerReview(f,'running',`CHECK: PASS ${sha}\nVERDICT: PASS`),/Review still running/);
await refuses('newest PASS stale CHECK',f=>newerReview(f,'completed',`CHECK: PASS ${other}\nVERDICT: PASS`),/current head/);
await refuses('newest run last message FAIL',f=>{newerReview(f,'completed',`CHECK: PASS ${sha}\nVERDICT: PASS`);f.review.items.push({type:'assistant_message',runId:'new',text:'VERDICT: FAIL'});},/VERDICT: PASS/);
fixture=structuredClone({head:good,review});
fixture.review.items[0].text='VERDICT: FAIL';
newerReview(fixture,'completed',`CHECK: PASS ${sha}\nVERDICT: PASS`);
fixture.review.recentRuns.reverse();
fixture.review.items.push({type:'assistant_message',runId:'r',text:'VERDICT: FAIL'});
await save();assert.equal((await hub.mergePlan(card)).sha,sha);checks.push('highest ordinal PASS accepted regardless of array order or other-run messages');
fixture=structuredClone({head:good,review});await save();assert.equal((await hub.mergePlan({...card,info:{pr:{repo:'shyamsivakumar/strategy-replay-workbench',number:131}}})).sha,sha);checks.push('SRW exact-head Opus CHECK permits missing agent check');
fixture=structuredClone({head:good,review});await save();
fixture.review.recentRuns[0].model='subscriptions/claude-opus-5-5';await save();assert.equal((await hub.mergePlan(card)).sha,sha);checks.push('subscription Opus route recognized');
const plan=await hub.mergePlan(card);assert.equal(plan.sha,sha);
let main=await readFile('empryo/mods/cockpit/main.js','utf8');
main=main.replace(/^import .*;\n/gm,'').replace('export default class Board extends View','class Board extends Object');
const Board=new Function('mergePlan','mergeThread','say','const ARM_FOR=4000, CONFIRM_GAP=400; return '+main.slice(main.indexOf('class Board')))(hub.mergePlan,hub.mergeThread,()=>{});
const board=Object.create(Board.prototype);board.guard=()=>false;board.reviewBlock=()=>null;board.refusalOf=()=>null;let result;board.merge=(groups,cx,seen)=>{result=hub.mergeThread(groups[0],plan);};
const cx={timer:{after:()=>{}},notify:()=>{}};const entry={col:'ready',key:'g:MO-186',group:card};
board.approve(entry,cx);assert.equal(result,undefined);board.armed.at-=500;board.approve(entry,cx);assert.equal((await result).text,'queued #7');
assert.equal((await hub.mergeThread(card,plan)).text,'queued #7');
const starts=calls.filter(([f])=>f==='empq');assert.equal(starts.length,1);const payload=JSON.parse(starts[0][1][1]);assert.equal(payload.projectId,'p');assert.equal(payload.taskType,'worker');assert.equal(payload.title,`MO-186 merge relay #131 ${sha.slice(0,8)}`);assert.ok(payload.message.includes(`gh pr merge 131 -R shyamsivakumar/mac-ops --squash --match-head-commit ${sha}`));checks.push('passing relay exact command','double press queues once','duplicate same head queues once');
const blocked=Object.create(Board.prototype);blocked.guard=()=>false;blocked.refusalOf=()=>null;blocked.reviewBlock=()=>'Review failed';
blocked.approve(entry,cx);assert.equal(blocked.armed,undefined);
blocked.reviewBlock=()=>null;blocked.refusalOf=()=>({text:'Queue outcome unknown',planned:false});blocked.approve(entry,cx);assert.equal(blocked.armed,undefined);
blocked.refusalOf=()=>({text:'Preflight refused',planned:true});blocked.approve(entry,cx);assert.equal(blocked.armed.kind,'approve');checks.push('blocked card does not arm','stored queue refusal does not arm','preflight refusal can retry confirmation');
const all=Object.create(Board.prototype);all.guard=(bound)=>{assert.equal(bound,false);return false;};all.layout={approvable:[{group:card}],nothing:''};let batches=0;all.merge=(groups)=>{assert.equal(groups.length,1);batches++;};all.approveAll(cx);assert.equal(batches,0);all.armed.at-=500;all.approveAll(cx);assert.equal(batches,1);checks.push('Approve all press twice dispatches one batch');
fixture=structuredClone({head:good,review});fixture.head.headRefOid='c'.repeat(40);fixture.review.items[0].text=`CHECK: PASS ${fixture.head.headRefOid}\nVERDICT: PASS`;fixture.noProject=true;await save();
const retryPlan=await hub.mergePlan(card);assert.match((await hub.mergeThread(card,retryPlan)).refused,/project/);
fixture.noProject=false;fixture.queueError=true;await save();assert.ok((await hub.mergeThread(card,retryPlan)).refused);
fixture.queueError=false;await save();const retried=await Promise.all([hub.mergeThread(card,retryPlan),hub.mergeThread(card,retryPlan)]);assert.ok(retried.every(r=>r.queued));
assert.equal(calls.filter(([f])=>f==='empq').length,3);checks.push('project lookup refusal can retry','nonzero queue failure can retry','concurrent same-head relay queues once');
fixture.head.headRefOid='d'.repeat(40);fixture.review.items[0].text=`CHECK: PASS ${fixture.head.headRefOid}\nVERDICT: PASS`;fixture.ambiguous=true;await save();
const uncertain=await hub.mergePlan(card);assert.match((await hub.mergeThread(card,uncertain)).refused,/unknown/);fixture.ambiguous=false;await save();assert.match((await hub.mergeThread(card,uncertain)).refused,/unknown/);assert.equal(calls.filter(([f])=>f==='empq').length,4);checks.push('ambiguous queue reply blocks duplicate retry');
const loaded=await hub.load();assert.equal(loaded.groups.flatMap(g=>g.threads).find(t=>t.key==='one').context,'pending request unknown');const lists=calls.filter(([f,a])=>f.endsWith('t3mcp')&&a[1]==='t3_pending_request'&&JSON.parse(a[2]).action==='list');assert.equal(lists.length,2);checks.push('pending failure isolated','one pending list per thread per load');
console.log(JSON.stringify({pass:true,checks,relay:payload,queueWrites:calls.filter(([f])=>f==='empq').length,liveMutations:0},null,2));
