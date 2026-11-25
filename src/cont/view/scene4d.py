"""설명용 단계 4D 보기: 공통 대상 명세(objspec)의 부품을 3D로 보이고 단계별로 재생한다.

- 부품은 명세의 부품 ID로 구분되고, 단계 자세는 `objspec.Timeline`이 준다. 같은 식을 JS가 다시 계산한다(POSE_JS).
- 재생 시간은 설명용이다. 물리 시간이 아니며, 온도·응력·접합 품질은 이 보기에 없다.
- 카메라와 단계별 속도는 `ViewState`에서 온다. 바꿔도 구조(부품 모양)는 다시 만들지 않는다.
- 외부 라이브러리 없이 WebGL만 쓰고, WebGL이 없으면 글로 알린다. 움직임을 줄이는 설정이면 자동 재생하지 않는다.
"""
from __future__ import annotations

import html
import json
import math

import numpy as np

from cont.objspec import ObjectSpec, ViewState
from cont.objspec.scene import Timeline
from cont.shape import assembly_mesh

ROLE_COLOR = {"substrate": "--sig", "dielectric": "--band", "metal": "--okbg"}

# t 시각의 한 부품 자세 [dz, dx]. objspec.scene.Timeline.pose_at과 같은 식이다 (시험이 둘을 맞춰 본다).
POSE_JS = r"""
function poseAt(T,t,id){
t=Math.min(Math.max(t,0),T.duration);
var i=0;for(;i<T.segments.length-1;i++){if(t<=T.segments[i].t1)break;}
var sg=T.segments[i],a=i>0?T.segments[i-1].end[id]:T.start[id],b=sg.end[id];
var u=Math.min(1,Math.max(0,(t-sg.t0)/(sg.t1-sg.t0)));if(T.ease==='smoothstep')u=u*u*(3-2*u);
return [a[0]+(b[0]-a[0])*u,a[1]+(b[1]-a[1])*u];}
"""

SCENE_JS = POSE_JS + r"""
(function(){
document.querySelectorAll('.s4d').forEach(function(box){
var cv=box.querySelector('canvas'),data=JSON.parse(box.querySelector('script[type="application/json"]').textContent),T=data.timeline;
var gl=cv.getContext('webgl',{antialias:true}),info=box.querySelector('.info'),slider=box.querySelector('input[type=range]'),playBtn=box.querySelector('.play');
if(!gl){box.querySelector('.msg').textContent='이 브라우저에서는 3D 보기를 쓸 수 없습니다.';cv.style.display='none';return;}
function sh(t,s){var o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);return o;}
var pr=gl.createProgram();
gl.attachShader(pr,sh(gl.VERTEX_SHADER,'attribute vec3 p;attribute vec3 n;uniform mat3 r;uniform vec3 c;uniform vec3 o;uniform float s;uniform float a;varying float l;'+
'void main(){vec3 q=r*((p+o-c)*s);vec3 m=normalize(r*n);l=0.38+0.62*max(dot(m,normalize(vec3(0.35,0.55,0.75))),0.0);gl_Position=vec4(q.x/a,q.y,-q.z*0.5,1.0);}'));
gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,'precision mediump float;uniform vec3 k;varying float l;void main(){gl_FragColor=vec4(k*l,1.0);}'));
gl.linkProgram(pr);gl.useProgram(pr);
var U={};['r','c','o','s','a','k'].forEach(function(x){U[x]=gl.getUniformLocation(pr,x)});
var ap=gl.getAttribLocation(pr,'p'),an=gl.getAttribLocation(pr,'n');
function rgb(v){var d=document.createElement('i');d.style.color='var('+v+')';box.appendChild(d);var m=getComputedStyle(d).color.match(/[\d.]+/g);box.removeChild(d);return [m[0]/255,m[1]/255,m[2]/255];}
var parts=data.parts.map(function(pt){var t=pt.tri,n=new Float32Array(t.length);
for(var i=0;i<t.length;i+=9){var ux=t[i+3]-t[i],uy=t[i+4]-t[i+1],uz=t[i+5]-t[i+2],vx=t[i+6]-t[i],vy=t[i+7]-t[i+1],vz=t[i+8]-t[i+2];
var x=uy*vz-uz*vy,y=uz*vx-ux*vz,z=ux*vy-uy*vx,q=Math.sqrt(x*x+y*y+z*z)||1;for(var j=0;j<9;j+=3){n[i+j]=x/q;n[i+j+1]=y/q;n[i+j+2]=z/q;}}
var bp=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bp);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(t),gl.STATIC_DRAW);
var bn=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bn);gl.bufferData(gl.ARRAY_BUFFER,n,gl.STATIC_DRAW);
return {id:pt.id,bp:bp,bn:bn,count:t.length/3,color:pt.color};});
var yaw0=data.camera.yaw,pitch0=data.camera.pitch,zoom0=data.camera.zoom,yaw=yaw0,pitch=pitch0,zoom=zoom0,now=Math.min(Math.max(data.start_t||0,0),T.duration),playing=false,last=null,tick=null;
function label(){var sg=T.segments[0],n=T.segments.length;for(var i=0;i<n;i++){sg=T.segments[i];if(now<sg.t1||i===n-1)break;}
info.textContent='단계 '+(T.segments.indexOf(sg)+1)+'/'+T.segments.length+' '+sg.name+' · 설명용 재생 '+now.toFixed(1)+'/'+T.duration.toFixed(1)+' s (속도 '+sg.speed+'배)';slider.value=now;}
function draw(){var w=cv.clientWidth*devicePixelRatio|0,h=cv.clientHeight*devicePixelRatio|0;if(cv.width!==w||cv.height!==h){cv.width=w;cv.height=h;}
gl.viewport(0,0,w,h);var bg=rgb('--bg');gl.clearColor(bg[0],bg[1],bg[2],1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
var cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
var R=[cy,sp*sy,-cp*sy, -sy,sp*cy,-cp*cy, 0,cp,sp];
gl.uniformMatrix3fv(U.r,false,new Float32Array(R));gl.uniform3fv(U.c,data.center);gl.uniform1f(U.s,zoom/data.radius);gl.uniform1f(U.a,w/h);
parts.forEach(function(p){var ps=poseAt(T,now,p.id);gl.uniform3f(U.o,ps[1],0,ps[0]);gl.uniform3fv(U.k,rgb(p.color));
gl.bindBuffer(gl.ARRAY_BUFFER,p.bp);gl.enableVertexAttribArray(ap);gl.vertexAttribPointer(ap,3,gl.FLOAT,false,0,0);
gl.bindBuffer(gl.ARRAY_BUFFER,p.bn);gl.enableVertexAttribArray(an);gl.vertexAttribPointer(an,3,gl.FLOAT,false,0,0);gl.drawArrays(gl.TRIANGLES,0,p.count);});label();}
function clamp(){pitch=Math.max(-1.5,Math.min(1.5,pitch));zoom=Math.max(0.4,Math.min(6,zoom));}
function stop(){playing=false;playBtn.textContent='재생';playBtn.setAttribute('aria-pressed','false');tick=null;}
function frame(ts){if(!playing)return;if(tick===null)tick=ts;now+=(ts-tick)/1000;tick=ts;if(now>=T.duration){now=T.duration;draw();stop();return;}draw();requestAnimationFrame(frame);}
playBtn.addEventListener('click',function(){if(playing){stop();return;}if(now>=T.duration)now=0;playing=true;tick=null;playBtn.textContent='멈춤';playBtn.setAttribute('aria-pressed','true');requestAnimationFrame(frame);});
slider.addEventListener('input',function(){stop();now=parseFloat(slider.value);draw();});
box.querySelectorAll('.stage').forEach(function(b){b.addEventListener('click',function(){stop();now=T.segments[+b.dataset.i].t0;draw();});});
cv.addEventListener('pointerdown',function(e){last=[e.clientX,e.clientY];cv.setPointerCapture(e.pointerId);cv.style.cursor='grabbing';});
cv.addEventListener('pointermove',function(e){if(!last)return;yaw-=(e.clientX-last[0])*0.01;pitch+=(e.clientY-last[1])*0.01;last=[e.clientX,e.clientY];clamp();draw();});
function up(){last=null;cv.style.cursor='grab';}cv.addEventListener('pointerup',up);cv.addEventListener('pointercancel',up);
cv.addEventListener('wheel',function(e){e.preventDefault();zoom*=e.deltaY<0?1.1:0.9;clamp();draw();},{passive:false});
cv.addEventListener('keydown',function(e){var k=e.key,d=0.1;if(k==='ArrowLeft')yaw+=d;else if(k==='ArrowRight')yaw-=d;else if(k==='ArrowUp')pitch-=d;else if(k==='ArrowDown')pitch+=d;
else if(k==='+'||k==='=')zoom*=1.1;else if(k==='-')zoom*=0.9;else return;e.preventDefault();clamp();draw();});
box.querySelector('.cam').addEventListener('click',function(){yaw=yaw0;pitch=pitch0;zoom=zoom0;draw();});
window.addEventListener('resize',draw);if(window.matchMedia)matchMedia('(prefers-color-scheme:dark)').addEventListener('change',draw);
draw();cv.dataset.ready='1';
});})();
"""

SCENE_CSS = """
.s4d{position:relative}.s4d canvas{width:100%;aspect-ratio:4/3;display:block;border-radius:8px;background:var(--bg);touch-action:none;cursor:grab}
.s4d canvas:focus-visible,.s4d button:focus-visible,.s4d input:focus-visible{outline:2px solid var(--sig);outline-offset:2px}
.s4d .bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px}.s4d input[type=range]{flex:1;min-width:140px}
.s4d button{font:inherit;font-size:13px;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:4px 12px;cursor:pointer}
.s4d button:hover{border-color:var(--sig)}.s4d .info{font-size:13px;color:var(--sub);margin-top:4px}
.s4d .key{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--sub)}.s4d .key i{width:11px;height:11px;border-radius:2px;display:inline-block;border:1px solid var(--line)}
"""


def scene_data(spec: ObjectSpec, view: ViewState | None = None, timeline: Timeline | None = None, start_t: float = 0.0) -> dict:
    view = view or ViewState()
    tl = timeline or Timeline(spec, view)
    asm = spec.to_assembly()
    z0, z1 = asm.z_range
    reach = max(max((abs(p.dz) for _, ps in tl.spec.start for p in [ps]), default=0.0),
                max((abs(p.dz) for st in spec.stages for _, p in st.poses), default=0.0))
    lateral = max(max((abs(p.dx) for _, p in spec.start), default=0.0), max((abs(p.dx) for st in spec.stages for _, p in st.poses), default=0.0))
    radius = float(np.hypot(asm.max_radius + lateral, (z1 - z0 + reach) / 2)) * 1.05
    parts = []
    for op, (part, mesh) in zip(spec.parts, assembly_mesh(asm)):
        tri = np.round(mesh.vertices[mesh.faces].reshape(-1), 3)
        parts.append({"id": op.id, "name": part.name, "role": part.role, "color": ROLE_COLOR.get(part.role, "--sub"), "tri": tri.tolist()})
    return {"center": [0.0, 0.0, (z0 + z1 + reach) / 2], "radius": radius, "parts": parts,
            "camera": {"yaw": -math.radians(view.azimuth), "pitch": math.radians(view.elevation), "zoom": 1.0 / view.distance},
            "timeline": tl.to_dict(), "start_t": float(start_t), "spec_version": spec.version, "dimension_status": spec.dimension_status}


def scene4d(spec: ObjectSpec, view: ViewState | None = None, label: str = "", start_t: float = 0.0) -> str:
    """4D 보기 조각(HTML). 화면에는 SCENE_CSS와 SCENE_JS를 한 번씩 넣어야 한다."""
    e = html.escape
    data = scene_data(spec, view, start_t=start_t)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    keys = "".join(f'<span class="key" data-part-id="{e(p["id"])}"><i style="background:var({e(p["color"])})"></i>{e(p["name"])}</span>' for p in data["parts"])
    stages = "".join(f'<button type="button" class="stage" data-i="{i}">{i + 1}. {e(sg["name"])}</button>' for i, sg in enumerate(data["timeline"]["segments"]))
    note = ("치수는 설명용 값입니다." if spec.dimension_status == "illustrative" else "치수는 사용자가 입력한 값입니다." if spec.dimension_status == "user_input"
            else "") + " 재생 시간은 설명용이며 물리 시간이 아닙니다."
    return (f'<div class="s4d"><canvas tabindex="0" role="img" aria-label="{e(label or spec.name)} 단계 장면. 끌거나 화살표 키로 돌리고 휠이나 +, - 키로 확대합니다"></canvas>'
            f'<div class="bar"><button type="button" class="play" aria-pressed="false">재생</button>'
            f'<input type="range" min="0" max="{data["timeline"]["duration"]}" step="0.01" value="{min(max(start_t, 0.0), data["timeline"]["duration"])}" aria-label="재생 위치">{stages}'
            f'<button type="button" class="cam">처음 시점으로</button></div>'
            f'<div class="info" aria-live="polite"></div><div class="bar">{keys}</div><div class="sub">{e(note.strip())}</div><div class="sub msg"></div>'
            f'<script type="application/json">{payload}</script></div>')


def scene4d_page(spec: ObjectSpec, view: ViewState | None = None, title: str = "", start_t: float = 0.0) -> str:
    """한 파일 HTML. 밝은 화면·어두운 화면을 함께 따르고, 움직임을 줄이는 설정이면 자동 재생하지 않는다(이 보기는 처음부터 자동 재생이 없다)."""
    t = html.escape(title or spec.name)
    css = (":root{--bg:#F5F7FA;--ink:#18385E;--sub:#5B6B7F;--line:#C9D3E0;--sig:#008E94;--band:#8FA6C4;--okbg:#C58B2B}"
           "@media(prefers-color-scheme:dark){:root{--bg:#10151C;--ink:#E6ECF4;--sub:#9AA9BC;--line:#2B3644;--sig:#38B6BC;--band:#5C7596;--okbg:#D9A24A}}"
           "body{margin:0;padding:16px;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;max-width:860px}")
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{t}</title><style>{css}{SCENE_CSS}</style></head><body><h1 style="font-size:18px">{t}</h1>'
            f'{scene4d(spec, view, start_t=start_t)}<script>{SCENE_JS}</script></body></html>')
