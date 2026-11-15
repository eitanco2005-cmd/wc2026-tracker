// Run on https://www.winner.co.il/ (Claude in Chrome javascript_tool). Produces window.__c:
// "mId|HOME-AWAY|YYMMDDHHMM|<FG|H1|Q1><S|O|T<team>>|sel:price,sel:price;..."  -> nbaw/compact.py
const T={ATL:["הוקס","אטלנטה"],BOS:["סלטיקס","בוסטון"],BKN:["נטס","ברוקלין"],CHA:["הורנטס","שארלוט"],CHI:["בולס","שיקגו"],CLE:["קאבלירס","קבלירס","קליבלנד"],DAL:["מאבריקס","מאווריקס","דאלאס"],DEN:["נאגטס","דנבר"],DET:["פיסטונס","דטרויט"],GS:["ווריורס","גולדן סטייט"],HOU:["רוקטס","יוסטון"],IND:["פייסרס","אינדיאנה"],LAC:["קליפרס"],LAL:["לייקרס"],MEM:["גריזליס","ממפיס"],MIA:["מיאמי"],MIL:["באקס","מילווקי"],MIN:["טימברוולבס","מינסוטה"],NO:["פליקנס","פליקאנס","ניו אורלינס"],NY:["ניקס","ניו יורק"],OKC:["ת'אנדר","אוקלהומה"],ORL:["מג'יק","אורלנדו"],PHI:["פילדלפיה","76"],PHX:["סאנס","פיניקס"],POR:["בלייזרס","פורטלנד"],SAC:["קינגס","סקרמנטו"],SA:["ספרס","סאן אנטוניו"],TOR:["ראפטורס","טורונטו"],UTAH:["ג'אז","יוטה"],WSH:["וויזארדס","וושינגטון"]};
const ab=s=>{let best=null,len=0;for(const k in T)for(const w of T[k])if(s.includes(w)&&w.length>len){best=k;len=w.length}return best||'?'};
const strip=s=>s.replace(/[‪-‮‎‏]/g,'');
const per=mp=>mp.includes('רבע ראשון')?'Q1':mp.includes('מחצית ראשונה')?'H1':'FG';
const j=await (await fetch('/api/v2/publicapi/GetCMobileLine?lineChecksum=0')).json();
const ok=/^(הימור יתרון|מעל\/מתחת נקודות)/;
window.__c=j.markets.filter(m=>m.league==='NBA'&&ok.test(strip(m.mp||''))).map(m=>{
 const [hh,aa]=strip(m.desc).split(' - ');const mp=strip(m.mp);let k;
 if(mp.startsWith('הימור יתרון'))k='S';else{const p=mp.split(' - ');k=p.length===3?'T'+ab(p[1]):'O'}
 const o=m.outcomes.map(x=>{const ds=strip(x.desc);if(k==='S'){const mm=ds.match(/^(.*)\(([-+]?[\d.]+)\)/);return ab(mm[1])+mm[2]+':'+x.price}
  return (ds.startsWith('מעל')?'o':'u')+ds.match(/[\d.]+/)[0]+':'+x.price}).join(',');
 return [m.mId,ab(hh)+'-'+ab(aa),''+m.e_date+m.m_hour,per(mp)+k,o].join('|')}).join(';');
window.__c.length
