"use strict";

// All account identities and research notes below are synthetic test data.
const test = require("node:test");
const assert = require("node:assert/strict");
const {createHash, randomUUID} = require("node:crypto");
const {execFileSync} = require("node:child_process");
const path = require("node:path");
const Core = require("../site/assets/records-core.js");
const copy = (value) => JSON.parse(JSON.stringify(value));
const stamp = "2026-01-01T08:45:00Z";
const project = (suffix = "one", values = {}) => Object.assign({
  title:"Synthetic project " + suffix, url:"https://example.org/projects/" + suffix,
  source_id:"manual", source_issue_date:null
}, values);
const digest = (value) => createHash("sha256").update(value).digest("hex");

class SyntheticServer {
  constructor() { this.records = new Map(); this.receipts = new Map(); this.calls = []; this.failList = false; this.failBefore = false; this.loseResponse = false; this.pause = null; }
  forUser(user) {
    return {
      list: async (after) => {
        if (this.failList) throw new Error("synthetic offline");
        const records = [...this.records.values()].filter((row) => row.owner === user && (!after || row.id > after)).sort((a,b) => a.id.localeCompare(b.id));
        const page = records.slice(0,100).map((row) => { const value = copy(row); delete value.owner; return value; });
        return {records:page,next_after:records.length > 100 ? page.at(-1).id : null};
      },
      mutate: async (operation) => {
        this.calls.push(copy(operation));
        if (this.failBefore) throw new Error("synthetic offline");
        if (this.pause) await this.pause;
        const result = this.apply(user, operation);
        if (this.loseResponse) { this.loseResponse = false; throw new Error("synthetic response lost"); }
        return result;
      }
    };
  }
  apply(user, operation) {
    const receiptKey = user + ":" + operation.mutation_id;
    const requestDigest = digest(JSON.stringify({id:operation.record_id,operation:operation.operation,expected:operation.expected_version,payload:operation.payload}));
    const receipt = this.receipts.get(receiptKey);
    if (receipt) {
      assert.equal(receipt.digest, requestDigest, "stable mutation IDs must carry immutable requests");
      return {status:"applied",applied_version:receipt.version,record:this.publicRow(this.records.get(receipt.recordId))};
    }
    let row = this.records.get(operation.record_id);
    if (row && row.owner !== user) throw new Error("synthetic ownership rejection");
    if (operation.operation === "create") {
      const value = Core.validateProject(operation.payload, true);
      const urlKey = digest(value.canonical_url);
      const existing = [...this.records.values()].find((item) => item.owner === user && item.url_key === urlKey);
      if (existing) return {status:existing.deleted_at ? "deleted" : "existing",applied_version:existing.version,record:this.publicRow(existing)};
      row = Object.assign(value,{id:operation.record_id,url_key:urlKey,owner:user,version:1,created_at:stamp,updated_at:stamp,deleted_at:null});
      this.records.set(row.id,row);
    } else {
      if (!row) return {status:"deleted",record:null,applied_version:null};
      if (row.deleted_at && operation.operation !== "restore") return {status:"deleted",applied_version:row.version,record:this.publicRow(row)};
      if (operation.expected_version !== row.version) return {status:"conflict",applied_version:row.version,record:this.publicRow(row)};
      if (operation.operation === "delete") {
        for (const key of ["url","canonical_url","title","source_id","source_issue_date","notes"]) row[key] = null;
        row.deleted_at = stamp;
      } else if (operation.operation === "restore") {
        if (!row.deleted_at) return {status:"conflict",applied_version:row.version,record:this.publicRow(row)};
        Object.assign(row,Core.validateProject(operation.payload,true),{deleted_at:null});
      } else {
        const value = Core.validateProject(Object.assign({},row,operation.payload),false);
        Object.assign(row,value);
      }
      row.version += 1;
      row.updated_at = new Date(Date.parse(stamp)+row.version*1000).toISOString();
    }
    this.receipts.set(receiptKey,{digest:requestDigest,recordId:row.id,version:row.version});
    return {status:"applied",applied_version:row.version,record:this.publicRow(row)};
  }
  publicRow(row) { const value=copy(row); delete value.owner; return value; }
}
async function library(server = new SyntheticServer(), user = "synthetic-A", store = new Core.MemoryStore()) {
  const result = new Core.Library({store,transport:server.forUser(user)});
  await result.init();
  return result;
}

test("URL normalization matches conservative Python identity for ordinary public URLs", () => {
  const inputs = [
    "https://EXAMPLE.org:443/Path/?utm_source=test&b=two&a=one#Section",
    "http://EXAMPLE.org.:80", "https://example.org/A/../B", "https://example.org/x?a=1&&b=2",
    "https://example.org/x?%75tm_source=test&a=%2f#frag", "https://example.org/Path/?semantic=Case",
    "https://example.org:8443/path", "https://[2606:4700:4700::1111]/path"
  ];
  const code="import sys,json;sys.path.insert(0,sys.argv[1]);import xait;print(json.dumps([xait.canonical_public_url(x) for x in json.load(sys.stdin)]))";
  const expected=JSON.parse(execFileSync("python3",["-c",code,path.resolve(__dirname,"..")],{input:JSON.stringify(inputs),encoding:"utf8"}));
  assert.deepEqual(inputs.map(Core.normalizeUrl),expected);
});

test("URL validator rejects dangerous, credential-bearing and local addresses", () => {
  const values=["javascript:alert(1)","file:///tmp/example","https://user:pass@example.org/x","http://localhost/x","http://intranet/", "http://example.local/x", "http://127.0.0.1/", "http://127.1/", "http://0x7f000001/", "http://2130706433/", "http://192.168.1.1/", "http://100.64.1.1/", "http://169.254.2.1/", "http://[::1]/", "http://[fe80::1]/", "http://[2001:db8::1]/", "https://example.org/?%61uth=x", "https://example.org/?access_token=x", "https://example.org/?x_amz_signature=x", "https://example.org/path with space"];
  for(const value of values) assert.throws(()=>Core.normalizeUrl(value),Core.RecordsError,value);
  for(const value of ["https://example.org/#access_token=synthetic", "https://example.org/#/route?token=synthetic", "https://example.org/#%61pi_key%3Dsynthetic", "https://example.org/#token%253Dsynthetic", "https://example.org/?my_auth_value=synthetic", "https://example.org/#/code=synthetic", "http://[2002:808:808::1]/", "http://[3fff::1]/", "http://localtest.me/", "https://sub.lvh.me/", "http://safe.nip.io/", "http://safe.sslip.io/", "http://safe.xip.io/"]){
    assert.throws(()=>Core.normalizeUrl(value),Core.RecordsError,value);
  }
});

test("record validation checks Unicode bounds, source, dates and unknown backup fields", () => {
  assert.equal(Core.validateProject(project("emoji",{notes:"🎯".repeat(5000)})).notes.length,10000);
  assert.throws(()=>Core.validateProject(project("bad",{notes:"x".repeat(5001)})),/invalid_text/);
  assert.throws(()=>Core.validateProject(project("bad",{source_issue_date:"2026-02-30"})),/invalid_date/);
  assert.throws(()=>Core.validateProject(project("bad",{status:"unknown"})),/invalid_status/);
  assert.throws(()=>Core.validateProject(project("bad",{source_id:"old-social"})),/invalid_source/);
  assert.throws(()=>Core.validateProject(Object.assign(project(),{owner_id:"synthetic-B"}),true),/unknown_field/);
});

test("host spellings, padded ports and encoded controls rejected by SQL fail before local commit", async () => {
  const app=await library();
  for(const url of ["https://例子.example/", "https://example.org:000443/", "https://example.org/a`b", "https://bad_host.example/", "https://a..example.org/", "https://-bad.example.org/", "https://example.org/%00", "https://example.org/#%0D"]){
    await assert.rejects(app.saveProject(project("invalid",{url})),Core.RecordsError,url);
    assert.equal((await app.list()).length,0); assert.equal(await app.pendingCount(),0);
  }
  assert.equal(Core.normalizeUrl("https://example.org:00443/"),"https://example.org/");
  assert.equal(Core.normalizeUrl("https://xn--fsqu00a.example/"),"https://xn--fsqu00a.example/");
});

test("local save commits record and outbox atomically before reporting success", async () => {
  const store=new Core.MemoryStore(); const app=await library(undefined,undefined,store);
  store.failNext=true;
  await assert.rejects(app.saveProject(project()),/storage_unavailable/);
  assert.equal((await app.list()).length,0); assert.equal(await app.pendingCount(),0);
  const saved=await app.saveProject(project());
  assert.equal(saved.sync_state,"pending"); assert.equal(await app.pendingCount(),1);
  assert.equal((await store.read()).outbox[0].record_id,saved.id);
});

test("duplicate saves across issues keep existing notes, title, state and first source", async () => {
  const app=await library(); const row=await app.saveProject(project());
  await app.updateRecord(row.id,{notes:"Synthetic prior research",status:"watching"});
  const again=await app.saveProject(project("one",{title:"Changed source title",source_id:"github-trending",source_issue_date:"2026-01-02"}));
  assert.equal(again.id,row.id); assert.equal(again.title,row.title);
  assert.equal(again.notes,"Synthetic prior research"); assert.equal(again.status,"watching");
  assert.equal(again.source_id,"manual"); assert.equal(await app.pendingCount(),1);
});

test("successful synchronization acknowledges the cloud without duplicating saves", async () => {
  const server=new SyntheticServer(); const app=await library(server);
  const row=await app.saveProject(project()); await app.sync(); await app.sync();
  assert.equal(server.records.size,1); assert.equal(server.calls.length,1);
  const [saved]=await app.list(); assert.equal(saved.id,row.id); assert.equal(saved.version,1);
  assert.equal(saved.sync_state,"synced"); assert.equal(await app.pendingCount(),0);
});

test("failed write keeps stable immutable mutation ID and private draft", async () => {
  const server=new SyntheticServer(); const app=await library(server);
  const row=await app.saveProject(project()); server.failBefore=true;
  await assert.rejects(app.sync());
  const first=copy(server.calls[0]);
  await app.updateRecord(row.id,{notes:"Synthetic edit after first attempt"});
  server.failBefore=false; await app.sync();
  assert.deepEqual(server.calls[1],first);
  assert.equal(server.records.size,1);
  assert.equal((await app.list())[0].notes,"Synthetic edit after first attempt");
  assert.equal(await app.pendingCount(),0);
});

test("response lost after commit retries old operation before applying a newer edit", async () => {
  const server=new SyntheticServer(); const app=await library(server);
  const row=await app.saveProject(project()); server.loseResponse=true;
  await assert.rejects(app.sync());
  assert.equal(server.records.size,1);
  await app.updateRecord(row.id,{notes:"Synthetic later note",status:"tried"});
  await app.sync();
  assert.equal(server.calls[0].mutation_id,server.calls[1].mutation_id);
  assert.deepEqual(server.calls[0].payload,server.calls[1].payload);
  assert.equal(server.records.get(row.id).notes,"Synthetic later note");
  assert.equal(server.records.get(row.id).version,2);
});

test("lost acknowledgement plus a different device's newer edit cannot silently rebase a successor", async () => {
  const server=new SyntheticServer(), left=await library(server);
  const row=await left.saveProject(project()); await left.sync();
  await left.updateRecord(row.id,{notes:"Synthetic first edit"}); server.loseResponse=true;
  await assert.rejects(left.sync());
  await left.updateRecord(row.id,{notes:"Synthetic unsent successor"});
  const right=await library(server); await right.sync();
  await right.updateRecord(row.id,{notes:"Synthetic second device edit"}); await right.sync();
  assert.equal(server.records.get(row.id).version,3);
  await left.sync();
  const [conflict]=await left.list();
  assert.equal(conflict.sync_state,"conflict");
  assert.equal(conflict.notes,"Synthetic unsent successor");
  assert.equal(conflict.conflict.remote.notes,"Synthetic second device edit");
  assert.equal(server.records.get(row.id).notes,"Synthetic second device edit");
});

test("editing while a sent operation waits never mutates that operation", async () => {
  const server=new SyntheticServer(); const app=await library(server);
  const row=await app.saveProject(project());
  let release; server.pause=new Promise((resolve)=>{release=resolve;});
  const pending=app.sync();
  while(server.calls.length===0) await new Promise((resolve)=>setImmediate(resolve));
  const sent=copy(server.calls[0]);
  await app.updateRecord(row.id,{notes:"Synthetic in-flight edit"});
  assert.deepEqual(server.calls[0],sent);
  release(); server.pause=null; await pending;
  assert.equal(server.records.get(row.id).notes,"Synthetic in-flight edit");
  assert.equal(server.calls.length,2);
});

test("two devices editing the same record preserve both sides and require explicit resolution", async () => {
  const server=new SyntheticServer(), left=await library(server), right=await library(server);
  const row=await left.saveProject(project()); await left.sync(); await right.sync();
  await left.updateRecord(row.id,{notes:"Synthetic left note"}); await right.updateRecord(row.id,{notes:"Synthetic right note"});
  await left.sync(); await right.sync();
  const [conflict]=await right.list();
  assert.equal(conflict.sync_state,"conflict"); assert.equal(conflict.notes,"Synthetic right note");
  assert.equal(conflict.conflict.remote.notes,"Synthetic left note");
  await right.resolveConflict(row.id,"merge",{notes:"Synthetic merged note"}); await right.sync();
  assert.equal(server.records.get(row.id).notes,"Synthetic merged note");
});

test("accepting remote conflict does not overwrite cloud content", async () => {
  const server=new SyntheticServer(), left=await library(server), right=await library(server);
  const row=await left.saveProject(project()); await left.sync(); await right.sync();
  await right.updateRecord(row.id,{notes:"Synthetic right note"});
  await left.updateRecord(row.id,{notes:"Synthetic left note"}); await left.sync(); await right.sync();
  await right.resolveConflict(row.id,"remote");
  assert.equal((await right.list())[0].notes,"Synthetic left note");
  assert.equal(await right.pendingCount(),0);
});

test("delete clears private cloud fields and old offline edits cannot resurrect it", async () => {
  const server=new SyntheticServer(), left=await library(server), right=await library(server);
  const row=await left.saveProject(project()); await left.sync(); await right.sync();
  await right.updateRecord(row.id,{notes:"Synthetic offline survivor"});
  await left.removeRecord(row.id); await left.sync(); await right.sync();
  assert.equal(server.records.get(row.id).notes,null);
  const [conflict]=await right.list(); assert.equal(conflict.sync_state,"conflict");
  assert.equal(conflict.notes,"Synthetic offline survivor"); assert.ok(conflict.conflict.remote.deleted_at);
  await assert.rejects(right.resolveConflict(row.id,"local"),/restore_required/);
  await right.saveProject(project(),{restore:true}); await right.sync();
  assert.equal(server.records.get(row.id).notes,"Synthetic offline survivor");
  assert.equal(server.records.get(row.id).deleted_at,null);
});

test("fresh device recognizes remote tombstone by URL hash and requires restore", async () => {
  const server=new SyntheticServer(), left=await library(server);
  const row=await left.saveProject(project()); await left.sync(); await left.removeRecord(row.id); await left.sync();
  const fresh=await library(server); await fresh.sync();
  await assert.rejects(fresh.saveProject(project()),/restore_required/);
  await fresh.saveProject(project(),{restore:true}); await fresh.sync();
  assert.equal(server.records.size,1); assert.equal((await fresh.list())[0].id,row.id);
});

test("removing a never-sent offline create performs no cloud operation", async () => {
  const server=new SyntheticServer(), app=await library(server);
  const row=await app.saveProject(project()); await app.removeRecord(row.id); await app.sync();
  assert.equal((await app.list()).length,0); assert.equal(server.calls.length,0);
});

for(const delivered of [false,true]) test("explicit restore reconciles attempted create " + (delivered ? "after a lost acknowledgement" : "that never reached the server"), async () => {
  const server=new SyntheticServer(), app=await library(server);
  const row=await app.saveProject(project());
  await app.updateRecord(row.id,{notes:"Synthetic note retained through restore",status:"watching"});
  server.failBefore=!delivered; server.loseResponse=delivered;
  await assert.rejects(app.sync());
  const first=copy(server.calls[0]);
  await app.removeRecord(row.id);
  await assert.rejects(app.saveProject(project()),/restore_required/);
  const restored=await app.saveProject(project(),{restore:true});
  assert.equal(restored.notes,"Synthetic note retained through restore");
  assert.deepEqual((await app.store.read()).outbox.map((op)=>op.operation),["create","update"]);
  server.failBefore=false; await app.sync();
  assert.deepEqual(server.calls[1],first,"the original attempted request is retried without changing its identity or payload");
  assert.equal(server.records.get(row.id).notes,"Synthetic note retained through restore");
  assert.equal(server.records.get(row.id).status,"watching");
  assert.equal(server.records.get(row.id).deleted_at,null);
  assert.equal(server.records.get(row.id).version,2);
  assert.equal((await app.list())[0].sync_state,"synced"); assert.equal(await app.pendingCount(),0);
});

test("explicit restore cancels an unsent delete of an existing cloud row", async () => {
  const server=new SyntheticServer(), app=await library(server);
  const row=await app.saveProject(project()); await app.sync();
  await app.updateRecord(row.id,{notes:"Synthetic note before cancelled delete"});
  await app.removeRecord(row.id); await app.saveProject(project(),{restore:true}); await app.sync();
  assert.deepEqual(server.calls.map((op)=>op.operation),["create","update"]);
  assert.equal(server.records.get(row.id).notes,"Synthetic note before cancelled delete");
  assert.equal(server.records.get(row.id).deleted_at,null);
});

test("explicit restore behind an in-flight delete preserves that request and rebases only its own acknowledgement", async () => {
  const server=new SyntheticServer(), app=await library(server);
  const row=await app.saveProject(project()); await app.updateRecord(row.id,{notes:"Synthetic note before in-flight deletion"}); await app.sync();
  let release; server.pause=new Promise((resolve)=>{release=resolve;});
  await app.removeRecord(row.id); const syncing=app.sync();
  while(server.calls.length<2) await new Promise((resolve)=>setImmediate(resolve));
  const sent=copy(server.calls[1]);
  await app.saveProject(project(),{restore:true});
  assert.deepEqual(server.calls[1],sent);
  assert.deepEqual((await app.store.read()).outbox.map((op)=>op.operation),["delete","restore"]);
  release(); server.pause=null; await syncing;
  assert.equal(server.records.get(row.id).notes,"Synthetic note before in-flight deletion");
  assert.equal(server.records.get(row.id).deleted_at,null);
  assert.equal(server.records.get(row.id).version,3); assert.equal(await app.pendingCount(),0);
});

test("offline create finding existing URL maps identities without resetting cloud notes", async () => {
  const server=new SyntheticServer(), left=await library(server), right=await library(server);
  const original=await left.saveProject(project()); await left.updateRecord(original.id,{notes:"Synthetic existing note",status:"watching"}); await left.sync();
  const offline=await right.saveProject(project()); assert.notEqual(offline.id,original.id);
  await right.sync();
  assert.equal((await right.list()).length,1); assert.equal((await right.list())[0].id,original.id);
  assert.equal((await right.list())[0].notes,"Synthetic existing note"); assert.equal(server.records.size,1);
});

test("offline create with its own notes conflicts with an existing URL rather than dropping notes", async () => {
  const server=new SyntheticServer(), left=await library(server), right=await library(server);
  const original=await left.saveProject(project()); await left.updateRecord(original.id,{notes:"Synthetic cloud note"}); await left.sync();
  const offline=await right.saveProject(project()); await right.updateRecord(offline.id,{notes:"Synthetic offline note"}); await right.sync();
  const [conflict]=await right.list();
  assert.equal(conflict.id,original.id); assert.equal(conflict.notes,"Synthetic offline note");
  assert.equal(conflict.conflict.remote.notes,"Synthetic cloud note");
  await right.resolveConflict(original.id,"local"); await right.sync();
  assert.equal(server.records.get(original.id).notes,"Synthetic offline note");
});

test("incomplete remote pagination commits no partial collection and preserves dirty local rows", async () => {
  const store=new Core.MemoryStore(); const app=await library(undefined,undefined,store);
  const local=await app.saveProject(project()); await app.updateRecord(local.id,{notes:"Synthetic dirty note"});
  const remote=Object.assign(Core.validateProject(project("remote")),{id:randomUUID(),url_key:digest(Core.normalizeUrl(project("remote").url)),version:1,created_at:stamp,updated_at:stamp,deleted_at:null});
  let count=0;
  app.transport={list:async()=>{count+=1;if(count===1)return{records:[remote],next_after:remote.id};throw new Error("synthetic page failure");},mutate:async()=>assert.fail("must not push after an incomplete collection")};
  await assert.rejects(app.sync());
  const rows=await app.list(); assert.equal(rows.length,1); assert.equal(rows[0].notes,"Synthetic dirty note");
  assert.equal(await app.pendingCount(),1);
});

test("full remote history may exceed 100 pages and 10000 lifetime tombstones", async () => {
  const rows=Array.from({length:10101},(_,index)=>({
    id:(index+1).toString(16).padStart(8,"0")+"-0000-4000-8000-000000000000",
    url_key:digest("synthetic deleted identity "+index),version:2,created_at:stamp,updated_at:stamp,deleted_at:stamp,
    canonical_url:null,url:null,title:null,source_id:null,source_issue_date:null,notes:null,status:"to_research"
  }));
  let calls=0;
  const store=new Core.MemoryStore(), app=new Core.Library({store,transport:{
    list:async(after)=>{calls+=1;const start=after ? rows.findIndex((row)=>row.id===after)+1 : 0;
      const page=rows.slice(start,start+100);return{records:page,next_after:start+page.length<rows.length?page.at(-1).id:null};},
    mutate:async()=>assert.fail("synthetic tombstones have no writes")
  }});
  await app.init(); await app.sync();
  assert.equal(calls,204); assert.equal(Object.keys((await store.read()).records).length,10101);
  assert.equal((await app.list()).length,0);
});

test("pagination rejects empty, repeated, descending or unrelated cursors without committing partial history", async () => {
  const id1="00000001-0000-4000-8000-000000000000",id2="00000002-0000-4000-8000-000000000000";
  const remote=(id)=>Object.assign(Core.validateProject(project(id)),{id,url_key:digest(id),version:1,created_at:stamp,updated_at:stamp,deleted_at:null});
  for(const pages of [
    [{records:[],next_after:id1}],
    [{records:[remote(id1)],next_after:id2}],
    [{records:[remote(id1)],next_after:id1},{records:[remote(id1)],next_after:null}],
    [{records:[remote(id2),remote(id1)],next_after:null}]
  ]){
    const store=new Core.MemoryStore();let page=0;
    const app=new Core.Library({store,transport:{list:async()=>pages[page++],mutate:async()=>assert.fail()}});await app.init();
    await assert.rejects(app.sync(),/invalid_remote/);assert.equal(Object.keys((await store.read()).records).length,0);
  }
});

test("missing rows are not treated as delete evidence", async () => {
  const server=new SyntheticServer(), app=await library(server);
  const row=await app.saveProject(project()); await app.sync();
  server.records.delete(row.id); await app.sync();
  assert.equal((await app.list()).length,1);
});

test("an unexpected missing mutation target retains the local record and immutable request", async () => {
  const server=new SyntheticServer(), app=await library(server);
  const row=await app.saveProject(project()); await app.sync();
  await app.updateRecord(row.id,{notes:"Synthetic note retained after missing target"});
  const queued=copy((await app.store.read()).outbox[0]); server.records.delete(row.id);
  await assert.rejects(app.sync(),/record_missing/);
  const [retained]=await app.list(); assert.equal(retained.notes,"Synthetic note retained after missing target");
  assert.equal(retained.sync_state,"error"); assert.equal(retained.last_error,"record_missing");
  assert.equal((await app.store.read()).outbox[0].mutation_id,queued.mutation_id);
  assert.deepEqual((await app.store.read()).outbox[0].payload,queued.payload);
});

test("stop rejects old account pull callbacks before they commit or notify", async () => {
  const server=new SyntheticServer(), source=await library(server);
  await source.saveProject(project()); await source.sync();
  const store=new Core.MemoryStore(); let release,notifications=0;
  const slow={list:()=>new Promise((resolve)=>{release=()=>resolve({records:[server.publicRow([...server.records.values()][0])],next_after:null});}),mutate:async()=>assert.fail()};
  const app=new Core.Library({store,transport:slow,onChange:()=>{notifications+=1;}}); await app.init();
  const syncing=app.sync(); app.stop(); release();
  await assert.rejects(syncing,/stopped/);
  assert.equal(Object.keys((await store.read()).records).length,0); assert.equal(notifications,1);
});

test("clearLocal guards against delayed write acknowledgement resurrecting records", async () => {
  const server=new SyntheticServer(), app=await library(server);
  await app.saveProject(project());
  let release; server.pause=new Promise((resolve)=>{release=resolve;});
  const syncing=app.sync(); while(server.calls.length===0) await new Promise((resolve)=>setImmediate(resolve));
  await app.clearLocal(); release(); server.pause=null;
  await assert.rejects(syncing,/stopped/);
  const state=await app.store.read(); assert.equal(Object.keys(state.records).length,0); assert.equal(state.outbox.length,0);
});

test("synthetic users never share storage or cloud rows", async () => {
  const server=new SyntheticServer(), left=await library(server,"synthetic-A"), right=await library(server,"synthetic-B");
  await left.saveProject(project()); await left.sync(); await right.sync();
  assert.equal((await right.list()).length,0);
  await right.saveProject(project()); await right.sync();
  assert.equal(server.records.size,2);
});

test("backup exports only content and rejects identity, machinery or malicious URL imports", async () => {
  const app=await library(); const row=await app.saveProject(project());
  await app.updateRecord(row.id,{notes:"Synthetic backup note"});
  const backup=await app.exportBackup();
  assert.deepEqual(Object.keys(backup.records[0]).sort(),["url","title","source_id","source_issue_date","notes","status"].sort());
  assert.equal(backup.records[0].notes,"Synthetic backup note");
  for(const field of ["owner_id","id","version","conflict","access_token"]){
    const bad=copy(backup); bad.records[0][field]="synthetic-forbidden";
    assert.throws(()=>Core.validateBackup(bad),Core.RecordsError);
  }
  const bad=copy(backup); bad.records[0].url="javascript:alert(1)";
  assert.throws(()=>Core.validateBackup(bad),Core.RecordsError);
  assert.throws(()=>Core.validateBackup(Object.assign(copy(backup),{session:{}})),Core.RecordsError);
});

test("backup imports are atomic and never silently overwrite existing private notes", async () => {
  const app=await library(); const row=await app.saveProject(project()); await app.updateRecord(row.id,{notes:"Synthetic original"});
  const backup={schemaVersion:1,exportedAt:stamp,records:[Object.assign(project(),{notes:"Synthetic imported",status:"tried"}),Object.assign(project("new"),{notes:"",status:"to_research"})]};
  const result=await app.importBackup(backup); assert.deepEqual(result,{added:1,conflicts:1});
  const existing=(await app.list()).find((item)=>item.id===row.id);
  assert.equal(existing.sync_state,"conflict"); assert.equal(existing.conflict.remote.notes,"Synthetic original");
  await app.resolveConflict(row.id,"remote"); await app.sync();
  assert.equal((await app.list()).find((item)=>item.id===row.id).notes,"Synthetic original");
  const broken=copy(backup); broken.records[1].notes="x".repeat(5001);
  const before=await app.store.read(); await assert.rejects(app.importBackup(broken));
  assert.deepEqual(await app.store.read(),before);
});

test("accepting prior pending content after an import conflict preserves its original cloud operation", async () => {
  const server=new SyntheticServer(), app=await library(server);
  const row=await app.saveProject(project()); await app.sync();
  await app.updateRecord(row.id,{notes:"Synthetic unsent original"});
  const prior=(await app.store.read()).outbox[0];
  await app.importBackup({schemaVersion:1,exportedAt:stamp,records:[Object.assign(project(),{notes:"Synthetic import candidate",status:"to_research"})]});
  await app.resolveConflict(row.id,"remote");
  assert.equal((await app.store.read()).outbox[0].mutation_id,prior.mutation_id);
  await app.sync();
  assert.equal(server.records.get(row.id).notes,"Synthetic unsent original");
});

test("importing a deleted URL retains imported notes until explicit restore or rejection", async () => {
  const server=new SyntheticServer(), app=await library(server);
  const row=await app.saveProject(project()); await app.sync(); await app.removeRecord(row.id); await app.sync();
  const result=await app.importBackup({schemaVersion:1,exportedAt:stamp,records:[Object.assign(project(),{notes:"Synthetic recovered note",status:"watching"})]});
  assert.deepEqual(result,{added:0,conflicts:1});
  const [conflict]=await app.list(); assert.equal(conflict.notes,"Synthetic recovered note");
  assert.equal((await app.exportBackup()).records[0].notes,"Synthetic recovered note");
  await app.saveProject(project(),{restore:true}); await app.sync();
  assert.equal(server.records.get(row.id).notes,"Synthetic recovered note");
});

test("an existing unresolved conflict is never overwritten by another import", async () => {
  const app=await library(); await app.saveProject(project());
  const backup={schemaVersion:1,exportedAt:stamp,records:[Object.assign(project(),{notes:"Synthetic first import",status:"watching"})]};
  await app.importBackup(backup); const before=await app.store.read();
  backup.records[0].notes="Synthetic later import";
  await assert.rejects(app.importBackup(backup),/conflict_unresolved/);
  assert.deepEqual(await app.store.read(),before);
});

test("editor drafts persist locally and export without becoming cloud operations", async () => {
  const server=new SyntheticServer(), app=await library(server);
  const row=await app.saveProject(project()); await app.sync();
  const draft=await app.saveEditorDraft(row.id,{title:"",notes:"Synthetic unconfirmed editor note",status:"tried",base_version:1,base_title:row.title,base_notes:"",base_status:"to_research"});
  assert.equal(draft.notes,"Synthetic unconfirmed editor note");
  assert.equal(await app.pendingCount(),0); assert.equal(await app.editorDraftCount(),1);
  assert.equal((await app.list())[0].has_editor_draft,true);
  await app.sync(); assert.equal(server.records.get(row.id).notes,"");
  const backup=await app.exportBackup(); assert.equal(backup.records[0].notes,draft.notes);
  assert.equal(backup.records[0].title,row.title);
  const reopened=await library(server,"synthetic-A",app.store);
  assert.deepEqual(await reopened.getEditorDraft(row.id),draft);
  await reopened.updateRecord(row.id,{notes:draft.notes,status:draft.status});
  assert.equal(await reopened.editorDraftCount(),0);
  assert.equal((await reopened.list())[0].has_editor_draft,false);
  await reopened.sync(); assert.equal(server.records.get(row.id).notes,draft.notes);
});

test("a draft already issued before an auth lock finishes only in its captured local partition", async () => {
  const store=new Core.MemoryStore(), app=await library(undefined,undefined,store);
  const row=await app.saveProject(project());
  const save=app.saveEditorDraft(row.id,{notes:"Synthetic account A draft"});
  app.stop(); await save;
  assert.equal((await store.read()).editor_drafts[row.id].notes,"Synthetic account A draft");
  const freshStore=new Core.MemoryStore(), fresh=await library(undefined,"synthetic-B",freshStore);
  assert.equal(await fresh.editorDraftCount(),0);
  await app.clearLocal(); assert.equal(Object.keys((await store.read()).editor_drafts).length,0);
});

test("storage failure does not falsely report draft persistence", async () => {
  const store=new Core.MemoryStore(), app=await library(undefined,undefined,store);
  const row=await app.saveProject(project()); store.failNext=true;
  await assert.rejects(app.saveEditorDraft(row.id,{notes:"Synthetic rejected draft"}),/storage_unavailable/);
  assert.equal(await app.editorDraftCount(),0);
});

test("Markdown output escapes markup instead of injecting untrusted HTML", () => {
  const backup={schemaVersion:1,exportedAt:stamp,records:[Object.assign(project(),{title:"Synthetic <script> title",notes:"[Synthetic](javascript:bad)\n<script>not executed</script>",status:"watching"})]};
  const value=Core.toMarkdown(backup);
  assert.ok(value.includes("\\<script\\>")); assert.ok(value.includes("\\[Synthetic\\]"));
});

test("Supabase transport sends exactly the documented RPC fields without ownership data", async () => {
  const account=randomUUID();
  const calls=[]; const transport=Core.createSupabaseTransport({rpc:async(name,args)=>{calls.push({name,args});return{data:{records:[],next_after:null},error:null};}},account);
  await transport.list(null);
  await transport.mutate({mutation_id:randomUUID(),record_id:randomUUID(),operation:"create",expected_version:0,payload:{title:"Synthetic"},owner_id:"must-not-send"});
  assert.equal(calls[0].name,"list_my_records"); assert.deepEqual(calls[0].args,{p_account_id:account,p_after_id:null,p_limit:100});
  assert.equal(calls[1].name,"apply_record_mutation"); assert.equal(Object.keys(calls[1].args).length,6);
  assert.equal(calls[1].args.p_account_id,account);
  assert.ok(!JSON.stringify(calls[1]).includes("must-not-send"));
});

test("captured account identity prevents an SDK session switch from acknowledging the wrong account", async () => {
  const accountA=randomUUID(), accountB=randomUUID(); let sdkAccount=accountA;
  const adapter=Core.createSupabaseTransport({rpc:async(name,args)=>{
    if(args.p_account_id!==sdkAccount) return {data:null,error:{message:"synthetic account mismatch"}};
    return {data:{records:[],next_after:null},error:null};
  }},accountA);
  const store=new Core.MemoryStore(); const app=new Core.Library({store,transport:adapter}); await app.init();
  await app.saveProject(project()); sdkAccount=accountB;
  await assert.rejects(app.sync(),/sync_failed/);
  assert.equal(await app.pendingCount(),1); assert.equal((await app.list())[0].sync_state,"pending");
  assert.throws(()=>Core.createSupabaseTransport({rpc:async()=>{}},"not-a-user"),/invalid_account/);
});

test("Supabase errors expose only exact fixed quota, session and validation categories", async () => {
  const cases=[
    ["P0001","record_limit_reached","record_limit"],
    ["P0001","storage_limit_reached","storage_limit"],
    ["28000","account_changed","session_required"],
    ["28000","authentication_required","session_required"],
    ["22023","notes_too_long","invalid_record"],
    ["P0001","Synthetic confidential diagnostics","sync_failed"],
    ["unexpected","record_limit_reached","sync_failed"],
    ["P0001","record_limit_reached Synthetic confidential diagnostics","sync_failed"]
  ];
  for(const [code,message,expected] of cases){
    const transport=Core.createSupabaseTransport({rpc:async()=>({data:null,error:{code,message,details:"Synthetic confidential detail",hint:"Synthetic confidential hint"}})},randomUUID());
    await assert.rejects(transport.list(null),(error)=>{
      assert.equal(error.code,expected); assert.equal(error.message,expected);
      assert.ok(!JSON.stringify(error).includes("confidential")); return true;
    });
  }
  const transport=Core.createSupabaseTransport({rpc:async()=>{throw new Error("Synthetic confidential thrown diagnostics");}},randomUUID());
  await assert.rejects(transport.list(null),(error)=>error.code==="sync_failed" && error.message==="sync_failed");
});

test("server quota rejection preserves local notes and the same pending mutation", async () => {
  for(const message of ["record_limit_reached","storage_limit_reached"]){
    const transport=Core.createSupabaseTransport({rpc:async(name)=>name==="list_my_records"
      ? {data:{records:[],next_after:null},error:null}
      : {data:null,error:{code:"P0001",message,details:"Synthetic confidential quota details"}}
    },randomUUID());
    const app=new Core.Library({store:new Core.MemoryStore(),transport}); await app.init();
    const row=await app.saveProject(project()); await app.updateRecord(row.id,{notes:"Synthetic quota-protected research"});
    const before=(await app.store.read()).outbox[0];
    const expected=message==="record_limit_reached"?"record_limit":"storage_limit";
    await assert.rejects(app.sync(),(error)=>error.code===expected);
    const [retained]=await app.list(); assert.equal(retained.notes,"Synthetic quota-protected research");
    assert.equal(retained.last_error,expected); assert.equal(retained.sync_state,"error");
    assert.equal((await app.store.read()).outbox[0].mutation_id,before.mutation_id);
    assert.equal(await app.pendingCount(),1);
  }
});
