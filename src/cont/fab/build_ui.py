"""ConT FAB 고르기 화면의 '내 FAB' 부분: 담은 것(조건과 보던 설정까지), 3D 돌려 보기, 4D·영상 재생, 구성 화면, 저장·다시 열기.

store.py의 화면 스크립트 안에 끼워 넣는다 (같은 변수 D, item, cur, curS를 쓴다).
담을 때 보존하는 것: 조건(규격·토크가 들어간 이름), 3D 시점·보이는 부품, 재생 단계. 데이터 연결은 연결 정보만 적고,
실제로 현장 신호를 읽어 오는 기능은 아직 없다. 저장 파일(cont-fab-selection v2)에 그 사실이 드러나도록 source를 남긴다.
"""

BUILD_HTML = """<dialog id="build" class="bld" aria-labelledby="b-h"><div class="bw">
<header><h2 id="b-h">내 FAB 구성</h2><input type="text" id="b-site" aria-label="현장 이름" placeholder="현장 이름" autocomplete="off">
<span class="sp"></span><button type="button" id="b-prv" aria-pressed="false">화면 미리보기</button><button type="button" id="b-local">저장된 구성 불러오기</button>
<button type="button" id="b-fbtn">파일 열기</button><input type="file" id="b-file" accept=".json,application/json" hidden>
<button type="button" id="b-dl">내려받기</button><button type="button" class="pri" id="b-save">저장</button><button type="button" id="b-close">닫기</button></header>
<div class="main"><div class="canvas" id="b-canvas"></div><aside id="b-side" aria-label="고른 것 설정"></aside></div>
<p class="msg" id="b-msg" role="status" aria-live="polite"></p></div></dialog>"""

BUILD_CSS = """
.myfab .got .gt{flex:none;display:flex;align-items:center;gap:8px;padding:4px 6px 4px 4px;border:1px solid #3A444F;border-radius:10px;max-width:260px}
.myfab .got .mini{width:56px;height:40px;border-radius:6px;overflow:hidden;background:#1A1F25;color:#EEF1F4;font-size:5px;line-height:1.2;flex:none;display:block}
.myfab .got .mini svg{display:block;width:100%;height:100%}.myfab .got em{font-style:normal;font-size:13px;line-height:1.25;min-width:0;display:flex;flex-direction:column}
.myfab .got em b{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.myfab .got em small{font-size:11.5px;color:#A3ABB4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.myfab .got .gt button{height:28px;width:28px;padding:0;border:0;border-radius:14px;color:#A3ABB4;font-size:16px}
.myfab .cp.pri{background:#EEF1F4;color:#14181D;font-weight:600}
.dl .ctl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:10px 16px;border-top:1px solid var(--line);background:#fff;font-size:13px;color:var(--sub)}.dl .ctl:empty{display:none}
.dl .ctl button{height:36px;padding:0 12px;border-radius:18px;border:1px solid var(--line);background:#fff;font-size:13px}.dl .ctl label{display:inline-flex;gap:6px;align-items:center;min-height:36px}.dl .ctl input[type=checkbox]{width:16px;height:16px;accent-color:var(--t)}
.dl .ctl input[type=range]{flex:1;min-width:120px;accent-color:var(--t)}.c3{display:block;width:100%;height:auto;touch-action:none;cursor:grab;background:#14181D}.c3:active{cursor:grabbing}
.plst{width:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:12px}.plst svg{width:min(100%,380px);height:auto}.plst .cap{font-size:15px;font-weight:600}
.ev{margin:0 0 8px;padding:0;list-style:none;font-size:13.5px;line-height:1.55}.ev li{padding:6px 0;border-bottom:1px solid var(--line)}.ev b{display:inline-block;min-width:44px;color:var(--t);font-weight:600}
#d-more h3{font-size:15px;font-weight:600;margin:6px 0}#d-more h4{font-size:13px;font-weight:600;color:var(--sub);margin:10px 0 4px}#d-more .steps{margin:0;padding-left:18px;font-size:13.5px}#d-more p{font-size:13.5px;margin:0}
dialog.bld{max-width:min(1440px,calc(100vw - 24px));width:100%;height:calc(100dvh - 24px);max-height:none;border-radius:20px}.bw{display:flex;flex-direction:column;height:100%;min-height:0}
.bw header{display:flex;gap:8px;align-items:center;padding:14px 20px;border-bottom:1px solid var(--line);flex-wrap:wrap}.bw header h2{font-size:20px;font-weight:600;margin-right:8px}.bw .sp{flex:1}
.bw header input[type=text]{height:40px;width:170px;padding:0 12px;border-radius:10px;border:1px solid var(--line);font-size:14px}
.bw header button{height:40px;padding:0 14px;border-radius:10px;border:1px solid var(--line);background:#fff;font-size:14px;white-space:nowrap}.bw header button.pri{background:var(--t);border-color:var(--t);color:#fff;font-weight:600}.bw header button[aria-pressed=true]{border-color:var(--ink);background:var(--ink);color:#fff}
.bw .main{display:grid;grid-template-columns:minmax(0,1fr) 320px;flex:1;min-height:0}.bw .canvas{overflow-y:auto;padding:18px 20px;display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px;align-content:start;background:var(--g)}
.bw .canvas .empty{grid-column:1/-1;font-size:14.5px;color:var(--sub);padding:40px 0;text-align:center}
.tile{border:1px solid var(--line);border-radius:16px;background:#fff;overflow:hidden;display:flex;flex-direction:column;cursor:pointer}.tile.s-S{grid-column:span 4}.tile.s-M{grid-column:span 6}.tile.s-L{grid-column:span 12}.tile.sel{border-color:var(--t);box-shadow:0 0 0 1px var(--t)}
.tile .pv{height:200px;border:0;padding:0;width:100%;cursor:inherit}.tile.s-L .pv{height:320px}.tile .pv{flex:none}.tile .pv .c3{width:100%;height:100%;object-fit:contain}.tile .plst{padding:6px}.tile .plst svg{width:auto;height:150px}.tile.s-L .plst svg{height:260px}.tile .plst .cap{font-size:13px}.tile .tb{padding:10px 14px 12px;display:flex;flex-direction:column;gap:3px}.tile h3{font-size:15px;font-weight:600}.tile .cd{font-size:13px;color:var(--ink)}.tile .stt{font-size:12.5px;color:var(--sub)}.tile .warn{font-size:12.5px;color:var(--warn)}
.tile .tc{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px}.tile .tc button,.tile .tc select{height:34px;padding:0 10px;border-radius:8px;border:1px solid var(--line);background:#fff;font-size:13px}.tile .tc button[aria-pressed=true]{border-color:var(--t);background:var(--ts);color:var(--t);font-weight:600}
.tile .tc input[type=range]{flex:1;min-width:90px;accent-color:var(--t)}.bld.prv .tc{display:none}.bld.prv .tile{cursor:default}.bld.prv .tile.sel{border-color:var(--line);box-shadow:none}.bld.prv aside{display:none}.bld.prv .main{grid-template-columns:1fr}
.bw aside{border-left:1px solid var(--line);padding:18px 18px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;font-size:14px}.bw aside h3{font-size:16px;font-weight:600}.bw aside h4{font-size:13px;color:var(--sub);font-weight:600;margin:6px 0 0}
.bw aside label{display:flex;gap:8px;align-items:center;min-height:36px}.bw aside input[type=text]{height:40px;width:100%;box-sizing:border-box;padding:0 10px;border-radius:8px;border:1px solid var(--line);font-size:14px}.bw aside .note{font-size:12.5px;color:var(--sub);line-height:1.55}
.bw aside .ctl{padding:0;border:0;background:transparent}.bw .msg{margin:0;padding:8px 20px;font-size:13px;color:var(--sub);border-top:1px solid var(--line);min-height:20px}
@media (max-width:900px){.bw .main{grid-template-columns:1fr}.bw aside{border-left:0;border-top:1px solid var(--line)}.tile.s-S,.tile.s-M{grid-column:span 12}.myfab .got .gt{max-width:200px}}
"""

BUILD_JS = r"""
/* ---------- 내 FAB: 담은 것(조건과 보던 설정까지) ---------- */
var picks=[],seq=0,sel=null,activeV=null,plTimer=null,STORE_KEY='cont-fab-mine',YAW=-0.785,PITCH=0.36;
var PARTS=[['bolt','볼트'],['plate_head','위 판'],['plate_nut','아래 판'],['zone','눌리는 영역']],UI={bolt_head:'bolt',bolt_shank:'bolt',nut:'bolt',plate_head:'plate_head',plate_nut:'plate_nut',zone:'zone'};
var C3={bolt:[174,182,191],plate_head:[74,84,95],plate_nut:[61,70,80],zone:[217,164,65]},R3=[[0,[168,178,188]],[.5,[184,153,92]],[.8,[217,164,65]],[1,[245,204,112]]];
function uid(){seq+=1;return 'c'+Date.now().toString(36)+seq;}
function has(k){return picks.some(function(p){return p.key===k;});}
function labelOf(k,si){var it=item(k),s=it.samples[si]||it.samples[0];return s.label;}
function isIn(k,si){var lb=labelOf(k,si);return picks.some(function(p){return p.key===k&&p.label===lb;});}
function found(p){var it=item(p.key),i=it.samples.map(function(x){return x.label;}).indexOf(p.label);return {it:it,s:it.samples[i<0?0:i],missing:i<0};}
function figs(h){var t=document.createElement('div');t.innerHTML=h;return all('figure',t).map(function(f){var s=$('svg',f);return {svg:s?s.outerHTML:'',cap:($('figcaption',f)||{}).textContent||''};});}
function is3(it,s){return !!(s.view3d&&D.meshes&&D.meshes[s.view3d.size]);}
function isPlay(it,s){return (it.form==='4d'||it.form==='video')&&figs(s.html).length>1;}
function defView(it,s){if(is3(it,s))return {yaw:YAW,pitch:PITCH,zoom:1,off:[],see:!!s.view3d.hidden};if(isPlay(it,s))return {frame:0};return {};}
function addPick(k,si,view){var it=item(k),s=it.samples[si]||it.samples[0],i=-1;picks.forEach(function(p,j){if(p.key===k&&p.label===s.label)i=j;});
if(i>=0){picks.splice(i,1);return false;}picks.push({id:uid(),key:k,label:s.label,params:s.params||{},size:'M',view:view||defView(it,s),data:{source:'engine',channel:'',note:''}});return true;}
function dropPick(id){picks=picks.filter(function(p){return p.id!==id;});if(sel===id)sel=null;}
function bar(){$('#got').innerHTML=picks.length?picks.map(function(p){var f=found(p);return '<span class="gt"><i class="mini">'+f.s.html+'</i><em><b>'+esc(f.it.name)+'</b><small>'+esc(p.label)+'</small></em><button type="button" data-drop="'+esc(p.id)+'" aria-label="'+esc(f.it.name)+' 빼기">×</button></span>';}).join(''):'<span>아직 담은 것이 없습니다. 카드의 "담기"를 눌러 보세요.</span>';
$('#pk').textContent=picks.length;$('#save').disabled=!picks.length;$('#bopen').disabled=!picks.length&&!readLocal();$('#cmpb').disabled=cmp.length<2;$('#cmpb').textContent='견주기 '+cmp.length;}
/* ---------- 3D: 돌리고 확대하고 부품을 끈다 ---------- */
function ramp3(u){u=Math.max(0,Math.min(1,u));for(var i=1;i<R3.length;i++){if(u<=R3[i][0]){var a=R3[i-1],b=R3[i],k=(u-a[0])/(b[0]-a[0]);return a[1].map(function(c,j){return Math.round(c+(b[1][j]-c)*k);});}}return R3[R3.length-1][1];}
function draw3d(cv,m,v,meta){var W=cv.width,H=cv.height,x=cv.getContext('2d');x.fillStyle='#14181D';x.fillRect(0,0,W,H);
var cy=Math.cos(v.yaw),sy=Math.sin(v.yaw),cp=Math.cos(v.pitch),sp=Math.sin(v.pitch),sc=1/m.r,half=Math.min(W,H)/2*.94*v.zoom,L=[.35,.6,.72],ln=Math.sqrt(L[0]*L[0]+L[1]*L[1]+L[2]*L[2]),solid=[],glass=[];L=L.map(function(c){return c/ln;});
m.p.forEach(function(part){var ui=UI[part.r];if(v.off.indexOf(ui)>=0)return;var plate=part.r.indexOf('plate')===0;if(part.r==='zone'&&!v.see)return;var bolt=ui==='bolt',base=(meta.use!=null&&bolt)?ramp3(meta.use):C3[ui],see=v.see&&(plate||part.r==='zone'),t=part.t;
for(var i=0;i<t.length;i+=9){var p=[0,3,6].map(function(k){var X=(t[i+k]-m.c[0])*sc,Y=(t[i+k+1]-m.c[1])*sc,Z=(t[i+k+2]-m.c[2])*sc;return [cy*X-sy*Y,sp*sy*X+sp*cy*Y+cp*Z,-cp*sy*X-cp*cy*Y+sp*Z];});
var ux=p[1][0]-p[0][0],uy=p[1][1]-p[0][1],uz=p[1][2]-p[0][2],vx=p[2][0]-p[0][0],vy=p[2][1]-p[0][1],vz=p[2][2]-p[0][2],nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx,n=Math.sqrt(nx*nx+ny*ny+nz*nz);
if(n===0||(nz<=0&&!see))continue;var lit=.28+.72*Math.max((nx*L[0]+ny*L[1]+nz*L[2])/n,0),col='rgb('+base.map(function(c){return Math.min(255,Math.round(c*lit));}).join(',')+')';
(see?glass:solid).push([(p[0][2]+p[1][2]+p[2][2])/3,col,p]);}});
function paint(list,a){list.sort(function(u,w){return u[0]-w[0];});x.globalAlpha=a;list.forEach(function(e){var p=e[2];x.beginPath();x.moveTo(W/2+p[0][0]*half,H/2-p[0][1]*half);x.lineTo(W/2+p[1][0]*half,H/2-p[1][1]*half);x.lineTo(W/2+p[2][0]*half,H/2-p[2][1]*half);x.closePath();x.fillStyle=e[1];x.strokeStyle=e[1];x.lineWidth=.6;x.fill();x.stroke();});}
paint(solid,1);paint(glass,.2);x.globalAlpha=1;}
function bind3d(cv,v,redraw){var d=null;cv.addEventListener('pointerdown',function(e){d=[e.clientX,e.clientY];cv.setPointerCapture(e.pointerId);});cv.addEventListener('pointerup',function(){d=null;});
cv.addEventListener('pointermove',function(e){if(!d)return;v.yaw+=(e.clientX-d[0])*.01;v.pitch=Math.max(-1.45,Math.min(1.45,v.pitch+(e.clientY-d[1])*.01));d=[e.clientX,e.clientY];redraw();});
cv.addEventListener('wheel',function(e){e.preventDefault();v.zoom=Math.max(.5,Math.min(4,v.zoom*(e.deltaY<0?1.12:.89)));redraw();},{passive:false});}
function ctl3(v){return '<span>드래그로 돌리고, 휠이나 버튼으로 확대합니다</span><button type="button" data-v3="zi" aria-label="확대">＋</button><button type="button" data-v3="zo" aria-label="축소">－</button><button type="button" data-v3="reset">처음 시점</button>'
+PARTS.map(function(q){return '<label><input type="checkbox" data-part="'+q[0]+'"'+(v.off.indexOf(q[0])<0?' checked':'')+'>'+q[1]+'</label>';}).join('')+'<label><input type="checkbox" data-see'+(v.see?' checked':'')+'>판을 비쳐 보기</label>';}
/* ---------- 4D·영상: 재생, 정지, 단계 이동 ---------- */
function stopPlay(){if(plTimer){clearInterval(plTimer);plTimer=null;}}
function frameHtml(fr,i){return '<div class="plst">'+fr[i].svg+'<div class="cap">'+esc(fr[i].cap)+' · '+(i+1)+' / '+fr.length+'</div></div>';}
function ctlPlay(n,i){return '<button type="button" data-pl="play">▶ 재생</button><button type="button" data-pl="prev" aria-label="이전 단계">◀</button><input type="range" min="0" max="'+(n-1)+'" value="'+i+'" data-pl="seek" aria-label="단계 이동"><button type="button" data-pl="next" aria-label="다음 단계">▶</button>';}
function mountPlay(stage,ctl,s,v,after){var fr=figs(s.html),n=fr.length;stopPlay();function show(i){v.frame=Math.max(0,Math.min(n-1,i));stage.innerHTML=frameHtml(fr,v.frame);var r=$('[data-pl=seek]',ctl);if(r)r.value=v.frame;if(after)after();}
ctl.innerHTML=ctlPlay(n,v.frame);show(v.frame);
ctl.onclick=function(e){var b=e.target.closest('button[data-pl]');if(!b)return;var a=b.dataset.pl;if(a==='play'){if(plTimer){stopPlay();b.textContent='▶ 재생';return;}if(v.frame>=n-1)show(0);b.textContent='■ 정지';plTimer=setInterval(function(){if(v.frame>=n-1){stopPlay();b.textContent='▶ 재생';return;}show(v.frame+1);},700);}else{stopPlay();var pb=$('[data-pl=play]',ctl);if(pb)pb.textContent='▶ 재생';show(v.frame+(a==='next'?1:-1));}};
ctl.oninput=function(e){if(e.target.dataset.pl==='seek'){stopPlay();show(Number(e.target.value));}};}
/* ---------- 상세 창: 형태마다 다른 미리보기 ---------- */
function richDetail(){var it=cur,s=it.samples[curS],pv=$('#d-pv'),ctl=$('#d-ctl'),more=$('#d-more');stopPlay();ctl.innerHTML='';ctl.onclick=null;ctl.oninput=null;activeV=null;var keep=detailKey===it.key&&detailView&&((is3(it,s)&&detailView.zoom!=null)||(isPlay(it,s)&&detailView.frame!=null));detailView=keep?detailView:defView(it,s);detailKey=it.key;if(isPlay(it,s))detailView.frame=Math.min(detailView.frame||0,figs(s.html).length-1);
if(is3(it,s)){pv.innerHTML='<canvas class="c3" width="640" height="440" aria-label="3D 모델. 끌어서 돌립니다"></canvas>';var cv=$('canvas',pv),m=D.meshes[s.view3d.size],v=detailView,red=function(){draw3d(cv,m,v,s.view3d);};red();bind3d(cv,v,red);ctl.innerHTML=ctl3(v);activeV={v:v,redraw:red};}
else if(isPlay(it,s)){pv.innerHTML='';mountPlay(pv,ctl,s,detailView);}
more.hidden=!s.more;more.innerHTML=s.more?'<h3>근거 확인</h3>'+s.more:'';
var mk=$('#mk');mk.hidden=!it.makeable;var live=!!D.make_url;all('input,select,button',mk).forEach(function(x){x.disabled=!live;});
$('#mk-msg').textContent=live?'규격과 조임 토크를 바꾸면 엔진이 다시 계산합니다. 토크를 비우면 추천 엔진이 고릅니다.':'공개 화면에서는 준비된 조건만 볼 수 있습니다. 서버로 실행하면 규격과 조임 토크를 바꿔 다시 계산합니다.';}
var detailView=null,detailKey=null;
/* ---------- 구성 화면 ---------- */
function statusOf(p){return p.data.source==='engine'?'데이터: 엔진 계산값 · 검증 전':'데이터: 현장 신호 '+(p.data.channel?'“'+esc(p.data.channel)+'”':'(이름 미입력)')+' · 연결 정보만 적음, 실제 연결은 아직 없음';}
function tileHtml(p){var f=found(p),it=f.it,opts=it.samples.map(function(x){return '<option'+(x.label===f.s.label?' selected':'')+'>'+esc(x.label)+'</option>';}).join('');
var ctrl='<div class="tc" role="group" aria-label="배치">'+['S','M','L'].map(function(z){return '<button type="button" data-sz="'+z+'" aria-pressed="'+(p.size===z)+'">'+z+'</button>';}).join('')+'<button type="button" data-mv="-1" aria-label="앞으로">◀</button><button type="button" data-mv="1" aria-label="뒤로">▶</button><select data-cond aria-label="조건">'+opts+'</select><button type="button" data-rm aria-label="빼기">×</button></div>'+(isPlay(it,f.s)?'<div class="tc"><input type="range" min="0" max="'+(figs(f.s.html).length-1)+'" value="'+(p.view.frame||0)+'" data-frame aria-label="단계"></div>':'');
return '<article class="tile s-'+p.size+(sel===p.id?' sel':'')+'" data-id="'+esc(p.id)+'"><div class="pv'+pad(it)+'"></div><div class="tb"><h3>'+esc(it.name)+'</h3><div class="cd">'+esc(p.label)+'</div>'+(f.missing?'<div class="warn">저장한 조건이 이 목록에 없어 첫 조건 그림을 보입니다.</div>':'')+'<div class="stt" data-st>'+statusOf(p)+'</div>'+ctrl+'</div></article>';}
function paintTile(el,p){var f=found(p),box=$('.pv',el);stopPlay();if(is3(f.it,f.s)){box.innerHTML='<canvas class="c3" width="640" height="420"></canvas>';var cv=$('canvas',box),m=D.meshes[f.s.view3d.size],red=function(){draw3d(cv,m,p.view,f.s.view3d);};red();bind3d(cv,p.view,red);}
else if(isPlay(f.it,f.s)){var fr=figs(f.s.html);box.innerHTML=frameHtml(fr,Math.min(p.view.frame||0,fr.length-1));}else box.innerHTML=f.s.html;}
function renderBuild(){var cv=$('#b-canvas');cv.innerHTML=picks.length?picks.map(tileHtml).join(''):'<p class="empty">아직 담은 것이 없습니다. 진열대에서 카드를 골라 "담기"를 누르면 여기에 놓입니다.</p>';picks.forEach(function(p){paintTile($('.tile[data-id="'+p.id+'"]',cv),p);});side();}
function side(){var s=$('#b-side'),p=picks.filter(function(x){return x.id===sel;})[0];activeV=null;if(!p){s.innerHTML='<h3>고른 것 설정</h3><p class="note">구성 화면의 칸을 누르면 데이터 연결과 보존된 설정을 여기서 고칩니다. 크기(S·M·L)와 순서는 칸 아래 단추로 바꿉니다.</p>';return;}
var f=found(p),it=f.it,keep=[];keep.push('조건 · '+p.label);if(is3(it,f.s))keep.push('3D 시점과 보이는 부품');if(isPlay(it,f.s))keep.push('재생 단계 '+((p.view.frame||0)+1)+' / '+figs(f.s.html).length);
s.innerHTML='<h3>'+esc(it.name)+'</h3><h4>필요한 입력</h4><p>'+esc(it.needs)+'</p><h4>저장되는 설정</h4><p>'+keep.map(esc).join('<br>')+'</p>'+(is3(it,f.s)?'<div class="ctl" id="b-ctl">'+ctl3(p.view)+'</div>':'')
+'<h4>데이터 연결</h4><label><input type="radio" name="src" value="engine"'+(p.data.source==='engine'?' checked':'')+'>엔진 계산값 (지금 보이는 값)</label><label><input type="radio" name="src" value="field"'+(p.data.source==='field'?' checked':'')+'>현장 신호 (이름을 적어 둡니다)</label>'
+'<input type="text" data-ch placeholder="신호 이름 예: 주축 전류" value="'+esc(p.data.channel)+'"'+(p.data.source==='field'?'':' disabled')+'><input type="text" data-nt placeholder="메모 (출처, 단위 등)" value="'+esc(p.data.note)+'">'
+'<p class="note">현장 신호를 실제로 읽어 오는 기능은 아직 없습니다. 여기서는 어떤 신호에 연결할지를 기록해 두고, 저장 파일에 남깁니다.</p>';
if(is3(it,f.s)){var cvv=$('.tile[data-id="'+p.id+'"] canvas'),m=D.meshes[f.s.view3d.size];activeV={v:p.view,redraw:function(){if(cvv)draw3d(cvv,m,p.view,f.s.view3d);}};}}
function picked1(){return picks.filter(function(x){return x.id===sel;})[0];}
function msg(t){$('#b-msg').textContent=t;}
function doc(){return {format:'cont-fab-selection',version:2,site:($('#site').value||$('#b-site').value||'').trim(),saved_at:new Date().toISOString(),
items:picks.map(function(p,i){var it=item(p.key);return {id:p.id,key:p.key,name:it.name,form:it.form,needs:it.needs,condition:{label:p.label,params:p.params},layout:{order:i,size:p.size},view:p.view,data:p.data};})};}
function readLocal(){try{var t=localStorage.getItem(STORE_KEY);return t?JSON.parse(t):null;}catch(e){return null;}}
function saveLocal(){try{localStorage.setItem(STORE_KEY,JSON.stringify(doc()));return true;}catch(e){return false;}}
function loadDoc(d){if(!d||d.format!=='cont-fab-selection'||!d.items)return {ok:false,text:'이 파일은 ConT FAB 구성 파일이 아닙니다.'};var skipped=0,list=d.items.slice();list.sort(function(a,b){return ((a.layout||{}).order||0)-((b.layout||{}).order||0);});picks=[];
list.forEach(function(r){var it=D.items.filter(function(x){return x.key===r.key;})[0];if(!it){skipped++;return;}var s=it.samples[0],lb=(r.condition&&r.condition.label)||s.label,fs=it.samples.filter(function(x){return x.label===lb;})[0]||s;
var dv=defView(it,fs),v=r.view&&typeof r.view==='object'?Object.assign(dv,r.view):dv;picks.push({id:r.id||uid(),key:r.key,label:lb,params:(r.condition&&r.condition.params)||{},size:['S','M','L'].indexOf((r.layout||{}).size)>=0?r.layout.size:'M',view:v,data:Object.assign({source:'engine',channel:'',note:''},r.data||{})});});
$('#site').value=$('#b-site').value=d.site||'';sel=null;return {ok:true,text:picks.length+'개를 열었습니다.'+(skipped?' 이 목록에 없는 '+skipped+'개는 건너뛰었습니다.':'')};}
function download(){var out=doc();var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:'application/json'}));a.download='my-fab.json';document.body.appendChild(a);a.click();a.remove();window.__lastSelection=out;}
function openBuild(){$('#b-site').value=$('#site').value;var d=$('#build');if(!d.open)d.showModal();renderBuild();}
document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('button'),t=e.target.closest&&e.target.closest('.tile');
if(t&&!b&&!e.target.closest('select,input,canvas')){sel=t.dataset.id;all('.tile').forEach(function(x){x.classList.toggle('sel',x===t);});side();return;}if(t&&e.target.closest('canvas')){sel=t.dataset.id;all('.tile').forEach(function(x){x.classList.toggle('sel',x===t);});side();return;}
if(!b)return;var id=t&&t.dataset.id,p=id&&picks.filter(function(x){return x.id===id;})[0];
if(b.id==='bopen'){openBuild();return;}if(b.id==='b-close'){stopPlay();$('#build').close();bar();apply();return;}
if(b.id==='b-prv'){var on=b.getAttribute('aria-pressed')!=='true';b.setAttribute('aria-pressed',on?'true':'false');$('#build').classList.toggle('prv',on);return;}
if(b.id==='b-save'){msg(saveLocal()?'저장했습니다. 이 브라우저에서 “저장된 구성 불러오기”로 다시 열 수 있습니다. 다른 곳에서 열려면 내려받기를 쓰세요.':'이 화면에서는 브라우저에 저장할 수 없습니다. 내려받기로 파일에 저장하세요.');return;}
if(b.id==='b-dl'){download();msg('my-fab.json을 내려받았습니다.');return;}if(b.id==='b-fbtn'){$('#b-file').click();return;}
if(b.id==='b-local'){var d=readLocal();if(!d){msg('저장된 구성이 없습니다.');return;}var r=loadDoc(d);msg(r.text);renderBuild();return;}
if(b.id==='save'){download();return;}
if(b.dataset.v3&&activeV){var v=activeV.v;if(b.dataset.v3==='zi')v.zoom=Math.min(4,v.zoom*1.25);if(b.dataset.v3==='zo')v.zoom=Math.max(.5,v.zoom/1.25);if(b.dataset.v3==='reset'){v.yaw=YAW;v.pitch=PITCH;v.zoom=1;}activeV.redraw();return;}
if(p&&b.dataset.sz){p.size=b.dataset.sz;t.className='tile s-'+p.size+(sel===p.id?' sel':'');all('[data-sz]',t).forEach(function(x){x.setAttribute('aria-pressed',x.dataset.sz===p.size?'true':'false');});return;}
if(p&&b.dataset.mv){var i=picks.indexOf(p),j=i+Number(b.dataset.mv);if(j<0||j>=picks.length)return;picks.splice(i,1);picks.splice(j,0,p);renderBuild();return;}
if(p&&b.hasAttribute('data-rm')){dropPick(p.id);renderBuild();bar();return;}});
document.addEventListener('change',function(e){var c=e.target,t=c.closest&&c.closest('.tile'),p=t&&picks.filter(function(x){return x.id===t.dataset.id;})[0];
if(c.id==='b-file'&&c.files&&c.files[0]){var fr=new FileReader();fr.onload=function(){var r;try{r=loadDoc(JSON.parse(fr.result));}catch(x){r={ok:false,text:'파일을 읽을 수 없습니다. 올바른 JSON이 아닙니다.'};}msg(r.text);if(r.ok)renderBuild();c.value='';};fr.readAsText(c.files[0]);return;}
if(p&&c.hasAttribute('data-cond')){var f=found(p),s=f.it.samples.filter(function(x){return x.label===c.value;})[0];if(s){p.label=s.label;p.params=s.params||{};p.view=defView(f.it,s);renderBuild();sel=p.id;}return;}
if(p&&c.hasAttribute('data-frame')){p.view.frame=Number(c.value);paintTile(t,p);return;}
if(activeV&&c.dataset&&c.dataset.part){var v=activeV.v,i=v.off.indexOf(c.dataset.part);if(!c.checked&&i<0)v.off.push(c.dataset.part);if(c.checked&&i>=0)v.off.splice(i,1);activeV.redraw();return;}
if(activeV&&c.dataset&&c.dataset.see!=null){activeV.v.see=c.checked;activeV.redraw();return;}
var q1=picked1();if(q1&&c.name==='src'){q1.data.source=c.value;side();var st=$('.tile[data-id="'+q1.id+'"] [data-st]');if(st)st.innerHTML=statusOf(q1);return;}});
document.addEventListener('input',function(e){var c=e.target,q1=picked1();if(!q1)return;if(c.hasAttribute('data-ch')){q1.data.channel=c.value;}else if(c.hasAttribute('data-nt')){q1.data.note=c.value;}else return;var st=$('.tile[data-id="'+q1.id+'"] [data-st]');if(st)st.innerHTML=statusOf(q1);});
document.addEventListener('close',function(e){if(e.target.id==='detail'){stopPlay();detailKey=null;}},true);
"""
