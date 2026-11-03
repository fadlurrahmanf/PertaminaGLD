import { bridgeFetch } from './bridge-client.js';
import { CHART_COLORS, state as legacyState } from './state.js';
import { showAlert } from './ui.js';
import { drawOneChart } from './chart.js';
import { formatGas } from './serial-protocol.js';

const $ = id => document.getElementById(id);
const sensors = ['MQ8','MQ135','MQ3','MQ5','MQ4','MQ7','MQ6','MQ2'];
const stepNames = ['connection','file','fields','mode','label'];
const prefix = '/api/dataset-workflow';
let snapshot = {state:'idle',devices:[],history:[],fields:{gain:false,status:false},mode:'direct',count:0};
let busy = false, initialized = false, revision = 0, syncing = false, error = '', syncError = '';
let observedRevision = -1;
let pendingStopNotice = false;
let formLoaded = false;
const activeStates = new Set(['starting','recording','pausing','paused','resuming','continuing','recovering','replaying','stopping','stop_pending','cleanup_wait','cleanup_pending']);
const titles = {idle:'Belum merekam',disconnected:'Belum terhubung',ready:'Menunggu Start',connecting:'Menghubungkan GLD…',starting:'Memulai rekaman…',
  recording:'Merekam',pausing:'Menyelesaikan jeda…',paused:'Dijeda',resuming:'Melanjutkan rekaman…',continuing:'Melanjutkan rekaman…',recovering:'Menunggu hotspot GLD…',
  replaying:'Memulihkan data…',stopping:'Menyelesaikan CSV…',stop_pending:'Menunggu konfirmasi Stop…',
  stopped:'Rekaman berhenti',complete:'Rekaman selesai',incomplete:'Sesi tidak lengkap',cleanup_wait:'Menunggu penutupan sesi GLD…',
  cleanup_pending:'Menutup sesi GLD…',error:'Perlu diperiksa'};
const settingIds=['wfScan','wfDevice','wfConnect','wfDisconnect','wfChooseFile','wfPrediction','wfGain','wfSensorStatus','wfMode','wfModeDirect','wfModeReplay','wfLabel'];

function selectedMode(){return $('wfModeReplay').checked?'replay':'direct';}
function setMode(mode){$('wfModeDirect').checked=mode!=='replay';$('wfModeReplay').checked=mode==='replay';}
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
  let history=value.history||snapshot.history||[];
  const row=value.sample;
  if(!value.history&&row&&Array.isArray(row.sensor_voltage)&&row.sensor_voltage.length===8&&row.sensor_voltage.every(Number.isFinite)) {
    history=[...history.filter(saved=>!(saved.session_id===row.session_id&&saved.seq===row.seq)),row].slice(-7200);
  }
  snapshot={...snapshot,...value,history};
  if(!formLoaded) {
    $('wfLabel').value=snapshot.label||'clear_air_test';setMode(snapshot.mode||'direct');
    for(const [id,key] of [['wfPrediction','prediction'],['wfGain','gain'],['wfSensorStatus','status']])$(id).checked=Boolean(snapshot.fields?.[key]);
    formLoaded=true;
  }
  render();
  if(pendingStopNotice&&snapshot.verification?.verified&&['stopped','complete','incomplete'].includes(snapshot.state)) {
    pendingStopNotice=false;
    showAlert(`${snapshot.complete===false?'Sesi tidak lengkap. Data yang diterima sudah tersimpan.':'Rekaman selesai.'}\n${snapshot.verification.count??snapshot.count} baris telah diperiksa.\n${snapshot.csv_path}`,snapshot.complete===false?'warn':'ok','CSV terverifikasi');
  }
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

function render() {
  const active=activeStates.has(snapshot.state)||snapshot.cleanup_pending===true;
  const paused=snapshot.state==='paused';
  const locked=snapshot.locked===true;
  const frozen=snapshot.configuration_frozen===true||Boolean(snapshot.ledger_path);
  const retryCleanup=snapshot.cleanup_pending===true&&snapshot.cleanup_paused===true&&!snapshot.connected;
  const steps=readiness();
  for(const id of settingIds) $(id).disabled=busy||locked||active;
  if(frozen) for(const id of ['wfScan','wfDevice','wfChooseFile','wfPrediction','wfGain','wfSensorStatus','wfMode','wfModeDirect','wfModeReplay','wfLabel'])$(id).disabled=true;
  // An owned session may need an explicit retry after transport/disk failure.
  // Only Connect reopens; credentials stay in the backend and ownership stays fixed.
  if(retryCleanup) $('wfConnect').disabled=busy;
  $('wfConnect').textContent=retryCleanup?'Hubungkan ulang':'Connect';
  $('wfDevice').disabled ||= !(snapshot.devices||[]).length;
  $('wfConnect').disabled ||= !snapshot.selected_device_id||snapshot.connected;
  $('wfDisconnect').disabled ||= !snapshot.connected;
  $('wfChooseFile').disabled ||= !snapshot.connected||!snapshot.ready;
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
    : 'Belum terhubung';
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
  $('wfReset').disabled=busy||(active&&!paused);
  $('wfExport').disabled=busy||!snapshot.count||!snapshot.csv_path;
  $('wfState').textContent=titles[snapshot.state]||snapshot.state||'Belum merekam';
  $('wfCount').textContent=`${snapshot.count||0} sampel tersimpan`;
  const verified=snapshot.verification?.verified;
  $('wfVerification').textContent=verified?`CSV terverifikasi · ${snapshot.verification.count??snapshot.count} baris`
    : snapshot.count?'CSV disimpan selama merekam. Verifikasi penuh dilakukan saat Stop.':'CSV belum direkam.';
  const message=error||syncError||(retryCleanup?'Penutupan sesi tertunda. Klik Hubungkan ulang untuk menyelesaikan GLD yang sama. CSV lama tidak bertambah.':snapshot.error)||snapshot.message||(snapshot.cleanup_pending
    ?'CSV lama tidak ditambah. Sambungkan kembali ke hotspot GLD agar sesi dapat ditutup.'
    : snapshot.state==='recovering'?'GLD menahan data selama tetap menyala. Kembali ke hotspot GLD untuk memulihkan CSV yang sama.'
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

function chartFeed() {
  let previous=null,timeline=0;
  const history=(snapshot.history||[]).filter(row=>Array.isArray(row.sensor_voltage)&&row.sensor_voltage.length===8).map(row=>{
    const delta=previous&&row.boot_id===previous.boot_id?row.timestamp_ms-previous.timestamp_ms:500;
    timeline+=Math.max(0,delta);
    const breakBefore=Boolean(previous&&(row.session_id!==previous.session_id||row.seq!==previous.seq+1||delta>1000||delta<0));
    previous=row;return {ts:timeline,sensorVoltage:row.sensor_voltage,featureOrder:sensors,breakBefore};
  });
  return {history,now:timeline,height:340};
}

function draw() {
  const canvas=$('wfChart');if(!canvas.clientWidth||!canvas.parentElement)return;
  const minutes=Number($('wfRange').value||60)/60;$('wfRangeValue').textContent=`${minutes} min`;
  drawOneChart(canvas,$('wfRange'),null,[],null,chartFeed());
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
  for(const id of ['wfLabel','wfModeDirect','wfModeReplay','wfPrediction','wfGain','wfSensorStatus'])$(id).addEventListener('change',()=>action('configure',configuration()));
  $('wfLock').addEventListener('change',()=>action('lock',{locked:$('wfLock').checked}));
  $('wfPrimary').addEventListener('click',()=>action(primaryCommand()));
  $('wfStop').addEventListener('click',()=>action('stop'));
  $('wfReset').addEventListener('click',()=>action('reset'));
  $('wfExport').addEventListener('click',exportCsv);
  $('wfRange').addEventListener('input',draw);
  $('wfLabel').addEventListener('input',()=>{$('wfLabelPreview').textContent=[snapshot.label_timestamp,$('wfLabel').value].filter(Boolean).join(' ');});
  window.addEventListener('gld-dataset-workflow',event=>apply(event.detail));
  window.addEventListener('gld-bridge-events-open',sync);
  window.addEventListener('resize',draw);new ResizeObserver(draw).observe($('wfChart'));
  $('datasetLegacyExpert')?.addEventListener('toggle',()=>{if($('datasetLegacyExpert').open)window.dispatchEvent(new Event('resize'));});
  window.setInterval(sync,3000);render();sync();
}
