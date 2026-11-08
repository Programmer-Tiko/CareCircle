const {chromium}=require(process.env.CADENCE_PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs');
(async()=>{
const browser=await chromium.launch({executablePath:process.env.CADENCE_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+process.env.CADENCE_MIC_WAV]});
try {
const context=await browser.newContext({permissions:['microphone']});const page=await context.newPage();
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto(process.env.CADENCE_BROWSER_URL+'/capture-proof');
await page.locator('#base').fill(process.env.CADENCE_BROWSER_URL);await page.locator('#profile').fill('browser-proof');
for(let i=0;i<3;i++){
 await page.locator('#record').click();await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Recording'));
 await page.waitForTimeout(2200+i*100);
 await page.locator('#stop').click();await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('WAV ready'));
}
const captures=await page.locator('#takes audio').count();if(captures!==3)throw new Error('Expected 3 browser captures');
await page.locator('#enroll').click();await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Enrolled'),null,{timeout:120000});
// Check-in path also gets a genuine MediaRecorder recording before controlled
// long-gap recordings exercise the legacy question/answer/confirm UI branch.
await page.locator('#record').click();await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Recording'));
await page.waitForTimeout(2300);await page.locator('#stop').click();await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('WAV ready'));
await page.locator('#checkin').click();await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Check-in stored')||document.getElementById('status').textContent.startsWith('Question returned'),null,{timeout:120000});
const actualCaptureStatus=await page.locator('#status').innerText();
if(!await page.locator('#questionBox').isVisible()){
 const data=fs.readFileSync(process.env.CADENCE_DEVIANT_WAV).toString('base64');
 for(let i=0;i<2;i++){
  await page.evaluate(data=>{const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));const blob=new Blob([bytes],{type:'audio/wav'});checkinTake={blob,seconds:6,url:URL.createObjectURL(blob)};renderTakes();update();},data);
  await page.locator('#checkin').click();await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Check-in stored')||document.getElementById('status').textContent.startsWith('Question returned'),null,{timeout:120000});
  if(await page.locator('#questionBox').isVisible())break;
 }
}
if(!await page.locator('#questionBox').isVisible())throw new Error('Trigger branch not reached');
await page.locator('#answerText').fill('This is a fictional demo. People ask me to repeat my words.');
await page.locator('#answer').click();await page.locator('#noteBox').waitFor({state:'visible',timeout:120000});
await page.locator('#confirm').click();await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Note confirmed'),null,{timeout:120000});
if(errors.length)throw new Error('Browser JS errors: '+errors.join(';'));
console.log(JSON.stringify({result:'PASS',browser:'installed Chrome headless',microphone:'simulated file input through real MediaRecorder',reference_captures:captures,recorded_checkin_status:actualCaptureStatus,legacy_answer_confirm:'PASS',multi_turn_UI:'not implemented by this page',javascript_errors:errors}));
}finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
