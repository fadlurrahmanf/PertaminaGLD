
  (()=>{
    const root=document.getElementById('gld-dataset-concepts');
    const template=document.getElementById('gld-concept-template');
    const sensors=['MQ8','MQ135','MQ3','MQ5','MQ4','MQ7','MQ6','MQ2'];
    const colors=['#ffa400','#4fd8e0','#ff8a3d','#8fd6ff','#c9a4ff','#ffd166','#6bd47a','#ff6b6b'];
    const stepNames=['connection','file','fields','mode','label'];
    const saved=globalThis.openai?.widgetState?.privateContent?.designs||{};
    const allStates={};
    const svgNS='http://www.w3.org/2000/svg';
    function makeSVG(tag,attrs,text){const n=document.createElementNS(svgNS,tag);for(const [key,value] of Object.entries(attrs||{}))n.setAttribute(key,value);if(text!==undefined)n.textContent=text;return n;}
    root.querySelectorAll('.gld-app').forEach(app=>{
      app.append(template.content.cloneNode(true));
      const key=app.dataset.layout,query=s=>app.querySelector(s),role=n=>query(`[data-role="${n}"]`),field=n=>query(`[data-field="${n}"]`),action=n=>query(`[data-action="${n}"]`);
      const state={segment:1,screen:'Merekam',phase:'recording',scanned:true,selected:'1002',connected:true,file:true,prediction:true,gain:true,quality:true,timing:false,mode:'replay',label:'clear_air_test',locked:true,started:true,verified:false,incomplete:false,count:64,range:'60',hidden:[],space:18,...saved[key]};
      allStates[key]=state;
      field('direct').name=field('replay').name=`mock-recording-mode-${key}`;
      const active=()=>['recording','paused','verifying','lost'].includes(state.phase);
      const feedback=message=>{role('feedback').textContent=message;};
      const gateValues=()=>{let previous=true;return [state.scanned&&state.selected&&(state.connected||state.started),state.file,true,['direct','replay'].includes(state.mode),state.label.trim().length>0].map(value=>previous=previous&&Boolean(value));};
      const persist=()=>{try{globalThis.openai?.setWidgetState?.({modelContent:{designs:Object.fromEntries(Object.entries(allStates).map(([name,s])=>[name,{mode:s.mode,screen:s.screen}]))},privateContent:{designs:allStates}})?.catch(()=>{});}catch{}};
      const sourceRows=()=>Array.from({length:state.count},(_,index)=>({index,time:index*.5,volts:sensors.map((_,channel)=>.115+channel*.092+.014*Math.sin(index*.19+channel*.65)+index*.00007)}));
      function dialog(title,copy,purpose='stop'){
        role('dialog-title').textContent=title;role('dialog-copy').textContent=copy;query('dialog').dataset.purpose=purpose;query('dialog').showModal();
      }
      function reset(){Object.assign(state,{screen:'Siap',phase:'setup',scanned:false,selected:'',connected:false,file:false,prediction:false,gain:true,quality:true,timing:false,mode:'direct',label:'clear_air_test',locked:false,started:false,verified:false,incomplete:false,count:0,hidden:[],segment:0});feedback('Mock direset. Tidak ada file atau perangkat asli yang diubah.');render();persist();}
      function draw(){
        const svg=role('chart'),width=svg.getBoundingClientRect().width;if(width<1)return;
        const height=svg.getBoundingClientRect().height||274,pad={left:43,right:43,top:19,bottom:32},plotW=width-pad.left-pad.right,plotH=height-pad.top-pad.bottom;
        svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.replaceChildren();
        const chartTitle=makeSVG('title',{},'Delapan tegangan sensor GLD — data contoh');svg.append(chartTitle);
        const axisColor=getComputedStyle(app).getPropertyValue('--gld-axis').trim(),gridColor=getComputedStyle(app).getPropertyValue('--gld-grid').trim();
        // SVG accepts computed theme-aware CSS variables directly.
        const grid='var(--gld-grid)',ink='var(--gld-axis)';
        for(let i=0;i<=5;i++){
          const y=pad.top+plotH*i/5;svg.append(makeSVG('line',{x1:pad.left,x2:width-pad.right,y1:y,y2:y,stroke:grid,'stroke-width':1}));
          svg.append(makeSVG('text',{x:pad.left-8,y:y+4,fill:ink,'font-size':11,'text-anchor':'end','font-family':'Consolas,monospace'},(1-i/5).toFixed(1)));
        }
        const visibleSeconds=Number(state.range),ticks=width<400?3:5;
        for(let i=0;i<=ticks;i++){
          const x=pad.left+plotW*i/ticks;svg.append(makeSVG('line',{x1:x,x2:x,y1:pad.top,y2:height-pad.bottom,stroke:grid,'stroke-width':1}));
          const value=-visibleSeconds+visibleSeconds*i/ticks;
          svg.append(makeSVG('text',{x,y:height-12,fill:ink,'font-size':11,'text-anchor':i===0?'start':i===ticks?'end':'middle','font-family':'Consolas,monospace'},`${Math.round(value)} s`));
        }
        svg.append(makeSVG('line',{x1:pad.left,x2:width-pad.right,y1:height-pad.bottom,y2:height-pad.bottom,stroke:ink,'stroke-width':1.5,'stroke-dasharray':'5 4'}));
        if(!state.count){svg.append(makeSVG('text',{x:width/2,y:height/2,fill:ink,'font-size':12,'text-anchor':'middle'},'Pratinjau siap setelah Start'));return;}
        const points=sourceRows().slice(-Math.min(120,state.count)),last=points.at(-1).time;
        sensors.forEach((name,channel)=>{
          if(state.hidden.includes(channel))return;
          let path='';points.forEach((point,index)=>{const x=pad.left+plotW*(1-(last-point.time)/visibleSeconds),y=pad.top+(1-point.volts[channel])*plotH;path+=`${index?' L':'M'}${x.toFixed(2)},${y.toFixed(2)}`;});
          svg.append(makeSVG('path',{d:path,fill:'none',stroke:colors[channel],'stroke-width':1.8,'stroke-linejoin':'round','stroke-linecap':'round','data-mock-series':channel}));
          const y=pad.top+(1-points.at(-1).volts[channel])*plotH;
          svg.append(makeSVG('text',{x:width-pad.right+5,y:y+3,fill:colors[channel],'font-size':11,'font-family':'Consolas,monospace'},name));
        });
      }
      let lastTweakScreen=state.screen;
      function render(){
        const gates=gateValues(),editable=!state.locked&&!active()&&!state.started,rows=sourceRows(),latest=rows.at(-1);
        app.style.setProperty('--gld-space',`${state.space}px`);
        app.querySelectorAll('.gld-step').forEach((step,index)=>{step.dataset.ready=String(gates[index]);step.querySelector('[data-role=step-state]').textContent=gates[index]?'Siap':index&&!gates[index-1]?'Menunggu':'Belum siap';});
        role('gate-count').textContent=`${gates.filter(Boolean).length}/5 siap`;
        role('device-status').textContent=state.connected?'GLD-1002 terhubung':state.phase==='stopped'?'GLD-1002 · sesi ditutup':'GLD belum terhubung';role('connection-dot').dataset.connected=String(state.connected);
        field('device').replaceChildren(new Option(state.scanned?'Pilih GLD…':'Scan terlebih dahulu',''),...(state.scanned?[new Option('GLD-1002','1002')]:[]));field('device').value=state.selected;
        field('device').disabled=!editable||!state.scanned;action('scan').disabled=!editable;action('connect').disabled=active()||state.locked||state.connected||!state.selected;action('disconnect').disabled=active()||state.locked||!state.connected;
        role('connection-hint').textContent=state.connected?'Connected · hotspot GLD':state.scanned?'1 GLD ditemukan. Pilih lalu Connect.':'Scan untuk menemukan hotspot GLD.';
        role('file-name').textContent=state.file?'dataset_gld1002.csv':'Belum ada file dipilih';role('file-name').setAttribute('data-tooltip','Dokumen / GLD / dataset_gld1002.csv');action('file').disabled=!editable||!gates[0];
        ['prediction','gain','quality','timing'].forEach(name=>{field(name).checked=state[name];field(name).disabled=!editable||!gates[1];});
        field('direct').checked=state.mode==='direct';field('replay').checked=state.mode==='replay';field('direct').disabled=field('replay').disabled=!editable||!gates[2];
        role('mode-hint').textContent=state.mode==='replay'?'Tahan hingga 5 menit, pulihkan ke CSV yang sama.':'CSV berhenti bertambah saat koneksi putus.';
        field('label').value=state.label;field('label').disabled=!editable||!gates[3];role('label-stamp').textContent=state.file?'08:00 Selasa 03/11/26':'--:-- Hari dd/mm/yy';
        field('lock').checked=state.locked;field('lock').disabled=active()||(!state.locked&&!gates.every(Boolean));
        role('lock-hint').textContent=state.started?'Skema dan label tetap hingga Reset sesi.':state.locked?'Semua input terkunci dan tetap terbaca.':'Lengkapi lima langkah, lalu aktifkan Lock.';
        const names={setup:'Menyiapkan',ready:'Siap merekam',recording:'Merekam',paused:'Dijeda',verifying:'Memverifikasi CSV',lost:'Koneksi terputus',stopped:state.incomplete?'Sesi tidak lengkap':'Selesai'};
        role('recording-state').textContent=names[state.phase]||'Siap merekam';role('recording-state').dataset.state=state.phase;role('session-file').textContent=state.file?'dataset_gld1002.csv':'Belum ada lokasi CSV';role('count').textContent=`${state.count} sampel`;
        query('.gld-transport').hidden=!state.locked;
        action('start').textContent=state.phase==='stopped'||state.segment>1?'Continue':'Start';action('start').disabled=!state.locked||!gates.every(Boolean)||active()||(state.started&&!state.verified);
        action('pause').textContent=state.phase==='paused'?'Resume':'Pause';action('pause').disabled=!['recording','paused'].includes(state.phase);
        action('stop').disabled=!['recording','paused','lost'].includes(state.phase);if(state.phase==='lost'&&state.mode==='direct')action('stop').disabled=true;
        action('reset').disabled=active()&&state.phase!=='paused';
        role('control-hint').textContent=!state.locked?'Lengkapi 5 langkah lalu Lock untuk menampilkan kontrol.':state.phase==='paused'?'Akuisisi dijeda. Resume melanjutkan sesi yang sama.':state.phase==='stopped'?'Continue menambah segmen dalam CSV yang sama.':state.phase==='lost'?'Pertahankan GLD menyala selama pemulihan.':'CSV disimpan selama merekam. Verifikasi penuh saat Stop.';
        role('recovery').hidden=state.phase!=='lost';role('recovery-title').textContent=state.mode==='replay'?'Menunggu koneksi GLD':'CSV dibekukan · penutupan tertunda';role('recovery-copy').textContent=state.mode==='replay'?'Sampel ditahan hingga 5 menit di RAM. Buffer hilang jika GLD mati.':'Sesi lama perlu diselesaikan sebelum Continue.';
        role('prediction').replaceChildren(document.createTextNode(!latest?'Menunggu sampel':state.prediction?'Clean Air':'Nonaktif'));
        if(latest&&state.prediction){const index=document.createElement('span');index.textContent='Class 0';role('prediction').append(index);}
        role('confidence').replaceChildren(document.createTextNode(latest&&state.prediction?'98.4':'—'));if(latest&&state.prediction){const percent=document.createElement('span');percent.textContent='%';role('confidence').append(percent);}
        field('range').value=state.range;role('chart-caption').textContent=!latest?'Data contoh · belum merekam':`Terakhir tersimpan · ${latest.time.toFixed(1)} s${state.phase==='paused'?' · dijeda':state.phase==='stopped'?' · selesai':''}`;
        role('readings').replaceChildren(...sensors.map((name,index)=>{const button=document.createElement('button'),dot=document.createElement('i'),label=document.createElement('span'),value=document.createElement('small');button.type='button';button.className='gld-series cursor-interaction';button.setAttribute('aria-pressed',String(!state.hidden.includes(index)));button.setAttribute('aria-label',`${state.hidden.includes(index)?'Tampilkan':'Sembunyikan'} seri ${name}`);dot.style.background=colors[index];label.textContent=name;value.textContent=latest?`${latest.volts[index].toFixed(4)} V`:'— V';button.append(dot,label,value);button.addEventListener('click',()=>{state.hidden=state.hidden.includes(index)?state.hidden.filter(item=>item!==index):[...state.hidden,index];render();persist();});return button;}));
        const columns=['No.','Waktu GLD',...sensors,...(state.prediction?['Class','Conf.']:[])],head=document.createElement('tr');columns.forEach(text=>{const th=document.createElement('th');th.textContent=text;head.append(th);});role('headers').replaceChildren(head);
        role('rows').replaceChildren(...rows.slice(-6).reverse().map(row=>{const tr=document.createElement('tr');[String(row.index+1),`${row.time.toFixed(1)} s`,...row.volts.map(v=>v.toFixed(4)),...(state.prediction?['0','98.4%']:[])].forEach(text=>{const td=document.createElement('td');td.textContent=text;tr.append(td);});return tr;}));
        if(!rows.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=columns.length;td.className='gld-empty';td.textContent='Sampel akan tampil setelah Start.';tr.append(td);role('rows').append(tr);}
        role('table-caption').textContent=rows.length?`${Math.min(6,rows.length)} baris terakhir`:'Belum ada sampel';role('verification').dataset.verified=String(state.verified);role('verification').textContent=state.verified?`${state.count} baris terverifikasi${state.incomplete?' · sesi tidak lengkap':''}`:'Verifikasi penuh setelah Stop';action('export').disabled=!state.count;
        draw();lastTweakScreen=state.screen;
      }
      app.addEventListener('click',event=>{
        const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
        switch(button.dataset.action){
          case'scan':state.scanned=true;feedback('Simulasi scan: GLD-1002 ditemukan.');break;
          case'connect':state.connected=true;state.phase='setup';feedback('Simulasi: GLD-1002 Connected. Pilih lokasi CSV.');break;
          case'disconnect':state.connected=false;feedback('Simulasi: koneksi GLD dilepas.');break;
          case'file':state.file=true;feedback('Lokasi contoh dipilih. Pengaturan berikutnya sekarang tersedia.');break;
          case'start':state.segment=state.started?state.segment+1:1;state.connected=true;state.phase='recording';state.screen='Merekam';state.started=true;state.verified=false;state.count+=64;feedback('Mock merekam data contoh. Tidak ada akuisisi perangkat asli.');break;
          case'pause':state.phase=state.phase==='paused'?'recording':'paused';state.screen=state.phase==='paused'?'Dijeda':'Merekam';feedback(state.phase==='paused'?'Akuisisi mock dijeda.':'Akuisisi mock dilanjutkan dalam sesi yang sama.');break;
          case'stop':state.phase='verifying';render();window.setTimeout(()=>{state.phase='stopped';state.screen='Selesai';state.connected=false;state.verified=true;render();persist();dialog('CSV terverifikasi',`Simulasi pemeriksaan selesai. ${state.count} baris data contoh cocok dengan CSV. Continue akan menambah ke file yang sama.`);},600);return;
          case'reset':if(state.phase==='paused'){dialog('Tutup sesi dan Reset?',`${state.count} baris data contoh akan diverifikasi sebelum form direset. File CSV tetap disimpan.`,'reset');return;}reset();return;
          case'recover':state.connected=true;if(state.mode==='replay'){state.count+=12;state.phase='recording';state.screen='Merekam';feedback('Simulasi: 12 sampel tertunda pulih ke CSV yang sama.');}else{state.phase='stopped';state.screen='Selesai';state.verified=true;state.incomplete=true;feedback('Penutupan sesi contoh selesai. Prefix CSV tetap, sesi ditandai tidak lengkap.');}break;
          case'export':{const rows=sourceRows(),headers=['sample','timestamp_ms','label',...sensors,...(state.gain?sensors.map(n=>'gain_'+n):[]),...(state.quality?sensors.map(n=>'status_'+n):[]),...(state.timing?['scan_end_ms','overrun_count']:[]),...(state.prediction?['predicted_class','confidence']:[])];const text=[headers,...rows.map(row=>[row.index+1,row.time*1000,`08:00 Selasa 03/11/26 ${state.label}`,...row.volts.map(v=>v.toFixed(6)),...(state.gain?[1,2,4,8,16,32,64,1]:[]),...(state.quality?Array(8).fill(0):[]),...(state.timing?[row.time*1000+230,0]:[]),...(state.prediction?[0,.984]:[])])].map(row=>row.map(value=>'"'+String(value).replaceAll('"','""')+'"').join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download='MOCK_dataset_gld1002.csv';link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000);feedback('Simulasi Export: CSV contoh disiapkan. File rekaman asli tidak disentuh.');break;}
          case'dismiss':{const purpose=query('dialog').dataset.purpose;query('dialog').close();if(purpose==='reset'){reset();return;}feedback('CSV contoh terverifikasi. Continue tersedia.');break;}
        }
        render();persist();
      });
      app.addEventListener('change',event=>{
        const name=event.target.dataset.field;if(!name)return;
        if(name==='device')state.selected=event.target.value;
        else if(['prediction','gain','quality','timing'].includes(name))state[name]=event.target.checked;
        else if(name==='direct'||name==='replay')state.mode=name;
        else if(name==='label')state.label=event.target.value;
        else if(name==='lock'){state.locked=event.target.checked;state.phase=state.locked?'ready':'setup';state.screen='Siap';}
        else if(name==='range')state.range=event.target.value;
        render();persist();
      });
      render();new ResizeObserver(draw).observe(role('chart'));
      if(globalThis.Tweak){
        const tweak=new Tweak({container:app,onChange:()=>{
          if(state.screen!==lastTweakScreen){const phases={Siap:'ready',Merekam:'recording',Dijeda:'paused',Terputus:'lost',Selesai:'stopped'};state.phase=phases[state.screen];state.started=state.screen!=='Siap';state.count=state.started?Math.max(64,state.count):0;state.verified=state.screen==='Selesai';state.scanned=true;state.selected='1002';state.file=true;state.connected=state.screen!=='Terputus';state.locked=true;}render();
        }});
        tweak.addSelect(state,'screen',{label:'Status layar',options:['Siap','Merekam','Dijeda','Terputus','Selesai']});
        tweak.addSlider(state,'space',{label:'Jarak antarpanel',min:12,max:24,step:2,unit:'px'});
      }
    });
    if(globalThis.lucide)globalThis.lucide.createIcons({attrs:{width:16,height:16}});
  })();
  