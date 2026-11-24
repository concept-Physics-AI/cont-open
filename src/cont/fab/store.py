"""ConT FAB의 고르기 화면: 물리 정보가 진열대에 상품처럼 놓이고, 골라서 '내 Fab'에 담는다.

파일 하나로:        python -m cont.fab.store --out fab.html
내 PC에서 띄우기:   python -m cont.fab.store            (조건을 바꾸면 엔진이 그 자리에서 다시 만든다)

- 진열대: 세트, 그리고 형태별(이미지 · 그래프 · 3D · 4D · 영상 · 신호 · 계산값 · 판단) 줄. 카드 하나 = 샘플 하나.
- 샘플은 엔진을 조건마다 실제로 돌린 결과다. 값은 모두 계산값이며 실측과 대조하기 전이다. 가격은 없다.
- 자세히 보기: 샘플을 넘겨 보고, 넣는 것 · 내는 것 · 한계 · 함께 담으면 좋은 것을 본다. 서버로 띄웠으면 규격과 토크를 바꿔 그 자리에서 다시 만든다.
- 견주기: 샘플 셋까지 나란히. 내 Fab: 담은 것이 조건·설정과 함께 아래 띠에 보이고, 구성 화면(build_ui.py)에서 크기·순서·데이터 연결을 정해 저장하고 다시 연다.
"""
from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping, Sequence

from cont.view.switcher import with_switcher
from cont.fab.catalog import catalog, load, make, meshes, own_sample, set_condition, types_data
from cont.view.diagnosis_html import CSS
from cont.view.fastening_html import EXTRA_CSS
from cont.fab.build_ui import BUILD_CSS, BUILD_HTML, BUILD_JS
from cont.fab.sketches import SKETCH_CSS
from cont.view.field_image import FIELD_CSS

MAX_BODY = 2000
MAX_UPLOAD = 8_000_000            # 올리는 CSV의 최대 크기 (바이트)
COMPARE_MAX = 3
CARD_VARIANTS = 5        # 카드에 바로 보이는 조건 단추의 수. 나머지는 자세히 보기에서 고른다

STORE_CSS = """
:root,:root:root{color-scheme:light;--bg:#fff;--card:#fff;--ink:#101317;--sub:#59626C;--line:#E1E4E8;--band:#D9EFEC;--sig:#0B7F7A;--bad:#B4541A;--t:#0B7F7A;--ts:#E3F4F2;--g:#F5F6F8;--warn:#855000;--warnbg:#FDF1DC;--okbg:#E3F4F2;--ok:#0B7F7A}
html{scroll-behavior:smooth}body{margin:0;padding-bottom:96px;background:#fff;color:var(--ink);font-family:"IBM Plex Sans KR","Segoe UI","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;font-size:15px;line-height:1.55;letter-spacing:-.01em}
button,input,select{font:inherit;color:inherit}button{cursor:pointer}h1,h2,h3,p,figure{margin:0}
.top{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:14px;min-height:56px;padding:6px 24px;transition:transform .25s;background:rgba(255,255,255,.96);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);flex-wrap:wrap}
.top.away{transform:translateY(-100%)}.top .name{font-size:22px;font-weight:600;letter-spacing:-.02em;white-space:nowrap}.top .name small{font-size:14px;font-weight:500;color:var(--t);background:var(--ts);padding:4px 10px;border-radius:6px;margin-left:12px;vertical-align:3px}
.find{flex:1 1 220px;max-width:340px;display:flex;align-items:center;gap:10px;height:38px;padding:0 16px;border-radius:19px;background:var(--g);border:1px solid var(--line)}
.find:focus-within{border-color:var(--t);background:#fff}.find svg{flex:none;width:18px;height:18px}.find input{flex:1;min-width:0;border:0;outline:none;background:transparent;font-size:15px}
.page{max-width:1480px;margin:0 auto;padding:0 32px}
.hero{display:grid;grid-template-columns:minmax(0,1fr) 240px;gap:24px;align-items:center;margin-top:14px;padding:16px 28px;border-radius:22px;background:#14181D;color:#EEF1F4}
.hero h1{font-size:26px;font-weight:500;letter-spacing:-.03em;line-height:1.3}.hero p{font-size:14px;color:#A3ABB4;margin-top:6px;line-height:1.55;max-width:620px}
.hero .cnt{display:flex;gap:24px;margin-top:10px}.hero .cnt b{display:inline;font-size:20px;margin-right:6px;font-weight:300;font-variant-numeric:tabular-nums}.hero .cnt span{font-size:13px;color:#A3ABB4}.hero .cnt>div{white-space:nowrap}
.mode{flex-basis:100%;order:9;font-size:12.5px;color:#5B6670;margin:0}.hero .live{position:relative;height:150px;border-radius:20px;overflow:hidden;background:#1A1F25}.hero .live svg{position:absolute;inset:0;width:100%;height:100%;opacity:0;transition:opacity .5s}.hero .live svg.on{opacity:1}
.hero .live .cap{position:absolute;left:16px;bottom:12px;font-size:13px;color:#A3ABB4}.hero .live .cap b{color:#EEF1F4;font-weight:500}
.fbar{display:flex;gap:8px;align-items:center;margin-left:auto}.dd{position:relative}.dd summary{list-style:none;display:flex;gap:6px;align-items:center;height:38px;padding:0 14px;border:1px solid var(--line);border-radius:19px;font-size:14px;cursor:pointer;background:#fff;white-space:nowrap}.dd summary::-webkit-details-marker{display:none}.dd summary span{color:var(--sub)}.dd summary b{font-weight:600}.dd summary::after{content:"▾";font-size:11px;color:var(--sub)}.dd[open] summary{border-color:var(--ink)}
.dd .menu{position:absolute;top:44px;right:0;min-width:190px;max-height:60vh;overflow:auto;background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 12px 40px rgba(16,19,23,.16);padding:6px;display:flex;flex-direction:column;z-index:30}.dd .menu button{height:40px;text-align:left;padding:0 12px;border:0;border-radius:8px;background:#fff;font-size:14px}.dd .menu button:hover{background:var(--g)}.dd .menu button[aria-pressed=true]{background:var(--ts);color:var(--t);font-weight:600}.dd .menu label{display:flex;gap:8px;align-items:center;min-height:40px;padding:0 10px;font-size:14px;white-space:nowrap}.dd .menu input{width:16px;height:16px;accent-color:var(--t)}
.frow{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.frow>span{font-size:13px;color:var(--sub);width:42px;flex:none}
.frow button{height:40px;padding:0 16px;border-radius:20px;font-size:14px;border:1px solid var(--line);background:#fff}.frow button[aria-pressed=true]{border-color:var(--ink);background:var(--ink);color:#fff;font-weight:600}
.more{font-size:14px}.more summary{cursor:pointer;color:var(--sub);height:36px;display:inline-flex;align-items:center}.more label{display:inline-flex;align-items:center;gap:8px;min-height:36px;margin-right:18px}.more input{width:16px;height:16px;accent-color:var(--t)}
.tshelf .rail{grid-auto-columns:minmax(268px,292px)}.type{scroll-snap-align:start;border:1px dashed #B8C1CA;border-radius:18px;overflow:hidden;background:#FBFCFD;display:flex;flex-direction:column}.type[hidden]{display:none}.type.rq{border-style:solid;border-color:var(--t);box-shadow:0 0 0 1px var(--t)}
.type .pv{height:170px;background:#F3F6F8;cursor:pointer}.type .bd{padding:12px 14px 14px;display:flex;flex-direction:column;gap:6px;flex:1}.type h3{font-size:16px;font-weight:600;line-height:1.35}.type .sm{font-size:13px;color:var(--sub);line-height:1.5}
.type .tags span.soon{color:var(--warn);background:var(--warnbg)}.type .chips{display:flex;gap:4px;flex-wrap:wrap}.type .chips span{font-size:12px;color:var(--sub);border:1px solid var(--line);border-radius:10px;padding:1px 8px}.type .eng{font-size:12.5px;color:var(--sub)}.type .eng b{color:var(--ink);font-weight:600}
.type .ft{display:flex;align-items:center;gap:8px;margin-top:auto;padding-top:8px}.add.req{background:#fff;color:var(--t);border:1px solid var(--t)}.add.req.in{background:var(--t);color:#fff}
details.old{margin-top:34px;border-top:1px solid var(--line);padding-top:10px}details.old>summary{cursor:pointer;font-size:17px;font-weight:600;min-height:44px;display:flex;align-items:center;gap:10px}details.old>summary small{font-size:13px;font-weight:400;color:var(--sub)}
#tdetail{border:0;border-radius:20px;padding:0;width:min(920px,94vw);max-height:92vh;overflow:auto}#tdetail::backdrop{background:rgba(20,24,29,.5)}#tdetail .dl{display:grid;grid-template-columns:1.1fr 1fr}#tdetail .big .pv{height:100%;min-height:300px;cursor:default}
.myfab .got .rq{border-style:dashed}.myfab .got .rq em{font-style:normal;display:flex;flex-direction:column;font-size:12.5px;color:#EEF1F4}.myfab .got .rq small{color:#A3ABB4;font-size:11.5px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:760px){#tdetail .dl{grid-template-columns:1fr}}
.shelf{margin-top:26px}.shelf[hidden]{display:none}.shelf>header{display:flex;align-items:baseline;gap:12px;margin-bottom:12px}.shelf h2{font-size:22px;font-weight:600;letter-spacing:-.02em}.shelf header span{font-size:13.5px;color:var(--sub)}
.shelf .nav{margin-left:auto;display:flex;gap:6px}.shelf .nav button{width:40px;height:40px;border-radius:20px;border:1px solid var(--line);background:#fff;font-size:18px;line-height:1}
.rail{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(268px,292px);gap:16px;overflow-x:auto;scroll-snap-type:x proximity;padding:2px 2px 14px;scrollbar-width:thin;scrollbar-color:#C3C9D0 transparent}
.none{color:var(--sub);padding:40px 0}.none[hidden]{display:none}
.item{scroll-snap-align:start;border:1px solid var(--line);border-radius:18px;overflow:hidden;background:#fff;display:flex;flex-direction:column}.item[hidden]{display:none}.item.in{border-color:var(--t);box-shadow:0 0 0 1px var(--t)}
.pv{height:190px;background:var(--g);display:flex;align-items:center;justify-content:center;overflow:hidden;color:var(--ink);border:0;padding:0;width:100%}
.pv>svg{display:block;width:100%;height:100%}.pv .tick{font-size:12px}.pv .sig{fill:none;stroke:var(--sig);stroke-width:2.6;stroke-linejoin:round;stroke-linecap:round}.pv .area{fill:var(--sig);opacity:.12;stroke:none}.pv .dot{fill:var(--sig)}.pv.pad>svg{padding:10px;box-sizing:border-box}.pv.dark{background:#14181D}
.pv ol,.pv dl{margin:0;padding:12px 16px;font-size:13px;line-height:1.5;width:100%;text-align:left;box-sizing:border-box}.pv ol{list-style:none;display:grid;gap:8px}.pv ol b{display:block;font-size:12px;color:var(--t)}
.pv dt{font-size:12px;color:var(--t);font-weight:600;margin-top:5px}.pv dd{margin:0}.pv dl.nums dd{font-size:20px;font-weight:300;font-variant-numeric:tabular-nums}
.strip{display:grid;grid-template-columns:repeat(4,1fr);width:100%;height:100%;background:#14181D}.strip.two{grid-template-columns:repeat(2,1fr)}.strip figure{position:relative;min-width:0}.strip svg{display:block;width:100%;height:100%}
.strip figcaption{position:absolute;left:0;right:0;bottom:6px;text-align:center;font-size:11.5px;color:#EEF1F4}
.item .bd{padding:12px 14px 14px;display:flex;flex-direction:column;gap:5px;flex:1}.tags{display:flex;gap:6px;flex-wrap:wrap}
.tags span{font-size:12px;font-weight:600;color:var(--t);background:var(--ts);padding:2px 8px;border-radius:6px}.tags span+span{color:var(--sub);background:var(--g)}.tags span:nth-child(2){color:var(--warn);background:var(--warnbg)}
.item h3{font-size:16px;font-weight:600;line-height:1.35}.item .sm{font-size:13px;color:var(--sub);line-height:1.5}.vars{display:flex;gap:5px;flex-wrap:wrap;margin:4px 0 2px}.vars button{height:32px;padding:0 10px;border-radius:16px;border:1px solid var(--line);background:#fff;font-size:12.5px}.vars button[aria-pressed=true]{border-color:var(--t);background:var(--ts);color:var(--t);font-weight:600}.pv .bar{fill:var(--sig)}.pv .bar.low{fill:var(--bad)}.item .fieldimg .fn,.item .fieldimg .fs,.item .fieldimg .ft{display:none}.item .fieldimg .fmark{stroke-width:5}.item{cursor:pointer}.item:hover{border-color:#aab4bd}.item .sm{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.dl .facts .lb{font-size:15px;font-weight:600;color:var(--ink);margin-bottom:6px}.dl .facts ul{list-style:none;margin:0;padding:0;display:grid;gap:0}.dl .facts li{display:flex;justify-content:space-between;gap:16px;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}.dl .facts li span{color:var(--sub)}.dl .facts li b{font-weight:600;font-variant-numeric:tabular-nums;text-align:right}.item .facts{font-size:12.5px;color:var(--sub);line-height:1.5}.item .facts b{color:var(--ink);font-weight:500}
.item .ft{display:flex;align-items:center;gap:8px;margin-top:auto;padding-top:8px}.item .ft label{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--sub);min-height:44px}.item .ft input{width:16px;height:16px;accent-color:var(--t)}
.add{margin-left:auto;height:44px;padding:0 18px;border-radius:10px;border:0;background:var(--t);color:#fff;font-size:14px;font-weight:600;white-space:nowrap}.add.in{border:1px solid var(--t);background:var(--ts);color:var(--t)}
.set{scroll-snap-align:start;border:1px solid var(--line);border-radius:18px;padding:18px;display:flex;flex-direction:column;gap:8px;background:var(--g)}.set h3{font-size:18px;font-weight:600}.set p{font-size:13.5px;color:var(--sub)}
.set ul{margin:0;padding:0;list-style:none;font-size:14px;line-height:1.8}.set li::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--t);margin-right:10px;vertical-align:2px}
dialog{border:0;border-radius:24px;padding:0;max-width:min(1100px,calc(100vw - 32px));width:100%;max-height:calc(100dvh - 32px);color:var(--ink);box-shadow:0 24px 80px rgba(16,19,23,.28)}dialog::backdrop{background:rgba(16,19,23,.45)}
.dl{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);max-height:calc(100dvh - 32px)}.dl .big{background:var(--g);display:flex;flex-direction:column;min-height:0}
.dl .big .pv{flex:1;height:auto;min-height:320px}.dl .picks{display:flex;gap:6px;flex-wrap:wrap;padding:12px 16px;border-top:1px solid var(--line);background:#fff}
.dl .picks button{height:36px;padding:0 12px;border-radius:18px;border:1px solid var(--line);background:#fff;font-size:13px}.dl .picks button[aria-pressed=true]{border-color:var(--t);background:var(--ts);color:var(--t);font-weight:600}
.dl .info{padding:24px 26px;overflow-y:auto;display:flex;flex-direction:column;gap:10px}.dl h2{font-size:24px;font-weight:600;letter-spacing:-.02em}.dl .sm{font-size:14.5px;color:var(--sub)}
.dl dl.meta{display:grid;grid-template-columns:76px 1fr;gap:6px 14px;margin:6px 0 0;font-size:14px}.dl dl.meta dt{color:var(--sub)}.dl dl.meta dd{margin:0}
.dl .st{font-size:13px;color:var(--warn);font-weight:500}.dl .with{display:flex;gap:6px;flex-wrap:wrap}.dl .with button{height:36px;padding:0 12px;border-radius:18px;border:1px solid var(--line);background:#fff;font-size:13px}
.mk{border-top:1px solid var(--line);padding-top:12px;display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap}.mk[hidden]{display:none}.mk label{font-size:12.5px;color:var(--sub)}
.mk select,.mk input{display:block;height:44px;margin-top:2px;padding:0 10px;border-radius:10px;border:1px solid var(--line);font-size:15px;background:#fff;width:130px}.mk button{height:44px;padding:0 16px;border-radius:10px;border:1px solid var(--ink);background:#fff;font-size:14px}
.mk .msg{flex-basis:100%;font-size:12.5px;color:var(--sub)}.dl .acts{display:flex;gap:8px;margin-top:auto;padding-top:12px}.dl .acts .add{margin:0;flex:1;height:48px}.dl .acts .x{height:48px;padding:0 18px;border-radius:10px;border:1px solid var(--ink);background:#fff}
.cmp{padding:22px 24px}.cmp h2{font-size:22px;font-weight:600;margin-bottom:14px}.cmp .cols{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:16px}.cmp .col{border:1px solid var(--line);border-radius:16px;overflow:hidden}
.cmp .col .pv{height:240px}.cmp .col .bd{padding:12px 14px;font-size:14px}.cmp .col h3{font-size:16px;font-weight:600}.cmp .col .facts{font-size:13px;color:var(--sub);margin-top:6px;line-height:1.7}.cmp .col .facts b{color:var(--ink);font-weight:500}
.cmp .x{margin-top:14px;height:44px;padding:0 18px;border-radius:10px;border:1px solid var(--ink);background:#fff}
.myfab{position:fixed;left:0;right:0;bottom:0;z-index:15;display:flex;align-items:center;gap:14px;min-height:72px;padding:10px 32px;background:#14181D;color:#EEF1F4;flex-wrap:wrap}
.myfab .ttl{font-size:16px;font-weight:600;white-space:nowrap}.myfab .ttl b{color:#5ED1CB;font-weight:600;margin-left:6px}.myfab .got{display:flex;gap:6px;flex:1;min-width:0;overflow-x:auto;scrollbar-width:none}
.myfab .got button{flex:none;height:36px;padding:0 12px;border-radius:18px;border:1px solid #3A444F;background:transparent;color:#EEF1F4;font-size:13px;white-space:nowrap}.myfab .got span{font-size:13.5px;color:#A3ABB4;align-self:center}
.myfab input{height:44px;width:190px;padding:0 12px;border-radius:10px;border:1px solid #3A444F;background:#1E242B;color:#EEF1F4;font-size:14px}.myfab input::placeholder{color:#8A929B}
.myfab .go{height:44px;padding:0 16px;border-radius:10px;border:0;background:#2BB5AE;color:#0B1114;font-size:14px;font-weight:600;white-space:nowrap}.myfab .go[disabled],.myfab .cp[disabled]{opacity:.4;cursor:default}
.myfab .cp{height:44px;padding:0 14px;border-radius:10px;border:1px solid #EEF1F4;background:transparent;color:#EEF1F4;font-size:14px;white-space:nowrap}.myfab .nx{font-size:12.5px;color:#A3ABB4;white-space:nowrap}
button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid var(--t);outline-offset:2px}.myfab button:focus-visible,.myfab input:focus-visible{outline-color:#5ED1CB}
@media (max-width:900px){.page{padding:0 16px}.top{padding:6px 16px;gap:8px;flex-wrap:wrap}.fbar{width:100%;margin-left:0;flex-wrap:wrap}.dd .menu{left:0;right:auto}.hero{grid-template-columns:1fr;padding:16px 20px;gap:12px}.hero h1{font-size:22px}.hero .live{display:none}
.dl{grid-template-columns:1fr;overflow-y:auto}.dl .big .pv{min-height:220px}.cmp .cols{grid-auto-flow:row}.myfab{padding:10px 16px;gap:8px}.myfab input{width:130px}.myfab .nx{display:none}body{padding-bottom:140px}}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition-duration:.01s!important}}
"""

STORE_JS = r"""
(function(){
var D=JSON.parse(document.getElementById('store-data').textContent),cmp=[],form='all',use='all',q='',cur=null,curS=0,grp='form';
var $=function(s,r){return (r||document).querySelector(s)},all=function(s,r){return [].slice.call((r||document).querySelectorAll(s));};
function esc(t){var d=document.createElement('div');d.textContent=t==null?'':String(t);return d.innerHTML;}
function item(k){return D.items.filter(function(x){return x.key===k;})[0];}
function pad(it){return (it.form==='graph'||it.form==='signal'||it.form==='image')?' pad':(it.form==='3d'||it.form==='4d'||it.form==='video')?' dark':'';}
function facts(s){return s.facts.map(function(f){return esc(f[0])+' <b>'+esc(f[1])+'</b>';}).join(' · ');}
function areas(){return all('input[data-area]').filter(function(x){return x.checked;}).map(function(x){return x.dataset.area;});}
function vars(it,si){if(it.samples.length<2)return '';var n=Math.min(it.samples.length,D.card_variants),short=it.samples.map(function(x){return x.label.split(' · ')[0];}),uniq=short.filter(function(v,i){return short.indexOf(v)===i;}).length===short.length;return '<div class="vars" role="group" aria-label="조건 고르기">'+it.samples.slice(0,n).map(function(x,i){return '<button type="button" data-var="'+i+'" aria-pressed="'+(i===si)+'">'+esc(uniq?short[i]:x.label)+'</button>';}).join('')
+(it.samples.length>n?'<button type="button" data-open>+'+(it.samples.length-n)+'</button>':'')+'</div>';}
function head(s){var f=s.facts[0];return f?esc(f[0])+' <b>'+esc(f[1])+'</b>':'';}
function thumb(h){return h.replace(/viewBox="[^"]*"( data-card="([^"]*)")/,function(m,a,b){return 'viewBox="'+b+'"'+a;});}
function card(it,si){var s=it.samples[si];return '<article class="item" data-k="'+esc(it.key)+'" data-s="'+si+'"><button type="button" class="pv'+pad(it)+'" data-open aria-label="'+esc(it.name)+' 자세히 보기">'+thumb(s.html)+'</button><div class="bd">'
+'<div class="tags"><span>'+esc(it.form_label)+'</span></div><h3>'+esc(it.name)+'</h3><p class="sm">'+esc(it.short)+'</p>'+vars(it,si)
+'<div class="facts">'+head(s)+'</div>'
+'<div class="ft"><label><input type="checkbox" data-cmp="'+esc(it.key+'#'+si)+'">견주기</label><button type="button" class="add" data-add>담기</button></div></div></article>';}
function swap(el,si){var it=item(el.dataset.k),s=it.samples[si],old=el.dataset.k+'#'+el.dataset.s,i=cmp.indexOf(old);el.dataset.s=si;$('.pv',el).innerHTML=thumb(s.html);$('.facts',el).innerHTML=head(s);
all('[data-var]',el).forEach(function(b){b.setAttribute('aria-pressed',Number(b.dataset.var)===si?'true':'false');});var c=$('input[data-cmp]',el);c.dataset.cmp=it.key+'#'+si;if(i>=0)cmp[i]=c.dataset.cmp;bar();}
function tcard(t){return '<article class="type" data-t="'+esc(t.key)+'"><button type="button" class="pv" data-topen aria-label="'+esc(t.name)+' 자세히 보기">'+t.sketch_svg+'</button><div class="bd"><div class="tags"><span>'+esc(t.form_label)+'</span><span class="soon">준비 중 · 엔진 없음</span></div><h3>'+esc(t.name)+'</h3><p class="sm">'+esc(t.shows)+'</p><div class="chips">'+t.controls.map(function(c){return '<span>'+esc(c)+'</span>';}).join('')+'</div><div class="eng">필요한 엔진 <b>'+esc(t.engine_name)+'</b></div><div class="ft"><span></span><button type="button" class="add req" data-req aria-pressed="false">필요해요</button></div></div></article>';}
function build(){var h='',groups=grp==='form'?D.forms:D.quantities.map(function(x){return [x,x];}),open=D.types.filter(function(t){return !t.covered_by.length;});
h+='<section class="shelf" data-shelf="set"><header><h2>세트</h2><span>지금 한 번에 담을 수 있는 묶음</span></header><p id="setnote" class="sm" role="status" hidden></p><div class="rail">'+D.sets.map(function(s,i){return '<article class="set"><h3>'+esc(s.name)+'</h3><p>'+esc(s.summary)+'</p><ul>'+s.items.map(function(k){return '<li>'+esc(item(k).name)+'</li>';}).join('')+'</ul>'+(s.condition&&s.condition.note?'<p class="sm setcond">'+esc(s.condition.note)+'</p>':'')+'<button type="button" class="add" style="margin:auto 0 0" data-set="'+i+'">세트 담기</button></article>';}).join('')+'</div></section>';
groups.forEach(function(f){var its=D.items.filter(function(x){return x[grp]===f[0];});if(!its.length)return;var n=its.reduce(function(a,x){return a+x.samples.length;},0);
h+='<section class="shelf" data-shelf="'+esc(f[0])+'"><header><h2>'+esc(f[1])+'</h2><span><b data-n></b> · 지금 쓸 수 있는 상품 '+its.length+'가지, 조건 '+n+'개</span><div class="nav"><button type="button" data-go="-1" aria-label="앞으로">‹</button><button type="button" data-go="1" aria-label="뒤로">›</button></div></header><div class="rail">'
+its.map(function(it){return card(it,0);}).join('')+'</div></section>';});
h+='<details class="old" id="soon"><summary>확장 예정 (엔진이 없는 것)<small>준비 중 '+open.length+'가지 · 아직 계산하지 못하고 실행 단추도 없습니다</small></summary>';
groups.forEach(function(f){var ts=open.filter(function(x){return x[grp]===f[0];});if(!ts.length)return;
h+='<section class="shelf tshelf" data-shelf="t-'+esc(f[0])+'"><header><h2>'+esc(f[1])+'</h2><span><b data-n></b> · 준비 중 '+ts.length+'가지</span><div class="nav"><button type="button" data-go="-1" aria-label="앞으로">‹</button><button type="button" data-go="1" aria-label="뒤로">›</button></div></header><div class="rail">'+ts.map(tcard).join('')+'</div></section>';});
h+='</details>';$('#shelves').innerHTML=h;}
function apply(){var on=areas(),total=0;all('.shelf').forEach(function(sh){if(sh.classList.contains('tshelf')){var ts=0;all('.type',sh).forEach(function(el){var t=typ(el.dataset.t),text=(t.name+' '+t.shows+' '+t.controls.join(' ')+' '+t.engine_name+' '+t.quantity+' '+t.form_label+' '+t.group).toLowerCase(),ok=(form==='all'||t.form===form)&&(use==='all'||t.uses.indexOf(use)>=0)&&(!q||text.indexOf(q)>=0);el.hidden=!ok;if(ok)ts++;var r=hasReq(t.key);el.classList.toggle('rq',r);var b=$('.add',el);b.textContent=r?'필요해요 ✓':'필요해요';b.classList.toggle('in',r);b.setAttribute('aria-pressed',r?'true':'false');});sh.hidden=!ts;total+=ts;var nn=$('[data-n]',sh);if(nn)nn.textContent='보이는 것 '+ts;return;}if(sh.dataset.shelf==='set'){sh.hidden=!!q||form!=='all'||use!=='all';return;}var shown=0;
all('.item',sh).forEach(function(el){var it=item(el.dataset.k),text=(it.name+' '+it.samples.map(function(x){return x.label;}).join(' ')+' '+it.summary+' '+it.area+' '+it.quantity+' '+it.form_label+' '+it.needs+' '+it.gives).toLowerCase();
var ok=(form==='all'||it.form===form)&&(use==='all'||it.uses.indexOf(use)>=0)&&on.indexOf(it.area)>=0&&(!q||text.indexOf(q)>=0);el.hidden=!ok;if(ok)shown++;
var inb=isIn(it.key,Number(el.dataset.s));el.classList.toggle('in',has(it.key));var a=$('.add',el);a.textContent=inb?'담김':'담기';a.classList.toggle('in',inb);a.setAttribute('aria-pressed',inb?'true':'false');
var c=$('input[data-cmp]',el);c.checked=cmp.indexOf(c.dataset.cmp)>=0;});sh.hidden=!shown;total+=shown;var n=$('[data-n]',sh);if(n)n.textContent='보이는 것 '+shown;});
$('#none').hidden=total>0;bar();}
/* 자세히 보기 */
function reduced(){return window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;}
function flip(card,d,out){if(!card||reduced()||!d.animate)return null;var a=card.getBoundingClientRect(),b=d.getBoundingClientRect();if(!b.width||!b.height)return null;var small='translate('+(a.left+a.width/2-b.left-b.width/2)+'px,'+(a.top+a.height/2-b.top-b.height/2)+'px) scale('+a.width/b.width+','+a.height/b.height+')',f=[{transform:small,opacity:.35},{transform:'none',opacity:1}];return d.animate(out?f.reverse():f,{duration:out?240:380,easing:'cubic-bezier(.2,.8,.2,1)'});}
function shut(){var d=$('#detail'),c=cur&&document.querySelector('.item[data-k="'+cur.key+'"]'),a=c&&c.getBoundingClientRect(),inview=a&&a.bottom>0&&a.top<innerHeight,m=inview&&flip(c,d,true);if(m){m.onfinish=function(){d.close();};}else d.close();}
function detail(k,si,src){cur=item(k);curS=si||0;var it=cur;$('#d-name').textContent=it.name;$('#d-sum').textContent=it.summary;$('#d-tags').innerHTML='<span>'+esc(it.form_label)+'</span><span>'+esc(it.quantity)+'</span><span>'+esc(it.area)+'</span>';
$('#d-meta').innerHTML='<dt>넣는 것</dt><dd>'+esc(it.needs)+'</dd><dt>내는 것</dt><dd>'+esc(it.gives)+'</dd><dt>이럴 때</dt><dd>'+esc(it.uses.join(', '))+'</dd><dt>알아둘 점</dt><dd>'+esc(it.limits)+'</dd>'+(it.preview_note?'<dt>미리보기</dt><dd>'+esc(it.preview_note)+'</dd>':'');
$('#d-with').innerHTML=it.together.map(function(t){return '<button type="button" data-open-k="'+esc(t)+'">'+esc(item(t).name)+'</button>';}).join('')||'<span class="sm">없음</span>';
ownForm();sample();if(!$('#detail').open){$('#detail').showModal();flip(src,$('#detail'),false);}}
function sample(){var it=cur,s=it.samples[curS];$('#d-pv').className='pv'+pad(it);$('#d-pv').innerHTML=s.html;$('#d-facts').innerHTML='<div class="lb">'+esc(s.label)+'</div><ul>'+s.facts.map(function(f){return '<li><span>'+esc(f[0])+'</span><b>'+esc(f[1])+'</b></li>';}).join('')+'</ul>';
$('#d-picks').innerHTML=it.samples.map(function(x,i){return '<button type="button" data-pick="'+i+'" aria-pressed="'+(i===curS)+'">'+esc(x.label)+'</button>';}).join('');
var inb=isIn(it.key,curS),a=$('#d-add');a.textContent=inb?'담김 (빼기)':'이 조건으로 내 FAB에 담기';a.classList.toggle('in',inb);a.disabled=!!s.own;if(s.own)a.textContent='내 신호는 아직 담을 수 없습니다';if(s.params&&s.params.size){$('#mk-size').value=s.params.size;$('#mk-torque').value=s.params.torque;}richDetail();}
function compare(){$('#c-cols').innerHTML=cmp.map(function(id){var p=id.split('#'),it=item(p[0]),s=it.samples[Number(p[1])];return '<div class="col"><div class="pv'+pad(it)+'">'+s.html+'</div><div class="bd"><h3>'+esc(it.name)+'</h3><div>'+esc(s.label)+'</div><div class="facts">'+s.facts.map(function(f){return esc(f[0])+' <b>'+esc(f[1])+'</b>';}).join('<br>')+'</div></div></div>';}).join('');$('#cmp').showModal();}
function tdetail(k){var t=typ(k);if(!t)return;$('#t-pv').innerHTML=t.sketch_svg;$('#t-tags').innerHTML='<span>'+esc(t.form_label)+'</span><span class="soon">준비 중 · 엔진 없음</span><span>'+esc(t.quantity)+'</span>';$('#t-name').textContent=t.name;$('#t-sum').textContent=t.shows;
$('#t-meta').innerHTML='<dt>바꿀 수 있는 것</dt><dd>'+esc(t.controls.join(', '))+'</dd><dt>필요한 엔진</dt><dd>'+esc(t.engine_name)+' — '+esc(D.engines[t.engine].summary)+'</dd><dt>넣는 것</dt><dd>'+esc(t.needs)+'</dd><dt>엔진이 생기면 보이는 것</dt><dd>'+esc(t.ready)+'</dd><dt>이럴 때</dt><dd>'+esc(t.uses.join(', '))+'</dd>'+(t.note?'<dt>알아둘 점</dt><dd>'+esc(t.note)+'</dd>':'');
$('#t-req').dataset.req=k;tsync(k);if(!$('#tdetail').open)$('#tdetail').showModal();}
function tsync(k){var r=hasReq(k),b=$('#t-req');b.textContent=r?'필요해요 ✓ (취소)':'필요해요';b.classList.toggle('in',r);}
document.addEventListener('click',function(e){var tb=e.target.closest&&e.target.closest('button'),tc=e.target.closest&&e.target.closest('.type');if(tb&&tb.dataset.req!=null){var tk=tb.id==='t-req'?tb.dataset.req:(tc&&tc.dataset.t);if(tk){toggleReq(tk);apply();tsync(tk);}return;}
if(tb&&tb.id==='t-close'){$('#tdetail').close();return;}if(tc&&(tb?tb.dataset.topen!=null:true)){tdetail(tc.dataset.t);return;}
var b=e.target.closest&&e.target.closest('button');if(!b){var cd=e.target.closest&&e.target.closest('.item');if(cd&&!e.target.closest('label,input'))detail(cd.dataset.k,Number(cd.dataset.s),cd);return;}var el=b.closest('.item');
if(b.dataset.var!=null&&el){swap(el,Number(b.dataset.var));return;}if(b.dataset.grp!=null){grp=b.dataset.grp;all('[data-grp]').forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});build();apply();return;}
if(b.dataset.open!=null&&el){detail(el.dataset.k,Number(el.dataset.s),el);return;}if(b.dataset.openK){detail(b.dataset.openK,0);return;}
if(b.dataset.add!=null&&el){addPick(el.dataset.k,Number(el.dataset.s));apply();return;}if(b.dataset.set!=null){var st=D.sets[Number(b.dataset.set)],pk=(st.condition&&st.condition.pick)||{};st.items.forEach(function(k){if(!has(k))addPick(k,pk[k]||0);});var nt=$('#setnote');if(nt){nt.textContent=st.name+': '+(st.condition&&st.condition.note||'조건 변수가 없는 상품만 있어 그대로 담습니다');nt.hidden=false;}apply();return;}
if(b.dataset.form!=null){form=b.dataset.form;all('[data-form]').forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});apply();return;}
if(b.dataset.use!=null){use=b.dataset.use;all('[data-use]').forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});apply();return;}
if(b.dataset.go!=null){var r=$('.rail',b.closest('.shelf'));r.scrollBy({left:Number(b.dataset.go)*r.clientWidth*0.85,behavior:'smooth'});return;}
if(b.dataset.drop!=null){dropPick(b.dataset.drop);apply();return;}if(b.dataset.pick!=null){curS=Number(b.dataset.pick);sample();var c0=document.querySelector('.item[data-k="'+cur.key+'"]');if(c0&&curS<D.card_variants)swap(c0,curS);return;}
if(b.id==='d-add'){if(cur.samples[curS].own)return;addPick(cur.key,curS,detailView&&JSON.parse(JSON.stringify(detailView)));apply();sample();return;}if(b.id==='d-close'){shut();return;}if(b.id==='c-close'){$('#cmp').close();return;}if(b.id==='cmpb'){compare();return;}
});
document.addEventListener('change',function(e){var c=e.target;if(c.dataset&&c.dataset.cmp!=null){var i=cmp.indexOf(c.dataset.cmp);if(c.checked&&i<0){if(cmp.length>=D.compare_max){c.checked=false;return;}cmp.push(c.dataset.cmp);}if(!c.checked&&i>=0)cmp.splice(i,1);bar();}
if(c.dataset&&c.dataset.area!=null)apply();});
$('#q').addEventListener('input',function(){q=this.value.trim().toLowerCase();apply();});
var ownText='',ownN=[];
function ownForm(){var w=$('#own');w.hidden=!cur.own;if(!cur.own)return;$('#own-static').hidden=!!D.analyze_url;$('#own-form').hidden=!D.analyze_url;all('#own [data-wave]').forEach(function(l){l.hidden=cur.own==='values';});ownFs();}
function ownFs(){$('#own-fs-l').hidden=cur.own==='values'||$('#own-time').value!=='-1';$('#own-time-unit-l').hidden=cur.own==='values'||$('#own-time').value==='-1';}
function ownNames(t){var l=t.replace(/^\uFEFF/,'').split(/\r?\n/).filter(function(x){return x.trim();})[0]||'',d=[',','\t',';'].map(function(c){return [c,l.split(c).length];}).sort(function(a,b){return b[1]-a[1];})[0][0],c=l.split(d).map(function(x){return x.trim();});
return c.every(function(x){return x!==''&&!isNaN(Number(x));})?c.map(function(_,i){return '열 '+(i+1);}):c.map(function(x,i){return x||'열 '+(i+1);});}
$('#own-file').addEventListener('change',function(){var f=this.files[0],m=$('#own-msg');ownText='';$('#own-go').disabled=true;if(!f)return;if(f.size>8000000){m.textContent='파일이 너무 큽니다 (8 MB 이하만 됩니다).';return;}
var r=new FileReader();r.onload=function(){ownText=String(r.result);ownN=ownNames(ownText);var ti=ownN.findIndex(function(x){return /^(t|time|시간|시각|sec|s)([\s_\-(\[].*)?$/i.test(x);}),vi=ownN.findIndex(function(_,i){return i!==ti;});if(vi<0)vi=0;
$('#own-col').innerHTML=ownN.map(function(x,i){return '<option value="'+i+'">'+esc(x)+'</option>';}).join('');$('#own-col').value=String(vi);
$('#own-time').innerHTML='<option value="-1">없음 (샘플링 주파수를 적습니다)</option>'+ownN.map(function(x,i){return '<option value="'+i+'">'+esc(x)+'</option>';}).join('');$('#own-time').value=String(ti);
$('#own-col').disabled=$('#own-time').disabled=false;$('#own-go').disabled=false;m.textContent=ownN.length+'개 열을 읽었습니다. 값 열을 확인하세요.';ownFs();};r.onerror=function(){m.textContent='파일을 읽지 못했습니다.';};r.readAsText(f);});
$('#own-time').addEventListener('change',ownFs);
$('#own-form').addEventListener('submit',function(e){e.preventDefault();if(!ownText||!cur||!cur.own)return;var m=$('#own-msg'),f=$('#own-file').files[0],asked=cur;m.textContent='엔진이 계산하는 중입니다.';
var body={key:cur.key,csv:ownText,column:Number($('#own-col').value),time_column:Number($('#own-time').value),time_unit:$('#own-time-unit').value,fs:$('#own-fs').value,fmax:$('#own-fmax').value,unit:$('#own-unit').value,filename:f?f.name:''};
fetch(D.analyze_url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(function(r){return r.json();}).then(function(s){if(s.error){m.textContent=s.error;return;}
var tg=asked,i=tg.samples.map(function(x){return x.label;}).indexOf(s.label);if(i<0){tg.samples.push(s);i=tg.samples.length-1;}else tg.samples[i]=s;if(cur===tg){curS=i;sample();m.textContent='계산했습니다: '+tg.name+' · '+s.label;}else m.textContent='「'+tg.name+'」에 계산 결과를 더했습니다. 지금 보는 상품에는 반영하지 않았습니다.';}).catch(function(){m.textContent='서버에 닿지 못했습니다.';});});
$('#mk').addEventListener('submit',function(e){e.preventDefault();var body={key:cur.key,size:$('#mk-size').value,torque:$('#mk-torque').value},asked=cur;$('#mk-msg').textContent='엔진이 계산하는 중입니다.';
fetch(D.make_url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(function(r){return r.json();}).then(function(s){if(s.error){$('#mk-msg').textContent=s.error;return;}
var tg=asked,i=tg.samples.map(function(x){return x.label;}).indexOf(s.label);if(i<0){tg.samples.push(s);i=tg.samples.length-1;}else tg.samples[i]=s;if(cur===tg){curS=i;sample();$('#mk-msg').textContent='다시 만들었습니다: '+tg.name+' · '+s.label;}else $('#mk-msg').textContent='「'+tg.name+'」에 결과를 더했습니다. 지금 보는 상품에는 반영하지 않았습니다.';}).catch(function(){$('#mk-msg').textContent='답을 받지 못했습니다. 서버가 켜져 있는지 확인해 주세요.';});});
/* 맨 위의 살아 있는 한 장: 조이는 과정의 장면을 차례로 */
(function(){var fr=all('#live svg'),cap=$('#livecap'),i=0;if(!fr.length)return;function show(){fr.forEach(function(x,k){x.classList.toggle('on',k===i);});cap.innerHTML=D.hero.caps[i];}
show();if(!(window.matchMedia&&matchMedia('(prefers-reduced-motion:reduce)').matches))setInterval(function(){i=(i+1)%fr.length;show();},1100);})();
/* 거르기 메뉴: 고르면 이름이 바뀌고 닫힌다. 바깥을 누르면 닫힌다 */
document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('.dd .menu button');if(b){var d=b.closest('.dd');$('summary b',d).textContent=b.textContent;d.open=false;return;}if(!(e.target.closest&&e.target.closest('.dd')))all('.dd[open]').forEach(function(x){x.open=false;});});
document.addEventListener('change',function(e){var c=e.target;if(!(c.dataset&&c.dataset.area!=null))return;var on=areas(),n=all('input[data-area]').length;$('summary b',c.closest('.dd')).textContent=on.length===n?'전체':on.length+'개';});
all('.dd').forEach(function(d){d.addEventListener('toggle',function(){if(d.open)all('.dd[open]').forEach(function(x){if(x!==d)x.open=false;});});});
/* 위 막대는 내려가면 숨고, 올리면 다시 나온다 */
(function(){var bar=$('.top'),y=window.scrollY;window.addEventListener('scroll',function(){var n=window.scrollY;if(n>y&&n>160&&!$('.dd[open]'))bar.classList.add('away');else if(n<y)bar.classList.remove('away');y=n;},{passive:true});})();
/*BUILD*/
build();apply();document.body.dataset.ready='1';
})();
"""


def render_store(items: Sequence[Mapping[str, Any]], data: Mapping[str, Any] | None = None, make_url: str | None = None, analyze_url: str | None = None, title: str = "ConT FAB · 고르기") -> str:
    if not items:
        raise ValueError("the catalog is empty")
    data = data or load()
    e = html.escape
    forms, uses, sets = data["forms"], data["uses"], data["sets"]
    areas = list(dict.fromkeys(i["area"] for i in items))
    n_samples = sum(len(i["samples"]) for i in items)
    fchips = '<button type="button" data-form="all" aria-pressed="true">전체</button>' + "".join(
        f'<button type="button" data-form="{e(k)}" aria-pressed="false">{e(v)}</button>' for k, v in forms.items() if any(i["form"] == k for i in items))
    uchips = '<button type="button" data-use="all" aria-pressed="true">전체</button>' + "".join(f'<button type="button" data-use="{e(u)}" aria-pressed="false">{e(u)}</button>' for u in uses)
    achecks = "".join(f'<label><input type="checkbox" data-area="{e(a)}" checked>{e(a)} ({sum(i["area"] == a for i in items)})</label>' for a in areas)
    # 맨 위: 조이는 과정의 장면들 (엔진이 만든 것). 없으면 첫 상품의 첫 샘플
    hero_item = next((i for i in items if i["key"] == "fastening_process"), None)
    frames, caps = [], []
    if hero_item:
        from cont.fab.previews import _frames, joint_for
        from cont.view.iso_svg import iso_svg
        pick = next((s for s in hero_item["samples"] if s["params"].get("size") == "M10"), hero_item["samples"][0])["params"]
        f = joint_for(pick["size"], pick["torque"])
        for x in _frames(f, 6):
            frames.append(iso_svg(f["state"]["viewer"], 420, 260, hidden=True, use=x["use"], label="조이는 과정의 한 장면", background=None))
            caps.append(f'조이는 과정 · {e(f["joint"].size)} · <b>{x["torque"]:.1f} N·m → {x["preload"]:,.0f} N</b>')
    from cont.packs.fastening.standards import thread_sizes
    T = types_data()
    blob = json.dumps({"types": T["types"], "engines": T["engines"], "items": list(items), "forms": [[k, v] for k, v in forms.items()], "sets": [{**x, "condition": set_condition(items, x)} for x in sets], "make_url": make_url, "analyze_url": analyze_url, "compare_max": COMPARE_MAX, "card_variants": CARD_VARIANTS, "quantities": list(data["quantities"]), "meshes": meshes(items),
                       "hero": {"caps": caps}}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body = f"""<header class="top"><span class="name">ConT FAB<small>고르기</small></span>
<p class="mode" id="mode" role="status">{"실시간 작업 가능: 규격·조건을 바꾸면 엔진이 다시 계산합니다." if (make_url or analyze_url) else "공개 시연: 미리 계산한 샘플만 보입니다. 직접 계산은 서버로 띄운 화면에서 됩니다."}</p>
<label class="find"><svg viewBox="0 0 18 18" aria-hidden="true"><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12.2 12.2L16 16" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
<input type="search" id="q" aria-label="물리 정보 찾기" placeholder="찾기: 응력, 4D, 전류, M12" autocomplete="off"></label>
<nav class="fbar" aria-label="거르기">
<details class="dd"><summary><span>묶기</span><b>형태별</b></summary><div class="menu" role="group" aria-label="묶는 방법"><button type="button" data-grp="form" aria-pressed="true">형태별</button><button type="button" data-grp="quantity" aria-pressed="false">물리 특성별</button></div></details>
<details class="dd"><summary><span>형태</span><b>전체</b></summary><div class="menu" role="group" aria-label="형태">{fchips}</div></details>
<details class="dd"><summary><span>쓰임</span><b>전체</b></summary><div class="menu" role="group" aria-label="쓰임">{uchips}</div></details>
<details class="dd"><summary><span>물리 영역</span><b>전체</b></summary><div class="menu" role="group" aria-label="물리 영역">{achecks}</div></details></nav></header>
<div class="page">
<section class="hero"><div><h1>물리 정보를 골라<br>내 Fab을 꾸리세요</h1><p>이미지, 그래프, 3D, 4D, 신호, 계산값이 진열대에 놓여 있습니다. 카드에서 조건을 눌러 바꿔 보세요. 점선 카드는 엔진이 아직 없는 표현 유형이며 예시 그림만 보입니다. 맨 아래 "지금 되는 것"은 엔진을 실제로 돌린 결과이고, 값은 계산값이며 실측과 대조하기 전입니다.</p>
<div class="cnt"><div><b>{len(items)}</b><span>상품 (엔진)</span></div><div><b>{n_samples}</b><span>조건별 결과</span></div><div><b>{len(sets)}</b><span>세트</span></div></div></div>
<div class="live" id="live" aria-label="조이는 과정의 장면">{"".join(frames)}<div class="cap" id="livecap"></div></div></section>
<div id="shelves"></div><p class="none" id="none" hidden>맞는 것이 없습니다. 찾는 말이나 거르기를 바꿔 보세요.</p>
</div>
<dialog id="detail" aria-labelledby="d-name"><div class="dl"><div class="big"><div class="pv" id="d-pv"></div><div class="ctl" id="d-ctl"></div><div class="picks" id="d-picks" role="group" aria-label="샘플 고르기"></div></div>
<div class="info"><div class="tags" id="d-tags"></div><h2 id="d-name"></h2><p class="sm" id="d-sum"></p><div class="facts" id="d-facts" style="font-size:14px"></div><span class="st">계산값 · 검증 전</span>
<dl class="meta" id="d-meta"></dl><div id="d-more" hidden></div><div><div class="sm" style="margin-bottom:6px">함께 담으면 좋은 것</div><div class="with" id="d-with"></div></div>
<form class="mk" id="mk" hidden><label>규격<select id="mk-size">{"".join(f"<option>{e(z)}</option>" for z in thread_sizes())}</select></label>
<label>조임 토크 (N·m)<input type="number" id="mk-torque" min="0" step="0.5" inputmode="decimal"></label><button type="submit">이 조건으로 다시 만들기</button><div class="msg" id="mk-msg" aria-live="polite"></div></form>
<div id="own" hidden><div class="sm" style="margin-bottom:6px">내 신호로 보기</div>
<p class="sm" id="own-static" hidden>내 신호를 올려 보는 것은 서버로 띄운 화면(python -m cont.fab.store)에서만 됩니다. 이 화면은 미리 계산한 샘플만 보입니다.</p>
<form class="mk" id="own-form"><label>CSV 파일<input type="file" id="own-file" accept=".csv,.tsv,.txt,text/csv,text/plain"></label>
<label>값 열<select id="own-col" disabled></select></label>
<label data-wave>시간 열<select id="own-time" disabled></select></label>
<label data-wave id="own-time-unit-l">시간 단위<select id="own-time-unit"><option value="s">초 (s)</option><option value="ms">밀리초 (ms)</option><option value="us">마이크로초 (us)</option></select></label>
<label data-wave id="own-fs-l">샘플링 주파수 (Hz)<input type="number" id="own-fs" min="0" step="any" inputmode="decimal"></label>
<label data-wave>표시 주파수 상한 (Hz, 선택)<input type="number" id="own-fmax" min="0" step="any" inputmode="decimal"></label>
<label>단위 (선택)<input type="text" id="own-unit" maxlength="16" autocomplete="off"></label>
<button type="submit" id="own-go" disabled>내 신호로 보기</button><div class="msg" id="own-msg" aria-live="polite"></div>
<p class="sm">파일은 이 컴퓨터의 서버로만 보내 계산하고 저장하지 않습니다. 소수점은 점(.)으로 적은 CSV만 읽습니다. 내 신호 결과는 아직 내 FAB에 담을 수 없습니다.</p></form></div>
<div class="acts"><button type="button" class="add" id="d-add">내 Fab에 담기</button><button type="button" class="x" id="d-close">닫기</button></div></div></div></dialog>
<dialog id="tdetail" aria-labelledby="t-name"><div class="dl"><div class="big"><div class="pv" id="t-pv"></div></div>
<div class="info"><div class="tags" id="t-tags"></div><h2 id="t-name"></h2><p class="sm" id="t-sum"></p><span class="st">준비 중 · 결과가 아직 없습니다</span><dl class="meta" id="t-meta"></dl>
<p class="sm">"필요해요"를 누르면 내 FAB에 엔진 필요 목록으로 쌓입니다. 어느 엔진부터 만들지 정하는 근거로 쓰는 요청이며, 계산 결과가 아닙니다.</p>
<div class="acts"><button type="button" class="add req" id="t-req">필요해요</button><button type="button" class="x" id="t-close">닫기</button></div></div></div></dialog>
<dialog id="cmp" aria-labelledby="c-h"><div class="cmp"><h2 id="c-h">견주기</h2><div class="cols" id="c-cols"></div><button type="button" class="x" id="c-close">닫기</button></div></dialog>
<div class="myfab" aria-label="내 Fab"><span class="ttl">내 Fab<b id="pk">0</b></span><div class="got" id="got"></div>
<button type="button" class="cp" id="cmpb" disabled>견주기 0</button><input type="text" id="site" aria-label="현장 이름" placeholder="현장 이름" autocomplete="off">
<button type="button" class="cp pri" id="bopen">구성 화면 열기</button><button type="button" class="go" id="save" disabled>내려받기</button></div>
{BUILD_HTML}
<script type="application/json" id="store-data">{blob}</script><script>{STORE_JS.replace("/*BUILD*/", BUILD_JS)}</script>"""
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap" rel="stylesheet">')
    page = (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f"<title>{e(title)}</title>{fonts}<style>{CSS}{EXTRA_CSS}{FIELD_CSS}{STORE_CSS}{BUILD_CSS}{SKETCH_CSS}</style></head><body>\n{body}\n</body></html>")
    return with_switcher(page, "fab")


def record_run(action: str, inputs: Mapping[str, Any], sample: Mapping[str, Any]) -> str:
    """저장소가 켜져 있으면(CONT_RUN_DIR) 결과를 실행 한 건으로 남기고 run_id를 돌려준다. 꺼져 있으면 빈 문자열. 올린 파일 본문은 해시만 남긴다."""
    import hashlib
    from cont.service import api, runs
    st = runs.store()
    if st is None:
        return ""
    ins = {k: v for k, v in inputs.items() if k != "csv"}
    if "csv" in inputs:
        ins["csv_sha256"] = hashlib.sha256(str(inputs["csv"]).encode("utf-8")).hexdigest()
    body = json.loads(json.dumps(sample, ensure_ascii=False, default=str))
    rid = api.new_run_id()
    st.save({"run_id": rid, "created_at": runs.now(), "pack": "fab", "action": action, "question": "", "inputs": ins,
             "model_version": runs.model_version("fab"), "project_id": "", "asset_id": "", "parent_run_id": "", "status": "complete",
             "error": "", "response": body, "content_hash": hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(), "revision_id": ""})
    return rid


def stored_sample(run_id: str) -> dict[str, Any]:
    """저장된 실행에서 샘플을 읽는다. 저장소가 꺼져 있거나 없는 실행이면 KeyError, 기록이 깨졌으면 ValueError."""
    from cont.service import runs
    st = runs.store()
    if st is None:
        raise KeyError("실행 저장소가 켜져 있지 않습니다")
    try:
        rec = st.get(run_id)
    except runs.RunNotFound:
        raise KeyError(run_id) from None
    if rec.get("pack") != "fab" or not isinstance(rec.get("response"), dict):
        raise KeyError(run_id)
    return rec["response"]


def make_server(port: int = 8768) -> ThreadingHTTPServer:
    page = render_store(catalog(), make_url="/make", analyze_url="/analyze").encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8")
            elif self.path.startswith("/run/"):
                try:
                    out = {"sample": stored_sample(self.path[5:])}
                except KeyError:
                    return self._send(404, json.dumps({"error": "저장된 결과를 찾지 못했습니다"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                except ValueError as exc:
                    return self._send(500, json.dumps({"error": f"저장된 기록이 깨졌습니다: {exc}"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                self._send(200, json.dumps(out, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/make", "/analyze"):
                return self._send(404, b"not found", "text/plain")
            analyze = self.path == "/analyze"
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= (MAX_UPLOAD if analyze else MAX_BODY):
                    raise ValueError("요청을 읽지 못했거나 파일이 너무 큽니다" if analyze else "요청을 읽지 못했습니다")
                d = json.loads(self.rfile.read(n))
                ins = d if analyze else {"key": str(d.get("key", "")), "size": d.get("size", ""), "torque": d.get("torque")}
                out = own_sample(str(d.get("key", "")), d) if analyze else make(str(d.get("key", "")), {"size": d.get("size", ""), "torque": d.get("torque")})
                out = {**out, "run_id": record_run("analyze" if analyze else "make", ins, out)}
            except Exception as exc:        # 계산할 수 없는 조건이면 이유를 돌려준다 (화면은 그대로 둔다)
                return self._send(200, json.dumps({"error": (f"이 파일로는 볼 수 없습니다: {exc}" if analyze else f"이 조건으로는 만들지 못했습니다: {exc}")}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            self._send(200, json.dumps(out, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, *_: Any) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="서버를 띄우지 않고 고르기 화면을 파일 하나로 쓴다")
    ap.add_argument("--port", type=int, default=8768)
    a = ap.parse_args(argv)
    if a.out:
        items = catalog()
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(render_store(items))
        print(f"written {a.out}: {len(items)} item(s), {sum(len(i['samples']) for i in items)} sample(s)")
        return
    srv = make_server(a.port)
    from cont.buildinfo import banner
    print(banner())
    print(f"http://127.0.0.1:{a.port}  (끝내기: Ctrl+C)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
