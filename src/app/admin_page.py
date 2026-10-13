"""管理后台单页应用（M2.1 重构版）：GET /admin 返回完整 HTML

布局与视觉完全对齐 demo（docs/demo/sftp-admin-demo.html）：
#f5f5f7 背景 + 白卡片 16px 圆角 + #0b3d62 深海军蓝主色，
标题/数字 Noto Serif SC，正文 Noto Sans SC；侧边栏 active 浅蓝底。
页面：仪表盘（含 7 日趋势 SVG）/ 账号管理（含加密路径卡片）/
会话监控 / 审计日志 / 用户 Web 访问（加密路径总览）/ 系统设置。
纯原生 JS，无外部依赖。
"""
import os

from .config import ADMIN_PORT, FILE_ROOT, SFTP_PORT

_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SFTP 管理后台</title>
<style>
:root{--bg:#f5f5f7;--card:#fff;--primary:#0b3d62;--primary-light:#e8f0f7;--text:#1d1d1f;
--text-sec:#6e6e73;--line:#e8e8ed;--green:#34a853;--red:#e5484d;--orange:#f5a623;--blue:#2f6fed;--radius:16px}
*{margin:0;padding:0;box-sizing:border-box;font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif}
body{background:var(--bg);color:var(--text);font-size:14px}
.num,.card-title,h1,h2{font-family:'Noto Serif SC','Songti SC',serif}
/* ===== 登录页 ===== */
#loginPage{position:fixed;inset:0;background:linear-gradient(135deg,#0b3d62 0%,#123f6d 60%,#1a5a8a 100%);
display:flex;align-items:center;justify-content:center;z-index:100}
.login-card{background:var(--card);border-radius:20px;padding:48px 44px;width:400px;box-shadow:0 24px 60px rgba(0,0,0,.35)}
.login-card h1{font-size:26px;color:var(--primary);margin-bottom:6px}
.login-card .sub{color:var(--text-sec);margin-bottom:28px;font-size:13px}
.fld{margin-bottom:16px}
.fld label{display:block;font-size:12px;color:var(--text-sec);margin-bottom:6px}
.fld input{width:100%;height:42px;border:1px solid var(--line);border-radius:10px;padding:0 14px;font-size:14px;outline:none;transition:border .15s}
.fld input:focus{border-color:var(--primary)}
.btn-primary{width:100%;height:44px;background:var(--primary);color:#fff;border:none;border-radius:10px;font-size:15px;cursor:pointer;margin-top:6px}
.btn-primary:hover{background:#0e4a75}
.btn-primary:disabled{opacity:.6}
.login-tip{margin-top:18px;text-align:center;font-size:12px;color:var(--text-sec)}
#lmsg{color:var(--red);font-size:13px;min-height:18px;margin-top:10px;text-align:center}
/* ===== 布局 ===== */
.layout{display:flex;min-height:100vh}
.sidebar{width:220px;background:var(--card);border-right:1px solid var(--line);padding:24px 12px;position:fixed;top:0;bottom:0;z-index:5}
.logo{font-family:'Noto Serif SC',serif;font-size:20px;font-weight:700;color:var(--primary);padding:0 12px 22px;letter-spacing:.5px}
.logo small{display:block;font-family:'Noto Sans SC',sans-serif;font-size:11px;font-weight:400;color:var(--text-sec);margin-top:2px}
.nav-item{display:flex;align-items:center;gap:10px;padding:11px 14px;border-radius:10px;cursor:pointer;color:var(--text-sec);margin-bottom:4px;transition:all .15s}
.nav-item:hover{background:var(--bg)}
.nav-item.active{background:var(--primary-light);color:var(--primary);font-weight:600}
.nav-item .ico{width:18px;text-align:center}
.main{margin-left:220px;flex:1;padding:28px 32px}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}
.topbar h2{font-size:22px}
.who{display:flex;align-items:center;gap:10px;color:var(--text-sec);font-size:13px}
.avatar{width:34px;height:34px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px}
/* ===== 卡片与统计 ===== */
.card{background:var(--card);border-radius:var(--radius);padding:22px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px}
.stat .lab{color:var(--text-sec);font-size:13px;margin-bottom:8px}
.stat .val{font-family:'Noto Serif SC',serif;font-size:28px;font-weight:700;color:var(--primary)}
.stat .val small{font-size:13px;color:var(--text-sec);font-weight:400;margin-left:4px}
.stat .delta{font-size:12px;margin-top:6px}
.up{color:var(--green)}.down{color:var(--red)}
.two-col{display:grid;grid-template-columns:2fr 1fr;gap:16px}
.card h3{font-size:15px;margin-bottom:16px}
/* ===== 表格 ===== */
table{width:100%;border-collapse:collapse}
th{font-size:12px;color:var(--text-sec);font-weight:500;text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:12px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#fafafc}
.badge{display:inline-block;padding:3px 10px;border-radius:99px;font-size:12px;white-space:nowrap}
.b-green{background:#e6f4ea;color:var(--green)}
.b-red{background:#fdebec;color:var(--red)}
.b-orange{background:#fdf3e0;color:#c77c0a}
.b-gray{background:#f0f0f3;color:var(--text-sec)}
.b-blue{background:#e8f0fe;color:var(--blue)}
.toolbar{display:flex;gap:10px;margin-bottom:16px;align-items:center;flex-wrap:wrap}
.toolbar input,.toolbar select{height:36px;border:1px solid var(--line);border-radius:9px;padding:0 12px;font-size:13px;outline:none;background:#fff}
.toolbar input:focus,.toolbar select:focus{border-color:var(--primary)}
.toolbar .sp{flex:1}
.btn{height:36px;padding:0 16px;border-radius:9px;border:1px solid var(--line);background:#fff;cursor:pointer;font-size:13px;white-space:nowrap}
.btn:hover{border-color:var(--primary);color:var(--primary)}
.btn.pri{background:var(--primary);color:#fff;border-color:var(--primary)}
.btn.pri:hover{background:#0e4a75}
.btn.sm{height:29px;padding:0 12px;font-size:12px;border-radius:8px}
.btn.danger:hover{border-color:var(--red);color:var(--red)}
.perm{display:inline-flex;gap:3px}
.perm span{width:20px;height:20px;border-radius:5px;font-size:11px;display:flex;align-items:center;justify-content:center}
.p-on{background:var(--primary-light);color:var(--primary);font-weight:600}
.p-off{background:#f0f0f3;color:#c0c0c6}
.usage-bar{width:120px;height:6px;background:#eee;border-radius:3px;overflow:hidden;display:inline-block;vertical-align:middle;margin-right:8px}
.usage-bar i{display:block;height:100%;background:var(--primary);border-radius:3px}
.usage-bar i.warn{background:var(--orange)}.usage-bar i.full{background:var(--red)}
.tok{font-family:Consolas,monospace;font-size:12px;color:var(--primary);background:var(--primary-light);padding:2px 8px;border-radius:6px;cursor:pointer}
.chart-wrap svg{width:100%;height:220px}
.legend{display:flex;gap:16px;font-size:12px;color:var(--text-sec);margin-bottom:8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:middle}
.page{display:none}.page.active{display:block}
.pager{display:flex;justify-content:flex-end;gap:6px;margin-top:14px;color:var(--text-sec);font-size:12px;align-items:center}
.pager button{width:28px;height:28px;border-radius:7px;border:1px solid var(--line);background:#fff;cursor:pointer}
.pager button.cur{background:var(--primary);color:#fff;border-color:var(--primary)}
.pager button:disabled{opacity:.4;cursor:default}
.empty-hint{color:var(--text-sec);font-size:12px;margin-top:14px;text-align:center}
.empty{text-align:center;color:#aab;padding:30px 0;font-size:13px}
/* 弹窗 */
.mask{position:fixed;inset:0;background:rgba(15,30,45,.4);display:none;align-items:center;justify-content:center;z-index:20}
.mask.show{display:flex}
.modal{background:#fff;border-radius:16px;padding:26px 28px;width:480px;max-height:86vh;overflow:auto}
.modal h3{color:var(--primary);font-size:17px;margin-bottom:16px}
.modal label{display:block;font-size:12px;color:var(--text-sec);margin:12px 0 5px}
.modal input[type=text],.modal input[type=password],.modal input[type=number],.modal input[type=date]{width:100%;height:38px;border:1px solid var(--line);border-radius:9px;padding:0 12px;font-size:13px;outline:none}
.modal input:focus{border-color:var(--primary)}
.modal .row{display:flex;gap:14px}.modal .row>div{flex:1}
.chk{display:inline-flex;align-items:center;gap:5px;margin-right:14px;margin-top:8px;font-size:13px}
.mfoot{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}
#toast{position:fixed;top:18px;left:50%;transform:translateX(-50%);background:var(--primary);color:#fff;
padding:10px 22px;border-radius:10px;font-size:13px;display:none;z-index:99}
.addr{display:flex;gap:10px;align-items:center;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-bottom:14px;flex-wrap:wrap}
</style></head><body>

<!-- ============ 登录页 ============ -->
<div id="loginPage"><div class="login-card">
  <h1>SFTP 管理后台</h1>
  <div class="sub">Secure File Transfer · Admin Console</div>
  <div class="fld"><label>管理员账号</label><input id="lu" placeholder="admin" value="admin"></div>
  <div class="fld"><label>密码</label><input id="lp" type="password" placeholder="••••••••" onkeydown="if(event.key==='Enter')doLogin()"></div>
  <button class="btn-primary" id="lb" onclick="doLogin()">登 录</button>
  <div id="lmsg"></div>
  <div class="login-tip">管理后台 · 与用户文件访问页（/web/login）相互独立</div>
</div></div>

<!-- ============ 主布局 ============ -->
<div class="layout" id="app" style="display:none">
  <div class="sidebar">
    <div class="logo">NexSFTP Admin<small>文件传输管理平台 v1.6</small></div>
    <div class="nav-item active" data-p="dashboard" onclick="go('dashboard')"><span class="ico">📊</span>仪表盘</div>
    <div class="nav-item" data-p="projects" onclick="go('projects')" id="nav-projects"><span class="ico">🗂️</span>项目管理</div>
    <div class="nav-item" data-p="accounts" onclick="go('accounts')"><span class="ico">👤</span>SFTP账号管理</div>
    <div class="nav-item" data-p="groups" onclick="go('groups')"><span class="ico">👥</span>后台账号管理</div>
    <div class="nav-item" data-p="sessions" onclick="go('sessions')"><span class="ico">🔗</span>会话监控</div>
    <div class="nav-item" data-p="logs" onclick="go('logs')"><span class="ico">📋</span>审计日志</div>
    <div class="nav-item" data-p="settings" onclick="go('settings')"><span class="ico">⚙️</span>系统设置</div>
    <div class="nav-item" data-p="webfiles" onclick="go('webfiles')" style="margin-top:14px;border-top:1px solid var(--line);padding-top:14px"><span class="ico">🌐</span><span>用户 Web 访问<br><small style="font-size:10px;color:var(--text-sec)">加密路径总览</small></span></div>
    <div style="position:absolute;bottom:16px;left:20px"><a href="/api/docs" target="_blank" style="color:var(--text-sec);font-size:12px;text-decoration:none">API 文档 ↗</a></div>
  </div>

  <div class="main">
    <div class="topbar">
      <h2 id="pageTitle">仪表盘</h2>
      <div class="who"><div class="avatar">管</div><span id="wuser">admin</span>
        <span class="badge b-blue" id="roleBadge" style="margin-right:6px"></span>
        <button class="btn sm" onclick="doLogout()">退出</button></div>
    </div>

    <div class="page active" id="p-dashboard"></div>
    <div class="page" id="p-projects"></div>
    <div class="page" id="p-accounts"></div>
    <div class="page" id="p-groups"></div>
    <div class="page" id="p-sessions"></div>
    <div class="page" id="p-logs"></div>
    <div class="page" id="p-settings">
      <div class="card" style="max-width:640px">
        <h3 style="margin-bottom:20px">基础设置</h3>
        <table>
          <tr><td style="width:180px;color:var(--text-sec)">SFTP 监听端口</td><td class="num">__SFTP_PORT__</td></tr>
          <tr><td style="color:var(--text-sec)">管理后台端口</td><td class="num">__ADMIN_PORT__</td></tr>
          <tr><td style="color:var(--text-sec)">SFTP 服务总开关</td><td><span class="badge b-green" id="svcBadge">🟢 检测中…</span></td></tr>
          <tr><td style="color:var(--text-sec)">密码策略</td><td>≥8 位，须含字母 + 数字</td></tr>
          <tr><td style="color:var(--text-sec)">日志保留</td><td class="num">90 天（规划值，M5 可配置）</td></tr>
          <tr><td style="color:var(--text-sec)">空闲超时</td><td>30 分钟（规划值，M5 可配置）</td></tr>
          <tr><td style="color:var(--text-sec)">用户数据根目录</td><td class="num">__FILE_ROOT__</td></tr>
          <tr><td style="color:var(--text-sec)">配额对账</td><td>每 5 分钟磁盘实扫，自动校正 used_bytes / used_files</td></tr>
        </table>
        <div class="empty-hint">本页为运行信息只读展示；端口/超时/保留期等可配置化在 M5 交付</div>
      </div>
    </div>
    <div class="page" id="p-webfiles"></div>
  </div>
</div>

<div class="mask" id="mask"><div class="modal" id="modal"></div></div>
<div id="toast"></div>

<script>
const API="/api/v1";
let TOKEN=sessionStorage.getItem("st")||"";
let ROLE=sessionStorage.getItem("role")||"admin";
let MYPROJ=[];try{MYPROJ=JSON.parse(sessionStorage.getItem("myproj")||"[]")}catch(e){}
const isSuper=()=>ROLE==="super_admin", isPA=()=>ROLE==="project_admin";
let PAGE="dashboard",LOGQ={page:1,username:"",action:""},SESS_TIMER=null,USERS=[];

/* ---------- 基础 ---------- */
async function api(m,p,body){
  const r=await fetch(API+p,{method:m,headers:{"Content-Type":"application/json",
    Authorization:"Bearer "+TOKEN},body:body?JSON.stringify(body):undefined});
  if(r.status===401){showLogin();throw new Error("未登录");}
  const j=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(j.detail||("HTTP "+r.status));
  return j;
}
function toast(t){const e=document.getElementById("toast");e.textContent=t;e.style.display="block";
  clearTimeout(e._t);e._t=setTimeout(()=>e.style.display="none",2200);}
function fmtB(n){n=n||0;if(n>=1073741824)return (n/1073741824).toFixed(2)+" GB";
  if(n>=1048576)return (n/1048576).toFixed(1)+" MB";if(n>=1024)return (n/1024).toFixed(1)+" KB";return n+" B";}
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function pageEl(p){return document.getElementById("p-"+p);}

/* ---------- 登录 ---------- */
async function doLogin(){
  const b=document.getElementById("lb"),m=document.getElementById("lmsg");
  b.disabled=true;m.textContent="";
  try{
    const r=await fetch(API+"/auth/login",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({username:lu.value.trim(),password:lp.value})});
    const j=await r.json().catch(()=>({}));
    if(!r.ok){m.textContent=j.detail||"认证失败";return;}
    TOKEN=j.token;sessionStorage.setItem("st",TOKEN);
    ROLE=j.role||"admin";sessionStorage.setItem("role",ROLE);
    MYPROJ=j.projects||[];sessionStorage.setItem("myproj",JSON.stringify(MYPROJ));
    document.getElementById("wuser").textContent=lu.value.trim();
    showApp();
  }catch(e){m.textContent="网络错误："+e;}
  finally{b.disabled=false;}
}
function doLogout(){api("POST","/auth/logout").catch(()=>{});TOKEN="";sessionStorage.removeItem("st");showLogin();}
function showLogin(){document.getElementById("loginPage").style.display="flex";
  document.getElementById("app").style.display="none";clearInterval(SESS_TIMER);}
async function showApp(){
  document.getElementById("loginPage").style.display="none";
  document.getElementById("app").style.display="flex";
  applyRole();
  if(!isPA()){try{PROJECTS=await api("GET","/projects")}catch(e){PROJECTS=[]}}
  go("dashboard");
}

/* ---------- 角色视角适配 ---------- */
function applyRole(){
  const rb=document.getElementById("roleBadge");
  const lbl={super_admin:"超级管理员",admin:"平台管理员",project_admin:"项目管理员"+(MYPROJ.length?" · "+MYPROJ.join("/"):"")};
  rb.textContent=lbl[ROLE]||ROLE;
  const hide=(id,cond)=>{const el=document.getElementById(id);if(el)el.style.display=cond?"none":""};
  const notPlatform=isPA();
  hide("nav-projects",notPlatform);
  hide("nav-groups",notPlatform);       /* 后台账号管理 */
  document.querySelector('[data-p="settings"]').style.display=notPlatform?"none":"";
}
/* ---------- 导航 ---------- */
const TITLES={dashboard:"仪表盘",projects:"项目管理",accounts:"SFTP账号管理",groups:"后台账号管理",sessions:"会话监控",logs:"审计日志",
  settings:"系统设置",webfiles:"用户 Web 文件访问（加密路径）"};
function go(p){
  PAGE=p;
  document.querySelectorAll(".nav-item").forEach(n=>n.classList.toggle("active",n.dataset.p===p));
  document.querySelectorAll(".page").forEach(pg=>pg.classList.remove("active"));
  pageEl(p).classList.add("active");
  document.getElementById("pageTitle").textContent=TITLES[p];
  clearInterval(SESS_TIMER);
  if(p==="dashboard"){renderDash();SESS_TIMER=setInterval(renderDash,10000);}
  if(p==="projects")renderProjects();
  if(p==="accounts")renderAcct();
  if(p==="groups")renderGroups();
  if(p==="sessions"){renderSess();SESS_TIMER=setInterval(renderSess,5000);}
  if(p==="logs")renderLogs();
  if(p==="settings")renderSettings();
  if(p==="webfiles")renderWebfiles();
}

/* ---------- 仪表盘 ---------- */
async function renderDash(){
  let d,trend;
  try{d=await api("GET","/dashboard/summary");}catch(e){pageEl("dashboard").innerHTML=`<div class="card empty">加载失败：${esc(e.message)}</div>`;return;}
  try{trend=(await api("GET","/dashboard/trend")).items;}catch(e){trend=[];}
  const upToday=trend.length?trend[trend.length-1].up:0, dnToday=trend.length?trend[trend.length-1].down:0;
  const top=d.disk_top.map(u=>{
    const pct=u.quota_bytes?Math.min(100,(u.used_bytes/u.quota_bytes*100)):(u.used_bytes?100:0);
    const cls=pct>=90?"full":pct>=80?"warn":"";
    return `<tr><td><b>${esc(u.username)}</b></td>
      <td><span class="usage-bar"><i class="${cls}" style="width:${pct}%"></i></span><span class="num">${pct.toFixed(0)}%</span></td>
      <td class="num">${fmtB(u.used_bytes)} / ${u.quota_bytes?fmtB(u.quota_bytes):"不限"}</td></tr>`;
  }).join("")||`<tr><td colspan=3 class="empty">暂无数据</td></tr>`;
  pageEl("dashboard").innerHTML=`
    <div class="stat-grid">
      <div class="card stat"><div class="lab">在线会话</div><div class="val num">${d.sessions_online}<small>个</small></div><div class="delta">SFTP 实时</div></div>
      <div class="card stat"><div class="lab">今日上传量</div><div class="val num">${fmtB(upToday).replace(/ .*/,"")}<small>${fmtB(upToday).replace(/.* /,"")}</small></div><div class="delta up">▲ 今日累计</div></div>
      <div class="card stat"><div class="lab">今日下载量</div><div class="val num">${fmtB(dnToday).replace(/ .*/,"")}<small>${fmtB(dnToday).replace(/.* /,"")}</small></div><div class="delta down">▼ 今日累计</div></div>
      <div class="card stat"><div class="lab">账号总数</div><div class="val num">${d.accounts_total}<small>启用 ${d.accounts_enabled}</small></div><div class="delta">今日审计 ${d.audit_today} 条</div></div>
    </div>
    <div class="two-col">
      <div class="card"><h3>近 7 日传输趋势 <span style="font-size:12px;font-weight:400;color:var(--text-sec)">（每 10 秒自动刷新）</span></h3>
        <div class="legend"><span><i style="background:#0b3d62"></i>上传</span><span><i style="background:#7fb3dd"></i>下载</span></div>
        <div class="chart-wrap">${trendSvg(trend)}</div></div>
      <div class="card"><h3>磁盘使用 TOP 5</h3>
        <table>${top}</table>
        <div class="empty-hint">阈值：🟡 80% · 🔴 90%</div></div>
    </div>`;
}
function trendSvg(trend){
  if(!trend.length)return `<div class="empty">暂无传输数据</div>`;
  const W=640,H=220,L=40,B=190,max=Math.max(1,...trend.map(t=>Math.max(t.up,t.down)));
  const step=(W-L-20)/trend.length,bw=28;
  const bar=(v,i,x,fill)=>{const h=Math.max(1,v/max*(B-20));
    return `<rect x="${x}" y="${B-h}" width="${bw}" height="${h}" rx="4" fill="${fill}"/>`;};
  let svg=`<svg viewBox="0 0 ${W} ${H}">
    <line x1="${L}" y1="10" x2="${L}" y2="${B}" stroke="#e8e8ed"/><line x1="${L}" y1="${B}" x2="${W-10}" y2="${B}" stroke="#e8e8ed"/>
    <text x="${L-8}" y="20" font-size="10" fill="#6e6e73" text-anchor="end">${(max/1073741824).toFixed(1)}G</text>
    <text x="${L-8}" y="${B}" font-size="10" fill="#6e6e73" text-anchor="end">0</text>`;
  trend.forEach((t,i)=>{
    const x0=L+10+i*step;
    svg+=bar(t.up,i,x0+2,"#0b3d62")+bar(t.down,i,x0+bw+6,"#7fb3dd");
    svg+=`<text x="${x0+bw+4}" y="${B+16}" font-size="10" fill="#6e6e73" text-anchor="middle">${t.date.slice(5)}</text>`;
  });
  return svg+"</svg>";
}

/* ---------- 项目管理 ---------- */
let PROJECTS=[];
async function renderProjects(){
  let list;
  try{list=await api("GET","/projects");}catch(e){pageEl("projects").innerHTML=`<div class="card empty">${esc(e.message)}</div>`;return;}
  PROJECTS=list;
  const rows=list.map(p=>`<tr>
    <td><b>${esc(p.name)}</b></td><td class="num">${esc(p.code)}</td>
    <td class="num">${p.user_count}</td>
    <td>${(p.admins||[]).map(a=>`<span class="badge b-blue">${esc(a)}</span>`).join(" ")||'<span style="color:var(--text-sec)">未分配</span>'}</td>
    <td>${p.enabled?'<span class="badge b-green">🟢 启用</span>':'<span class="badge b-red">🔴 停用</span>'}</td>
    <td style="white-space:nowrap">
      <button class="btn sm" onclick="openProjEdit(${p.id})">编辑</button>
      <button class="btn sm" onclick="openBindAdmins(${p.id})">分配管理员</button>
      <button class="btn sm ${p.enabled?"danger":""}" onclick="toggleProj(${p.id},${p.enabled})">${p.enabled?"停用":"启用"}</button>
    </td></tr>`).join("");
  pageEl("projects").innerHTML=`
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <h3 style="margin:0">项目列表</h3>
        <button class="btn pri" onclick="openProjCreate()">＋ 新建项目</button></div>
      <table><thead><tr><th>项目</th><th>标识</th><th>账号数</th><th>项目管理员</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>${rows||'<tr><td colspan="6" class="empty">暂无项目</td></tr>'}</tbody></table>
      <div class="empty-hint">停用项目：该项目全部账号登录即时冻结，在线会话自动断开。项目归属调整请到 SFTP账号管理。</div>
    </div>`;
}
function openProjCreate(){
  modal(`<h3>新建项目</h3>
    <label>项目名称<input id="np_n" placeholder="如：司法调证"></label>
    <label>项目标识（小写/数字/-/_）<input id="np_c" placeholder="如：evidence"></label>
    <label>备注<input id="np_r"></label>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:18px">
    <button class="btn" onclick="closeModal()">取消</button>
    <button class="btn pri" onclick="submitProjCreate()">创建</button></div>`);
}
async function submitProjCreate(){
  try{await api("POST","/projects",{name:np_n.value,code:np_c.value,remark:np_r.value});}
  catch(e){toast("创建失败："+e.message);return;}
  closeModal();toast("项目已创建");renderProjects();
}
function openProjEdit(id){
  const p=PROJECTS.find(x=>x.id===id);if(!p)return;
  modal(`<h3>编辑项目 · ${esc(p.name)}</h3>
    <label>项目名称<input id="ep_n" value="${esc(p.name)}"></label>
    <label>备注<input id="ep_r" value="${esc(p.remark||"")}"></label>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:18px">
    <button class="btn" onclick="closeModal()">取消</button>
    <button class="btn pri" onclick="submitProjEdit(${p.id})">保存</button></div>`);
}
async function submitProjEdit(id){
  try{await api("PATCH","/projects/"+id,{name:ep_n.value,remark:ep_r.value});}
  catch(e){toast("保存失败："+e.message);return;}
  closeModal();toast("已保存");renderProjects();
}
async function toggleProj(id,en){
  const p=PROJECTS.find(x=>x.id===id);if(!p)return;
  if(en&&!confirm(`确定停用项目「${p.name}」？\n该项目 ${p.user_count} 个账号登录将即时冻结，在线会话立即断开。`))return;
  try{await api("PATCH","/projects/"+id,{enabled:!en});}
  catch(e){toast("操作失败："+e.message);return;}
  toast(en?"项目已停用":"项目已启用");renderProjects();
}
async function openBindAdmins(pid){
  const p=PROJECTS.find(x=>x.id===pid);if(!p)return;
  let ADM;try{ADM=await api("GET","/admins");}catch(e){toast(e.message);return;}
  const pas=ADM.filter(a=>a.role==="project_admin");
  if(!pas.length){toast("请先在后台账号管理创建 project_admin 角色账号");return;}
  const cur=new Set(p.admins||[]);
  modal(`<h3>分配项目管理员 · ${esc(p.name)}</h3>
    ${pas.map(a=>`<label class="chk"><input type="checkbox" value="${a.id}" ${cur.has(a.username)?"checked":""}> ${esc(a.username)}（${esc(a.remark||"")}）</label>`).join("")}
    <div class="empty-hint">仅 project_admin 角色可被分配；保存为全量覆盖</div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:18px">
    <button class="btn" onclick="closeModal()">取消</button>
    <button class="btn pri" onclick="submitBind(${pid})">保存</button></div>`);
}
async function submitBind(pid){
  const ids=[...document.querySelectorAll('#modal input:checked')].map(i=>+i.value);
  try{await api("POST",`/projects/${pid}/admins`,{admin_ids:ids});}
  catch(e){toast("保存失败："+e.message);return;}
  closeModal();toast("已保存");renderProjects();
}

/* ---------- 账号管理 ---------- */
async function renderAcct(){
  pageEl("accounts").innerHTML=`
    <div class="card">
      <div class="toolbar">
        <input id="q" placeholder="搜索用户名 / 备注…" style="width:220px" onkeydown="if(event.key==='Enter')loadUsers()">
        <button class="btn" onclick="loadUsers()">搜索</button>
        <div class="sp"></div>
        <button class="btn pri" onclick="openCreate()">＋ 新建账号</button>
      </div>
      <div id="ulist" class="empty">加载中…</div>
    </div>
    <div class="card" style="margin-top:16px">
      <h3>Web 访问 · 每用户固定加密路径</h3>
      <div id="weblist" class="empty">加载中…</div>
    </div>`;
  await loadUsers();
}
function permSq(u){return ["perm_read","perm_write","perm_delete","perm_rename"].map((k,i)=>
  `<span class="${u&&u[k]?"p-on":"p-off"}">${"RWDM"[i]}</span>`).join("");}
async function loadUsers(){
  try{
    USERS=await api("GET","/users?q="+encodeURIComponent(document.getElementById("q")?document.getElementById("q").value:""));
    const rows=USERS.map(u=>{
      const pct=u.quota_bytes?Math.min(100,u.used_bytes/u.quota_bytes*100):0;
      const cls=pct>=90?"full":pct>=80?"warn":"";
      const expired=u.expires_at&&new Date(u.expires_at)<new Date();
      const exp=u.expires_at?`<span class="num ${expired?"":""}" style="${expired?"color:var(--red)":""}">${u.expires_at.slice(0,10)}</span>`:"长期";
      const status=u.enabled?(expired?'<span class="badge b-gray">⚫ 已过期</span>':'<span class="badge b-green">🟢 启用</span>'):'<span class="badge b-red">🔴 已禁用</span>';
      const lim=[u.rate_up?`↑${(u.rate_up/1024).toFixed(0)}K`:"",u.rate_down?`↓${(u.rate_down/1024).toFixed(0)}K`:"",
                 u.max_sessions?`并发${u.max_sessions}`:""].filter(Boolean).join(" / ");
      return `<tr>
        <td><b>${esc(u.username)}</b><br><span style="color:var(--text-sec);font-size:12px">${esc(u.remark||"")}${lim?` · ${lim}`:""}</span></td>
        <td>${u.project_id?`<span class="badge b-blue">${esc((PROJECTS.find(x=>x.id===u.project_id)||{}).name||("#"+u.project_id))}</span>`:'<span class="badge b-gray">未分配</span>'}</td>
        <td><span class="num" style="font-size:12px">${esc(u.root_dir)}</span></td>
        <td><span class="perm">${permSq(u)}</span></td>
        <td><span class="usage-bar"><i class="${cls}" style="width:${pct}%"></i></span><span class="num">${fmtB(u.used_bytes)}${u.quota_bytes?"/"+fmtB(u.quota_bytes):""}</span></td>
        <td>${exp}</td><td>${status}</td>
        <td style="white-space:nowrap">
          <button class="btn sm" onclick="openEdit(${u.id})">编辑</button>
          <button class="btn sm" onclick="openReset(${u.id},'${esc(u.username)}')">重置密码</button>
          <button class="btn sm ${u.enabled?"danger":""}" onclick="toggleUser(${u.id},${u.enabled})">${u.enabled?"禁用":"启用"}</button>
          <button class="btn sm danger" onclick="delUser(${u.id},'${esc(u.username)}')">删除</button>
        </td></tr>`;
    }).join("");
    document.getElementById("ulist").innerHTML=rows?
      `<table><thead><tr><th>用户名</th><th>项目</th><th>根目录</th><th>权限（R/W/D/M）</th><th>配额使用</th><th>有效期</th><th>状态</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table>`
      :"无匹配账号";
    /* 加密路径卡片 */
    const wrows=USERS.map(u=>{
      const st=u.web_enabled?'<span class="badge b-green">🟢 开启</span>':'<span class="badge b-red">🔴 关闭</span>';
      return `<tr><td><b>${esc(u.username)}</b></td>
        <td><span class="tok" title="点击复制加密路径 URL" onclick="copyTok('${u.web_token}')">/f/${u.web_token}/</span></td>
        <td class="num">${(u.web_token_at||u.created_at||"").replace("T"," ").slice(0,10)}</td>
        <td>${st}</td>
        <td style="white-space:nowrap">
          <button class="btn sm" onclick="copyTok('${u.web_token}')">复制</button>
          <button class="btn sm danger" onclick="regenTok(${u.id})">重新生成</button>
          <button class="btn sm" onclick="toggleWeb(${u.id},${u.web_enabled})">${u.web_enabled?"关闭 Web":"开启 Web"}</button>
        </td></tr>`;
    }).join("");
    document.getElementById("weblist").innerHTML=wrows?
      `<table><thead><tr><th>用户名</th><th>加密路径（HTTPS）</th><th>生成时间</th><th>Web 访问</th><th>操作</th></tr></thead><tbody>${wrows}</tbody></table>`
      :"暂无账号";
  }catch(e){const el=document.getElementById("ulist");if(el)el.textContent="加载失败："+e.message;}
}
function copyTok(t){navigator.clipboard.writeText(location.origin+"/f/"+t+"/");toast("已复制加密路径 URL");}

function permChk(u){return ["perm_read","perm_write","perm_delete","perm_rename"].map(k=>
  `<label class="chk"><input type="checkbox" id="f_${k}" ${u&&u[k]?"checked":""}>${
    {perm_read:"读取",perm_write:"写入",perm_delete:"删除",perm_rename:"改名"}[k]}</label>`).join("");}

async function openCreate(){
  if(!PROJECTS.length&&!isPA()){try{PROJECTS=await api("GET","/projects")}catch(e){PROJECTS=[]}}
  const projOpts=isPA()
    ? MYPROJ.map(n=>{const p=PROJECTS.find(x=>x.name===n);return p?`<option value="${p.id}">${esc(n)}</option>`:""}).join("")
    : `<option value="">（未分配）</option>`+PROJECTS.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join("");
  modal(`<h3>＋ 新建账号</h3>
    <div class="row"><div><label>用户名（小写字母/数字/下划线）</label><input id="f_username" type="text"></div>
    <div><label>初始密码（≥8位，含字母数字）</label><input id="f_password" type="password"></div></div>
    <label>所属项目</label><select id="f_project" style="width:100%;height:38px;border:1px solid var(--line);border-radius:9px;padding:0 12px">${projOpts}</select>
    <label>权限（读/写/删/改）</label><div class="perm" style="gap:14px">${permChk(null)}</div>
    <div class="row"><div><label>空间配额（MB，0=不限）</label><input id="f_quota" type="number" value="10240"></div>
    <div><label>单文件上限（MB，0=不限）</label><input id="f_maxfs" type="number" value="0"></div></div>
    <div class="row"><div><label>上传限速（KB/s，0=不限）</label><input id="f_rup" type="number" value="0"></div>
    <div><label>下载限速（KB/s，0=不限）</label><input id="f_rdn" type="number" value="0"></div>
    <div><label>并发会话数（0=不限）</label><input id="f_msess" type="number" value="0"></div></div>
    <label class="chk"><input type="checkbox" id="f_web" checked>允许 Web 加密路径访问</label>
    <label>备注</label><input id="f_remark" type="text">
    <div class="mfoot"><button class="btn" onclick="closeModal()">取消</button>
    <button class="btn pri" onclick="submitCreate()">创建</button></div>`);
}
async function submitCreate(){
  try{
    await api("POST","/users",{
      username:f_username.value.trim(),password:f_password.value,
      perm_read:f_perm_read.checked,perm_write:f_perm_write.checked,
      perm_delete:f_perm_delete.checked,perm_rename:f_perm_rename.checked,
      quota_bytes:+f_quota.value*1048576,max_file_size:+f_maxfs.value*1048576,
      rate_up:+f_rup.value*1024,rate_down:+f_rdn.value*1024,max_sessions:+f_msess.value,
      web_enabled:f_web.checked,remark:f_remark.value,
      project_id:f_project.value?+f_project.value:null});
    closeModal();toast("账号已创建");loadUsers();
  }catch(e){alert("创建失败："+e.message);}
}
function openEdit(id){
  const u=USERS.find(x=>x.id===id);if(!u)return;
  modal(`<h3>✏️ 编辑账号：${esc(u.username)}</h3>
    <label>权限（读/写/删/改）</label><div class="perm" style="gap:14px">${permChk(u)}</div>
    <div class="row"><div><label>空间配额（MB，0=不限）</label><input id="e_quota" type="number" value="${(u.quota_bytes/1048576).toFixed(0)}"></div>
    <div><label>单文件上限（MB，0=不限）</label><input id="e_maxfs" type="number" value="${(u.max_file_size/1048576).toFixed(0)}"></div></div>
    <div class="row"><div><label>上传限速（KB/s，0=不限）</label><input id="e_rup" type="number" value="${((u.rate_up||0)/1024).toFixed(0)}"></div>
    <div><label>下载限速（KB/s，0=不限）</label><input id="e_rdn" type="number" value="${((u.rate_down||0)/1024).toFixed(0)}"></div>
    <div><label>并发会话数（0=不限）</label><input id="e_msess" type="number" value="${u.max_sessions||0}"></div></div>
    <div class="row"><div><label>有效期至（留空=永久）</label><input id="e_exp" type="date" value="${u.expires_at?u.expires_at.slice(0,10):""}"></div>
    <div><label>备注</label><input id="e_remark" type="text" value="${esc(u.remark)}"></div></div>
    ${!isPA()?`<label>所属项目（平台管理员可调整）</label><select id="e_project" style="width:100%;height:38px;border:1px solid var(--line);border-radius:9px;padding:0 12px">
      <option value="">（未分配）</option>
      ${PROJECTS.map(pp=>`<option value="${pp.id}" ${u.project_id===pp.id?"selected":""}>${esc(pp.name)}</option>`).join("")}</select>`:""}
    <label class="chk"><input type="checkbox" id="e_web" ${u.web_enabled?"checked":""}>允许 Web 加密路径访问</label>
    <div class="mfoot"><button class="btn" onclick="closeModal()">取消</button>
    <button class="btn pri" onclick="submitEdit(${id})">保存</button></div>`);
}
async function submitEdit(id){
  try{
    await api("PATCH","/users/"+id,{
      perm_read:f_perm_read.checked,perm_write:f_perm_write.checked,
      perm_delete:f_perm_delete.checked,perm_rename:f_perm_rename.checked,
      quota_bytes:+e_quota.value*1048576,max_file_size:+e_maxfs.value*1048576,
      rate_up:+e_rup.value*1024,rate_down:+e_rdn.value*1024,max_sessions:+e_msess.value,
      expires_at:e_exp.value||null,remark:e_remark.value,web_enabled:e_web.checked,
      ...(document.getElementById("e_project")?{project_id:e_project.value?+e_project.value:null}:{})});
    closeModal();toast("已保存");loadUsers();
  }catch(e){alert("保存失败："+e.message);}
}
function openReset(id,name){
  modal(`<h3>🔑 重置密码：${esc(name)}</h3>
    <label>新密码（≥8位）</label><input id="r_pw" type="password">
    <div class="mfoot"><button class="btn" onclick="closeModal()">取消</button>
    <button class="btn pri" onclick="submitReset(${id})">确定</button></div>`);
}
async function submitReset(id){
  try{await api("POST",`/users/${id}/reset-password`,{password:r_pw.value});
    closeModal();toast("密码已重置");}catch(e){alert(e.message);}
}
async function regenTok(id){
  if(!confirm("轮换后旧加密路径立即失效，确定？"))return;
  const j=await api("POST",`/users/${id}/regen-web-token`);
  toast("新路径：/f/"+j.web_token+"/");loadUsers();
}
async function toggleWeb(id,on){
  await api("PATCH","/users/"+id,{web_enabled:!on});
  toast(on?"已关闭 Web 访问（SFTP 不受影响）":"已开启 Web 访问");loadUsers();
}
async function toggleUser(id,en){
  await api("POST",`/users/${id}/toggle`,{enabled:!en});
  toast(!en?"已启用":"已禁用");loadUsers();
}
async function delUser(id,name){
  const c=prompt(`确定删除账号 ${name}？\n（软删除：SFTP/Web 立即失效，记录保留）\n\n防误删确认：请输入该用户名继续`);
  if(c===null)return;
  if(c!==name){toast("确认用户名不匹配，已取消");return;}
  try{await api("DELETE","/users/"+id+"?confirm="+encodeURIComponent(name));}
  catch(e){toast("删除失败："+e.message);return;}
  toast("已删除");loadUsers();
}

/* ---------- 会话监控 ---------- */
async function renderSess(){
  let list=[];
  try{list=await api("GET","/sessions");}catch(e){}
  const rows=list.map(s=>`<tr>
    <td><b>${esc(s.username)}</b></td>
    <td class="num">${esc(s.ip||"-")}</td>
    <td class="num">${esc((s.login_at||"").replace("T"," ").slice(0,19))}</td>
    <td style="font-family:Consolas;font-size:12px">${esc(s.sid)}</td>
    <td><button class="btn sm danger" onclick="kick('${esc(s.sid)}')">断开</button></td></tr>`).join("");
  pageEl("sessions").innerHTML=`
    <div class="card">
      <div class="toolbar"><span class="badge b-green">● 实时</span>
        <span style="color:var(--text-sec);font-size:12px">每 5 秒自动刷新</span></div>
      ${rows?`<table><thead><tr><th>用户名</th><th>来源 IP</th><th>登录时间</th><th>会话 ID</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table>`
        :`<div class="empty">当前无在线 SFTP 会话</div>`}
      <div class="empty-hint">强制断开后客户端需重新认证</div>
    </div>`;
}
async function kick(sid){
  if(!confirm("确定强制断开该会话？"))return;
  await api("DELETE","/sessions/"+sid);toast("已断开");renderSess();
}

/* ---------- 审计日志 ---------- */
const ACTION_BADGE={login:"b-blue",logout:"b-gray",upload:"b-blue",download:"b-blue",delete:"b-red",
  mkdir:"b-gray",rename:"b-gray",deny:"b-red",quota_deny:"b-orange",manage:"b-gray",list:"b-gray",symlink:"b-gray"};
async function renderLogs(){
  pageEl("logs").innerHTML=`
    <div class="card">
      <div class="toolbar">
        <input id="lf_u" placeholder="搜索用户…" style="width:160px" value="${esc(LOGQ.username)}">
        <select id="lf_a">
          <option value="">全部动作</option>
          ${["login","logout","upload","download","delete","mkdir","rename","quota_deny","manage"]
            .map(a=>`<option ${LOGQ.action===a?"selected":""} value="${a}">${a}</option>`).join("")}
        </select>
        <button class="btn" onclick="LOGQ.page=1;loadLogs()">查询</button>
        <div class="sp"></div>
        <button class="btn" onclick="exportCsv()">导出 CSV</button>
      </div>
      <div id="lglist" class="empty">加载中…</div>
    </div>`;
  await loadLogs();
}
async function loadLogs(){
  LOGQ.username=document.getElementById("lf_u").value.trim();
  LOGQ.action=document.getElementById("lf_a").value;
  const j=await api("GET",`/logs?page=${LOGQ.page}&size=50&username=${encodeURIComponent(LOGQ.username)}&action=${encodeURIComponent(LOGQ.action)}`);
  const rows=j.items.map(r=>`<tr>
    <td class="num" style="font-size:12px;white-space:nowrap">${esc(r.ts.replace("T"," ").slice(0,19))}</td>
    <td>${esc(r.username)}</td>
    <td><span class="badge ${ACTION_BADGE[r.action]||"b-gray"}">${esc(r.action)}</span></td>
    <td style="max-width:380px;word-break:break-all">${esc(r.detail)}</td>
    <td class="num">${esc(r.client_ip||"-")}</td>
    <td>${r.result==="deny"?'<span class="badge b-red">⛔ 拒绝</span>':'<span class="badge b-green">✅ 成功</span>'}</td></tr>`).join("");
  const pages=Math.max(1,Math.ceil(j.total/50));
  document.getElementById("lglist").innerHTML=rows?
    `<table><thead><tr><th>时间</th><th>用户</th><th>动作</th><th>对象 / 说明</th><th>来源 IP</th><th>结果</th></tr></thead><tbody>${rows}</tbody></table>
     <div class="pager">共 ${j.total} 条
       <button ${LOGQ.page<=1?"disabled":""} onclick="LOGQ.page--;loadLogs()">‹</button>
       <button class="cur">${LOGQ.page} / ${pages}</button>
       <button ${LOGQ.page>=pages?"disabled":""} onclick="LOGQ.page++;loadLogs()">›</button></div>`
    :"无匹配记录";
}
async function exportCsv(){
  /* 服务端导出（上限 10 万行，含 size_bytes 列，导出动作入审计） */
  const p=new URLSearchParams({username:LOGQ.username,action:LOGQ.action,days:"7"});
  const resp=await fetch("/api/v1/logs/export?"+p.toString(),{
    headers:{Authorization:"Bearer "+TOKEN}});
  if(!resp.ok){toast("导出失败："+resp.status);return;}
  const blob=await resp.blob();
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download="audit-logs.csv";a.click();toast("已导出（服务端生成）");
}

/* ---------- 后台账号管理 ---------- */
async function renderGroups(){
  const el=pageEl("groups");
  el.innerHTML=`
    <div class="card">
      <div style="display:flex;gap:10px;margin-bottom:16px">
        <div style="font-size:15px;font-weight:600;align-self:center">🛡️ 后台管理员（仅管理后台）</div>
        <div class="sp" style="flex:1"></div>
        <button class="btn pri" onclick="openAdminCreate()">＋ 新建管理员</button>
      </div>
      ${await groupsAdminTab()}
    </div>`;
}
async function groupsAdminTab(){
  let ADM;
  try{ADM=await api("GET","/admins");}
  catch(e){return `<div class="empty">加载失败：${esc(e.message)}<br><small>仅超级管理员可见此列表</small></div>`;}
  window._lastAdmins=ADM;
  const rows=ADM.map(a=>{
    const st=a.enabled?'<span class="badge b-green">🟢 启用</span>':'<span class="badge b-red">🔴 禁用</span>';
    const role=a.role==="super_admin"?'<span class="badge b-blue">超级管理员</span>':'<span class="badge b-gray">管理员</span>';
    return `<tr><td><b>${esc(a.username)}</b></td><td>${role}</td><td>${st}</td>
      <td class="num">${(a.last_login_at||"-").replace("T"," ").slice(0,16)}</td>
      <td>${esc(a.remark||"")}</td>
      <td style="white-space:nowrap">
        <button class="btn sm" onclick="openAdminEdit(${a.id})">编辑</button>
        <button class="btn sm" onclick="openAdminReset(${a.id},'${esc(a.username)}')">重置密码</button>
        <button class="btn sm danger" onclick="delAdmin(${a.id},'${esc(a.username)}')">删除</button>
      </td></tr>`;}).join("");
  return `<table><thead><tr><th>用户名</th><th>角色</th><th>状态</th><th>最后登录</th><th>备注</th><th>操作</th></tr></thead>
    <tbody>${rows||'<tr><td colspan="6" class="empty">暂无管理员</td></tr>'}</tbody></table>
    <div class="empty-hint">后台管理员仅可登录管理后台（/admin），无法登录 SFTP 传输面与 Web 文件访问；SFTP/Web 账号请在「SFTP账号管理」页维护。管理员增删改仅超级管理员可操作。</div>`;
}
function openAdminCreate(){
  modal(`<h3>新建管理员</h3>
    <label>用户名<input id="na_u" placeholder="小写字母/数字/下划线"></label>
    <label>初始密码<input id="na_p" type="password" placeholder="≥8位，含字母+数字"></label>
    <label>角色<select id="na_r"><option value="admin">管理员（仅后台管理）</option><option value="super_admin">超级管理员（可管理用户组）</option></select></label>
    <label>备注<input id="na_m" placeholder="选填"></label>
    <div style="display:flex;gap:10px;margin-top:16px"><button class="btn pri" onclick="submitAdminCreate()">创建</button><button class="btn" onclick="closeModal()">取消</button></div>`);
}
async function submitAdminCreate(){
  try{await api("POST","/admins",{username:na_u.value,password:na_p.value,role:na_r.value,remark:na_m.value});}
  catch(e){toast("创建失败："+e.message);return;}
  closeModal();toast("管理员已创建");renderGroups();
}
function openAdminEdit(id){
  const a=window._lastAdmins&&window._lastAdmins.find(x=>x.id===id);
  if(!a){toast("数据过期，请刷新");return;}
  modal(`<h3>编辑管理员 · ${esc(a.username)}</h3>
    <label>角色<select id="ea_r">
      <option value="admin" ${a.role!=="super_admin"?"selected":""}>管理员（仅后台管理）</option>
      <option value="super_admin" ${a.role==="super_admin"?"selected":""}>超级管理员</option></select></label>
    <label class="chk"><input type="checkbox" id="ea_e" ${a.enabled?"checked":""}>启用</label>
    <label>备注<input id="ea_m" value="${esc(a.remark||"")}"></label>
    <div style="display:flex;gap:10px;margin-top:16px"><button class="btn pri" onclick="submitAdminEdit(${a.id})">保存</button><button class="btn" onclick="closeModal()">取消</button></div>`);
}
async function submitAdminEdit(id){
  try{await api("PATCH","/admins/"+id,{role:ea_r.value,enabled:ea_e.checked,remark:ea_m.value});}
  catch(e){toast("保存失败："+e.message);return;}
  closeModal();toast("已保存");renderGroups();
}
function openAdminReset(id,name){
  modal(`<h3>重置密码 · ${esc(name)}</h3>
    <label>新密码<input id="rp_p" type="password" placeholder="≥8位，含字母+数字"></label>
    <div style="display:flex;gap:10px;margin-top:16px"><button class="btn pri" onclick="submitAdminReset(${id})">重置</button><button class="btn" onclick="closeModal()">取消</button></div>`);
}
async function submitAdminReset(id){
  try{await api("POST",`/admins/${id}/reset-pass`,{password:rp_p.value});}
  catch(e){toast("重置失败："+e.message);return;}
  closeModal();toast("密码已重置");renderGroups();
}
async function delAdmin(id,name){
  if(!confirm(`确定删除管理员 ${name}？此操作不可恢复。`))return;
  try{await api("DELETE","/admins/"+id);}
  catch(e){toast("删除失败："+e.message);return;}
  toast("已删除");renderGroups();
}

/* ---------- 用户 Web 访问（加密路径总览） ---------- */
async function renderWebfiles(){
  try{USERS=await api("GET","/users");}catch(e){pageEl("webfiles").innerHTML=`<div class="card empty">加载失败：${esc(e.message)}</div>`;return;}
  const first=USERS.find(u=>u.web_enabled&&u.web_token);
  const example=first?`${location.origin}/f/${first.web_token}/`:"（暂无开启 Web 的账号）";
  const wrows=USERS.map(u=>{
    const expired=u.expires_at&&new Date(u.expires_at)<new Date();
    const st=!u.enabled?'<span class="badge b-red">🔴 账号禁用</span>'
      :expired?'<span class="badge b-gray">⚫ 已过期</span>'
      :u.web_enabled?'<span class="badge b-green">🟢 开启</span>':'<span class="badge b-red">🔴 关闭</span>';
    return `<tr><td><b>${esc(u.username)}</b></td>
      <td><span class="tok" title="点击复制" onclick="copyTok('${u.web_token}')">/f/${u.web_token}/</span></td>
      <td class="num">${(u.web_token_at||u.created_at||"").replace("T"," ").slice(0,10)}</td>
      <td>${st}</td>
      <td class="num">${fmtB(u.used_bytes)}${u.quota_bytes?"/"+fmtB(u.quota_bytes):""}</td>
      <td style="white-space:nowrap">
        <button class="btn sm" onclick="copyTok('${u.web_token}')">复制</button>
        <button class="btn sm danger" onclick="regenTok(${u.id})">重新生成</button>
        <button class="btn sm" onclick="toggleWeb(${u.id},${u.web_enabled})">${u.web_enabled?"关闭 Web":"开启 Web"}</button>
      </td></tr>`;
  }).join("");
  pageEl("webfiles").innerHTML=`
    <div class="card" style="margin-bottom:16px">
      <h3>用户视角 · HTTPS 文件访问入口</h3>
      <div class="addr"><span style="color:var(--green);font-size:16px">🔒</span>
        <span class="num" style="font-size:14px">${esc(example)}</span>
        <span class="badge b-blue">每用户固定 · 恒不变</span>
        <div class="sp" style="flex:1"></div>
        ${first?`<button class="btn sm" onclick="copyTok('${first.web_token}')">复制</button>`:""}
      </div>
      <table>
        <tr><td style="width:170px;color:var(--text-sec)">用户登录页</td><td><a href="/web/login" target="_blank" style="color:var(--primary)">/web/login ↗</a>（用户登录后自动跳转本人加密路径）</td></tr>
      </table>
    </div>
    <div class="card">
      <h3>全部用户加密路径</h3>
      ${wrows?`<table><thead><tr><th>用户名</th><th>加密路径</th><th>生成时间</th><th>状态</th><th>配额使用</th><th>操作</th></tr></thead><tbody>${wrows}</tbody></table>`
        :`<div class="empty">暂无账号</div>`}
    </div>`;
}

/* ---------- 系统设置 ---------- */
async function renderSettings(){
  try{
    const d=await api("GET","/dashboard/summary");
    const b=document.getElementById("svcBadge");
    if(b)b.innerHTML="🟢 运行中（在线会话 "+d.sessions_online+"）";
  }catch(e){}
}

/* ---------- 弹窗 ---------- */
function modal(html){document.getElementById("modal").innerHTML=html;
  document.getElementById("mask").classList.add("show");}
function closeModal(){document.getElementById("mask").classList.remove("show");}
document.getElementById("mask").addEventListener("click",e=>{
  if(e.target.id==="mask")closeModal();});

/* ---------- 启动 ---------- */
if(TOKEN){
  api("GET","/dashboard/summary").then(()=>{document.getElementById("wuser").textContent="admin";showApp();})
    .catch(()=>showLogin());
}else showLogin();
</script></body></html>
"""

FILE_ROOT_LABEL = os.path.basename(FILE_ROOT.rstrip("/\\")) or FILE_ROOT
ADMIN_HTML = (_TEMPLATE
              .replace("__SFTP_PORT__", str(SFTP_PORT))
              .replace("__ADMIN_PORT__", str(ADMIN_PORT))
              .replace("__FILE_ROOT__", FILE_ROOT)
              .replace("__FILE_ROOT_LABEL__", FILE_ROOT_LABEL))
