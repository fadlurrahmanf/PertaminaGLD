import { bridgeFetch } from './bridge-client.js';
import { CHART_COLORS, state as legacyState } from './state.js';
import { showAlert } from './ui.js';
import { drawOneChart, runningDisplayHistory } from './chart.js';
import { formatGas } from './serial-protocol.js';

const $ = id => document.getElementById(id);
const sensors = ['MQ8','MQ135','MQ3','MQ5','MQ4','MQ7','MQ6','MQ2'];
const stepNames = ['connection','file','fields','mode','label'];
const prefix = '/api/dataset-workflow';
let snapshot = {state:'idle',devices:[],history:[],fields:{gain:false,status:false},mode:'direct',count:0};
let busy = false, initialized = false, revision = 0, syncing = false, error = '', syncError = '';
let observedRevision = -1;
let pendingStopNotice = false;
// Chart-only history extends the server's one-hour UI snapshot while this page
// stays open. CSV, ledger, latest readings and the ten-row table stay raw.
// A 24-hour moving average needs one extra hour of raw history to draw the
// earliest point in the chart's one-hour visible range at full window length.
const VISUAL_HISTORY_LIMIT = 180001;
let visualHistory = [], visualLedgerPath = '', visualHistoryVersion = 0, chartCache = null;
const visualKeys = new Set();
let averageEnabled = false;
let visualBackfillPending = false, visualBackfillError = '';
// Rendering-only animation clock; never changes workflow samples or state.
let workflowFrameKey = "", workflowFrameStarted = 0;
let formLoaded = false;
const activeStates = new Set(['starting','recording','pausing','paused','resuming','continuing','recovering','replaying','stopping','stop_pending','cleanup_wait','cleanup_pending']);
const titles = {idle:'Belum merekam',disconnected:'Belum terhubung',ready:'Menunggu Start',connecting:'Menghubungkan GLD…',starting:'Memulai rekaman…',
  recording:'Merekam',pausing:'Menyelesaikan jeda…',paused:'Dijeda',resuming:'Melanjutkan rekaman…',continuing:'Melanjutkan rekaman…',recovering:'Menunggu hotspot GLD…',
  replaying:'Memulihkan data…',stopping:'Menyelesaikan CSV…',stop_pending:'Menunggu konfirmasi Stop…',
  stopped:'Rekaman berhenti',complete:'Rekaman selesai',incomplete:'Sesi tidak lengkap',cleanup_wait:'Menunggu penutupan sesi GLD…',
  cleanup_pending:'Menutup sesi GLD…',error:'Perlu diperiksa'};
const settingIds=['wfScan','wfDevice','wfConnect','wfDisconnect','wfChooseFile','wfDefaultFile','wfPrediction','wfGain','wfSensorStatus','wfMode','wfModeDirect','wfModeReplay','wfLabel'];

function selectedMode(){return $('wfModeReplay').checked?'replay':'direct';}
function setMode(mode){$('wfModeDirect').checked=mode!=='replay';$('wfModeReplay').checked=mode==='replay';}
function csvVerificationText(value) {
  const check=value.verification||{};
  const matched=Number.isInteger(check.matched_count)?check.matched_count:check.verified?check.count:null;
  const stored=Number.isInteger(check.stored_count)?check.stored_count:check.verified?value.count:null;
  if(check.verified&&Number.isInteger(matched)&&Number.isInteger(stored))
    return `CSV: ${matched}/${stored} baris tersimpan terverifikasi terhadap ledger.`;
  if(check.attempted===true&&Number.isInteger(matched)&&Number.isInteger(stored)&&['complete','incomplete','error'].includes(value.state))
    return `CSV: ${matched}/${stored} baris tersimpan cocok dengan ledger; verifikasi keseluruhan gagal. ${check.message||''}`;
  if(value.count&&['complete','incomplete','error'].includes(value.state))
    return value.cleanup_pending?'CSV: verifikasi menunggu penutupan sesi perangkat.':`CSV: verifikasi belum berhasil. ${check.message||''}`;
  return value.count?'CSV disimpan selama merekam; verifikasi dilakukan saat Stop.':'CSV belum direkam.';
}
function sessionEvidence(value) {
  const cause=value.cause||{};
  const closure=value.session_closure_status;
  const session=value.start_rejected===true&&value.count===0
    ?'Sesi: Mulai ditolak GLD sebelum rekaman; belum ada sampel atau sesi perangkat yang diterima.'
    :value.state==='complete'&&value.complete===true
    ?'Sesi: lengkap; penutupan normal terkonfirmasi.'
    :value.state==='incomplete'
      ?closure==='confirmed_normal'?'Sesi: penutupan normal terkonfirmasi, tetapi verifikasi file atau kelengkapan keseluruhan belum berhasil.'
        :closure==='confirmed_incomplete'?'Sesi: perangkat melaporkan akhir sesi tidak lengkap.'
          :closure==='cleanup_confirmed'?'Sesi: penutupan cleanup terkonfirmasi; rekaman publik tetap tidak lengkap.'
            :value.cleanup_pending?'Sesi: tidak lengkap; penutupan perangkat belum terkonfirmasi.'
              :'Sesi: tidak lengkap; penutupan normal belum terkonfirmasi.'
      :['recording','paused','replaying','recovering','stopping','stop_pending'].includes(value.state)
        ?'Sesi: masih berlangsung atau menunggu penutupan.':'Sesi: belum dimulai.';
  const reason=!value.ledger_path&&!value.recent_diagnostic_path?'Penyebab: belum ada sesi.'
    :cause.code&&cause.code!=='reason_unavailable'
    ?`Penyebab tercatat: ${cause.code}${cause.description?` — ${cause.description}`:''}`
    :'Penyebab: belum diketahui.';
  const total=value.device_final_total;
  const device=Number.isInteger(total?.count)&&total?.status!=='unknown'
    ?`Total sampel dari perangkat: ${total.count} (${total.status==='reconciled'?'urutan sesi perangkat direkonsiliasi; cakupan CSV terpisah':'dilaporkan; rekonsiliasi belum terkonfirmasi'}).`
    :'Total sampel sesi dari perangkat: belum diketahui.';
  const reconcile={confirmed:'Rekonsiliasi: selesai dan terkonfirmasi.',cleanup_confirmed:'Rekonsiliasi: penutupan cleanup terkonfirmasi; sesi akuisisi tetap tidak lengkap.',pending:'Rekonsiliasi: masih menunggu konfirmasi perangkat.',unconfirmed:'Rekonsiliasi: penutupan normal belum terkonfirmasi.',not_started:'Rekonsiliasi: belum dimulai.'};
  const path=value.diagnostic_path?`${value.diagnostic_error?'Lokasi catatan diagnostik yang dituju':'Catatan diagnostik'}: ${value.diagnostic_path}`
    :value.recent_diagnostic_path?`Catatan sesi sebelumnya: ${value.recent_diagnostic_path}`
      :value.ledger_path?'Catatan diagnostik historis tidak tersedia.':'Catatan diagnostik: belum ada sesi.';
  return {session,reason,device,reconcile:reconcile[value.reconciliation_status]||'Rekonsiliasi: status belum diketahui.',path};
}
function readiness() {
  const source=snapshot.wizard_steps||{...snapshot.steps,connection:snapshot.steps?.scan&&snapshot.steps?.device&&snapshot.steps?.connection};
  const result={};let previous=true;
  for(const name of stepNames){previous=previous&&Boolean(source?.[name]);result[name]=previous;}
  return result;
}

function apply(value) {
  if(!value || typeof value !== 'object') return;
  if(Number.isInteger(value.revision)) {
    if(value.revision < observedRevision) return;
    observedRevision=value.revision;
  }
  const resetHistory=value.ledger_path===''&&Boolean(snapshot.ledger_path);
  let history=value.history||(resetHistory?[]:snapshot.history||[]);
  const row=value.sample;
  if(!value.history&&row&&Array.isArray(row.sensor_voltage)&&row.sensor_voltage.length===8&&row.sensor_voltage.every(Number.isFinite)) {
    history=[...history.filter(saved=>!(saved.session_id===row.session_id&&saved.seq===row.seq)),row].slice(-7200);
  }
  snapshot={...snapshot,...value,history};
  mergeVisualHistory(value);
  if(!formLoaded) {
    $('wfLabel').value=snapshot.label||'clear_air_test';setMode(snapshot.mode||'direct');
    for(const [id,key] of [['wfPrediction','prediction'],['wfGain','gain'],['wfSensorStatus','status']])$(id).checked=Boolean(snapshot.fields?.[key]);
    formLoaded=true;
  }
  if(snapshot.configuration_frozen||snapshot.ledger_path) {
    // A frozen session may be started by another local client. Show its actual
    // immutable settings without overwriting an operator's editable draft.
    $('wfLabel').value=snapshot.label||'clear_air_test';setMode(snapshot.mode||'direct');
    for(const [id,key] of [['wfPrediction','prediction'],['wfGain','gain'],['wfSensorStatus','status']])$(id).checked=Boolean(snapshot.fields?.[key]);
  }
  render();
  if(pendingStopNotice&&snapshot.verification?.verified&&['stopped','complete','incomplete'].includes(snapshot.state)) {
    pendingStopNotice=false;
    const evidence=sessionEvidence(snapshot);
    showAlert(`${csvVerificationText(snapshot)}\n${evidence.session}\n${evidence.reason}\n${evidence.device}\n${snapshot.csv_path}`,snapshot.complete===false?'warn':'ok','Hasil verifikasi CSV');
  }
}

function mergeVisualHistory(value) {
  const ledger=snapshot.ledger_path||'';
  if(ledger!==visualLedgerPath){
    visualHistory=[];visualKeys.clear();visualLedgerPath=ledger;visualHistoryVersion++;
    visualBackfillError='';
  }
  const incoming=Array.isArray(value.history)?value.history:value.sample?[value.sample]:[];
  appendVisualRows(incoming);
}

function appendVisualRows(incoming) {
  for(const row of incoming){
    if(!row||!Number.isInteger(row.seq)||!Number.isFinite(row.timestamp_ms)||
       !Array.isArray(row.sensor_voltage)||row.sensor_voltage.length!==8||
       !row.sensor_voltage.every(Number.isFinite))continue;
    const key=`${row.boot_id}|${row.session_id}|${row.seq}`;
    if(visualKeys.has(key))continue;
    visualKeys.add(key);
    const previous=visualHistory.at(-1);
    const delta=previous&&row.boot_id===previous.boot_id?row.timestamp_ms-previous.timestamp_ms:500;
    const breakBefore=Boolean(previous&&(row.boot_id!==previous.boot_id||
      row.session_id!==previous.session_id||row.seq!==previous.seq+1||delta>1000||delta<0));
    visualHistory.push({boot_id:row.boot_id,session_id:row.session_id,seq:row.seq,
      row_id:Number.isInteger(row.row_id)?row.row_id:null,
      timestamp_ms:row.timestamp_ms,sensor_voltage:[...row.sensor_voltage],
      ts:(previous?.ts||0)+Math.max(0,delta),breakBefore});
    visualHistoryVersion++;
  }
  if(visualHistory.length>VISUAL_HISTORY_LIMIT){
    const removed=visualHistory.splice(0,visualHistory.length-VISUAL_HISTORY_LIMIT);
    for(const old of removed)visualKeys.delete(`${old.boot_id}|${old.session_id}|${old.seq}`);
  }
}

async function maybeBackfillVisualHistory() {
  const ledger=visualLedgerPath,settings=averageSettings();
  if(!settings.enabled||!ledger||visualBackfillPending||snapshot.count<=(snapshot.history||[]).length)return;
  const first=Math.max(0,visualHistory.findLastIndex(point=>point.breakBefore));
  const count=visualHistory.length-first;
  const span=count>1?visualHistory.at(-1).ts-visualHistory[first].ts:0;
  const rangeMs=Number($('wfRange').value||3600)*1000;
  const neededCount=Math.min(VISUAL_HISTORY_LIMIT,settings.count+Math.ceil(rangeMs/500));
  const neededSpan=Math.min((VISUAL_HISTORY_LIMIT-1)*500,settings.durationMs+rangeMs);
  if(settings.byDuration?span>=neededSpan:count>=neededCount)return;
  visualBackfillPending=true;visualBackfillError='';
  try {
    const response=await bridgeFetch(prefix+'/chart-history',{timeoutMs:30000});
    if(ledger!==visualLedgerPath||response?.ledger_path!==ledger||!Array.isArray(response.history))return;
    const live=visualHistory;
    const serverTail=response.history.at(-1);
    const serverRowId=serverTail?.row_id;
    const hasComparableIds=Number.isInteger(serverRowId)&&live.every(row=>Number.isInteger(row.row_id));
    const tailKey=serverTail?`${serverTail.boot_id}|${serverTail.session_id}|${serverTail.seq}`:'';
    const overlapIndex=hasComparableIds?-1:live.findIndex(row=>`${row.boot_id}|${row.session_id}|${row.seq}`===tailKey);
    const newerLive=!serverTail?live:hasComparableIds
      ?live.filter(row=>row.row_id>serverRowId)
      :overlapIndex>=0?live.slice(overlapIndex+1)
        :live.filter(row=>row.boot_id===serverTail.boot_id&&
          row.session_id===serverTail.session_id&&row.seq>serverTail.seq);
    visualHistory=[];visualKeys.clear();visualHistoryVersion++;
    appendVisualRows(response.history);
    appendVisualRows(newerLive);
    draw();
  } catch(failure) {
    if(ledger===visualLedgerPath){visualBackfillError='Riwayat lama belum dapat dimuat; grafik memakai data yang tersedia.';draw();}
  } finally {visualBackfillPending=false;}
}

function configuration() {
  return {label:$('wfLabel').value,mode:selectedMode(),fields:{prediction:$('wfPrediction').checked,
    gain:$('wfGain').checked,status:$('wfSensorStatus').checked,timing:false}};
}

function primaryCommand() {
  if(snapshot.state==='recording')return 'pause';
  if(snapshot.state==='paused')return 'resume';
  return snapshot.can_continue||snapshot.configuration_frozen||snapshot.ledger_path||snapshot.segment_id>1?'continue':'start';
}

// The value is last-reported metadata, not proof that RF reception works.
function radioAutoTxText(value) {
  if (!value.connected) return '';
  if (value.radio_auto_tx === false) return 'LoRa Auto TX OFF (laporan terakhir); TX otomatis tidak akan dijadwalkan; jendela RX biasanya mengikuti TX. Periksa QC melalui serial bila diperlukan; rekaman sensor tetap bisa digunakan. Jika diubah lewat QC, setelah rekaman berhenti Connect ulang untuk mencoba memperbarui.';
  if (value.radio_auto_tx === true) return 'LoRa Auto TX ON (laporan terakhir; bukan bukti penerimaan RX). Jika diubah lewat QC, setelah rekaman berhenti Connect ulang untuk mencoba memperbarui.';
  return 'Status Auto TX LoRa belum diketahui atau sudah lama. Periksa QC melalui serial bila diperlukan; rekaman sensor tetap bisa digunakan.';
}

function render() {
  const active=activeStates.has(snapshot.state)||snapshot.cleanup_pending===true;
  const paused=snapshot.state==='paused';
  const locked=snapshot.locked===true;
  const frozen=snapshot.configuration_frozen===true||Boolean(snapshot.ledger_path);
  const retryCleanup=snapshot.cleanup_pending===true&&snapshot.cleanup_paused===true&&!snapshot.connected;
  const steps=readiness();
  for(const id of settingIds) $(id).disabled=busy||locked||active;
  if(frozen) for(const id of ['wfScan','wfDevice','wfChooseFile','wfDefaultFile','wfPrediction','wfGain','wfSensorStatus','wfMode','wfModeDirect','wfModeReplay','wfLabel'])$(id).disabled=true;
  // An owned session may need an explicit retry after transport/disk failure.
  // Only Connect reopens; credentials stay in the backend and ownership stays fixed.
  if(retryCleanup) $('wfConnect').disabled=busy;
  $('wfConnect').textContent=retryCleanup?'Hubungkan ulang':'Connect';
  $('wfDevice').disabled ||= !(snapshot.devices||[]).length;
  $('wfConnect').disabled ||= !snapshot.selected_device_id||snapshot.connected;
  $('wfDisconnect').disabled ||= !snapshot.connected;
  $('wfChooseFile').disabled ||= !snapshot.connected||!snapshot.ready;
  $('wfDefaultFile').disabled ||= !snapshot.connected||!snapshot.ready;
  for(const id of ['wfPrediction','wfGain','wfSensorStatus'])$(id).disabled ||= !steps.file;
  for(const id of ['wfMode','wfModeDirect','wfModeReplay'])$(id).disabled ||= !steps.fields;
  $('wfLabel').disabled ||= !steps.mode;
  $('wfPrediction').disabled ||= !snapshot.prediction_available;
  $('wfPredictionInfo').textContent=!steps.file?'Hubungkan GLD dan pilih file CSV terlebih dahulu.':snapshot.prediction_available
    ? 'Aktifkan untuk mengisi kolom Predicted Class dan Confidence. Saat pemanasan, keduanya masih kosong.'
    : snapshot.connected ? 'Prediksi belum tersedia pada perangkat ini. Rekaman delapan sensor tetap dapat digunakan.'
      : 'Ketersediaan prediksi diperiksa setelah Connect.';
  const devices=snapshot.devices||[];
  const options=[...$('wfDevice').options];
  if(options.length!==devices.length+1||devices.some((d,i)=>options[i+1]?.value!==d.device_id)) {
    $('wfDevice').replaceChildren(new Option(devices.length?'Pilih GLD…':'Scan untuk mencari GLD…',''),
      ...devices.map(d=>new Option(d.name||`GLD-${d.device_id}`,d.device_id)));
  }
  $('wfDevice').value=snapshot.selected_device_id||'';
  $('wfScanInfo').textContent=snapshot.scanned
    ? devices.length ? `${devices.length} GLD ditemukan.` : 'GLD belum terlihat. Periksa daya dan hotspot, lalu Scan lagi.'
    : 'Belum melakukan scan.';
  $('wfConnection').dataset.connected=String(Boolean(snapshot.connected&&snapshot.ready));
  $('wfConnection').textContent=snapshot.connected
    ? snapshot.ready?`Connected · GLD-${snapshot.device_id||snapshot.selected_device_id}`:'Terhubung · perangkat belum siap'
    : frozen&&!snapshot.cleanup_pending&&['complete','incomplete'].includes(snapshot.state)
      ? `Sesi ditutup · GLD-${snapshot.device_id||snapshot.selected_device_id}`:'Belum terhubung';
  const radioHint=$('wfRadioAutoTx');
  if(radioHint){const text=radioAutoTxText(snapshot);radioHint.hidden=!text;radioHint.textContent=text;}
  $('wfPath').textContent=snapshot.csv_path||'Belum ada lokasi dipilih.';
  $('wfLabelStamp').textContent=snapshot.label_timestamp||'--:-- Hari dd/mm/yy';
  $('wfLabelPreview').textContent=snapshot.label_timestamp?`${snapshot.label_timestamp} ${$('wfLabel').value}`:'Timestamp dibuat setelah lokasi CSV dipilih. Label ini terpisah dari hasil prediksi model.';
  for(const name of stepNames) {
    const element=document.querySelector(`[data-wf-step="${name}"]`);
    if(element) element.dataset.ready=String(Boolean(steps[name]));
  }
  const prepared=stepNames.every(name=>steps[name]);
  $('wfLock').checked=locked;
  $('wfLock').disabled=busy||active||(!locked&&!prepared);
  $('wfLockInfo').textContent=frozen?'CSV sudah dimulai. Continue memakai pengaturan yang sama; gunakan Reset sesi untuk mengubahnya.':locked?'Pengaturan terkunci selama sesi.':prepared
    ? 'Aktifkan Lock untuk menampilkan kontrol rekaman.':'Lengkapi lima langkah secara berurutan sebelum mengunci.';
  $('wfControls').hidden=!locked;
  const primary=primaryCommand();
  const primaryLabel={start:'Start',pause:'Pause',resume:'Resume',continue:'Continue'}[primary];
  $('wfPrimaryLabel').textContent=primaryLabel;
  $('wfPrimary').dataset.command=primary;
  $('wfPrimary').setAttribute('aria-label',`${primaryLabel} rekaman`);
  $('wfPrimaryPlay').hidden=primary==='pause';$('wfPrimaryPause').hidden=primary!=='pause';
  $('wfPrimary').disabled=busy||!locked||(['pause','resume'].includes(primary)
    ? !['recording','paused'].includes(snapshot.state)||snapshot.cleanup_pending===true
    : active||(frozen&&!snapshot.can_continue)||(!snapshot.can_continue&&(!snapshot.connected||!snapshot.ready)));
  $('wfStop').disabled=busy||!locked||!active||snapshot.cleanup_pending===true||['starting','stopping','stop_pending','cleanup_wait','cleanup_pending'].includes(snapshot.state);
  const resetButton=$('wfReset');if(resetButton)resetButton.disabled=busy||(active&&!paused);
  $('wfExport').disabled=busy||!snapshot.count||!snapshot.csv_path;
  $('wfState').textContent=snapshot.start_rejected&&snapshot.count===0?'Mulai ditolak':titles[snapshot.state]||snapshot.state||'Belum merekam';
  $('wfCount').textContent=`${snapshot.count||0} sampel tersimpan`;
  $('wfVerification').textContent=csvVerificationText(snapshot);
  const evidence=sessionEvidence(snapshot);
  $('wfSessionStatus').textContent=evidence.session;
  $('wfCause').textContent=evidence.reason;
  $('wfDeviceTotal').textContent=evidence.device;
  $('wfReconciliation').textContent=evidence.reconcile;
  $('wfDiagnosticPath').textContent=evidence.path;
  $('wfDiagnosticError').textContent=snapshot.diagnostic_error||'';
  const message=(snapshot.start_rejected&&snapshot.count===0?snapshot.error:'')||error||syncError||(retryCleanup?'Penutupan sesi tertunda. Klik Hubungkan ulang untuk menyelesaikan GLD yang sama. CSV lama tidak bertambah.':snapshot.error)||snapshot.message||(snapshot.cleanup_pending
    ?'CSV lama tidak ditambah. Sambungkan kembali ke hotspot GLD agar sesi dapat ditutup.'
    : snapshot.state==='recovering'?'GLD menahan data selama tetap menyala. Hub mencoba menyambung ulang hotspot dan memulihkan CSV yang sama.'
      :snapshot.state==='starting'&&snapshot.start_retry_count>0?'GLD sibuk sesaat; Hub mencoba Mulai lagi setelah penolakan yang terkonfirmasi.'
      :'Pengaturan dapat diedit sebelum Lock. Biarkan backend Operator Hub tetap berjalan selama merekam.');
  $('wfMessage').textContent=message;
  $('wfMessage').dataset.error=String(Boolean(error||syncError||snapshot.error));
  $('wfModeHelp').textContent=selectedMode()==='replay'
    ?'Saat koneksi putus, data ditahan hingga 5 menit selama GLD tetap menyala, lalu dipulihkan ke CSV yang sama.'
    :'CSV berhenti bertambah saat putus. Sesi berikutnya tersedia setelah penutupan sesi selesai.';
  renderRows();renderPrediction();renderSensors();draw();
}

function renderRows() {
  const prediction=Boolean(snapshot.fields?.prediction);
  const columns=['Baris','Waktu GLD',...sensors,...(prediction?['Predicted Class','Confidence']:[])];
  $('wfHeaders').replaceChildren(...columns.map(value=>{const n=document.createElement('th');n.textContent=value;return n;}));
  const records=(snapshot.history||[]).slice(-10).reverse();
  $('wfRows').replaceChildren(...records.map(row=>{
    const tr=document.createElement('tr');
    const p=row.prediction;
    const values=[row.row_id??row.seq,`${(Number(row.timestamp_ms)/1000).toFixed(3)} s`,...(row.sensor_voltage||[]).map(v=>Number(v).toFixed(6))];
    if(prediction) values.push(p?.valid?p.predicted_class:p?.status==='warmup'?'Pemanasan':'—',p?.valid?`${(p.confidence*100).toFixed(1)}%`:'—');
    for(const value of values){const td=document.createElement('td');td.textContent=String(value);tr.append(td);}return tr;
  }));
  if(!records.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=columns.length;td.textContent='Belum ada sampel.';tr.append(td);$('wfRows').append(tr);}
}

function renderPrediction() {
  const row=(snapshot.history||[]).at(-1),prediction=row?.prediction;
  const valid=prediction?.valid===true&&Number.isFinite(prediction.confidence);
  const labels={warmup:'Pemanasan',not_ready:'Model belum siap',error:'Inferensi gagal',disabled:'Nonaktif'};
  $('wfPredictedClass').textContent=valid?`Class ${prediction.predicted_class} · ${formatGas(prediction.gas_class)}`
    : labels[prediction?.status]||(snapshot.fields?.prediction?'Menunggu sampel':'Nonaktif');
  $('wfConfidenceScore').textContent=valid?`${(prediction.confidence*100).toFixed(1)}%`:'—';
  const sampleState=snapshot.state==='paused'?'dijeda':snapshot.state==='complete'||snapshot.state==='stopped'?'rekaman selesai'
    :snapshot.state==='incomplete'&&!snapshot.cleanup_pending?'rekaman tidak lengkap':!snapshot.connected?'menunggu koneksi':'';
  $('wfPredictionState').textContent=!snapshot.fields?.prediction?'Centang Predicted Class + Confidence untuk menyertakan hasil inferensi.'
    : !row?'Prediksi akan tampil bersama sampel pertama.'
      : `Sampel terakhir tersimpan · ${(row.timestamp_ms/1000).toFixed(3)} s${sampleState?' · '+sampleState:''}`;
}

function renderSensors() {
  const row=(snapshot.history||[]).at(-1);
  $('wfReadings').replaceChildren(...sensors.map((name,channel)=>{
    const card=document.createElement('div'),title=document.createElement('strong'),swatch=document.createElement('i');
    card.className='wf-reading';swatch.style.background=CHART_COLORS[channel];swatch.setAttribute('aria-hidden','true');
    title.append(swatch,document.createTextNode(name));
    const value=document.createElement('span'),detail=document.createElement('small');
    value.textContent=Number.isFinite(row?.sensor_voltage?.[channel])?`${row.sensor_voltage[channel].toFixed(6)} V`:'— V';
    detail.textContent=row?`Gain ${row.sensor_gain?.[channel]??'—'} · Status ${row.sensor_status?.[channel]??'—'}`:'Menunggu sampel';
    card.append(title,value,detail);return card;
  }));
}

function averageSettings() {
  const byDuration=$('wfAverageByDuration').checked;
  const integer=(id,min,max,fallback)=>{
    const value=Number($(id).value);
    return Number.isFinite(value)&&Number.isInteger(value)?Math.max(min,Math.min(max,value)):fallback;
  };
  const count=integer('wfAverageCount',1,172800,10);
  const requestedMinutes=integer('wfAverageHours',0,24,0)*60+integer('wfAverageMinutes',0,59,1);
  const totalMinutes=Math.min(1440,Math.max(1,requestedMinutes));
  const hours=Math.floor(totalMinutes/60),minutes=totalMinutes%60;
  return {enabled:averageEnabled,byDuration,count,hours,minutes,
    durationMs:totalMinutes*60000};
}

function averageDurationLabel(hours,minutes) {
  return [hours?`${hours} jam`:'',minutes?`${minutes} menit`:''].filter(Boolean).join(' ')||'1 menit';
}

function movingAverageHistory(history, settings, visibleStart=-Infinity) {
  const voltage=point=>point.sensorVoltage||point.sensor_voltage;
  if(!settings.enabled)return visibleStart===-Infinity?history:history.filter(point=>point.ts>=visibleStart).map(point=>({
    ts:point.ts,sensorVoltage:voltage(point),featureOrder:point.featureOrder||sensors,breakBefore:point.breakBefore}));
  let window=[],head=0;
  const sums=Array(8).fill(0),result=[];
  for(const point of history){
    if(point.breakBefore){window=[];head=0;sums.fill(0);}
    window.push(point);
    for(let channel=0;channel<8;channel++)sums[channel]+=voltage(point)[channel];
    while(window.length-head>1&&(settings.byDuration
      ?point.ts-window[head].ts>settings.durationMs:window.length-head>settings.count)){
      const removed=window[head++];
      for(let channel=0;channel<8;channel++)sums[channel]-=voltage(removed)[channel];
    }
    if(head>4096&&head*2>window.length){window=window.slice(head);head=0;}
    if(point.ts>=visibleStart)result.push({ts:point.ts,
      sensorVoltage:sums.map(sum=>sum/(window.length-head)),
      featureOrder:point.featureOrder||sensors,breakBefore:point.breakBefore});
  }
  return result;
}

function chartFeed() {
  const settings=averageSettings();
  const rangeMs=Number($('wfRange').value||3600)*1000;
  const key=`${visualHistoryVersion}|${rangeMs}|${settings.enabled}|${settings.byDuration}|${settings.count}|${settings.durationMs}`;
  if(chartCache?.key===key)return {history:chartCache.history,now:chartCache.now,height:340};
  const timeline=visualHistory.at(-1)?.ts||0;
  chartCache={key,history:movingAverageHistory(visualHistory,settings,timeline-rangeMs-1000),now:timeline};
  return {history:chartCache.history,now:timeline,height:340};
}

function draw() {
  const canvas=$('wfChart');
  const settings=averageSettings();
  $('wfAverageToggle').setAttribute('aria-pressed',String(settings.enabled));
  $('wfAverageToggle').textContent=settings.enabled?'Average: Aktif':'Average: Mati';
  $('wfAverageOptions').hidden=!settings.enabled;
  $('wfAverageCountField').hidden=settings.byDuration;
  $('wfAverageDurationField').hidden=!settings.byDuration;
  $('wfAverageStatus').textContent=!settings.enabled?'Grafik mentah':settings.byDuration
    ?`Average ${averageDurationLabel(settings.hours,settings.minutes)}`:`Average ${settings.count} data`;
  if(!canvas.clientWidth||!canvas.parentElement)return;
  const minutes=Number($('wfRange').value||60)/60;$('wfRangeValue').textContent=`${minutes} min`;
  const feed=chartFeed();
  const currentStart=Math.max(0,visualHistory.findLastIndex(point=>point.breakBefore));
  const availableCount=visualHistory.length-currentStart;
  const availableMs=availableCount>1?feed.now-visualHistory[currentStart].ts:0;
  const partial=settings.enabled&&(settings.byDuration?availableMs<settings.durationMs:availableCount<settings.count);
  $('wfAverageNote').textContent='Hanya garis grafik yang dirata-ratakan. Angka sensor, tabel, dan CSV tetap mentah. Durasi maksimum 24 jam; riwayatnya dapat dimuat ulang dari catatan sesi.'+
    (partial&&availableCount?` Jendela belum penuh; memakai ${availableCount} data grafik yang tersedia.`:'')+
    (visualBackfillError?` ${visualBackfillError}`:'');
  canvas.setAttribute('aria-label',settings.enabled
    ?`Grafik moving average delapan sensor Dataset GLD, ${$('wfAverageStatus').textContent}`
    :'Grafik delapan sensor Dataset GLD');
  const last=(snapshot.history||[]).at(-1);
  const key=last?`${last.session_id}|${last.boot_id}|${last.seq}`:"";
  if(key!==workflowFrameKey){workflowFrameKey=key;workflowFrameStarted=Date.now();}
  if(['recording','replaying'].includes(snapshot.state) && feed.history.length>1){
    const visualNow=feed.now-500+Math.max(0,Math.min(500,Date.now()-workflowFrameStarted));
    feed.history=runningDisplayHistory(feed.history,visualNow+500,true);
    feed.now=visualNow;
  }
  drawOneChart(canvas,$('wfRange'),null,[],null,feed);
}

async function sync() {
  if(syncing||busy||!legacyState.bridgeAvailable)return;
  syncing=true;const expected=revision;
  try {const value=await bridgeFetch(prefix+'/state');if(expected===revision){syncError='';apply(value);}}
  catch(failure){if(expected===revision){syncError=`Status Dataset belum tersedia: ${failure.message}`;render();}}
  finally{syncing=false;}
}

async function action(command,payload={}) {
  if(busy)return;
  if(!legacyState.bridgeAvailable){error='Jalankan backend Operator Hub terlebih dahulu.';render();return;}
  busy=true;revision++;error='';if(command==='stop')pendingStopNotice=true;if(command==='reset')pendingStopNotice=false;render();
  try {
    if(command==='lock'&&payload.locked) {
      apply(await bridgeFetch(prefix+'/configure',{method:'POST',body:JSON.stringify(configuration())}));
    }
    const result=await bridgeFetch(prefix+'/'+command,{method:'POST',body:JSON.stringify(payload),timeoutMs:command==='choose-file'?180000:45000});
    apply(result);
    if(command==='connect'&&!result.configuration_frozen&&!result.ledger_path&&!result.prediction_available)$('wfPrediction').checked=false;
    if(command==='reset') {
      $('wfLabel').value=result.label||'clear_air_test';setMode(result.mode||'direct');
      $('wfPrediction').checked=false;$('wfGain').checked=false;$('wfSensorStatus').checked=false;
    }
  } catch(failure){error=failure.message;}
  finally{busy=false;revision++;render();await sync();}
}

async function exportCsv() {
  if(busy)return;busy=true;render();
  try{
    const data=await bridgeFetch(prefix+'/export',{method:'POST',body:'{}'});
    const url=URL.createObjectURL(new Blob([data.csv],{type:'text/csv;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download=data.filename;link.click();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(failure){error=failure.message;}finally{busy=false;render();}
}

export function initDatasetWorkflow() {
  if(initialized||!$('datasetWorkflow'))return;initialized=true;
  $('wfScan').addEventListener('click',()=>action('scan'));
  $('wfDevice').addEventListener('change',()=>action('select',{device_id:$('wfDevice').value}));
  $('wfConnect').addEventListener('click',()=>action('connect',{device_id:$('wfDevice').value}));
  $('wfDisconnect').addEventListener('click',()=>action('disconnect'));
  $('wfChooseFile').addEventListener('click',()=>action('choose-file'));
  $('wfDefaultFile').addEventListener('click',()=>action('choose-default-file'));
  for(const id of ['wfLabel','wfModeDirect','wfModeReplay','wfPrediction','wfGain','wfSensorStatus'])$(id).addEventListener('change',()=>action('configure',configuration()));
  $('wfLock').addEventListener('change',()=>action('lock',{locked:$('wfLock').checked}));
  $('wfPrimary').addEventListener('click',()=>action(primaryCommand()));
  $('wfStop').addEventListener('click',()=>action('stop'));
  $('wfReset')?.addEventListener('click',()=>action('reset'));
  $('wfExport').addEventListener('click',exportCsv);
  $('wfRange').addEventListener('input',draw);
  $('wfAverageToggle').addEventListener('click',()=>{averageEnabled=!averageEnabled;draw();if(averageEnabled)void maybeBackfillVisualHistory();});
  for(const id of ['wfAverageByCount','wfAverageByDuration','wfAverageCount','wfAverageHours','wfAverageMinutes']){
    $(id).addEventListener('input',draw);
    $(id).addEventListener('change',()=>{
      const settings=averageSettings();
      if(settings.byDuration){
        $('wfAverageHours').value=String(settings.hours);
        $('wfAverageMinutes').value=String(settings.minutes);
      } else $('wfAverageCount').value=String(settings.count);
      draw();void maybeBackfillVisualHistory();
    });
  }
  $('wfLabel').addEventListener('input',()=>{$('wfLabelPreview').textContent=[snapshot.label_timestamp,$('wfLabel').value].filter(Boolean).join(' ');});
  window.addEventListener('gld-dataset-workflow',event=>apply(event.detail));
  window.addEventListener('gld-bridge-events-open',sync);
  window.addEventListener('resize',draw);new ResizeObserver(draw).observe($('wfChart'));
  $('datasetLegacyExpert')?.addEventListener('toggle',()=>{if($('datasetLegacyExpert').open)window.dispatchEvent(new Event('resize'));});
  window.setInterval(sync,3000);
  window.setInterval(()=>{const canvas=$('wfChart');if(['recording','replaying'].includes(snapshot.state) && Date.now()-workflowFrameStarted < 550 && !document.hidden && canvas &&
    (typeof canvas.getClientRects!=='function'||canvas.getClientRects().length))draw();},50);
  render();sync();
}
