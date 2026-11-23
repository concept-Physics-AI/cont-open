"""3D 보기 (한 파일 HTML 안에 들어가는 작은 WebGL 보기). 외부 라이브러리를 쓰지 않는다.

끌어서 돌리고, 휠로 확대하고, 화살표 키로도 돌린다. WebGL을 쓸 수 없으면 그 사실을 글로 알린다.
부품 색은 화면의 색 변수에서 읽어 밝은 화면·어두운 화면을 함께 따른다.
"""
from __future__ import annotations

import html
import json

import numpy as np

from cont.shape import Assembly, assembly_mesh

# 부품 역할 → 화면 색 변수
ROLE_COLOR = {"bolt_head": "--sig", "bolt_shank": "--sig", "nut": "--sig", "plate_head": "--band", "plate_nut": "--okbg"}

VIEWER_CSS = """
.v3d{position:relative}.v3d canvas{width:100%;aspect-ratio:4/3;display:block;border-radius:8px;background:var(--bg);touch-action:none;cursor:grab}
.v3d canvas:focus-visible{outline:2px solid var(--sig);outline-offset:2px}.v3d .bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px}
.v3d button{font:inherit;font-size:13px;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:4px 12px;cursor:pointer}
.v3d button:hover{border-color:var(--sig)}.v3d button:focus-visible{outline:2px solid var(--sig);outline-offset:2px}
.v3d .key{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--sub)}.v3d .key i{width:11px;height:11px;border-radius:2px;display:inline-block;border:1px solid var(--line)}
"""

VIEWER_JS = r"""
(function(){
document.querySelectorAll('.v3d').forEach(function(box){
var cv=box.querySelector('canvas'),data=JSON.parse(box.querySelector('script[type="application/json"]').textContent);
var gl=cv.getContext('webgl',{antialias:true});
if(!gl){box.querySelector('.msg').textContent='이 브라우저에서는 3D 보기를 쓸 수 없습니다. 위의 단면 그림을 봐 주세요.';cv.style.display='none';return;}
function sh(t,s){var o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);return o;}
var pr=gl.createProgram();
gl.attachShader(pr,sh(gl.VERTEX_SHADER,'attribute vec3 p;attribute vec3 n;uniform mat3 r;uniform vec3 c;uniform float s;uniform float a;varying float l;'+
'void main(){vec3 q=r*((p-c)*s);vec3 m=normalize(r*n);l=0.38+0.62*max(dot(m,normalize(vec3(0.35,0.55,0.75))),0.0);gl_Position=vec4(q.x/a,q.y,-q.z*0.5,1.0);}'));
gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,'precision mediump float;uniform vec3 k;varying float l;void main(){gl_FragColor=vec4(k*l,1.0);}'));
gl.linkProgram(pr);gl.useProgram(pr);
var U={};['r','c','s','a','k'].forEach(function(x){U[x]=gl.getUniformLocation(pr,x)});
var ap=gl.getAttribLocation(pr,'p'),an=gl.getAttribLocation(pr,'n');
function rgb(v){var d=document.createElement('i');d.style.color='var('+v+')';box.appendChild(d);var m=getComputedStyle(d).color.match(/[\d.]+/g);box.removeChild(d);return [m[0]/255,m[1]/255,m[2]/255];}
var parts=data.parts.map(function(pt){var t=pt.tri,n=new Float32Array(t.length);
for(var i=0;i<t.length;i+=9){var ux=t[i+3]-t[i],uy=t[i+4]-t[i+1],uz=t[i+5]-t[i+2],vx=t[i+6]-t[i],vy=t[i+7]-t[i+1],vz=t[i+8]-t[i+2];
var x=uy*vz-uz*vy,y=uz*vx-ux*vz,z=ux*vy-uy*vx,q=Math.sqrt(x*x+y*y+z*z)||1;for(var j=0;j<9;j+=3){n[i+j]=x/q;n[i+j+1]=y/q;n[i+j+2]=z/q;}}
var bp=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bp);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(t),gl.STATIC_DRAW);
var bn=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bn);gl.bufferData(gl.ARRAY_BUFFER,n,gl.STATIC_DRAW);
return {bp:bp,bn:bn,count:t.length/3,color:pt.color};});
var yaw0=-0.785,pitch0=0.4,yaw=yaw0,pitch=pitch0,zoom=1;
function draw(){var w=cv.clientWidth*devicePixelRatio|0,h=cv.clientHeight*devicePixelRatio|0;if(cv.width!==w||cv.height!==h){cv.width=w;cv.height=h;}
gl.viewport(0,0,w,h);var bg=rgb('--bg');gl.clearColor(bg[0],bg[1],bg[2],1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
var cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
/* 모델의 z(볼트 축)를 화면 위쪽으로 세우고, 화면 세로축으로 yaw, 가로축으로 pitch. 거울상이 되지 않는 회전(행렬식 +1)이다 */
var R=[cy,sp*sy,-cp*sy, -sy,sp*cy,-cp*cy, 0,cp,sp];
gl.uniformMatrix3fv(U.r,false,new Float32Array(R));gl.uniform3fv(U.c,data.center);gl.uniform1f(U.s,zoom/data.radius);gl.uniform1f(U.a,w/h);
parts.forEach(function(p){gl.uniform3fv(U.k,rgb(p.color));gl.bindBuffer(gl.ARRAY_BUFFER,p.bp);gl.enableVertexAttribArray(ap);gl.vertexAttribPointer(ap,3,gl.FLOAT,false,0,0);
gl.bindBuffer(gl.ARRAY_BUFFER,p.bn);gl.enableVertexAttribArray(an);gl.vertexAttribPointer(an,3,gl.FLOAT,false,0,0);gl.drawArrays(gl.TRIANGLES,0,p.count);});}
function clamp(){pitch=Math.max(-1.5,Math.min(1.5,pitch));zoom=Math.max(0.4,Math.min(6,zoom));}
var last=null;
cv.addEventListener('pointerdown',function(e){last=[e.clientX,e.clientY];cv.setPointerCapture(e.pointerId);cv.style.cursor='grabbing';});
cv.addEventListener('pointermove',function(e){if(!last)return;yaw-=(e.clientX-last[0])*0.01;pitch+=(e.clientY-last[1])*0.01;last=[e.clientX,e.clientY];clamp();draw();});
function up(){last=null;cv.style.cursor='grab';}cv.addEventListener('pointerup',up);cv.addEventListener('pointercancel',up);
cv.addEventListener('wheel',function(e){e.preventDefault();zoom*=e.deltaY<0?1.1:0.9;clamp();draw();},{passive:false});
cv.addEventListener('keydown',function(e){var k=e.key,d=0.1;if(k==='ArrowLeft')yaw+=d;else if(k==='ArrowRight')yaw-=d;else if(k==='ArrowUp')pitch-=d;else if(k==='ArrowDown')pitch+=d;
else if(k==='+'||k==='=')zoom*=1.1;else if(k==='-')zoom*=0.9;else return;e.preventDefault();clamp();draw();});
box.querySelector('button').addEventListener('click',function(){yaw=yaw0;pitch=pitch0;zoom=1;draw();});
window.addEventListener('resize',draw);if(window.matchMedia)matchMedia('(prefers-color-scheme:dark)').addEventListener('change',draw);
draw();cv.dataset.ready='1';
});})();
"""


def viewer_data(assembly: Assembly) -> dict:
    """보기에 넘기는 값: 부품별 삼각형 좌표(면마다 꼭짓점 3개를 따로 둔다), 중심, 화면에 맞추는 반지름."""
    z0, z1 = assembly.z_range
    radius = float(np.hypot(assembly.max_radius, (z1 - z0) / 2)) * 1.05
    parts = []
    for part, mesh in assembly_mesh(assembly):
        tri = np.round(mesh.vertices[mesh.faces].reshape(-1), 3)
        parts.append({"name": part.name, "role": part.role, "color": ROLE_COLOR.get(part.role, "--sub"), "tri": tri.tolist()})
    return {"center": [0.0, 0.0, (z0 + z1) / 2], "radius": radius, "parts": parts}


def viewer(assembly: Assembly, label: str = "", legend: tuple[tuple[str, str], ...] = ()) -> str:
    """3D 보기 조각(HTML). 화면에는 VIEWER_CSS와 VIEWER_JS를 한 번씩 넣어야 한다."""
    e = html.escape
    data = json.dumps(viewer_data(assembly), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    keys = "".join(f'<span class="key"><i style="background:var({e(c)})"></i>{e(n)}</span>' for n, c in legend)
    return (f'<div class="v3d"><canvas tabindex="0" role="img" aria-label="{e(label or assembly.name)} 3D 형상. 끌거나 화살표 키로 돌리고 휠이나 +, - 키로 확대합니다"></canvas>'
            f'<div class="bar"><button type="button">처음 보기로</button>{keys}</div><div class="sub msg"></div>'
            f'<script type="application/json">{data}</script></div>')
