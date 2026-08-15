/* Ogni mercato ha tre nomi diversi, e servono tutti e tre:
     perp   il contratto su cui il bot opera davvero (prezzi in USD)
     spot   la coppia spot Kraken in USD: e' l'unica fonte di candele storiche
            che il browser riesce a leggere, perche' futures.kraken.com risponde
            senza un Access-Control-Allow-Origin valido e il browser blocca tutto.
            Lo spot USD sta a meno di uno 0,1% dal mark price del perpetuo, quindi
            le candele restano sulla stessa scala dei prezzi d'ingresso.
     bybit  perpetuo di riserva, se Kraken non risponde
   Il tempo reale invece arriva dal WebSocket di Kraken Futures: sui WebSocket
   il CORS non si applica, quindi da li' il mark price esatto lo otteniamo. */
const MKT={
 XXBTZEUR:{perp:'PF_XBTUSD', spot:'XBTUSD', bybit:'BTCUSDT', nome:'BTC'},
 XETHZEUR:{perp:'PF_ETHUSD', spot:'ETHUSD', bybit:'ETHUSDT', nome:'ETH'},
 XXRPZEUR:{perp:'PF_XRPUSD', spot:'XRPUSD', bybit:'XRPUSDT', nome:'XRP'},
 SOLEUR:  {perp:'PF_SOLUSD', spot:'SOLUSD', bybit:'SOLUSDT', nome:'SOL'},
 LINKEUR: {perp:'PF_LINKUSD',spot:'LINKUSD',bybit:'LINKUSDT',nome:'LINK'},
 XLTCZEUR:{perp:'PF_LTCUSD', spot:'LTCUSD', bybit:'LTCUSDT', nome:'LTC'},
 ADAEUR:  {perp:'PF_ADAUSD', spot:'ADAUSD', bybit:'ADAUSDT', nome:'ADA'},
 DOTEUR:  {perp:'PF_DOTUSD', spot:'DOTUSD', bybit:'DOTUSDT', nome:'DOT'},
 AVAXEUR: {perp:'PF_AVAXUSD',spot:'AVAXUSD',bybit:'AVAXUSDT',nome:'AVAX'},
 BCHEUR:  {perp:'PF_BCHUSD', spot:'BCHUSD', bybit:'BCHUSDT', nome:'BCH'},
 XXMRZEUR:{perp:'PF_XMRUSD', spot:'XMRUSD', bybit:'XMRUSDT', nome:'XMR'},
 ATOMEUR: {perp:'PF_ATOMUSD',spot:'ATOMUSD',bybit:'ATOMUSDT',nome:'ATOM'},
 FILEUR:  {perp:'PF_FILUSD', spot:'FILUSD', bybit:'FILUSDT', nome:'FIL'},
 UNIEUR:  {perp:'PF_UNIUSD', spot:'UNIUSD', bybit:'UNIUSDT', nome:'UNI'}};
const PERP=Object.fromEntries(Object.entries(MKT).map(([k,m])=>[k,m.perp]));
const DA_PERP=Object.fromEntries(Object.entries(MKT).map(([k,m])=>[m.perp,k]));
const nome=p=>MKT[p]?MKT[p].nome
  :String(p).replace('PF_','').replace(/USDT?$/,'').replace('XBT','BTC');
// La motivazione dell'IA e' testo generato da un modello e finisce in
// innerHTML: va sempre neutralizzato. Non e' paranoia teorica — e' l'unico
// pezzo di questa pagina che nessuno di noi due ha scritto.
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const eur=n=>n==null?'—':n.toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2})+' €';
// Virgola, non punto: accanto a "200,66 €" un "+0.33%" e' due convenzioni
// diverse nella stessa riga, e si nota.
const pct=n=>n==null?'—':(n>=0?'+':'')+(n*100).toLocaleString('it-IT',
  {minimumFractionDigits:2,maximumFractionDigits:2})+'%';
// Quattro decimali su BTC sono rumore, due su ADA cancellano il prezzo.
const cifre=n=>(+n).toFixed(n<1?6:n<100?4:2);
const cls=n=>n==null?'':(n>=0?'up':'down');

/* I grafici sono disegnati su canvas: non ereditano niente dal CSS, quindi i
   colori vanno letti dalle variabili e riapplicati a mano quando il tema
   cambia. Ogni grafico e ogni serie registrano in 'perTema' come ricolorarsi;
   senza, cambiare tema lascerebbe assi e candele con i colori del tema
   precedente, illeggibili su uno sfondo che nel frattempo si e' invertito. */
const tok=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const perTema=[];

function opzioni(){
  return {layout:{background:{color:'transparent'},textColor:tok('--dim'),
      fontFamily:"ui-monospace,'SF Mono',monospace",fontSize:11},
    grid:{vertLines:{color:tok('--line')},horzLines:{color:tok('--line')}},
    rightPriceScale:{borderColor:tok('--line')},
    timeScale:{borderColor:tok('--line')},
    crosshair:{mode:1,vertLine:{color:tok('--line2'),labelBackgroundColor:tok('--surf2')},
               horzLine:{color:tok('--line2'),labelBackgroundColor:tok('--surf2')}}};
}

const COLORI_CANDELA=()=>({upColor:tok('--up'),downColor:tok('--down'),
  borderUpColor:tok('--up'),borderDownColor:tok('--down'),
  wickUpColor:tok('--up'),wickDownColor:tok('--down')});

/* ---- i tre portafogli ----
   Girano sugli stessi dati e differiscono per UNA variabile ciascuno: e' il
   solo modo di attribuire una differenza a una causa. La dashboard esiste
   soprattutto per affiancarli, quindi il colore di ognuno e' fisso e ritorna
   ovunque — card, linee del grafico, bordo delle posizioni, storico. */
const WALLET=[
  {id:'reale', nome:'Reale', colore:'--w-reale', nota:'leva da volatility targeting'},
  {id:'ombra', nome:'Ombra', colore:'--w-ombra', nota:'stesse decisioni, leva fissa 1x'},
  {id:'ia',    nome:'IA',    colore:'--w-ia',    nota:'universo scelto dal modello'}];

/* Il blocco 'wallet' lo scrive il Pi, questa pagina la scrive il Mac, e i due
   si allineano solo dopo un pull: fino a cinquanta minuti, di piu' se il pull
   fallisce. Senza questo ripiego quella finestra e' una dashboard rotta. */
function walletDaDati(D){
  const W=D.wallet||null;
  return WALLET.map(w=>{
    const d=W?(W[w.id]||null):null;
    const legacy={reale:{equity:D.eq_ora, posizioni:D.posizioni||{}, avviato:true},
                  ombra:{equity:D.ombra_ora, posizioni:null, avviato:D.ombra_ora!=null},
                  ia:   {equity:D.ia_ora,    posizioni:null, avviato:D.ia_ora!=null}}[w.id];
    const base=d||legacy;
    return {...w, equity:base.equity, avviato:!!base.avviato,
            // null = "non pubblicato", diverso da {} = "nessuna posizione".
            // Confonderli mostrerebbe 0 € di esposizione su un portafoglio che
            // potrebbe averne 200, che e' un'affermazione, non un'assenza.
            posizioni:d?(d.posizioni||{}):legacy.posizioni};
  });
}

function esposizione(posizioni){
  if(!posizioni) return null;
  const v=Object.values(posizioni);
  const somma=f=>v.filter(f).reduce((s,p)=>s+Math.abs(+p.notional||0),0);
  return {lorda:somma(()=>true),
          lunga:somma(p=>p.side>0), corta:somma(p=>p.side<0),
          nLunghe:v.filter(p=>p.side>0).length,
          nCorte:v.filter(p=>p.side<0).length};
}

/* NON viene mostrata una "liquidita'". In questa contabilita' aprire una
   posizione non sottrae nulla dal cash — open_position scala solo le
   commissioni — quindi il cash resta intorno ai 200 € mentre l'esposizione e'
   81 €, e affiancarli darebbe 281 € su un conto da 200. Un numero che sembra
   il complemento di un altro e non lo e' vale meno di un numero assente. */
function cardWallet(D){
  document.getElementById('wallets').innerHTML=walletDaDati(D).map(w=>{
    const r=w.equity==null?null:w.equity/D.capitale-1;
    const e=esposizione(w.posizioni);
    const q=(e&&w.equity)?e.lorda/w.equity:null;
    const larghezza=v=>w.equity?Math.min(100,v/w.equity*100):0;
    return `<div class="wc${w.avviato?'':' spento'}" style="--wc:var(${w.colore})">
      <div class="wc-nome"><span class="wc-dot"></span>${w.nome}</div>
      <div class="wc-eq mono">${w.equity==null?'—':eur(w.equity)}</div>
      <div class="wc-pc ${w.avviato?cls(r):''}">${w.avviato?pct(r):'non ancora avviato'}</div>
      ${!w.avviato
        // Un portafoglio mai partito non ha esposizione, e non c'e' nessun
        // dato da attendere: dire "in attesa" suggerirebbe che stia per
        // arrivare un numero che non esistera' finche' non opera.
        ? `<div class="wc-esp"><span>esposizione —</span></div>
           <div class="wc-bar"></div>
           <div class="wc-ls">non ha ancora operato</div>`
        : e?`<div class="wc-esp"><span>esposizione ${eur(e.lorda)}</span>
             <span class="mono">${q==null?'':(q*100).toFixed(0)+'%'}</span></div>
           <div class="wc-bar">
             <i style="width:${larghezza(e.lunga)}%;background:var(--up)"></i>
             <i style="width:${larghezza(e.corta)}%;background:var(--down)"></i>
           </div>
           <div class="wc-ls">${e.lorda?`${eur(e.lunga)} long · ${e.nLunghe} · ${eur(e.corta)} short · ${e.nCorte}`
                                       :'nessuna posizione aperta'}</div>`
        :`<div class="wc-esp"><span>esposizione —</span></div>
          <div class="wc-bar"></div>
          <div class="wc-ls">in attesa che il Pi pubblichi il dato</div>`}
      <div class="wc-nota">${w.nota}</div></div>`;
  }).join('');
}

const ORA=3600;              // le candele sono orarie
const GIORNI=3;              // quanto storico mostrare in ogni riquadro
let D=null, live=false, ws=null, riconnetti=null, tentativi=0;
let prezzi={}, serie={}, grafici=[];

// I grafici vanno distrutti a mano: senza remove() ogni ricarica ne lascia
// uno vecchio attaccato al DOM, con il suo ResizeObserver ancora vivo.
// perTema va svuotato insieme a loro, altrimenti restano closure attaccate a
// grafici gia' rimossi e il primo cambio tema le richiama tutte.
function pulisci(){
  grafici.forEach(c=>{try{c.remove()}catch(e){}});
  grafici=[]; perTema.length=0; serie={};
}

function crea(el,extra){
  const c=LightweightCharts.createChart(el,{...opzioni(),autoSize:true,...extra});
  grafici.push(c);
  perTema.push(()=>c.applyOptions(opzioni()));
  return c;
}

matchMedia('(prefers-color-scheme: dark)')
  .addEventListener('change',()=>perTema.forEach(f=>{try{f()}catch(e){}}));

async function carica(){
  D=await (await fetch('data.json?t='+Date.now())).json();
  pulisci();
  render();
  proiezione();
  await candele();
}

function render(){
  const rEq=D.eq_ora/D.capitale-1, rBh=D.bh_ora?D.bh_ora/D.capitale-1:null;
  const diff=rBh==null?null:rEq-rBh;
  document.getElementById('mkt').textContent=D.mercato||'perpetui';
  document.getElementById('sub').textContent=
    `capitale versato ${D.capitale} € · ${D.n_ops} operazioni chiuse · aggiornato ${new Date(D.aggiornato).toLocaleString('it-IT')}`;

  let a='';
  if(D.halted) a+=`<div class="note">Sistema bloccato: ${esc(D.halt_reason||'')}</div>`;
  if(D.paused) a+=`<div class="note">Sistema in pausa — capitale liquidato.</div>`;
  if(D.n_ops<30) a+=`<div class="note">Solo ${D.n_ops} operazioni chiuse. Sotto le ~30 qualunque risultato è statisticamente indistinguibile dal caso: questi numeri non dicono ancora se la strategia funziona.</div>`;
  document.getElementById('alert').innerHTML=a;

  cardWallet(D);

  // Niente tessera "Portafoglio": ripeterebbe parola per parola la card
  // Reale, che sta trenta pixel piu' in alto ed e' piu' grande. Qui restano
  // solo le misure che le card non danno — il metro di paragone esterno e il
  // conteggio delle posizioni.
  document.getElementById('kpis').innerHTML=`
   <div class="kpi"><div class="l">Solo BTC (buy &amp; hold)</div>
     <div class="v ${cls(rBh)} mono">${eur(D.bh_ora)}</div>
     <div class="d ${cls(rBh)}">${pct(rBh)}</div></div>
   <div class="kpi"><div class="l">Differenza vs BTC</div>
     <div class="v ${cls(diff)} mono">${pct(diff)}</div>
     <div class="d">${diff==null?'dati insufficienti':(diff>=0?'meglio di BTC':'peggio di BTC')}</div></div>
   <div class="kpi"><div class="l">Posizioni aperte</div>
     <div class="v mono">${D.n_pos}</div>
     <div class="d">${D.n_ops} chiuse finora</div></div>`;
   // Le tessere "Senza volatility targeting" e "Mercati scelti dall'IA" sono
   // sparite da qui: erano due portafogli descritti dalla loro variabile
   // invece che chiamati per nome, in coda a una fila di KPI del reale. Ora
   // sono card, accanto al reale e alla stessa dimensione.

  const eqEl=document.getElementById('eq'); eqEl.innerHTML='';
  const ch=crea(eqEl);
  const s1=ch.addAreaSeries({lineColor:tok('--w-reale'),
    topColor:tok('--w-reale-fill'),bottomColor:'rgba(0,0,0,0)',
    lineWidth:2,priceLineVisible:false});
  const s2=ch.addLineSeries({color:tok('--bench'),lineWidth:2,lineStyle:2,priceLineVisible:false});
  // Portafoglio ombra: stesse decisioni, leva fissa 1x. Tratteggiato e
  // smorzato perche' e' un metro di paragone, non un risultato.
  const s3=ch.addLineSeries({color:tok('--w-ombra'),lineWidth:1,lineStyle:3,priceLineVisible:false});
  // Portafoglio sperimentale: stesso segnale e stessa size, universo scelto
  // dall'IA. Anche questo smorzato: e' un esperimento in corso, non un
  // risultato — e va guardato come tale finche' non ha mesi di dati dietro.
  const s4=ch.addLineSeries({color:tok('--w-ia'),lineWidth:1,lineStyle:1,priceLineVisible:false});
  perTema.push(()=>{
    s1.applyOptions({lineColor:tok('--w-reale'),topColor:tok('--w-reale-fill')});
    s2.applyOptions({color:tok('--bench')});
    s3.applyOptions({color:tok('--w-ombra')});
    s4.applyOptions({color:tok('--w-ia')});
  });
  const conv=a=>a.map(p=>({time:Math.floor(new Date(p.x).getTime()/1000),value:p.y}))
                 .filter((v,i,a)=>i===0||v.time>a[i-1].time);
  if(D.equity.length) s1.setData(conv(D.equity));
  if(D.benchmark.length) s2.setData(conv(D.benchmark));
  if((D.ombra||[]).length) s3.setData(conv(D.ombra));
  if((D.ia||[]).length) s4.setData(conv(D.ia));
  ch.timeScale().fitContent();

  document.getElementById('eqnote').innerHTML=
   `<span style="color:var(--w-reale)">━</span> portafoglio ·
    <span style="color:var(--bench)">╌</span> solo BTC, con gli stessi versamenti` +
   ((D.ombra||[]).length
     ? ` · <span style="color:var(--w-ombra)">┈</span> ombra: stesse decisioni, leva fissa 1x
         <br>L'ombra è più esposta (le leve reali oggi stanno sotto 1x), quindi
         è normale che guadagni e perda di più. Il confronto che conta non è
         quale linea sta più in alto, ma quanto rendimento produce ciascuna
         per unità di oscillazione.`
     : ` · l'ombra comparirà dopo la prima operazione`) +
   ((D.ia||[]).length
     ? `<br><span style="color:var(--w-ia)">·</span> IA: stesso segnale e stessa
         size, ma su mercati scelti da un modello linguistico. Serve a
         misurare in avanti se la selezione ragionata vale qualcosa: non si
         può backtestare, perché il modello ha già letto il passato.`
     : '');

  // La scelta dell'IA va mostrata con la sua motivazione, altrimenti è un
  // oracolo. Con la motivazione è una tesi verificabile.
  const iaEl=document.getElementById('ia');
  if(iaEl) iaEl.innerHTML=(D.ia_universo||[]).length
    ? `<b>Universo scelto dall'IA</b>
       ${D.ia_scelto_il?`<span style="color:var(--faint)">— ${new Date(D.ia_scelto_il).toLocaleString('it-IT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</span>`:''}
       <div style="margin:6px 0">${D.ia_universo.map(p=>`<span class="pill">${esc(nome(p))}</span>`).join(' ')}</div>
       ${D.ia_motivazione?`<div style="color:var(--faint)">${esc(D.ia_motivazione)}</div>`:''}`
    : '';

  // 'versa' e' un versamento di capitale, non un'operazione di mercato:
  // deve stare qui, altrimenti l'equity salta nel grafico senza spiegazione.
  const ETICHETTA={open:'apre',close:'chiude',deposit:'versa'};
  const CLASSE={open:'op',close:'cl',deposit:'dep'};
  document.getElementById('ops').innerHTML=D.ops.map(o=>`<tr>
    <td class="mono">${new Date(o.ts).toLocaleString('it-IT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</td>
    <td><span class="pill ${CLASSE[o.action]||'cl'}">${ETICHETTA[o.action]||esc(o.action)}</span></td>
    <td>${o.action==='deposit'?'—':esc(nome(o.pair))}</td>
    <td class="mono">${o.action!=='deposit'&&o.price?(+o.price).toFixed(4):''}</td>
    <td class="mono">${o.notional?(+o.notional).toFixed(2)+' €':''}</td>
    <td class="mono">${o.action!=='deposit'&&o.leverage&&+o.leverage?(+o.leverage).toFixed(2)+'x':''}</td>
    <td class="why">${esc(o.reason||'')}</td></tr>`).join('')
    ||'<tr><td colspan="7" class="skel">nessuna operazione ancora</td></tr>';

  document.getElementById('ft').innerHTML=
   `Paper trading — nessun capitale reale impiegato. Lo stato del portafoglio arriva dal Raspberry Pi, aggiornato ogni 30 minuti.<br>
    Candele orarie da Kraken spot USD (di riserva Bybit); col tasto <b>Avvia live</b> i prezzi passano al mark price dei perpetui Kraken Futures via WebSocket, quello stesso su cui il bot calcola le posizioni.<br>
    <a href="ricerca.html">Report tecnico: day trading, IA e cosa abbiamo misurato</a> ·
    <a href="https://github.com/75davide75/TradeBot">github.com/75davide75/TradeBot</a>`;
}

function proiezione(){
  const el=document.getElementById('proj'), nota=document.getElementById('projnote');
  el.innerHTML='';
  const H=D.equity||[];
  if(H.length<3){nota.textContent=
    'Servono almeno qualche giorno di storico prima di poter stimare un rendimento annuo. Adesso non ci sono abbastanza dati.';
    return}
  const r=[];
  for(let i=1;i<H.length;i++){
    const dt=(new Date(H[i].x)-new Date(H[i-1].x))/86400000;
    if(dt>0&&H[i-1].y>0) r.push({t:H[i].x,g:(H[i].y/H[i-1].y-1)/dt});
  }
  if(!r.length){nota.textContent='Dati insufficienti.';return}
  const stima=[],alto=[],basso=[];
  let s=0,s2=0;
  r.forEach((x,i)=>{
    s+=x.g; s2+=x.g*x.g;
    const n=i+1, m=s/n, sd=n>1?Math.sqrt(Math.max(0,(s2-n*m*m)/(n-1))):0;
    const ann=m*365, err=n>1?sd/Math.sqrt(n)*365:0;
    const time=Math.floor(new Date(x.t).getTime()/1000);
    stima.push({time,value:ann*100});
    alto.push({time,value:(ann+1.96*err)*100});
    basso.push({time,value:(ann-1.96*err)*100});
  });
  const uniq=a=>a.filter((v,i,z)=>i===0||v.time>z[i-1].time);
  const ch=crea(el);
  const b=ch.addLineSeries({color:tok('--faint'),lineWidth:1,lineStyle:2,priceLineVisible:false});
  const a=ch.addLineSeries({color:tok('--faint'),lineWidth:1,lineStyle:2,priceLineVisible:false});
  const c=ch.addLineSeries({color:tok('--w-reale'),lineWidth:2,priceLineVisible:false});
  perTema.push(()=>{
    b.applyOptions({color:tok('--faint')});
    a.applyOptions({color:tok('--faint')});
    c.applyOptions({color:tok('--w-reale')});
  });
  b.setData(uniq(basso)); a.setData(uniq(alto)); c.setData(uniq(stima));
  ch.timeScale().fitContent();

  const u=stima[stima.length-1].value, lo=basso[basso.length-1].value, hi=alto[alto.length-1].value;
  const gg=r.length;
  nota.innerHTML=`Stima corrente <b class="${u>=0?'up':'down'}">${u>=0?'+':''}${u.toFixed(1)}% annuo</b>
    — intervallo di confidenza al 95%: da ${lo.toFixed(1)}% a ${hi.toFixed(1)}%.
    ${(lo<0&&hi>0)?'<b>Lo zero cade dentro questo intervallo: la stima non è ancora distinguibile da un rendimento nullo.</b>':''}
    Basata su ${gg} osservazioni. Le linee tratteggiate sono i limiti dell'incertezza, non previsioni.`;
}

async function candele(){
  const box=document.getElementById('pos');
  const P=D.posizioni||{};
  const aperte=Object.keys(P).length>0;
  document.getElementById('postit').textContent=
    aperte?'Posizioni aperte':'Mercati sorvegliati (nessuna posizione aperta)';

  // Quando non c'e' nulla di aperto mostro comunque i grafici dell'universo:
  // una pagina vuota non dice se il sistema sta lavorando o e' fermo.
  const lista=mercatiMostrati();
  if(!lista.length){box.innerHTML='<div class="skel">nessun mercato configurato</div>';return}

  box.innerHTML=lista.map(([p,v])=>`
    <div class="pos" data-p="${p}">
      <header><div><div class="sym">${nome(p)}
        ${v?`<span class="side ${v.side>0?'long':'short'}">${v.side>0?'LONG':'SHORT'}</span>`
           :'<span class="side" style="background:var(--surf2);color:var(--dim)">IN ATTESA</span>'}</div>
        <div class="meta mono">${v?`ingresso ${cifre(+v.entry)} · leva ${(+v.leverage).toFixed(2)}x`
                                  :'nessuna posizione'}</div></div>
        <div class="pnl"><div class="p mono" data-pnl>—</div><div class="q mono" data-px>—</div></div>
      </header>
      <div class="chart" data-chart></div>
      <div class="foot"><span>${v?`nozionale ${(+v.notional).toFixed(2)} €`:'in osservazione'}</span>
        <span data-fonte class="fonte"></span>
        <span>${v?`stop a ${(-8/(+v.leverage||1)).toFixed(1)}%`:''}</span></div>
    </div>`).join('');

  // Le candele storiche le prende lo spot USD di Kraken. Il perpetuo sarebbe la
  // fonte esatta, ma futures.kraken.com non manda un Access-Control-Allow-Origin
  // valido e dal browser la chiamata non parte proprio.
  const guai=[];
  await inParallelo(lista,3,async ([p,v])=>{
    const el=document.querySelector(`.pos[data-p="${p}"] [data-chart]`);
    if(!el) return;
    try{
      const {dati,fonte}=await storico(p);
      if(!dati.length) throw new Error('nessuna candela restituita');
      const ch=crea(el,{timeScale:{...opzioni().timeScale,timeVisible:true,secondsVisible:false}});
      const s=ch.addCandlestickSeries(COLORI_CANDELA());
      perTema.push(()=>s.applyOptions(COLORI_CANDELA()));
      s.setData(dati);
      if(v) s.createPriceLine({price:+v.entry,color:tok('--faint'),lineWidth:1,lineStyle:2,
        axisLabelVisible:true,title:'ingresso'});
      ch.timeScale().fitContent();
      // Copia dell'ultima candela: da qui in poi la aggiorna il flusso live.
      serie[p]={ch,s,fonte,ultima:{...dati[dati.length-1]}};
      const f=el.parentElement.querySelector('[data-fonte]');
      if(f) f.textContent=fonte;
      // Cosi' il P&L e' gia' pieno all'apertura, senza aspettare il tasto live.
      mostra(p,v,dati[dati.length-1].close,false);
    }catch(e){
      el.innerHTML=`<div class="skel">grafico non disponibile — ${esc(e.message)}</div>`;
      guai.push(nome(p));
    }
  });
  if(guai.length) avviso(`Candele non caricate per ${guai.join(', ')}. Il resto della pagina resta valido.`);
}

// Poche richieste alla volta: Kraken limita le chiamate pubbliche, e otto
// fetch tutte insieme si prendono un rifiuto per eccesso di traffico.
async function inParallelo(elenco,quante,f){
  const coda=[...elenco];
  await Promise.all(Array.from({length:Math.min(quante,coda.length)},async()=>{
    while(coda.length) await f(coda.shift());
  }));
}

async function storico(p){
  const m=MKT[p];
  if(!m) throw new Error('mercato sconosciuto');
  try{ return {dati:await daKraken(m), fonte:'Kraken spot'}; }
  catch(e1){
    try{ return {dati:await daBybit(m), fonte:'Bybit perp'}; }
    catch(e2){ throw new Error(`${e1.message}; anche il ripiego Bybit ha fallito (${e2.message})`); }
  }
}

async function daKraken(m){
  // 'since' evita di scaricare i 30 giorni pieni per mostrarne tre.
  const da=Math.floor(Date.now()/1000)-GIORNI*86400;
  const r=await fetch(`https://api.kraken.com/0/public/OHLC?pair=${m.spot}&interval=60&since=${da}`);
  if(!r.ok) throw new Error('Kraken HTTP '+r.status);
  const j=await r.json();
  if(j.error&&j.error.length) throw new Error('Kraken '+j.error.join(' '));
  // La chiave del risultato non e' quella richiesta (XBTUSD torna XXBTZUSD).
  const k=Object.keys(j.result||{}).find(x=>x!=='last');
  if(!k) throw new Error('Kraken: risposta senza dati');
  return taglia(j.result[k].map(c=>
    ({time:+c[0],open:+c[1],high:+c[2],low:+c[3],close:+c[4]})));
}

async function daBybit(m){
  const r=await fetch(`https://api.bybit.com/v5/market/kline?category=linear&symbol=${m.bybit}&interval=60&limit=200`);
  if(!r.ok) throw new Error('Bybit HTTP '+r.status);
  const j=await r.json();
  if(j.retCode!==0) throw new Error('Bybit '+(j.retMsg||j.retCode));
  // Bybit le manda dalla piu' recente: vanno rovesciate.
  return taglia((j.result?.list||[]).map(c=>
    ({time:Math.floor(+c[0]/1000),open:+c[1],high:+c[2],low:+c[3],close:+c[4]})).reverse());
}

// Tiene solo la finestra che mostriamo, in ordine e senza tempi ripetuti:
// lightweight-charts rifiuta i dati non crescenti.
function taglia(c){
  const da=Math.floor(Date.now()/1000)-GIORNI*86400;
  return c.filter(k=>Number.isFinite(k.close)&&k.time>=da)
          .sort((a,b)=>a.time-b.time)
          .filter((k,i,z)=>i===0||k.time>z[i-1].time);
}

function avviso(t){
  const el=document.getElementById('alert');
  el.innerHTML+=`<div class="note">${esc(t)}</div>`;
}

// Scrive prezzo e P&L di un mercato. 'vivo' distingue il dato in streaming
// dall'ultima chiusura nota, perche' non valgono la stessa cosa.
function mostra(p,v,px,vivo){
  prezzi[p]=px;
  const card=document.querySelector(`.pos[data-p="${p}"]`); if(!card) return;
  const e=card.querySelector('[data-pnl]'), q=card.querySelector('[data-px]');
  if(v){
    const mv=(px-v.entry)/v.entry*v.side, pl=v.notional*mv;
    e.textContent=(pl>=0?'+':'')+pl.toFixed(2)+' €';
    e.className='p mono '+(pl>=0?'up':'down');
    q.textContent=`${cifre(px)} (${pct(mv)})`;
  }else{
    e.textContent=cifre(px); e.className='p mono';
    q.textContent=vivo?'prezzo in diretta':'ultima chiusura';
  }
  card.classList.toggle('vivo',!!vivo);
}

/* ---- tempo reale: WebSocket di Kraken Futures ----
   Sui WebSocket il CORS non si applica, quindi questa e' l'unica strada per
   avere il mark price vero dei perpetui dentro una pagina su github.io.
   In piu' e' un flusso push: la versione precedente interrogava l'API REST
   una volta al secondo, che e' traffico sprecato e rischia il blocco. */
function stato(classe,testo){
  const b=document.getElementById('live');
  b.classList.remove('on','attesa','ko');
  if(classe) b.classList.add(classe);
  document.getElementById('livetxt').textContent=testo;
}

function apriLive(){
  const prodotti=[...new Set(mercatiMostrati().map(([p])=>MKT[p]?.perp).filter(Boolean))];
  if(!prodotti.length){stato('ko','Nessun mercato');return}
  stato('attesa','Connessione…');
  try{ ws=new WebSocket('wss://futures.kraken.com/ws/v1'); }
  catch(e){ stato('ko','Live non disponibile'); return; }

  ws.onopen=()=>{ tentativi=0; stato('on','Live attivo');
    ws.send(JSON.stringify({event:'subscribe',feed:'ticker',product_ids:prodotti})); };

  ws.onmessage=ev=>{
    let d; try{ d=JSON.parse(ev.data) }catch(e){ return }
    if(d.event==='error'||d.event==='alert'){ stato('ko',d.message||'Errore del flusso'); return }
    if(d.feed!=='ticker'||!d.product_id) return;
    const px=+(d.markPrice ?? d.last);
    if(!Number.isFinite(px)) return;
    const p=DA_PERP[d.product_id]; if(!p) return;
    mostra(p,(D.posizioni||{})[p],px,true);
    disegnaTick(p,px);
  };

  ws.onclose=()=>{ ws=null; if(!live) return;
    // Rientro con attesa crescente, per non martellare l'exchange se e' giu'.
    const attesa=Math.min(30000,1000*2**tentativi++);
    stato('attesa',`Riconnessione tra ${Math.round(attesa/1000)} s…`);
    riconnetti=setTimeout(apriLive,attesa); };

  ws.onerror=()=>{ if(live) stato('attesa','Problema di rete…'); };
}

function chiudiLive(){
  clearTimeout(riconnetti); riconnetti=null; tentativi=0;
  if(ws){ const s=ws; ws=null; s.onclose=null; try{s.close()}catch(e){} }
}

// Aggiunge il tick alla candela in corso, e ne apre una nuova quando scatta
// l'ora. Prima mancava questo passaggio: dopo il cambio d'ora il flusso
// continuava a riscrivere la stessa candela, che si allungava all'infinito.
function disegnaTick(p,px){
  const S=serie[p]; if(!S) return;
  const secchio=Math.floor(Date.now()/1000/ORA)*ORA;
  let u=S.ultima;
  if(!u||secchio>u.time) u=S.ultima={time:secchio,open:px,high:px,low:px,close:px};
  else{ u.high=Math.max(u.high,px); u.low=Math.min(u.low,px); u.close=px; }
  try{ S.s.update({...u}) }catch(e){}
}

function mercatiMostrati(){
  const P=D&&D.posizioni||{};
  return Object.keys(P).length?Object.entries(P):((D&&D.universo)||[]).map(p=>[p,null]);
}

document.getElementById('live').onclick=function(){
  live=!live;
  if(live) apriLive();
  else{ chiudiLive(); stato(null,'Avvia live'); }
};
document.getElementById('rel').onclick=()=>location.reload();
carica().catch(()=>{document.getElementById('sub').textContent=
  'Impossibile caricare data.json — il Pi non ha ancora pubblicato.'});
