/* Real Chromium MediaRecorder smoke. TTS/ASR responses are explicit stubs. */
const {chromium}=require(process.env.CADENCE_PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs');
const BASE=process.env.CADENCE_BROWSER_URL;
const CHROME=process.env.CADENCE_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const report={result:'PASS',browser:'installed Chrome headless',microphone:'file-backed fake microphone through real MediaRecorder',
  tts:'browser request stub, not ElevenLabs verification',asr:'browser request stub, not transcription-model verification',events:[],screenshots:[]};
const errors=[];
let answerRequests=0;
async function launch(wav,storageState){
  const browser=await chromium.launch({executablePath:CHROME,headless:true,args:[
    '--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+wav]});
  const context=await browser.newContext({permissions:['microphone'],storageState,viewport:{width:1280,height:900}});
  await context.route('**/capabilities',async route=>{const response=await route.fetch();const caps=await response.json();caps.asr_enabled=true;caps.tts_enabled=true;await route.fulfill({response,contentType:'application/json',body:JSON.stringify(caps)});});
  await context.route('**/speak',route=>route.fulfill({status:200,contentType:'audio/wav',body:fs.readFileSync(process.env.CADENCE_TTS_STUB_WAV)}));
  await context.route('**/transcribe',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({text:'People ask me to repeat my words.',transcript:'People ask me to repeat my words.',provider:'browser-test-stub'})}));
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  page.on('request',r=>{if(r.method()==='POST' && /\/turns\/[^/]+\/answer$/.test(new URL(r.url()).pathname))answerRequests++;});
  return {browser,context,page};
}
async function openSettings(page){
  if(!await page.locator('#connectionSettings').evaluate(el=>el.open))await page.locator('#connectionSettings summary').click();
}
async function connect(page){
  await page.goto(BASE+'/');
  await openSettings(page);
  await page.locator('#apiBase').fill(BASE);
  await page.locator('#profileId').fill('ui-smoke');
  await page.locator('#connectBtn').click();
  await page.waitForTimeout(700);
  if(await page.locator('#verifyPassageToggle').count())await page.locator('#verifyPassageToggle').uncheck();
}
async function record(page,seconds,keyboard=false){
  const count=await page.locator('#takeList audio').count();
  if(keyboard){await page.locator('#recordBtn').focus();await page.keyboard.press('Enter');}
  else await page.locator('#recordBtn').click();
  await page.waitForFunction(()=>!document.querySelector('#stopBtn').disabled);
  await page.waitForTimeout(seconds*1000);
  await page.locator('#stopBtn').click();
  await page.waitForFunction(previous=>document.querySelectorAll('#takeList audio').length>previous,count,{timeout:30000});
}
async function upload(page){
  const response=page.waitForResponse(r=>r.request().method()==='POST' && /\/profiles\/[^/]+\/checkin$/.test(new URL(r.url()).pathname));
  await page.locator('#uploadBtn').click();
  const received=await response;
  if(!received.ok())throw new Error('checkin '+received.status()+' '+await received.text());
  const body=await received.json();
  report.events.push({checkin_status:body.status,experimental:Boolean(body.measured?.waveform_evidence || body.waveform_evidence)});
  await page.waitForTimeout(800);
  return body;
}
(async()=>{
 let active=await launch(process.env.CADENCE_MIC_WAV);
 try{
  let {page,context}=active;
  await connect(page);
  await page.locator('#captureKind').selectOption('reference');
  for(let index=0;index<3;index++)await record(page,3.2+index*.1,index===0);
  report.keyboard_record_start='PASS';
  report.reference_recordings=await page.locator('#takeList audio').count();
  const enrollment=page.waitForResponse(r=>/\/profiles\/[^/]+\/enroll$/.test(new URL(r.url()).pathname));
  await page.locator('#enrollBtn').click();
  const enrolled=await enrollment;if(!enrolled.ok())throw new Error('enrollment failed: '+await enrolled.text());
  await page.waitForTimeout(700);
  await page.locator('#captureKind').selectOption('checkin');
  if(await page.locator('#experimentalToggle').count())await page.locator('#experimentalToggle').check();
  await record(page,3.4);
  const usual=await upload(page);
  if(usual.status==='no_change'){
    await page.locator('#routineNoteText').fill('Fictional patient report despite a typical acoustic reading.');
    const reportSaved=page.waitForResponse(r=>r.request().method()==='POST' && /\/reports$/.test(new URL(r.url()).pathname));
    await page.locator('#saveRoutineNoteBtn').click();
    const savedReport=await reportSaved;if(!savedReport.ok())throw new Error('Routine report failed '+await savedReport.text());
    report.patient_report_without_acoustic_trigger='PASS';
  }
  // Use another real browser file-backed microphone to produce the changed
  // reading. No recording blob is injected into page state.
  const saved=await context.storageState();await active.browser.close();
  active=await launch(process.env.CADENCE_DEVIANT_WAV,saved);({page,context}=active);
  await connect(page);
  let last=usual;
  for(let repeat=0;repeat<3 && last.status!=='awaiting_answer';repeat++){
    await page.locator('#captureKind').selectOption('checkin');
    if(await page.locator('#experimentalToggle').count())await page.locator('#experimentalToggle').check();
    await record(page,6.8);
    last=await upload(page);
  }
  if(last.status!=='awaiting_answer')throw new Error('Persistent change did not trigger');
  await page.locator('#answerText').waitFor({state:'visible',timeout:30000});
  const desktop='/private/tmp/cadence-ui-desktop.png';await page.screenshot({path:desktop,fullPage:true});report.screenshots.push(desktop);
  // Reload before answering, requiring the session's pending question to restore.
  await page.reload();await page.locator('#answerText').waitFor({state:'visible',timeout:30000});
  report.pending_question_reload=true;
  const spokenQuestion=page.waitForResponse(r=>new URL(r.url()).pathname==='/speak');
  await page.locator('#speakQuestionBtn').click();await spokenQuestion;
  report.tts_question_request='PASS (stub response)';
  await page.locator('#answerText').fill('');
  const requestsBeforeASR=answerRequests;
  await page.locator('#recordAnswerBtn').click();
  await page.waitForFunction(()=>!document.querySelector('#stopAnswerBtn').disabled);
  await page.waitForTimeout(2200);
  const transcript=page.waitForResponse(r=>new URL(r.url()).pathname==='/transcribe');
  await page.locator('#stopAnswerBtn').click();await transcript;
  await page.waitForFunction(()=>document.querySelector('#answerText').value.includes('repeat my words'));
  if(answerRequests!==requestsBeforeASR)throw new Error('ASR automatically sent an answer before review');
  report.asr_transcript_editable='PASS (stub response, no automatic send)';
  let terminalSession;
  for(let turn=0;turn<3;turn++){
    await page.locator('#answerText').fill('People ask me to repeat my words. This is a fictional browser test.');
    const answered=page.waitForResponse(r=>r.request().method()==='POST' && /\/turns\/[^/]+\/answer$/.test(new URL(r.url()).pathname));
    await page.locator('#answerBtn').click();
    const response=await answered;if(!response.ok())throw new Error('answer failed '+await response.text());
    const session=await response.json();report.events.push({turn:turn+1,state:session.state,revision:session.revision});
    await page.waitForTimeout(300);
    if(session.state!=='active'){terminalSession=session;break;}
  }
  if(!terminalSession || terminalSession.revision!==3)throw new Error('Expected exactly three explicit answer submissions');
  await page.locator('#confirmBtn').waitFor({state:'visible'});
  await page.locator('#correctionText').fill('Fictional correction: the difficulty was during dinner.');
  const correctionResponse=page.waitForResponse(r=>r.request().method()==='POST' && /\/correction$/.test(new URL(r.url()).pathname));
  await page.locator('#correctionBtn').click();
  const corrected=await correctionResponse;if(!corrected.ok())throw new Error('Correction failed '+await corrected.text());
  const newRevision=await corrected.json();
  if(newRevision.revision!==terminalSession.revision+1)throw new Error('Correction did not increment revision');
  const stale=await page.request.post(BASE+'/profiles/ui-smoke/conversations/'+terminalSession.session_id+'/confirm',{data:{revision:terminalSession.revision}});
  if(stale.status()!==409)throw new Error('Stale revision was not rejected');
  report.correction_and_stale_confirmation='PASS';
  const spokenNote=page.waitForResponse(r=>new URL(r.url()).pathname==='/speak');
  await page.locator('#speakNoteBtn').click();await spokenNote;
  report.tts_note_readback='PASS (stub response)';
  const confirmation=page.waitForResponse(r=>r.request().method()==='POST' && /\/conversations\/[^/]+\/confirm$/.test(new URL(r.url()).pathname));
  await page.locator('#confirmBtn').click();
  const confirmed=await confirmation;if(!confirmed.ok())throw new Error('confirmation failed '+await confirmed.text());
  report.note_confirmation='PASS';
  // Start a separate real recorded check-in, then choose the explicit user
  // stop path. Unanswered content must stay closed and unresolved, not answered.
  await page.locator('#captureKind').selectOption('checkin');
  await page.locator('#verifyPassageToggle').uncheck();
  await record(page,6.8);
  const nextCheckin=await upload(page);
  if(nextCheckin.status!=='awaiting_answer')throw new Error('Second conversation did not open after changed reading');
  await page.locator('#finishConversationBtn').waitFor({state:'visible'});
  const stoppedQuestion=await page.locator('#questionText').innerText();
  const finishResponse=page.waitForResponse(r=>r.request().method()==='POST' && /\/conversations\/[^/]+\/finish$/.test(new URL(r.url()).pathname));
  await page.locator('#finishConversationBtn').click();
  const finish=await finishResponse;if(!finish.ok())throw new Error('Finish-for-now failed '+await finish.text());
  const finished=await finish.json();
  const unanswered=finished.turns.find(turn=>turn.question.text===stoppedQuestion);
  if(finished.state!=='abstained' || !finished.note.session_ended_by_user || !unanswered?.closed_at || unanswered.answer!==null || unanswered.answered_at!==null || unanswered.resolved!==false)throw new Error('Finish-for-now changed or resolved unanswered content');
  await page.waitForFunction(()=>document.querySelector('#noteUnresolved').textContent.includes('before all questions were answered'));
  const finishConfirmation=page.waitForResponse(r=>r.request().method()==='POST' && /\/conversations\/[^/]+\/confirm$/.test(new URL(r.url()).pathname));
  await page.locator('#confirmBtn').click();
  const finishConfirmed=await finishConfirmation;if(!finishConfirmed.ok())throw new Error('Stopped conversation could not be confirmed');
  const confirmedStopped=await finishConfirmed.json();
  if(confirmedStopped.state!=='confirmed' || !confirmedStopped.note.unresolved.length)throw new Error('Confirmation lost finish-for-now uncertainty');
  report.finish_for_now={state_before_confirmation:finished.state,pending_question_retained:true,
    unanswered_closed_at:true,answer_stays_null:true,resolved_stays_false:true,uncertainty_visible:true,confirmed:true};
  await page.waitForTimeout(400);
  const finalDesktop='/private/tmp/cadence-ui-final-desktop.png';await page.screenshot({path:finalDesktop,fullPage:true});report.screenshots.push(finalDesktop);
  await page.reload();await page.waitForTimeout(700);
  await page.locator('#historyBtn').click();await page.locator('#historyList').waitFor({state:'visible'});
  if(!(await page.locator('#historyList').innerText()).trim())throw new Error('History empty after reload');
  report.history_reload='PASS';
  await page.setViewportSize({width:375,height:812});
  await page.waitForTimeout(250);
  const cleanMobile='/private/tmp/cadence-ui-mobile.png';await page.screenshot({path:cleanMobile,fullPage:true});report.screenshots.push(cleanMobile);
  await page.locator('#checkinBtn').click();
  await page.evaluate(()=>{window.__realGetUserMedia=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Denied for browser test','NotAllowedError');};});
  await page.locator('#recordBtn').click();
  await page.waitForFunction(()=>document.querySelector('#errorMessage').textContent.includes('permission was denied'));
  report.simulated_microphone_denial_visible=true;
  await page.evaluate(()=>{navigator.mediaDevices.getUserMedia=window.__realGetUserMedia;});
  // Narrow viewport plus keyboard navigation and controlled backend failure.
  await page.setViewportSize({width:375,height:812});
  await page.waitForTimeout(250);
  const width=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));
  if(width.scroll>width.viewport+1)throw new Error('Mobile horizontal overflow: '+JSON.stringify(width));
  const mobile='/private/tmp/cadence-ui-mobile-error.png';await page.screenshot({path:mobile,fullPage:true});report.screenshots.push(mobile);
  report.mobile_no_horizontal_overflow=true;
  await openSettings(page);
  await page.locator('#profileId').focus();await page.keyboard.press('Tab');
  const focus=await page.evaluate(()=>document.activeElement.id);if(!focus)throw new Error('Keyboard focus lost');
  report.keyboard_focus=focus;
  await page.route('**/profiles/ui-smoke',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Intentional browser test outage'})}));
  await page.locator('#connectBtn').click();
  await page.waitForFunction(()=>document.querySelector('#errorMessage').textContent.trim().length>0);
  report.backend_error_visible=true;
  await page.unroute('**/profiles/ui-smoke');
  await page.locator('#connectBtn').click();await page.waitForTimeout(500);
  if(errors.length)throw new Error('Browser JS errors: '+errors.join(';'));
  report.javascript_errors=errors;
  console.log(JSON.stringify(report));
 }catch(error){
   try { await active.page.screenshot({path:'/private/tmp/cadence-ui-failure.png',fullPage:true});
     console.error('UI state:',(await active.page.locator('body').innerText()).slice(-5000)); } catch {}
   throw error;
 }finally{await active.browser.close();}
})().catch(error=>{console.error(error.stack || error.message);process.exitCode=1;});
