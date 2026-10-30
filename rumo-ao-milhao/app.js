/* Rumo ao 1 Milhão 1.1 — dados e cálculos feitos somente neste dispositivo. */
'use strict';
(() => {
  const KEY = 'rumo-ao-milhao-v1';
  const $ = id => document.getElementById(id);
  const by = selector => document.querySelectorAll(selector);
  const money = cents => new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'}).format(cents/100);
  const fmtNumber = cents => (cents/100).toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2});
  const dateLocal = (d=new Date()) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const monthLocal = (d=new Date()) => dateLocal(d).slice(0,7);
  const previousMonthStart = () => {const d=new Date();return dateLocal(new Date(d.getFullYear(),d.getMonth()-1,1));};
  const monthName = month => {const [y,m]=month.split('-').map(Number);return new Intl.DateTimeFormat('pt-BR',{month:'long',year:'numeric'}).format(new Date(y,m-1,1)).replace(/^./,x=>x.toUpperCase());};
  const formatDate = date => { const [y,m,d]=date.split('-'); return `${d}/${m}/${y}`; };
  function isDate(v) {if(!/^\d{4}-\d{2}-\d{2}$/.test(v))return false; const [y,m,d]=v.split('-').map(Number);const x=new Date(y,m-1,d);return x.getFullYear()===y&&x.getMonth()===m-1&&x.getDate()===d&&y>=1900&&y<=2200;}
  function parseCents(input) {
    if (typeof input !== 'string') return null;
    let v = input.trim().replace(/[R$\s\u00a0]/g,'');
    if (!v) return null;
    let sign=1;
    if (v[0]==='-' || v[0]==='−') {sign=-1;v=v.slice(1);} else if(v[0]==='+'){v=v.slice(1);}
    if(!v || !/^[\d.,]+$/.test(v)) return null;
    if(v.includes(',')) {
      if(!/^\d{1,3}(\.\d{3})*(,\d{1,2})?$/.test(v) && !/^\d+(,\d{1,2})?$/.test(v)) return null;
      v=v.replace(/\./g,'').replace(',','.');
    } else if(v.includes('.')) {
      if(/^\d{1,3}(\.\d{3})+$/.test(v)) v=v.replace(/\./g,'');
      else if(!/^\d+\.\d{1,2}$/.test(v))return null;
    }
    const parts=v.split('.');
    if(parts.length>2 || !/^\d+$/.test(parts[0]) || (parts[1]!==undefined && !/^\d{1,2}$/.test(parts[1]))) return null;
    const n=Number(parts[0])*100+Number((parts[1]||'').padEnd(2,'0'));
    return Number.isSafeInteger(n)&&n<=1e14 ? sign*n : null;
  }
  const defaultState = () => ({version:1,setupComplete:false,initialCents:0,goalCents:100000000,startedAt:dateLocal(),entries:[]});
  let state=defaultState();
  let editingId=null;
  let toastTimer;
  function toast(message){const e=$('toast');e.textContent=message;e.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>e.classList.remove('show'),3500);}
  function persist(next){try {localStorage.setItem(KEY,JSON.stringify(next));state=next;return true;}catch(e){console.error('Erro ao salvar:',e);toast('Não foi possível salvar neste iPhone. Confira o espaço disponível.');return false;}}
  const validKind = k => ['yield','deposit','withdrawal'].includes(k);
  function validateBackup(s){
    if(!s||s.version!==1||typeof s.setupComplete!=='boolean'||!Number.isSafeInteger(s.initialCents)||s.initialCents<0||s.initialCents>1e14||!Number.isSafeInteger(s.goalCents)||s.goalCents<=0||s.goalCents>1e14||!isDate(s.startedAt)||!Array.isArray(s.entries)||s.entries.length>20000)throw new Error('Formato de backup incompatível.');
    const seen=new Set(),yieldDates=new Set();
    s.entries.forEach(e=>{
      if(!e||(typeof e.id!=='string'&&typeof e.id!=='number')||String(e.id).length>80||seen.has(String(e.id))||!validKind(e.kind)||!isDate(e.date)||!Number.isSafeInteger(e.cents)||Math.abs(e.cents)>1e14||(e.kind!=='yield'&&e.cents<=0)||typeof e.note!=='string'||e.note.length>100||(e.includedInInitial!==undefined&&typeof e.includedInInitial!=='boolean'))throw new Error('Um dos lançamentos é inválido.');
      seen.add(String(e.id));
      if(e.kind==='yield'){if(yieldDates.has(e.date))throw new Error('O backup contém rendimentos duplicados na mesma data.');yieldDates.add(e.date);}
    });
    return {version:1,setupComplete:s.setupComplete,initialCents:s.initialCents,goalCents:s.goalCents,startedAt:s.startedAt,entries:s.entries.map(e=>({id:String(e.id),kind:e.kind,date:e.date,cents:e.cents,note:e.note,includedInInitial:e.includedInInitial===true}))};
  }
  function load() {try {const raw=localStorage.getItem(KEY);if(raw)state=validateBackup(JSON.parse(raw));}catch(e){console.error('Falha ao carregar dados:',e);state=defaultState();toast('Não foi possível ler os dados salvos. Importe um backup, se tiver.');}}
  function signedAmount(e){return e.kind==='withdrawal'?-e.cents:e.cents;}
  // Lançamentos que já faziam parte do patrimônio inicial são apenas históricos.
  function accountedAmount(e){return e.includedInInitial===true?0:signedAmount(e);}
  function entriesBefore(month){return state.entries.filter(e=>e.date.slice(0,7)<month).reduce((s,e)=>s+accountedAmount(e),0);}
  function monthly(month){const group=state.entries.filter(e=>e.date.startsWith(month));const opening=state.initialCents+entriesBefore(month);
    return {opening,closing:opening+group.reduce((s,e)=>s+accountedAmount(e),0),yield:group.filter(e=>e.kind==='yield').reduce((s,e)=>s+e.cents,0),deposits:group.filter(e=>e.kind==='deposit').reduce((s,e)=>s+e.cents,0),withdrawals:group.filter(e=>e.kind==='withdrawal').reduce((s,e)=>s+e.cents,0),days:new Set(group.filter(e=>e.kind==='yield').map(e=>e.date)).size,count:group.filter(e=>e.kind==='yield').length};}
  const totalBalance=()=>state.initialCents+state.entries.reduce((s,e)=>s+accountedAmount(e),0);
  function renderHome(){
    const total=totalBalance(), target=state.goalCents, remaining=Math.max(0,target-total), pct=target>0?Math.max(0,Math.min(100,total/target*100)):0;
    const mo=monthLocal(),m=monthly(mo);
    $('totalBalance').textContent=money(total);
    $('goalPercent').textContent= `${pct.toLocaleString('pt-BR',{maximumFractionDigits:1})}%`;
    $('goalProgress').style.width=pct+'%';
    $('goalBase').textContent=`${money(total)} acumulados`;
    $('goalTarget').textContent=money(target);
    $('remainingValue').textContent=money(remaining);
    $('remainingSub').textContent=remaining===0?'Meta alcançada! Parabéns!':'Continue avançando';
    $('monthlyYield').textContent=money(m.yield);
    $('yieldCount').textContent=`${m.count} ${m.count===1?'lançamento':'lançamentos'}`;
    $('currentMonthName').textContent=monthName(mo);
    $('monthlyDeposits').textContent=money(m.deposits);
    $('monthlyWithdrawals').textContent=money(m.withdrawals);
    $('monthlyOpening').textContent=money(m.opening);
    $('monthlyEnding').textContent=money(m.closing);
    renderChart();
  }
  function monthsBetween(start,end){ const out=[];const [sy,sm]=start.split('-').map(Number);const [ey,em]=end.split('-').map(Number);let y=sy,m=sm;while(y<ey||(y===ey&&m<=em)){out.push(`${y}-${String(m).padStart(2,'0')}`);m++;if(m>12){m=1;y++;}if(out.length>240)break;}return out; }
  function renderChart(){
    const start=state.startedAt.slice(0,7);
    const months=monthsBetween(start,monthLocal()).slice(-6);
    if(!months.length){$('chartArea').textContent='Sem dados para o gráfico.';return;}
    const vals=months.map(m=>{const group=state.entries.filter(e=>e.date.slice(0,7)<=m);return state.initialCents+group.reduce((s,e)=>s+accountedAmount(e),0);});
    const min=Math.min(...vals),max=Math.max(...vals),range=Math.max(1,max-min);
    const w=330,h=160,top=18,bottom=32,left=8,right=8,usableW=w-left-right,usableH=h-top-bottom;
    const points=vals.map((v,i)=>({x:left+(months.length===1?usableW/2:i*usableW/(months.length-1)),y:top+(max-v)/range*usableH}));
    if(months.length===1)points[0].y=top+usableH/2;
    const line=points.map((p,i)=>`${i?'L':'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const area= `${line} L${points[points.length-1].x},${top+usableH} L${points[0].x},${top+usableH} Z`;
    const labels=months.map((m,i)=>{const [y,mm]=m.split('-').map(Number);let name=new Intl.DateTimeFormat('pt-BR',{month:'short'}).format(new Date(y,mm-1,1)).replace('.','');return `<text x="${points[i].x}" y="${h-11}" font-size="10" text-anchor="middle" fill="#93a59a">${name}</text>`;}).join('');
    const dots=points.map((p,i)=>`<circle cx="${p.x}" cy="${p.y}" r="${i===points.length-1?4.5:2.7}" fill="#168252" stroke="white" stroke-width="1.8"/>`).join('');
    const yLine=[0,.5,1].map(f=>`<line x1="${left}" x2="${w-right}" y1="${top+f*usableH}" y2="${top+f*usableH}" stroke="#eef2ef" stroke-width="1"/>`).join('');
    $('chartArea').innerHTML=`<svg viewBox="0 0 ${w} ${h}" aria-hidden="true" focusable="false"><defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#35a976" stop-opacity=".24"/><stop offset="1" stop-color="#35a976" stop-opacity=".015"/></linearGradient></defs>${yLine}<path d="${area}" fill="url(#chartFill)"/><path d="${line}" fill="none" stroke="#168252" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots}${labels}</svg>`;
    $('chartArea').setAttribute('aria-label',`Evolução patrimonial: ${months.map((m,i)=>`${monthName(m)}: ${money(vals[i])}`).join('; ')}`);
  }
  function typeLabel(k){return k==='yield'?'Rendimento':k==='deposit'?'Aporte':'Retirada';}
  function renderHistory(){
    const mo=$('monthPicker').value||monthLocal(),m=monthly(mo);
    $('historyYield').textContent=money(m.yield);
    $('historyDays').textContent=`${m.days} / 22`;
    const group=state.entries.filter(e=>e.date.startsWith(mo)).sort((a,b)=>b.date.localeCompare(a.date)||String(b.id).localeCompare(String(a.id)));
    $('historySubtitle').textContent=`${group.length} ${group.length===1?'registro':'registros'} em ${monthName(mo)}`;
    const list=$('historyList');list.replaceChildren();
    if(!group.length){const p=document.createElement('div');p.className='empty-state';p.textContent='Nenhum lançamento neste mês. Use “Lançar” para adicionar o primeiro.';list.append(p);return;}
    for(const e of group){
      const row=document.createElement('article');row.className='history-entry';
      const lhs=document.createElement('div');lhs.className='entry-left';
      const mark=document.createElement('div');mark.className='entry-mark'+(e.kind==='withdrawal'?' withdrawal':'');mark.textContent=e.kind==='withdrawal'?'−':e.kind==='deposit'?'+':'↗';
      const info=document.createElement('div');const nm=document.createElement('div');nm.className='entry-name';nm.textContent=typeLabel(e.kind);const dt=document.createElement('div');dt.className='entry-date';dt.textContent=formatDate(e.date);info.append(nm,dt);
      if(e.note){const note=document.createElement('div');note.className='entry-note';note.textContent=e.note;info.append(note);}
      if(e.includedInInitial){const flag=document.createElement('span');flag.className='historical-label';flag.textContent='Já incluído no patrimônio inicial';info.append(flag);}lhs.append(mark,info);
      const rhs=document.createElement('div');rhs.className='entry-right';const value=document.createElement('div');value.className='entry-sum'+(signedAmount(e)<0?' negative':'');value.textContent=`${signedAmount(e)>0?'+':''}${money(signedAmount(e))}`;
      const actions=document.createElement('div');actions.className='action-row';const edit=document.createElement('button');edit.type='button';edit.textContent='Editar';edit.addEventListener('click',()=>beginEdit(e.id));const del=document.createElement('button');del.type='button';del.textContent='Excluir';del.addEventListener('click',()=>removeEntry(e.id));actions.append(edit,del);rhs.append(value,actions);row.append(lhs,rhs);list.append(row);
    }
  }
  function renderSettings(){$('initialBalance').value=fmtNumber(state.initialCents);$('goalAmount').value=fmtNumber(state.goalCents);}
  function renderAll(){renderHome();renderHistory();renderSettings();}
  function navigate(view){if(!['home','add','history','settings'].includes(view))return;
    by('.view').forEach(el=>el.classList.toggle('active',el.id==='view-'+view));
    by('.nav-item').forEach(el=>{const active=el.dataset.view===view;el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    if(view==='history')renderHistory();if(view==='settings')renderSettings();window.scrollTo({top:0,behavior:'instant'});
  }
  function changeKind(kind){if(!validKind(kind))return;$('entryKind').value=kind;
    by('.type-chip').forEach(e=>e.classList.toggle('active',e.dataset.kind===kind));
    $('saveEntry').textContent=editingId!==null?'Salvar alteração':`Salvar ${typeLabel(kind).toLowerCase()}`;
    $('valueHint').textContent=kind==='yield'?'Para um rendimento negativo, coloque − antes do valor.':kind==='deposit'?'Aporte feito: será somado ao patrimônio.':'Retirada feita: será descontada do patrimônio.';
  }
  function updateDateControls(preserveCheck=false){
    const date=$('entryDate').value,older=isDate(date)&&date<state.startedAt;
    const wrap=$('alreadyInInitialBox');const wasOlder=!wrap.classList.contains('hidden');
    wrap.classList.toggle('hidden',!older);
    if(older&&!wasOlder&&!preserveCheck)$('entryAlreadyIncluded').checked=true;
    if(!older)$('entryAlreadyIncluded').checked=false;
    $('dateToday').classList.toggle('active',date===dateLocal());
    $('datePast').classList.toggle('active',date!==dateLocal());
    $('dateHelp').textContent=older?'Você escolheu uma data anterior ao início do acompanhamento. Confira se esse valor já está no patrimônio inicial.':'Você pode escolher o dia exato dos rendimentos anotados no seu caderno.';
  }
  function resetEntry(){editingId=null;$('entryForm').reset();$('entryDate').value=dateLocal();$('entryAlreadyIncluded').checked=false;$('alreadyInInitialBox').classList.add('hidden');$('entryNote').value='';$('entryFormTitle').textContent='Novo lançamento';$('cancelEdit').classList.add('hidden');changeKind('yield');updateDateControls();}
  function beginEdit(id){const e=state.entries.find(x=>x.id===id);if(!e)return;editingId=id;$('entryAmount').value=fmtNumber(e.cents);$('entryDate').value=e.date;$('entryNote').value=e.note;$('entryAlreadyIncluded').checked=e.includedInInitial===true;$('alreadyInInitialBox').classList.add('hidden');$('entryFormTitle').textContent='Editar lançamento';$('cancelEdit').classList.remove('hidden');changeKind(e.kind);updateDateControls(true);navigate('add');}
  function newPastEntry(){resetEntry();$('entryDate').value=previousMonthStart();updateDateControls();navigate('add');} 
  function removeEntry(id){const e=state.entries.find(x=>x.id===id);if(!e)return;if(!window.confirm(`Excluir ${typeLabel(e.kind).toLowerCase()} de ${formatDate(e.date)} no valor de ${money(e.cents)}?`))return;
    const next={...state,entries:state.entries.filter(x=>x.id!==id)};if(persist(next)){renderAll();toast('Lançamento excluído.');}
  }
  function onEntrySubmit(ev){ev.preventDefault();const kind=$('entryKind').value,cents=parseCents($('entryAmount').value),date=$('entryDate').value,note=$('entryNote').value.trim();
    if(!validKind(kind)||cents===null||(kind!=='yield'&&cents<=0)){toast('Informe um valor válido. Aportes e retiradas devem ser positivos.');return;}
    if(!isDate(date)){toast('Informe uma data válida.');return;}
    if(kind==='yield'&&state.entries.some(e=>e.kind==='yield'&&e.date===date&&e.id!==editingId)){toast('Já existe rendimento nessa data. Use Histórico para editar.');return;}
    const record={id:editingId||`${Date.now()}-${Math.random().toString(36).slice(2,11)}`,kind,date,cents,note,includedInInitial:date<state.startedAt&&$('entryAlreadyIncluded').checked};
    const next={...state,entries:editingId?state.entries.map(e=>e.id===editingId?record:e):[...state.entries,record]};
    if(persist(next)){
      const past=date<dateLocal();resetEntry();
      if(past){$('entryDate').value=date;updateDateControls();$('monthPicker').value=date.slice(0,7);renderAll();navigate('add');toast('Data anterior salva! Você pode lançar o próximo dia.');}
      else{renderAll();navigate('home');toast('Lançamento salvo! Patrimônio atualizado.');}
    }
  }
  function onSettingsSubmit(ev){ev.preventDefault();const ini=parseCents($('initialBalance').value),goal=parseCents($('goalAmount').value);
    if(ini===null||ini<0||goal===null||goal<=0){toast('Confira os valores. A meta precisa ser maior que zero.');return;}
    if(persist({...state,initialCents:ini,goalCents:goal})){renderAll();navigate('home');toast('Patrimônio e meta atualizados!');}
  }
  function onWelcomeSubmit(ev){ev.preventDefault();const ini=parseCents($('welcomeInitial').value),goal=parseCents($('welcomeGoal').value);
    if(ini===null||ini<0||goal===null||goal<=0){toast('Digite o patrimônio inicial e uma meta válida.');return;}
    if(persist({...state,initialCents:ini,goalCents:goal,setupComplete:true,startedAt:dateLocal()})){$('welcomeModal').classList.add('hidden');renderAll();toast('Tudo pronto! Vamos rumo à sua meta.');}
  }
  async function shareOrDownload(file,filename){
    try{if(navigator.canShare?.({files:[file]})&&typeof navigator.share==='function') {await navigator.share({files:[file],title:filename});return true;}}catch(e){if(e.name==='AbortError')return false;console.warn('Compartilhamento indisponível, tentando baixar:',e);}
    try{const url=URL.createObjectURL(file);const a=document.createElement('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);toast('Arquivo preparado. Salve uma cópia no app Arquivos.');return true;}catch(e){toast('Não foi possível exportar. Tente abrir no Safari.');return false;}
  }
  function exportBackup(){const name=`rumo-ao-milhao-backup-${dateLocal()}.json`;const blob=new File([JSON.stringify({...state,exportedAt:new Date().toISOString()},null,2)],name,{type:'application/json'});shareOrDownload(blob,name);}
  function csvCell(v){let s=String(v??'');if(/^[\s]*[=+@\-\t\r]/.test(s))s="'"+s;return `"${s.replace(/"/g,'""')}"`;}
  function exportCsv(){const rows=[['Data','Tipo','Valor (R$)','Observação','Já incluído no patrimônio inicial?']];
    for(const e of state.entries.slice().sort((a,b)=>a.date.localeCompare(b.date)))rows.push([formatDate(e.date),typeLabel(e.kind),(signedAmount(e)/100).toFixed(2).replace('.',','),e.note,e.includedInInitial?'Sim':'Não']);
    const body='\ufeff'+rows.map(row=>row.map(csvCell).join(';')).join('\r\n');const filename=`rumo-ao-milhao-historico-${dateLocal()}.csv`;const file=new File([body],filename,{type:'text/csv;charset=utf-8'});shareOrDownload(file,filename);
  }
  async function importBackup(e){const file=e.target.files?.[0];e.target.value='';if(!file)return;
    try{if(file.size>8*1024*1024)throw Error('O arquivo é grande demais.');const data=validateBackup(JSON.parse(await file.text()));
      if(!window.confirm(`Restaurar ${data.entries.length} lançamentos do backup? Isso substitui TODOS os dados atuais deste iPhone.`))return;
      if(persist(data)){resetEntry();$('monthPicker').value=monthLocal();renderAll();$('welcomeModal').classList.toggle('hidden',data.setupComplete);navigate('home');toast('Backup restaurado com sucesso.');}
    }catch(err){toast(`Não foi possível restaurar: ${err.message||'arquivo inválido'}`);}
  }
  function clearData(){if(!window.confirm('Apagar TODOS os lançamentos e configurações deste aparelho? Esta ação não pode ser desfeita sem um backup.'))return;
    if(persist(defaultState())){resetEntry();$('monthPicker').value=monthLocal();renderAll();navigate('home');$('welcomeModal').classList.remove('hidden');toast('Dados apagados. Configure seu patrimônio novamente.');}
  }
  function initOffline(){const el=$('offlineStatus');if(!('serviceWorker' in navigator)){el.textContent='Este navegador não oferece instalação offline. Abra no Safari.';return;}
    const update=()=>{const dot=document.createElement('span');dot.className='status-dot';el.replaceChildren(dot,document.createTextNode(navigator.onLine?' Pronto para uso offline':' Você está sem internet; o app continua funcionando.'));};
    navigator.serviceWorker.register('./sw.js',{scope:'./'}).then(()=>navigator.serviceWorker.ready).then(()=>{update();window.addEventListener('online',update);window.addEventListener('offline',update);}).catch(err=>{console.warn('Offline indisponível:',err);el.textContent='Offline ainda não disponível. Abra o link HTTPS no Safari com internet e recarregue.';});
  }
  function init(){load();$('entryDate').value=dateLocal();$('monthPicker').value=monthLocal();updateDateControls();renderAll();if(!state.setupComplete)$('welcomeModal').classList.remove('hidden');
    by('.nav-item').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.view)));
    by('.type-chip').forEach(b=>b.addEventListener('click',()=>changeKind(b.dataset.kind)));
    $('entryForm').addEventListener('submit',onEntrySubmit);
    $('cancelEdit').addEventListener('click',()=>{resetEntry();navigate('history');});
    $('settingsForm').addEventListener('submit',onSettingsSubmit);
    $('welcomeForm').addEventListener('submit',onWelcomeSubmit);
    $('homeNewYield').addEventListener('click',()=>{resetEntry();navigate('add');});
    $('homePastYield').addEventListener('click',newPastEntry);
    $('dateToday').addEventListener('click',()=>{$('entryDate').value=dateLocal();updateDateControls();});
    $('datePast').addEventListener('click',()=>{$('entryDate').value=previousMonthStart();updateDateControls();$('entryDate').focus();});
    $('entryDate').addEventListener('change',()=>updateDateControls());
    $('settingsShortcut').addEventListener('click',()=>navigate('settings'));
    $('monthPicker').addEventListener('change',renderHistory);
    $('exportBackup').addEventListener('click',exportBackup);
    $('downloadCsv').addEventListener('click',exportCsv);
    $('importBackup').addEventListener('change',importBackup);
    $('clearData').addEventListener('click',clearData);
    initOffline();
  }
  init();
})();
