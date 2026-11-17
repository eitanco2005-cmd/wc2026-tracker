// Live odds come from api.winner.co.il (the www /api path is a stale snapshot).
// Run on https://www.winner.co.il/ (Claude in Chrome javascript_tool). Produces window.__c:
// "mId|HOME-AWAY|YYMMDDHHMM|<FG|H1|Q1><S|O|T<team>|P<hebrew player name>>|sel:price,sel:price;..."  -> nbaw/compact.py
// P = player points ("מעל/מתחת נקודות שחקן"); its "exactly N" outcome is dropped.
const T={ATL:["הוקס","אטלנטה"],BOS:["סלטיקס","בוסטון"],BKN:["נטס","ברוקלין"],CHA:["הורנטס","שארלוט"],CHI:["בולס","שיקגו"],CLE:["קאבלירס","קבלירס","קליבלנד"],DAL:["מאבריקס","מאווריקס","דאלאס"],DEN:["נאגטס","דנבר"],DET:["פיסטונס","דטרויט"],GS:["ווריורס","גולדן סטייט"],HOU:["רוקטס","יוסטון"],IND:["פייסרס","אינדיאנה"],LAC:["קליפרס"],LAL:["לייקרס"],MEM:["גריזליס","ממפיס"],MIA:["מיאמי"],MIL:["באקס","מילווקי"],MIN:["טימברוולבס","מינסוטה"],NO:["פליקנס","פליקאנס","ניו אורלינס"],NY:["ניקס","ניו יורק"],OKC:["ת'אנדר","אוקלהומה"],ORL:["מג'יק","אורלנדו"],PHI:["פילדלפיה","76"],PHX:["סאנס","פיניקס"],POR:["בלייזרס","פורטלנד"],SAC:["קינגס","סקרמנטו"],SA:["ספרס","סאן אנטוניו"],TOR:["ראפטורס","טורונטו"],UTAH:["ג'אז","יוטה"],WSH:["וויזארדס","וושינגטון"]};
const ab=s=>{let best=null,len=0;for(const k in T)for(const w of T[k])if(s.includes(w)&&w.length>len){best=k;len=w.length}return best||'?'};
const strip=s=>s.replace(/[‪-‮‎‏]/g,'');
const per=mp=>mp.includes('רבע ראשון')?'Q1':mp.includes('מחצית ראשונה')?'H1':'FG';
const g=async u=>(await (await fetch(u,{credentials:'include'})).json());
const j=await g('https://api.winner.co.il/v2/publicapi/GetCMobileLine?lineChecksum=0');
const byId=new Map(j.markets.map(m=>[m.mId,m]));
try{const d=await g('https://api.winner.co.il/v2/publicapi/GetDMobileLine?lineChecksum='+j.hashes.lineChecksum);const L=d.lines||d;(L.u||[]).concat(L.a||[]).forEach(m=>byId.set(m.mId,m));(L.d||[]).forEach(x=>byId.delete(x.mId||x));}catch(e){}
j.markets=[...byId.values()];
const ok=/^(הימור יתרון|מעל\/מתחת נקודות( שחקן)? -)/;
window.__c=j.markets.filter(m=>m.league==='NBA'&&ok.test(strip(m.mp||''))).map(m=>{
 const [hh,aa]=strip(m.desc).split(' - ');const mp=strip(m.mp);let k;
 if(mp.startsWith('הימור יתרון'))k='S';
 else if(mp.startsWith('מעל/מתחת נקודות שחקן'))k='P'+strip((m.outcomes[0]||{desc:''}).desc).split(' - ')[0].replace(/[|;,:]/g,'').trim();
 else{const p=mp.split(' - ');k=p.length===3?'T'+ab(p[1]):'O'}
 const o=m.outcomes.map(x=>{let ds=strip(x.desc);if(k==='S'){const mm=ds.match(/^(.*)\(([-+]?[\d.]+)\)/);return ab(mm[1])+mm[2]+':'+x.price}
  if(k[0]==='P'){ds=ds.split(' - ').pop();if(!/^(מעל|מתחת)/.test(ds))return null}
  return (ds.startsWith('מעל')?'o':'u')+ds.match(/[\d.]+/)[0]+':'+x.price}).filter(Boolean).join(',');
 return [m.mId,ab(hh)+'-'+ab(aa),''+m.e_date+m.m_hour,per(mp)+k,o].join('|')}).join(';');
window.__c.length
