#!/usr/bin/env python3
"""scripts/board.py — backlog 需求树 HTML 看板渲染(遵 DESIGN.md)。
从 backlog.py 抽出(守 800 行铁律);纯标准库,被 backlog.py 的 board 子命令惰性 import。"""
import html
import json
import os
import re

from backlog import load_leaves, build_tree, SHIPPED, STATUS_ORDER, STAGE_TO_STATUS

# ───────────────────────── board 渲染(遵 DESIGN.md) ─────────────────────────
BOARD_CSS = """
:root{
  --bg:#f6f1e6;--panel:#fffaf0;--ink:#1f2d24;--muted:#66776c;--line:#d8cfbd;
  --green:#6f925f;--green-soft:#d9e5cf;--radius:8px;--shadow:0 2px 0 rgba(31,45,36,.18);
  --blue:#cddce2;--yellow:#f3d77a;--orange:#df8a54;--danger:#c75f5f;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.board{max-width:1100px;margin:0 auto;padding:24px 24px 80px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);font-size:12px;margin-bottom:20px}
.cov{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 24px}
.cov .item{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:8px 12px;min-width:150px}
.cov .name{font-size:12px;color:var(--muted)}
.cov .bar{height:6px;background:var(--green-soft);border-radius:4px;margin-top:6px;overflow:hidden}
.cov .bar>i{display:block;height:100%;background:var(--green)}
details{margin:4px 0}
details>summary{cursor:pointer;padding:6px 8px;border-radius:6px;font-weight:600;list-style:none}
details>summary::-webkit-details-marker{display:none}
details>summary:before{content:"\\25b8";color:var(--green);margin-right:6px;font-size:11px}
details[open]>summary:before{content:"\\25be"}
details>summary:hover{background:var(--green-soft)}
details>summary:focus-visible{outline:2px solid var(--green);outline-offset:1px}
.domain{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);
  box-shadow:var(--shadow);margin:10px 0;padding:4px 8px}
.subdomain{margin-left:16px}
.subdomain>summary{font-weight:500}
.cnt{color:var(--muted);font-weight:400;font-size:11px}
.leaf{margin:6px 0 6px 32px;padding:8px 10px;background:var(--bg);
  border:1px solid var(--line);border-radius:6px}
.leaf h2{font-size:13px;margin:0 0 6px;font-weight:600}
.leaf[aria-current="true"]{border-left:3px solid var(--green);background:var(--green-soft)}
.meta{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:11px;color:var(--muted)}
.badge{padding:1px 7px;border-radius:4px;font-size:11px;color:var(--ink)}
.status-captured{background:#e6e2d6}
.status-specd{background:var(--blue)}
.status-planned{background:var(--yellow)}
.status-built{background:var(--orange)}
.status-validated{background:var(--green-soft)}
.status-shipped{background:var(--green);color:#fff}
.prio{padding:1px 6px;border-radius:4px;font-weight:600}
.prio-P0{background:var(--danger);color:#fff}.prio-P1{background:var(--orange)}
.prio-P2{background:var(--yellow)}.prio-P3{background:#e6e2d6}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.risk-high{background:var(--danger)}.risk-medium{background:var(--orange)}.risk-low{background:var(--muted)}
.deps{font-style:italic}
.empty{color:var(--muted);padding:48px;text-align:center}
/* 布局:左树 + 右侧常驻聊天栏 */
.app{display:flex;gap:16px;max-width:1480px;margin:0 auto;align-items:flex-start;padding:0 16px}
.board{flex:1;min-width:0;padding:24px 8px 80px;max-width:none;margin:0}
.leaf{cursor:pointer}
.leaf:hover{border-color:var(--green)}
.leaf:focus-visible{outline:2px solid var(--green);outline-offset:1px}
.leaf[aria-current="true"]{border-left:3px solid var(--green);background:var(--green-soft)}
/* 聊天面板 */
.chat-panel{width:380px;flex:none;position:sticky;top:16px;height:calc(100vh - 32px);
  display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line);
  border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
.chat-head{padding:12px 14px;border-bottom:1px solid var(--line);font-weight:600;font-size:13px}
.chat-detail{padding:0 14px;border-bottom:1px solid var(--line);max-height:40%;overflow:auto}
.chat-detail:empty{display:none}
.ld-title{font-size:13px;font-weight:600;margin:10px 0 6px}
.ld-badges{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.ld-risk{font-size:11px;color:var(--muted)}
.ld-meta{font-size:11px;color:var(--muted);margin-bottom:6px;word-break:break-word}
.ld-cross{font-size:11px;color:var(--muted);margin-bottom:6px;word-break:break-word;border-left:2px solid var(--green-soft);padding-left:6px}
.ld-body{font-size:12px;line-height:1.55;white-space:pre-wrap;color:var(--ink);background:var(--bg);
  border:1px solid var(--line);border-radius:6px;padding:8px;margin-bottom:10px}
.chat-msgs{flex:1;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:8px}
.chat-empty{color:var(--muted);text-align:center;margin-top:48px;font-size:13px}
.msg{max-width:85%;padding:8px 11px;border-radius:10px;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
.msg.user{align-self:flex-end;background:var(--green-soft);border:1px solid var(--line)}
.msg.agent{align-self:flex-start;background:var(--bg);border:1px solid var(--line)}
.chat-box{display:flex;gap:8px;padding:10px;border-top:1px solid var(--line)}
.chat-box textarea{flex:1;resize:none;height:42px;border:1px solid var(--line);border-radius:6px;
  padding:9px;font:13px/1.4 inherit;background:#fff}
.chat-box textarea:focus{outline:none;border-color:var(--green)}
.chat-box button{background:var(--green);color:#fff;border:0;border-radius:6px;padding:0 16px;
  font-weight:600;cursor:pointer}
.chat-box button:disabled{opacity:.5;cursor:not-allowed}
.chat-box button:hover:not(:disabled){filter:brightness(1.06)}
@media(max-width:768px){
  .app{flex-direction:column;padding:0}
  .board{padding:16px;width:100%}.leaf{margin-left:16px}
  .chat-panel{position:fixed;left:0;right:0;bottom:0;top:auto;width:auto;height:62vh;
    border-radius:12px 12px 0 0;transform:translateY(calc(100% - 46px));transition:transform .2s;z-index:50}
  .chat-panel.open{transform:translateY(0)}
  .chat-head{cursor:pointer}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

# 聊天面板逻辑(自包含):点叶选中→该叶会话气泡;发送 POST /feedback;轮询 /replies.json 追加 agent 回复;
# 轮询 /rev 树变即 reload;加载时读 /feedback-history.jsonl + /replies.json 重建线程(刷新不丢)。
# 后端复用 web-review/server.py(/feedback /wait /rev + 静态文件),不依赖 annotate.*。
CHAT_JS = """<script>
(function(){
  var current=null, threads={}, shown={};
  var head=document.getElementById('chat-leaf'), msgs=document.getElementById('chat-msgs');
  var input=document.getElementById('chat-input'), send=document.getElementById('chat-send');
  var panel=document.getElementById('chat'), detailEl=document.getElementById('chat-detail');
  var seq=0; function genId(){seq++;return 'm'+seq+'_'+(new Date().getTime());}
  var LEAFDATA={}; try{LEAFDATA=JSON.parse(document.getElementById('leaf-data').textContent||'{}');}catch(e){}
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function csss(s){return String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');}
  function renderDetail(){
    if(!current||!LEAFDATA[current]){detailEl.innerHTML='';return;}
    var d=LEAFDATA[current], deps=(d.depends_on||[]).join(', ')||'无';
    detailEl.innerHTML=
      '<div class="ld-title">'+esc(d.title)+'</div>'+
      '<div class="ld-badges"><span class="badge status-'+csss(d.status)+'">'+esc(d.status)+'</span>'+
      '<span class="prio prio-'+esc(d.priority)+'">'+esc(d.priority)+'</span>'+
      '<span class="ld-risk">risk: '+esc(d.risk_level)+'</span></div>'+
      '<div class="ld-meta">域: '+esc(d.domain_path)+' · old: '+esc(d.old_system_ref||'—')+' · 依赖: '+esc(deps)+'</div>'+
      crossRow(d)+
      '<div class="ld-body">'+esc(d.body)+'</div>';
  }
  function crossRow(d){
    var parts=[];
    if(d.actor)parts.push('参与者: '+esc(d.actor));
    if(d.failure_class)parts.push('失败类: '+esc(d.failure_class));
    if(d.data_owner)parts.push('数据源: '+esc(d.data_owner));
    if(d.contract_refs&&d.contract_refs.length)parts.push('契约: '+esc(d.contract_refs.join(', ')));
    return parts.length?'<div class="ld-cross">'+parts.join(' · ')+'</div>':'';
  }
  function render(){
    msgs.innerHTML='';
    if(!current){msgs.innerHTML='<p class="chat-empty">点左侧一片需求叶，开始对话。</p>';return;}
    (threads[current]||[]).forEach(function(m){
      var d=document.createElement('div');d.className='msg '+m.role;d.textContent=m.text;msgs.appendChild(d);
    });
    msgs.scrollTop=msgs.scrollHeight;
  }
  function selectLeaf(id){
    current=id;
    document.querySelectorAll('.leaf').forEach(function(el){
      el.setAttribute('aria-current', el.getAttribute('data-leaf')===id?'true':'false');});
    head.textContent='\\uD83D\\uDCAC '+id;
    input.disabled=false;send.disabled=false;
    if(panel)panel.classList.add('open');
    renderDetail();render();input.focus();
  }
  document.querySelectorAll('.leaf').forEach(function(el){
    el.setAttribute('tabindex','0');
    el.addEventListener('click',function(){selectLeaf(el.getAttribute('data-leaf'));});
    el.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();selectLeaf(el.getAttribute('data-leaf'));}});
  });
  if(head)head.addEventListener('click',function(){if(panel&&window.innerWidth<=768)panel.classList.toggle('open');});
  function doSend(){
    var text=input.value.trim();if(!text||!current)return;
    var id=genId();(threads[current]=threads[current]||[]).push({id:id,role:'user',text:text});
    input.value='';render();
    fetch('/feedback',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:id,leaf:current,message:text})}).catch(function(){});
  }
  if(send)send.addEventListener('click',doSend);
  if(input)input.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend();}});
  function applyReplies(rep){
    if(!rep)return;
    Object.keys(rep).forEach(function(mid){
      if(shown[mid])return;
      for(var leaf in threads){
        var t=threads[leaf],i=-1,k;
        for(k=0;k<t.length;k++){if(t[k].id===mid){i=k;break;}}
        if(i>=0){
          var has=false;for(k=0;k<t.length;k++){if(t[k].id===mid+'-r'){has=true;break;}}
          if(!has)t.splice(i+1,0,{id:mid+'-r',role:'agent',text:rep[mid]});
          shown[mid]=true;break;
        }
      }
    });
    if(current)render();
  }
  function pollReplies(){fetch('/replies.json',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).then(applyReplies).catch(function(){});}
  // 重建历史:用户消息来自 feedback-history.jsonl,agent 回复来自 replies.json
  fetch('/feedback-history.jsonl',{cache:'no-store'}).then(function(r){return r.ok?r.text():'';}).then(function(txt){
    (txt||'').split('\\n').forEach(function(line){
      if(!line.trim())return;var rec;try{rec=JSON.parse(line);}catch(e){return;}
      if(!rec.leaf||!rec.id)return;var t=threads[rec.leaf]=threads[rec.leaf]||[];
      var dup=false,k;for(k=0;k<t.length;k++){if(t[k].id===rec.id){dup=true;break;}}
      if(!dup)t.push({id:rec.id,role:'user',text:rec.message||''});
    });
    pollReplies();
  }).catch(function(){pollReplies();});
  setInterval(pollReplies,3000);
  var lastRev=null;
  setInterval(function(){fetch('/rev',{cache:'no-store'}).then(function(r){return r.ok?r.text():null;}).then(function(t){
    if(t==null)return;if(lastRev===null){lastRev=t;return;}if(t!==lastRev)location.reload();}).catch(function(){});},2000);
  render();
})();
</script>"""


def _css_safe(s):
    """状态/风险值 → CSS 类名安全片段(spec'd → specd)。"""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


DETAIL_KEYS = ["title", "status", "priority", "risk_level", "domain_path",
               "old_system_ref", "new_domain_path", "depends_on", "cross_link",
               "actor", "failure_class", "contract_refs", "data_owner"]


def _leaf_detail_map(leaves):
    """{id: {字段... + body}} —— 供聊天面板"叶详情"显示(选叶后看清需求内容)。"""
    detail = {}
    for lf in leaves:
        lid = lf.get("id")
        if not lid:
            continue
        d = {k: lf.get(k) for k in DETAIL_KEYS}
        d["body"] = lf.get("_body", "")
        detail[lid] = d
    return detail


def _read_state_overlay(req_root):
    """读 <req_root>/../STATE.md → {leaf, stage, status} 供看板惰性叠加在飞特性 live badge。
    无 STATE / source-leaf=(none) / stage 非过渡态 → None(向后兼容纯文件 status 渲染)。"""
    state = os.path.join(os.path.dirname(os.path.abspath(req_root.rstrip("/"))), "STATE.md")
    if not os.path.isfile(state):
        return None
    try:
        txt = open(state, encoding="utf-8").read()
    except OSError:
        return None

    def v(key):
        m = re.search(rf"(?mi)^{key}:\s*(.+)$", txt)
        return m.group(1).strip() if m else ""
    leaf, stage = v("source-leaf"), v("stage")
    if not leaf or leaf == "(none)":
        return None
    to = STAGE_TO_STATUS.get(stage)
    return {"leaf": leaf, "stage": stage, "status": to} if to else None


def render_board(tree, leaves, title="Backlog 需求树看板", live=None):
    """整树 → 自包含 HTML 看板(左折叠树 + 右聊天面板 + 叶详情 + Live 回路)。只读渲染。
    live={leaf,stage,status}: 对在飞特性源叶叠加 live badge(惰性派生,不写文件);None=纯文件 status。"""
    esc = html.escape
    summ = tree["summary"]
    # 叶详情数据嵌入(防 </script> 注入:转义 </)
    leaf_data_json = json.dumps(_leaf_detail_map(leaves), ensure_ascii=False).replace("</", "<\\/")
    cov_items = []
    for d in tree["domains"]:
        leaves = [lf for sub in d["subdomains"] for lf in sub["leaves"]]
        total = len(leaves)
        shipped = sum(1 for lf in leaves if lf.get("status") == SHIPPED)
        pct = int(shipped * 100 / total) if total else 0
        cov_items.append(
            f'<div class="item"><div class="name">{esc(d["domain"])} · {shipped}/{total} shipped</div>'
            f'<div class="bar"><i style="width:{pct}%"></i></div></div>')
    cov_html = ('<div class="cov">' + "".join(cov_items) + "</div>") if cov_items else ""

    if not tree["domains"]:
        body = '<p class="empty">暂无需求（.sdlc/requirements/ 为空）</p>'
    else:
        doms = []
        for d in tree["domains"]:
            subs = []
            for sub in d["subdomains"]:
                lvs = []
                for lf in sub["leaves"]:
                    raw_id = lf.get("id") or ""
                    lid = esc(raw_id)
                    st = lf.get("status") or "unknown"
                    pr = esc(lf.get("priority") or "P?")
                    risk = lf.get("risk_level") or "medium"
                    deps = lf.get("depends_on") or []
                    deps_html = (f'<span class="deps">依赖: {esc(", ".join(deps))}</span>'
                                 if deps else "")
                    # 惰性叠加:在飞特性源叶显示 live badge(不改文件 status)
                    live_html = ""
                    if live and live["leaf"] == raw_id:
                        live_html = (f'<span class="live-badge status-{_css_safe(live["status"])}" '
                                     f'title="在飞:{esc(live["stage"])}">⏳ {esc(live["stage"])}中</span>')
                    lvs.append(
                        f'<section class="leaf" id="{lid}" data-leaf="{lid}" '
                        f'role="button" aria-label="选择 {lid} 开始对话" aria-current="false">'
                        f'<h2>{lid} · {esc(lf.get("title") or "")}</h2>'
                        f'<div class="meta">'
                        f'<span class="badge status-{_css_safe(st)}">{esc(st)}</span>'
                        f'{live_html}'
                        f'<span class="prio prio-{pr}">{pr}</span>'
                        f'<span class="dot risk-{_css_safe(risk)}" title="risk: {esc(risk)}"></span>'
                        f'{deps_html}</div></section>')
                subs.append(
                    f'<details class="subdomain" open><summary>{esc(sub["subdomain"])} '
                    f'<span class="cnt">({len(sub["leaves"])})</span></summary>'
                    + "".join(lvs) + "</details>")
            doms.append(
                f'<details class="domain" open><summary>{esc(d["domain"])}</summary>'
                + "".join(subs) + "</details>")
        body = "".join(doms)

    chat_panel = (
        '<aside class="chat-panel" id="chat">'
        '<div class="chat-head" id="chat-leaf">💬 选择一片需求叶</div>'
        '<div class="chat-detail" id="chat-detail"></div>'
        '<div class="chat-msgs" id="chat-msgs">'
        '<p class="chat-empty">点左侧一片需求叶，开始对话。</p></div>'
        '<div class="chat-box">'
        '<textarea id="chat-input" aria-label="对选中的需求叶发送消息" '
        'placeholder="问 / 改这片叶…（Enter 发送，Shift+Enter 换行）" '
        'disabled></textarea>'
        '<button id="chat-send" disabled>发送</button></div></aside>'
    )
    leaf_data = f'<script type="application/json" id="leaf-data">{leaf_data_json}</script>'
    return (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(title)}</title><style>{BOARD_CSS}</style></head><body>'
        f'<div class="app"><div class="board"><h1>{esc(title)}</h1>'
        f'<div class="sub">共 {summ["total"]} 条需求 · ready {summ["ready_count"]} 条</div>'
        f'{cov_html}{body}</div>{chat_panel}</div>'
        f'{leaf_data}{CHAT_JS}</body></html>'
    )


def cmd_board(args):
    leaves = load_leaves(args.root)
    tree = build_tree(leaves)
    out = args.out or os.path.join(args.root, "_board.html")
    live = _read_state_overlay(args.root)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render_board(tree, leaves, live=live))
    print(json.dumps({"board": out, "domains": len(tree["domains"]),
                      "total": tree["summary"]["total"]}, ensure_ascii=False))
    return 0
