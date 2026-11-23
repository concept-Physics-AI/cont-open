"""ConT Fab의 고르기 화면: 물리 정보가 상품처럼 놓이고, 골라서 바구니에 담는다.

파일 하나로:  python -m cont.fab.store --out fab.html

- 목록에는 지금 코드에 실제로 있는 엔진만 싣는다. 미리보기는 엔진을 예제 값으로 돌린 결과다.
- 값은 모두 계산값이며 실측과 대조하기 전이다. 가격은 없다.
- 바구니는 이 화면 안에서만 담긴다. "고른 것 내려받기"로 파일(JSON)로 받는다. 꾸리기 화면은 아직 없다.
"""
from __future__ import annotations

import argparse
import html
import json
from typing import Any, Mapping, Sequence

from cont.fab.catalog import catalog, load
from cont.view.diagnosis_html import CSS
from cont.view.fastening_html import EXTRA_CSS
from cont.view.field_image import FIELD_CSS

STORE_CSS = """
:root,:root:root{color-scheme:light;--bg:#fff;--card:#fff;--ink:#101317;--sub:#59626C;--line:#E1E4E8;--band:#D9EFEC;--sig:#0B7F7A;--bad:#B4541A;--t:#0B7F7A;--ts:#E3F4F2;--g:#F5F6F8;--warn:#855000;--warnbg:#FDF1DC;--okbg:#E3F4F2;--ok:#0B7F7A}
html,body{height:100%}body{margin:0;background:#fff;color:var(--ink);font-family:"IBM Plex Sans KR","Segoe UI","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;font-size:15px;line-height:1.55;letter-spacing:-.01em}
button,input{font:inherit;color:inherit}button{cursor:pointer}h1,h2,h3,p{margin:0}
.top{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:20px;min-height:64px;padding:8px 32px;background:#fff;border-bottom:1px solid var(--line);flex-wrap:wrap}
.top .name{font-size:24px;font-weight:600;letter-spacing:-.02em;white-space:nowrap}
.find{flex:1 1 260px;max-width:520px;display:flex;align-items:center;gap:10px;height:44px;padding:0 16px;border-radius:22px;background:var(--g);border:1px solid var(--line)}
.find:focus-within{border-color:var(--t)}.find svg{flex:none;width:18px;height:18px}.find input{flex:1;min-width:0;border:0;outline:none;background:transparent;font-size:15px}
.top .cart{margin-left:auto;height:44px;padding:0 18px;border-radius:10px;border:0;background:var(--ink);color:#fff;font-size:14px;font-weight:600;white-space:nowrap}
.wrap{display:grid;grid-template-columns:232px minmax(0,1fr);max-width:1500px;margin:0 auto}
.side{padding:6px 24px 24px 32px;border-right:1px solid var(--line)}.side .grp{padding:14px 0;border-bottom:1px solid var(--line)}.side h2{font-size:14px;font-weight:600;margin-bottom:6px}
.side label{display:flex;align-items:center;gap:10px;min-height:36px;font-size:14px}.side input{width:16px;height:16px;accent-color:var(--t)}.side .n{margin-left:auto;color:var(--sub);font-size:12.5px}
.side .fine{font-size:12.5px;color:var(--sub);line-height:1.6;margin-top:14px}
.main{padding:20px 32px 40px 28px;min-width:0}.main h1{font-size:26px;font-weight:600;letter-spacing:-.02em}.main .lead{font-size:14px;color:var(--sub);margin-top:2px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}.chips button{height:44px;padding:0 18px;border-radius:22px;font-size:14px;border:1px solid var(--line);background:#fff}
.chips button[aria-pressed=true]{border-color:var(--ink);background:var(--ink);color:#fff;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px}.none{color:var(--sub);padding:30px 0}
.item{border:1px solid var(--line);border-radius:16px;overflow:hidden;background:#fff;display:flex;flex-direction:column}.item[hidden]{display:none}.item.in{border-color:var(--t)}
.item .pv{height:190px;background:var(--g);display:flex;align-items:center;justify-content:center;padding:10px;overflow:hidden;color:var(--ink)}
.item .pv svg{display:block;width:100%;height:100%;max-height:170px}.item .pv .tick{font-size:11px}.item .pv .sig{fill:none;stroke:var(--sig);stroke-width:2}.item .pv .dot{fill:var(--sig)}
.item .pv ol,.item .pv dl{margin:0;padding:0 6px;font-size:13px;line-height:1.55;width:100%}.item .pv ol{list-style:none;display:grid;gap:8px}.item .pv ol b{display:block;font-size:12px;color:var(--t)}
.item .pv dt{font-size:12px;color:var(--t);font-weight:600;margin-top:6px}.item .pv dd{margin:0}.item .pv dl.nums dd{font-size:20px;font-weight:300;font-variant-numeric:tabular-nums}
.item .bd{padding:12px 14px 14px;display:flex;flex-direction:column;gap:6px;flex:1}.tags{display:flex;gap:6px;flex-wrap:wrap}
.tags span{font-size:12px;font-weight:600;color:var(--t);background:var(--ts);padding:2px 8px;border-radius:6px}.tags span+span{color:var(--sub);background:var(--g)}
.item h3{font-size:16px;font-weight:600;line-height:1.35}.item .sm{font-size:13px;color:var(--sub);line-height:1.5}.item .kv{font-size:12.5px;color:var(--sub)}.item .kv b{color:var(--ink);font-weight:400}
.item .facts{font-size:12.5px;color:var(--sub);border-top:1px solid var(--line);padding-top:6px;margin-top:2px}.item .facts b{color:var(--ink);font-weight:500}
.item .ft{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:auto;padding-top:6px}.item .st{font-size:12.5px;color:var(--warn);font-weight:500}
.item .add{height:44px;padding:0 18px;border-radius:10px;border:0;background:var(--t);color:#fff;font-size:14px;font-weight:600}.item.in .add{border:1px solid var(--t);background:var(--ts);color:var(--t)}
.basket{position:fixed;right:0;top:0;bottom:0;z-index:20;width:min(380px,100%);background:#fff;border-left:1px solid var(--line);box-shadow:-12px 0 40px rgba(16,19,23,.10);padding:20px 24px;display:flex;flex-direction:column;gap:12px}
.basket[hidden]{display:none}.basket h2{font-size:20px;font-weight:600}.basket ul{list-style:none;margin:0;padding:0;overflow-y:auto;flex:1}
.basket li{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--line);font-size:14.5px}.basket li small{display:block;color:var(--sub);font-size:12.5px}
.basket li button{margin-left:auto;height:36px;padding:0 12px;border-radius:8px;border:1px solid var(--line);background:#fff;font-size:13px}
.basket label{font-size:13px;color:var(--sub)}.basket input{display:block;box-sizing:border-box;width:100%;height:44px;margin-top:4px;padding:0 12px;border-radius:10px;border:1px solid var(--line);font-size:15px}
.basket .go{height:48px;border-radius:10px;border:0;background:var(--t);color:#fff;font-weight:600}.basket .go[disabled]{opacity:.45;cursor:default}.basket .x{height:44px;border-radius:10px;border:1px solid var(--ink);background:#fff}
.basket .fine{font-size:12.5px;color:var(--sub);line-height:1.6}
button:focus-visible,input:focus-visible{outline:2px solid var(--t);outline-offset:2px}
@media (max-width:860px){.wrap{display:block}.side{border:0;border-bottom:1px solid var(--line);padding:6px 20px 16px}.main{padding:16px 20px 40px}.top{padding:8px 20px;gap:12px}}
"""

STORE_JS = r"""
(function(){
var D=JSON.parse(document.getElementById('store-data').textContent),picked=[],form='all',q='';
var $=function(s,r){return (r||document).querySelector(s)},all=function(s){return [].slice.call(document.querySelectorAll(s));};
function esc(t){var d=document.createElement('div');d.textContent=t==null?'':String(t);return d.innerHTML;}
function areas(){return all('.side input[data-area]').filter(function(x){return x.checked;}).map(function(x){return x.dataset.area;});}
function apply(){var on=areas(),shown=0;all('.item').forEach(function(el){var it=D.items[Number(el.dataset.i)],text=(it.name+' '+it.summary+' '+it.area+' '+it.form_label+' '+it.needs+' '+it.gives).toLowerCase();
var ok=(form==='all'||it.form===form)&&on.indexOf(it.area)>=0&&(!q||text.indexOf(q)>=0);el.hidden=!ok;if(ok)shown++;el.classList.toggle('in',picked.indexOf(it.key)>=0);
$('.add',el).textContent=picked.indexOf(it.key)>=0?'담김':'담기';$('.add',el).setAttribute('aria-pressed',picked.indexOf(it.key)>=0?'true':'false');});
$('#none').hidden=shown>0;$('#count').textContent='Physics가 만든 것 '+D.items.length+'가지 · 보이는 것 '+shown+' · 고른 것 '+picked.length;$('#cart').textContent='바구니 '+picked.length;basket();}
function basket(){$('#list').innerHTML=picked.length?picked.map(function(k){var it=D.items.filter(function(x){return x.key===k;})[0];return '<li><span>'+esc(it.name)+'<small>넣는 것: '+esc(it.needs)+'</small></span><button type="button" data-drop="'+esc(k)+'">빼기</button></li>';}).join(''):'<li>아직 고른 것이 없습니다.</li>';
$('#save').disabled=!picked.length;}
document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('button');if(!b)return;
if(b.classList.contains('add')){var k=D.items[Number(b.closest('.item').dataset.i)].key,i=picked.indexOf(k);if(i>=0)picked.splice(i,1);else picked.push(k);apply();return;}
if(b.dataset.form!=null){form=b.dataset.form;all('.chips button').forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});apply();return;}
if(b.dataset.drop!=null){picked.splice(picked.indexOf(b.dataset.drop),1);apply();return;}
if(b.id==='cart'){$('#basket').hidden=false;$('#site').focus();return;}if(b.id==='close'){$('#basket').hidden=true;$('#cart').focus();return;}
if(b.id==='save'){var out={format:'cont-fab-selection',version:1,site:$('#site').value.trim(),items:picked.map(function(k){var it=D.items.filter(function(x){return x.key===k;})[0];return {key:k,name:it.name,needs:it.needs};})};
var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:'application/json'}));a.download='my-fab.json';document.body.appendChild(a);a.click();a.remove();window.__lastSelection=out;}});
all('.side input[data-area]').forEach(function(x){x.addEventListener('change',apply);});
$('#q').addEventListener('input',function(){q=this.value.trim().toLowerCase();apply();});
apply();document.body.dataset.ready='1';
})();
"""


def render_store(items: Sequence[Mapping[str, Any]], forms: Mapping[str, str], title: str = "ConT Fab · 고르기") -> str:
    if not items:
        raise ValueError("the catalog is empty")
    e = html.escape
    areas = list(dict.fromkeys(i["area"] for i in items))
    chips = '<button type="button" data-form="all" aria-pressed="true">전체</button>' + "".join(
        f'<button type="button" data-form="{e(k)}" aria-pressed="false">{e(v)}</button>' for k, v in forms.items() if any(i["form"] == k for i in items))
    side = "".join(f'<label><input type="checkbox" data-area="{e(a)}" checked>{e(a)}<span class="n">{sum(i["area"] == a for i in items)}</span></label>' for a in areas)

    def card(n: int, it: Mapping[str, Any]) -> str:
        facts = " · ".join(f"{e(k)} <b>{e(v)}</b>" for k, v in it["facts"])
        note = f'<div class="kv">{e(it["preview_note"])}</div>' if it.get("preview_note") else ""
        return (f'<article class="item" data-i="{n}"><div class="pv">{it["preview_html"]}</div><div class="bd">'
                f'<div class="tags"><span>{e(it["form_label"])}</span><span>{e(it["area"])}</span></div><h3>{e(it["name"])}</h3><p class="sm">{e(it["summary"])}</p>'
                f'<div class="kv">넣는 것 <b>{e(it["needs"])}</b></div><div class="kv">내는 것 <b>{e(it["gives"])}</b></div>'
                f'<div class="facts">예제로 돌린 값: {facts}</div>{note}'
                f'<div class="ft"><span class="st">계산값 · 검증 전</span><button type="button" class="add" aria-pressed="false">담기</button></div></div></article>')

    blob = json.dumps({"items": [{k: i[k] for k in ("key", "name", "form", "form_label", "area", "summary", "needs", "gives")} for i in items]},
                      ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body = f"""<header class="top"><span class="name">ConT Fab</span>
<label class="find"><svg viewBox="0 0 18 18" aria-hidden="true"><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12.2 12.2L16 16" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
<input type="search" id="q" aria-label="물리 정보 찾기" placeholder="물리 정보 찾기: 응력, 4D, 전류" autocomplete="off"></label>
<button type="button" class="cart" id="cart">바구니 0</button></header>
<div class="wrap"><aside class="side" aria-label="거르기"><div class="grp"><h2>물리 영역</h2>{side}</div>
<p class="fine">지금 코드에 실제로 있는 엔진만 실었습니다. 미리보기는 엔진을 예제 값으로 돌린 결과이며, 값은 모두 계산값이고 실측과 대조하기 전입니다.</p></aside>
<main class="main" style="max-width:none;margin:0"><h1>물리 정보를 골라 내 Fab에 담으세요</h1><p class="lead" id="count"></p>
<div class="chips" role="group" aria-label="형태">{chips}</div>
<div class="grid">{"".join(card(n, it) for n, it in enumerate(items))}</div><p class="none" id="none" hidden>맞는 것이 없습니다. 찾는 말이나 거르기를 바꿔 보세요.</p></main></div>
<aside class="basket" id="basket" hidden aria-label="바구니"><h2>바구니</h2><ul id="list"></ul>
<label>현장 이름<input type="text" id="site" placeholder="예: 1공장 절삭 라인" autocomplete="off"></label>
<button type="button" class="go" id="save" disabled>고른 것 내려받기 (my-fab.json)</button>
<p class="fine">고른 것은 이 화면 안에서만 담깁니다. 내려받은 파일이 "내 Fab 꾸리기"의 출발점이 됩니다. 꾸리기 화면은 아직 만들지 않았습니다.</p>
<button type="button" class="x" id="close">닫기</button></aside>
<script type="application/json" id="store-data">{blob}</script><script>{STORE_JS}</script>"""
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap" rel="stylesheet">')
    return (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f"<title>{e(title)}</title>{fonts}<style>{CSS}{EXTRA_CSS}{FIELD_CSS}{STORE_CSS}</style></head><body>\n{body}\n</body></html>")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="고르기 화면을 파일 하나로 쓴다")
    a = ap.parse_args(argv)
    items = catalog()
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render_store(items, load()["forms"]))
    print(f"written {a.out}: {len(items)} item(s)")


if __name__ == "__main__":
    main()
