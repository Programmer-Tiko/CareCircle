/* Opt-in live provider UI acceptance. No request interception or model stubs. */
const {chromium}=require(process.env.CADENCE_PLAYWRIGHT_MODULE || 'playwright');
const BASE=process.env.CADENCE_BROWSER_URL;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CADENCE_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+process.env.CADENCE_MIC_WAV]});
 const report={provider_stubs:false,browser:'installed real Chrome headless',microphone:'synthetic speech file through real MediaRecorder',events:[]};
 try{
  const context=await browser.newContext({permissions:['microphone'],viewport:{width:1280,height:900}});
  const page=await context.newPage();const errors=[];let answerRequests=0;
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(request.method()==='POST' && /\/turns\/[^/]+\/answer$/.test(new URL(request.url()).pathname))answerRequests++;});
  await page.goto(BASE+'/');
  if(!await page.locator('#connectionSettings').evaluate(el=>el.open))await page.locator('#connectionSettings summary').click();
  await page.locator('#apiBase').fill(BASE);await page.locator('#profileId').fill('live-ui-proof');
  await page.locator('#connectBtn').click();await page.waitForTimeout(1200);
  await page.locator('#historyBtn').click();
  await page.getByRole('button',{name:'Open question',exact:true}).click();
  await page.locator('#questionPanel').waitFor({state:'visible',timeout:30000});
  async function speak(button){
   const previousSource=await page.locator('#speechPlayer').getAttribute('src');
   const pending=page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/speak',{timeout:90000});
   await page.locator(button).click();const response=await pending;
   if(!response.ok() || !(response.headers()['content-type']||'').startsWith('audio/mpeg'))throw new Error('Real TTS response unavailable: HTTP '+response.status());
   // Chrome/CDP can omit binary response bodies after fetch consumes them.
   // Inspect the actual blob URL created by the UI, then require playable audio.
   await page.waitForFunction(previous=>{const src=document.querySelector('#speechPlayer').getAttribute('src');return src?.startsWith('blob:') && src!==previous;},previousSource,{timeout:30000});
   await page.waitForFunction(()=>document.querySelector('#speechPlayer').readyState>=2,null,{timeout:30000});
   const bytes=await page.evaluate(async()=>{const audio=document.querySelector('#speechPlayer');return (await (await fetch(audio.src)).arrayBuffer()).byteLength;});
   if(bytes<1000)throw new Error('Real TTS player blob has insufficient bytes: '+bytes);
   return {http_status:response.status(),content_type:response.headers()['content-type'],bytes,playable:true};
  }
  report.question_tts=await speak('#speakQuestionBtn');
  const beforeASR=answerRequests;
  await page.locator('#recordAnswerBtn').click();await page.waitForFunction(()=>!document.querySelector('#stopAnswerBtn').disabled);
  await page.waitForTimeout(13000);
  const pendingTranscript=page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/transcribe',{timeout:180000});
  await page.locator('#stopAnswerBtn').click();
  const response=await pendingTranscript;
  if(!response.ok())throw new Error('Real transcription failed: HTTP '+response.status()+' '+await response.text());
  const transcript=await response.json();
  await page.waitForFunction(()=>document.querySelector('#answerText').value.trim().length>0,null,{timeout:30000});
  if(answerRequests!==beforeASR)throw new Error('Transcription auto-sent before review');
  report.real_asr={http_status:response.status(),model_id:transcript.model_id,characters:transcript.text.length,
    word_count:transcript.words?.length,review_without_autosend:true};
  let terminal;
  for(let index=0;index<18;index++){
   await page.locator('#answerText').fill('This is a fictional demonstration. My voice feels weak and I have trouble speaking; people ask me to repeat myself.');
   const pending=page.waitForResponse(r=>r.request().method()==='POST' && /\/turns\/[^/]+\/answer$/.test(new URL(r.url()).pathname),{timeout:120000});
   await page.locator('#answerBtn').click();const response=await pending;
   if(!response.ok())throw new Error('Live conversation answer failed: HTTP '+response.status());
   const session=await response.json();report.events.push({answer:index+1,state:session.state,revision:session.revision,
     next_question_id:session.turns?.at(-1)?.question?.id});
   await page.waitForTimeout(350);
   if(session.state!=='active'){terminal=session;break;}
  }
  if(!terminal || !['complete','abstained'].includes(terminal.state))throw new Error('Conversation failed to terminate within 18 explicit answers');
  report.terminal_state=terminal.state;
  report.note_tts=await speak('#speakNoteBtn');
  await page.locator('#correctionText').fill('Fictional correction: this example concerns conversations at dinner.');
  const correction=page.waitForResponse(r=>r.request().method()==='POST' && /\/correction$/.test(new URL(r.url()).pathname));
  await page.locator('#correctionBtn').click();const changed=await correction;
  if(!changed.ok())throw new Error('Correction failed: HTTP '+changed.status());
  const confirm=page.waitForResponse(r=>r.request().method()==='POST' && /\/conversations\/[^/]+\/confirm$/.test(new URL(r.url()).pathname));
  await page.locator('#confirmBtn').click();const confirmed=await confirm;
  if(!confirmed.ok())throw new Error('Confirmation failed: HTTP '+confirmed.status());
  const final=await confirmed.json();if(final.state!=='confirmed')throw new Error('Note not confirmed');
  report.confirmed_revision=final.revision;
  await page.reload();await page.waitForTimeout(1200);await page.locator('#historyBtn').click();
  await page.waitForFunction(()=>document.querySelector('#historyList').textContent.includes('Note confirmed'));
  report.reload_history_confirmed=true;
  await page.screenshot({path:'/private/tmp/cadence-live-ui-final.png',fullPage:true});
  if(errors.length)throw new Error('Browser JavaScript errors: '+errors.join(';'));
  report.javascript_errors=errors;report.result='PASS';console.log(JSON.stringify(report));
 }catch(error){
  console.error(error.stack || error.message);throw error;
 }finally{await browser.close();}
})().catch(()=>{process.exitCode=1;});
