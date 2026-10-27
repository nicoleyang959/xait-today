"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const ui = require("../site/assets/records-ui.js");

const disabled = {enabled:false, supabaseUrl:"", publishableKey:"", redirectUrl:""};
const enabled = {
  enabled:true,
  supabaseUrl:"https://" + "a".repeat(20) + ".supabase.co",
  publishableKey:"sb_publishable_" + "synthetic-public-value-000000",
  redirectUrl:"https://library.example/xait-today/"
};

test("default configuration is explicitly off and must contain no hidden settings", () => {
  assert.deepEqual(ui.readConfig(JSON.stringify(disabled)), disabled);
  assert.throws(() => ui.readConfig(JSON.stringify({...disabled, supabaseUrl:enabled.supabaseUrl})));
  assert.throws(() => ui.readConfig(JSON.stringify({...disabled, extra:true})));
  assert.throws(() => ui.readConfig("null"));
});

test("enabled configuration accepts only the declared publishable format", () => {
  assert.deepEqual(ui.readConfig(JSON.stringify(enabled)), enabled);
  for (const publishableKey of ["sb_secret_synthetic", "synthetic-session-value", "eyJsynthetic"]) {
    assert.throws(() => ui.readConfig(JSON.stringify({...enabled,publishableKey})));
  }
  for (const supabaseUrl of ["https://api.example", enabled.supabaseUrl+"/", enabled.supabaseUrl+"?key=synthetic", "http://api.example"]) {
    assert.throws(() => ui.readConfig(JSON.stringify({...enabled,supabaseUrl})));
  }
});

test("OAuth return URL has no query, fragment, user information or arbitrary path scope", () => {
  for (const redirectUrl of ["http://library.example/xait-today/", "https://reader@library.example/xait-today/", enabled.redirectUrl+"?next=elsewhere", enabled.redirectUrl+"#saved", "https://library.example/xait-today"]) {
    assert.throws(() => ui.readConfig(JSON.stringify({...enabled,redirectUrl})));
  }
});

test("a foreign clone and ordinary insecure runtime cannot connect to author's cloud", () => {
  assert.equal(ui.isAllowedRuntime(enabled,"../../",enabled.redirectUrl+"archive/2026-10-27/",true),true);
  assert.equal(ui.isAllowedRuntime(enabled,"./",enabled.redirectUrl,true),true);
  assert.equal(ui.isAllowedRuntime(enabled,"./","https://copy.example/xait-today/",true),false);
  assert.equal(ui.isAllowedRuntime(enabled,"./",enabled.redirectUrl,false),false);
  assert.equal(ui.isAllowedRuntime(enabled,"/other/",enabled.redirectUrl,true),false);
  assert.equal(ui.isAllowedRuntime(disabled,"./",enabled.redirectUrl,true),false);
});

test("return navigation cannot escape site or carry authentication parameters", () => {
  assert.equal(ui.safeReturnPath("/xait-today/archive/2026-10-27/#main-content",enabled.redirectUrl),"/xait-today/archive/2026-10-27/#main-content");
  for (const value of ["https://other.example/", "/other/", "//other.example/", "/xait-today-evil/", "/xait-today/?code=synthetic", "/xait-today/#access_token=synthetic"]) {
    assert.equal(ui.safeReturnPath(value,enabled.redirectUrl),null);
  }
});

test("callback authentication fields are removed without persisting or displaying values", () => {
  const result=ui.cleanAuthLocation(enabled.redirectUrl+"?lang=en&code=synthetic-once#error=denied");
  assert.equal(result.code,"synthetic-once");
  assert.equal(result.clean,"/xait-today/?lang=en");
  assert.equal(result.changed,true);
  const clean=ui.cleanAuthLocation(enabled.redirectUrl+"?lang=zh#saved");
  assert.equal(clean.changed,false);
  assert.equal(clean.clean,"/xait-today/?lang=zh#saved");
});

test("error copy uses safe fixed categories, never raw provider details", () => {
  assert.equal(ui.errorKey({code:"record_limit",message:"synthetic diagnostic"}),"quota");
  assert.equal(ui.errorKey({code:"unsafe_url"}),"invalidLink");
  assert.equal(ui.errorKey({code:"storage_failed"}),"storageError");
  assert.equal(ui.errorKey({code:"session_required"}),"signInAgain");
  assert.equal(ui.errorKey({message:"untrusted text"}),"unavailable");
});

if (process.env.XAIT_RECORDS_BROWSER_TEST === "1") {
  const fs=require("node:fs");
  const path=require("node:path");
  const {chromium}=require("playwright");
  const rootDir=path.resolve(__dirname,"..","docs");
  const base="https://library.example/";
  const fixtureConfig={...enabled,redirectUrl:base};
  const userA="11111111-1111-4111-8111-111111111111";
  const userB="22222222-2222-4222-8222-222222222222";
  let browser;
  test.before(async()=>{browser=await chromium.launch({channel:"chrome",headless:true});});
  test.after(async()=>{if(browser)await browser.close();});

  async function contextFor(cloud) {
    const context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:"block"});
    let blockedRequests=0;
    await context.route("**/*",async(route)=>{
      const requestUrl=new URL(route.request().url());
      if(requestUrl.origin!==new URL(base).origin){blockedRequests++;await route.abort();return;}
      const relative=decodeURIComponent(requestUrl.pathname).replace(/^\//,"")||"index.html";
      let file=path.resolve(rootDir,relative.endsWith("/")?relative+"index.html":relative);
      if(!file.startsWith(rootDir+path.sep)){await route.abort();return;}
      if(["assets/records-ui.js","assets/records-core.js","assets/records.css"].includes(relative))file=path.resolve(rootDir,"..","site",relative);
      if(!fs.existsSync(file)){await route.fulfill({status:404,body:"Not found"});return;}
      let body=fs.readFileSync(file);
      if(file.endsWith(".html")&&cloud){
        let html=body.toString("utf8");
        const serialized=JSON.stringify(fixtureConfig).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
        html=html.replace(/(<template\b[^>]*id="xait-records-config"[^>]*>)[\s\S]*?(<\/template>)/,"$1"+serialized+"$2");
        body=Buffer.from(html);
      }
      const extension=path.extname(file);
      const type=extension===".html"?"text/html":extension===".js"?"application/javascript":extension===".css"?"text/css":"application/json";
      await route.fulfill({status:200,contentType:type,body});
    });
    if(cloud)await context.addInitScript(({userA,userB})=>{
      let current={id:userA,user_metadata:{user_name:"Synthetic reader A"}};
      const callbacks=new Set();
      const database=new Map();
      const receipts=new Map();
      const now=()=>new Date().toISOString();
      function bucket(id){if(!database.has(id))database.set(id,new Map());return database.get(id);}
      async function digest(value){const bytes=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value));return [...new Uint8Array(bytes)].map(v=>v.toString(16).padStart(2,"0")).join("");}
      const client={auth:{
        getSession:async()=>({data:{session:current?{user:current}:null},error:null}),
        getUser:async()=>({data:{user:current},error:null}),
        onAuthStateChange(callback){callbacks.add(callback);return{data:{subscription:{unsubscribe(){callbacks.delete(callback);}}}};},
        signInWithOAuth:async()=>({data:{},error:null}),exchangeCodeForSession:async()=>({data:{session:{user:current}},error:null}),
        stopAutoRefresh(){},signOut:async()=>{current=null;callbacks.forEach(fn=>fn("SIGNED_OUT",null));return{error:null};}
      },async rpc(name,args){
        if(!current||args.p_account_id!==current.id)return{error:{code:"account_mismatch"},data:null};
        const mine=bucket(current.id);
        if(name==="list_my_records")return{error:null,data:{records:[...mine.values()].sort((a,b)=>a.id.localeCompare(b.id)),next_after:null}};
        if(name!=="apply_record_mutation")return{error:{code:"unknown_rpc"},data:null};
        const receiptKey=current.id+"/"+args.p_mutation_id;
        if(receipts.has(receiptKey))return{error:null,data:receipts.get(receiptKey)};
        let record=mine.get(args.p_record_id);
        const canonical=args.p_payload.canonical_url||args.p_payload.url;
        const existing=canonical?[...mine.values()].find(row=>row.url_key===undefined?row.canonical_url===canonical:false):null;
        let status="applied";
        if(args.p_operation==="create"){
          const key=await digest(canonical);
          const duplicate=[...mine.values()].find(row=>row.url_key===key);
          if(duplicate){record=duplicate;status=duplicate.deleted_at?"deleted":"existing";}
          else {record={...args.p_payload,id:args.p_record_id,url_key:key,canonical_url:canonical,version:1,created_at:now(),updated_at:now(),deleted_at:null};mine.set(record.id,record);}
        }else if(!record||record.version!==args.p_expected_version){status="conflict";}
        else if(record.deleted_at&&args.p_operation!=="restore"){status="deleted";}
        else {
          record={...record,...args.p_payload,version:record.version+1,updated_at:now()};
          if(args.p_operation==="delete")Object.assign(record,{canonical_url:null,url:null,title:null,source_id:null,source_issue_date:null,notes:null,status:null,deleted_at:now()});
          else record.deleted_at=null;
          mine.set(record.id,record);
        }
        const result={status,record:record||null,applied_version:record?record.version:null};
        if(status==="applied"||status==="existing")receipts.set(receiptKey,result);
        return{error:null,data:result};
      }};
      Object.defineProperty(window,"supabase",{configurable:true,get:()=>({createClient:()=>client}),set(){}});
      window.__recordsFixture={emit(id){current=id?{id,user_metadata:{user_name:id===userA?"Synthetic reader A":"Synthetic reader B"}}:null;callbacks.forEach(fn=>fn(current?"SIGNED_IN":"SIGNED_OUT",current?{user:current}:null));},count(id){return[...bucket(id).values()].filter(r=>!r.deleted_at).length;},remoteEdit(id,changes){const mine=bucket(current.id);const old=mine.get(id);mine.set(id,{...old,...changes,version:old.version+1,updated_at:now()});},userA,userB};
    },{userA,userB});
    return {context,blocked:()=>blockedRequests};
  }
  async function ready(page){await page.waitForSelector("#records-workspace:not([hidden])");}
  async function manual(page,title,url){
    await page.locator("#records-add").evaluate(el=>{el.open=true;});
    await page.locator("#records-manual-title").fill(title);await page.locator("#records-manual-url").fill(url);
    await page.locator("#records-manual-form button[type=submit]").click();
    await page.waitForFunction(title=>[...document.querySelectorAll("#records-list h3")].some(n=>n.textContent===title),title);
  }
  test("browser: default off is usable and makes no external cloud requests",async()=>{
    const fixture=await contextFor(false);const page=await fixture.context.newPage();const errors=[];
    page.on("pageerror",e=>errors.push(e.message));
    await page.goto(base+"#saved");
    await page.locator("#records-gate-heading").waitFor();
    assert.match(await page.locator("#records-gate-heading").innerText(),/尚未启用/);
    assert.equal(await page.locator("#records-login").isVisible(),false);
    await page.locator("#records-back").click();
    assert.equal(await page.locator("#briefing-view").isVisible(),true);
    assert.equal(fixture.blocked(),0);assert.deepEqual(errors,[]);
    await fixture.context.close();
  });
  test("browser: private editing, offline save, account isolation and unsaved draft recovery",async()=>{
    const fixture=await contextFor(true);const page=await fixture.context.newPage();const errors=[];
    page.on("pageerror",e=>errors.push(e.message));
    await page.goto(base+"#saved");await ready(page);
    await manual(page,"Synthetic project","https://example.org/project");
    await page.locator("#records-list button").filter({hasText:"写笔记"}).first().click();
    await page.locator("#records-edit-notes").fill("Synthetic private note A");
    await page.locator("#records-edit-form button[type=submit]").click();
    await page.waitForFunction(()=>document.querySelector("#records-list").textContent.includes("Synthetic private note A"));
    await page.waitForFunction(()=>window.__recordsFixture.count(window.__recordsFixture.userA)===1);
    await fixture.context.setOffline(true);
    await manual(page,"Synthetic offline project","https://example.org/offline");
    assert.match(await page.locator("#records-sync-state").innerText(),/待同步/);
    await fixture.context.setOffline(false);
    await page.waitForFunction(()=>window.__recordsFixture.count(window.__recordsFixture.userA)===2);
    await page.locator("#records-list button").filter({hasText:"写笔记"}).last().click();
    await page.locator("#records-editor").waitFor({state:"visible"});
    const editedId=await page.locator("#records-edit-id").inputValue();
    await page.locator("#records-edit-notes").fill("Synthetic unsaved draft A");
    await page.locator("#records-search").fill("Synthetic");
    await page.locator("#records-add").evaluate(el=>{el.open=true;});
    await page.locator("#records-manual-title").fill("Synthetic unfinished A input");
    await page.evaluate(()=>window.__recordsFixture.emit(window.__recordsFixture.userB));
    await page.waitForFunction(()=>document.querySelector("#records-account").textContent.includes("reader B"));
    assert.equal(await page.locator("#records-list").innerText(),"");
    assert.equal(await page.locator("#records-edit-notes").inputValue(),"");
    assert.equal(await page.locator("#records-search").inputValue(),"");
    assert.equal(await page.locator("#records-manual-title").inputValue(),"");
    const isolatedDraft=await page.evaluate(async(id)=>{
      const store=await window.XaitRecordsCore.openStore("a".repeat(20)+".supabase.co/",window.__recordsFixture.userA);
      const state=await store.read();if(store.close)store.close();
      return state.editor_drafts[id]||null;
    },editedId);
    assert.equal(isolatedDraft&&isolatedDraft.notes,"Synthetic unsaved draft A","synthetic A draft must remain in A's IndexedDB partition during B session");
    await page.evaluate(()=>window.__recordsFixture.emit(window.__recordsFixture.userA));
    await page.waitForFunction(()=>document.querySelector("#records-account").textContent.includes("reader A"));
    await page.locator('.records-item[data-record-id="'+editedId+'"] button').filter({hasText:"写笔记"}).click();
    await page.locator("#records-editor").waitFor({state:"visible"});
    assert.equal(await page.locator("#records-edit-notes").inputValue(),"Synthetic unsaved draft A");
    assert.equal(await page.locator("html").evaluate(el=>el.scrollWidth>innerWidth),false);
    assert.equal(fixture.blocked(),0);assert.deepEqual(errors,[]);
    await fixture.context.close();
  });
  test("browser: capture, backup import/export, conflict choice, removal and safe pending logout",async()=>{
    const fixture=await contextFor(true);const page=await fixture.context.newPage();const errors=[];
    page.on("pageerror",e=>errors.push(e.message));
    await page.goto(base);
    await page.waitForFunction(()=>!document.querySelector("#records-workspace").hidden);
    const sourceButton=page.locator("[data-save-project]").first();
    await sourceButton.click();
    await page.waitForFunction(()=>document.querySelector("[data-save-project]").getAttribute("aria-pressed")==="true");
    await sourceButton.click();
    await page.locator("#records-editor").waitFor({state:"visible"});
    const capturedId=await page.locator("#records-edit-id").inputValue();
    await page.locator("#records-edit-notes").fill("Synthetic captured note");
    await page.locator("#records-edit-form button[type=submit]").click();
    await page.waitForFunction(()=>document.querySelector("#records-list").textContent.includes("Synthetic captured note")&&document.querySelector("#records-sync-state").textContent.includes("所有记录已同步"));
    assert.equal(await page.locator("#records-toast").innerText(),"笔记已存本地。","acknowledged save must not retain a contradictory waiting toast");
    await page.locator("#records-editor-close").click();
    const exportedDownload=page.waitForEvent("download");
    await page.locator("#records-export-json").click();
    const exported=JSON.parse(fs.readFileSync(await(await exportedDownload).path(),"utf8"));
    assert.equal(exported.schemaVersion,1);assert.equal(exported.records.length,1);
    assert.equal(exported.records[0].notes,"Synthetic captured note");
    assert.deepEqual(Object.keys(exported.records[0]).sort(),["url","title","source_id","source_issue_date","notes","status"].sort());
    const invalid={...exported,records:[{...exported.records[0],owner_id:userB}]};
    await page.locator("#records-import-file").setInputFiles({name:"synthetic-invalid.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(invalid))});
    await page.waitForFunction(()=>document.querySelector("#records-feedback").textContent.includes("备份无效"));
    const added={...exported,records:[{url:"https://example.org/imported",title:"Synthetic imported project",source_id:"manual",source_issue_date:null,notes:"Synthetic imported note",status:"watching"}]};
    await page.locator("#records-import-file").setInputFiles({name:"synthetic-valid.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(added))});
    await page.locator("#records-dialog[open] button[value=import]").click();
    await page.waitForFunction(()=>document.querySelectorAll("#records-list .records-item").length===2);
    await page.locator("#records-search").fill("imported");
    await page.waitForFunction(()=>document.querySelectorAll("#records-list .records-item").length===1);
    await page.locator("#records-search").fill("");
    await page.locator("#records-filter").selectOption("watching");
    assert.equal(await page.locator("#records-list .records-item").count(),1);
    await page.locator("#records-filter").selectOption("all");
    await page.waitForFunction(()=>document.querySelector("#records-sync-state").textContent.includes("所有记录已同步"));
    await page.locator('.records-item[data-record-id="'+capturedId+'"] button').filter({hasText:"写笔记"}).click();
    await page.locator("#records-editor").waitFor({state:"visible"});
    await fixture.context.setOffline(true);
    await page.locator("#records-edit-notes").fill("Synthetic local conflict note");
    await page.locator("#records-edit-form button[type=submit]").click();
    await page.evaluate(id=>window.__recordsFixture.remoteEdit(id,{notes:"Synthetic remote conflict note"}),capturedId);
    await fixture.context.setOffline(false);
    await page.locator('.records-item[data-record-id="'+capturedId+'"] button').filter({hasText:"处理冲突"}).waitFor();
    await page.locator('.records-item[data-record-id="'+capturedId+'"] button').filter({hasText:"处理冲突"}).click();
    assert.match(await page.locator("#records-dialog-detail").innerText(),/Synthetic local conflict note/);
    assert.match(await page.locator("#records-dialog-detail").innerText(),/Synthetic remote conflict note/);
    await page.locator("#records-dialog[open] button[value=local]").click();
    await page.waitForFunction(()=>document.querySelector("#records-sync-state").textContent.includes("所有记录已同步"));
    assert.match(await page.locator('.records-item[data-record-id="'+capturedId+'"] .records-item-notes').innerText(),/Synthetic local conflict note/);
    await page.locator('.records-item[data-record-id="'+capturedId+'"] button').filter({hasText:"移除"}).click();
    await page.locator("#records-dialog[open] button[value=cancel]").click();
    assert.equal(await page.locator('.records-item[data-record-id="'+capturedId+'"]').count(),1);
    await page.locator('.records-item[data-record-id="'+capturedId+'"] button').filter({hasText:"移除"}).click();
    await page.locator("#records-dialog[open] button[value=remove]").click();
    await page.waitForFunction(id=>!document.querySelector('.records-item[data-record-id="'+id+'"]'),capturedId);
    await fixture.context.setOffline(true);
    await manual(page,"Synthetic pending logout","https://example.org/pending");
    await page.locator("#records-signout").click();
    await page.locator("#records-dialog[open] button[value=cancel]").click();
    assert.equal(await page.locator("#records-workspace").isVisible(),true);
    await page.locator("#records-signout").click();
    const logoutBackup=page.waitForEvent("download");
    await page.locator("#records-dialog[open] button[value=export]").click();
    await logoutBackup;
    assert.equal(await page.locator("#records-workspace").isVisible(),true);
    await page.locator("#records-signout").click();
    await page.locator("#records-dialog[open] button[value=discard]").click();
    await page.waitForFunction(()=>document.querySelector("#records-feedback").textContent.includes("已退出"));
    assert.equal(await page.locator("#records-workspace").isVisible(),false);
    assert.equal(await page.locator("#records-edit-notes").inputValue(),"");
    assert.equal(fixture.blocked(),0);assert.deepEqual(errors,[]);
    await fixture.context.close();
  });
  test("browser: mobile seven-theme controls and English switch keep private notes as text",async()=>{
    const fixture=await contextFor(true);const page=await fixture.context.newPage();const errors=[];
    page.on("pageerror",e=>errors.push(e.message));
    await page.setViewportSize({width:390,height:844});
    await page.goto(base+"?lang=zh&code=synthetic-once#saved");await ready(page);
    assert.equal(new URL(page.url()).searchParams.has("code"),false);
    await manual(page,"Synthetic mobile project","https://example.org/mobile");
    await page.locator("#records-list button").filter({hasText:"写笔记"}).click();
    await page.locator("#records-editor").waitFor({state:"visible"});
    const privateText="私人笔记 <img src=x onerror=alert(1)>";
    await page.locator("#records-edit-notes").fill(privateText);
    await page.locator("#records-edit-form button[type=submit]").click();
    await page.waitForFunction(()=>document.querySelector("#records-list").textContent.includes("私人笔记"));
    await page.locator(".settings-drawer").evaluate(el=>{el.open=true;});
    for(const theme of ["terminal","cyberpunk","swiss","editorial","consulting","minimal","paper"]){
      await page.locator('[data-theme="theme-'+theme+'"]').click();
      assert.equal(await page.locator("body").evaluate((el,cls)=>el.classList.contains(cls),"theme-"+theme),true);
      assert.equal(await page.locator("html").evaluate(el=>el.scrollWidth>innerWidth),false,theme+" has no mobile overflow");
    }
    assert.equal(await page.locator("#sidebar").evaluate(el=>getComputedStyle(el).visibility),"hidden");
    await page.locator("#sidebar-toggle").click();
    assert.equal(await page.locator("#sidebar").evaluate(el=>getComputedStyle(el).visibility),"visible");
    await page.locator("#sidebar-toggle").click();
    assert.equal(await page.locator("#sidebar").evaluate(el=>getComputedStyle(el).visibility),"hidden");
    await page.locator('[data-language="en"]').click();
    await page.waitForFunction(()=>document.querySelector("#records-heading").textContent==="My projects");
    assert.match(await page.locator("#records-account").innerText(),/^Account:/);
    await page.waitForFunction(()=>!/[㐀-鿿]/.test(document.querySelector("#records-sync-state").textContent));
    assert.doesNotMatch(await page.locator("#records-feedback").innerText(),/[㐀-鿿]/);
    assert.equal(await page.locator(".records-item-notes").innerText(),privateText);
    assert.equal(await page.locator("#records-list img").count(),0);
    assert.equal(await page.locator("#records-edit-notes").inputValue(),privateText);
    await page.locator("#records-edit-notes").focus();
    await page.keyboard.type(" x");
    assert.match(await page.locator("#records-edit-notes").inputValue(),/ x$/);
    assert.equal(await page.locator("html").evaluate(el=>el.scrollWidth>innerWidth),false);
    if(process.env.XAIT_RECORDS_SCREENSHOT_DIR){
      const output=process.env.XAIT_RECORDS_SCREENSHOT_DIR;fs.mkdirSync(output,{recursive:true});
      await page.locator(".settings-drawer").evaluate(el=>{el.open=false;});
      await page.locator("#records-edit-notes").blur();
      await page.evaluate(()=>{window.scrollTo(0,0);return new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
      await page.screenshot({path:path.join(output,"records-mobile.png"),fullPage:true});
      const desktop=await fixture.context.newPage();desktop.on("pageerror",e=>errors.push(e.message));
      await desktop.setViewportSize({width:1440,height:960});await desktop.goto(base+"?lang=en#saved");await ready(desktop);
      await desktop.locator("#records-list button").filter({hasText:"Edit notes"}).click();
      await desktop.locator("#records-editor").waitFor({state:"visible"});
      await desktop.locator("#records-heading").focus();
      await desktop.evaluate(()=>{window.scrollTo(0,0);return new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
      await desktop.evaluate(()=>Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{}))));
      await desktop.screenshot({path:path.join(output,"records-desktop.png"),fullPage:true});
      await desktop.close();
    }
    assert.equal(fixture.blocked(),0);assert.deepEqual(errors,[]);
    await fixture.context.close();
  });
}
