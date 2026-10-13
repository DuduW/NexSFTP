"""用户侧 HTTPS Web 文件访问（加密目录路径 /f/{token}/）"""
import os
from datetime import datetime, date

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from .. import security, state
from ..audit import audit
from ..config import load_secret
from ..db import SessionLocal
from ..models import SftpUser
from ..vfs import PathEscape, resolve

router = APIRouter()

WEB_COOKIE = "websess"


def _auth_user(request: Request, token: str) -> SftpUser:
    """三重校验（不泄露存在性）：
    1. token 必须命中某账号的当前加密路径，否则 404（含已轮换/禁用场景）
    2. 必须已登录 Web 会话，否则 404（避免向未认证者泄露 token 有效性）
    3. 会话用户必须等于 token 属主，否则 404（拿他人 token 同样 404）
    """
    username = security.web_get(request.cookies.get(WEB_COOKIE, ""))
    with SessionLocal() as s:
        u = s.query(SftpUser).filter_by(web_token=token, deleted_at=None).first()
        if not u or not u.enabled or not u.web_enabled:
            raise HTTPException(404, "Not Found")
        if not username or username != u.username:
            raise HTTPException(404, "Not Found")
        s.expunge(u)
        return u


def _check(u: SftpUser, need: str):
    if need == "read" and not u.perm_read:
        raise HTTPException(403, "无读取权限")
    if need == "write" and not u.perm_write:
        raise HTTPException(403, "无写入权限")
    if need == "delete" and not u.perm_delete:
        raise HTTPException(403, "无删除权限")
    if need == "rename" and not u.perm_rename:
        raise HTTPException(403, "无改名权限")


@router.get("/web/login")
def web_login_page():
    """浏览器登录页（人工测试用）：登录成功后跳转到本人加密路径"""
    return HTMLResponse(
        """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>SFTP Web 登录</title><style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#f5f5f7;font-family:"Noto Sans SC","Microsoft YaHei",sans-serif}
.card{background:#fff;border-radius:16px;padding:40px 36px;width:320px;
box-shadow:0 8px 30px rgba(11,61,98,.12)}
h1{margin:0 0 6px;font-size:20px;color:#0b3d62;font-family:"Noto Serif SC",serif}
p{margin:0 0 22px;font-size:12px;color:#889}
input{width:100%;box-sizing:border-box;padding:11px 12px;margin-bottom:12px;
border:1px solid #d8dde3;border-radius:10px;font-size:14px;outline:none}
input:focus{border-color:#0b3d62}
button{width:100%;padding:12px;border:0;border-radius:10px;background:#0b3d62;
color:#fff;font-size:15px;cursor:pointer}
button:disabled{opacity:.6}
#msg{margin-top:14px;font-size:13px;color:#c0392b;min-height:18px}
</style></head><body><div class="card">
<h1>文件访问登录</h1><p>登录后进入你的加密目录路径</p>
<input id="u" placeholder="用户名" autofocus>
<input id="p" type="password" placeholder="密码" onkeydown="if(event.key==='Enter')doLogin()">
<button id="b" onclick="doLogin()">登 录</button>
<div id="msg"></div></div>
<script>
async function doLogin(){
  const b=document.getElementById('b'),m=document.getElementById('msg');
  b.disabled=true;m.textContent='';m.style.color='#c0392b';
  try{
    const r=await fetch('/web/login',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:u.value.trim(),password:p.value})});
    if(!r.ok){const t=await r.text();m.textContent=t.replace(/<[^>]+>/g,'').slice(0,80)||('HTTP '+r.status);return;}
    const h=await r.text();
    const tok=(h.match(/\\/f\\/([A-Za-z0-9]+)\\//)||[])[1];
    if(tok){location.href='/f/'+tok+'/';}else{m.textContent='登录成功但未获取到路径';}
  }catch(e){m.textContent='网络错误：'+e;}
  finally{b.disabled=false;}
}
</script></body></html>""")


@router.post("/web/login")
def web_login(body: dict, request: Request):
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    ip = request.client.host if request.client else ""
    if state.is_locked(username):
        audit("web", username, "login", "账号锁定中", ip, result="deny")
        raise HTTPException(423, "账号已锁定，请稍后再试")
    with SessionLocal() as s:
        u = s.query(SftpUser).filter_by(username=username, deleted_at=None).first()
        expired = bool(u and u.expires_at and
                       (u.expires_at if isinstance(u.expires_at, datetime) else
                        datetime.strptime(str(u.expires_at), "%Y-%m-%d %H:%M:%S")) <= datetime.now())
        from ..sftp_server import project_disabled
        proj_off = bool(u and project_disabled(u.project_id))
        if not (u and u.enabled and u.web_enabled and not expired and not proj_off
                and security.verify_password(password, u.password_hash)):
            state.record_fail(username)
            audit("web", username, "login", "认证失败（统一提示，不区分原因）", ip, result="deny")
            raise HTTPException(401, "认证失败")
        state.clear_fails(username)
        token = security.make_admin_token()
        security.web_login(token, username)
        audit("web", username, "login", "Web 登录成功", ip)
        resp = HTMLResponse(f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="2;url=/f/{u.web_token}/">
<title>登录成功</title><style>
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#f5f5f7;font-family:"Noto Sans SC","Microsoft YaHei",sans-serif}}
.card{{background:#fff;border-radius:16px;padding:40px 36px;width:380px;text-align:center;
box-shadow:0 8px 30px rgba(11,61,98,.12)}}
.ok{{width:52px;height:52px;border-radius:50%;background:#e6f4ea;color:#34a853;font-size:28px;
line-height:52px;margin:0 auto 14px}}
h3{{margin:0 0 8px;font-size:19px;color:#0b3d62;font-family:"Noto Serif SC",serif}}
p{{margin:0 0 18px;font-size:13px;color:#6e6e73}}
code{{display:block;background:#f5f5f7;border-radius:8px;padding:9px 12px;font-size:12px;
color:#0b3d62;margin-bottom:18px;word-break:break-all}}
a{{display:block;padding:11px;border-radius:10px;background:#0b3d62;color:#fff;
text-decoration:none;font-size:14px}}
small{{display:block;margin-top:12px;font-size:11px;color:#9aa}}
</style></head><body><div class="card">
<div class="ok">✓</div>
<h3>登录成功</h3><p>正在进入你的加密目录…</p>
<code>/f/{u.web_token}/</code>
<a href="/f/{u.web_token}/">立即进入文件列表</a>
<small>2 秒后自动跳转</small>
</div></body></html>""")
        resp.set_cookie(WEB_COOKIE, token, httponly=True, samesite="lax")
        return resp


@router.get("/f/{token}/")
def web_index(token: str, request: Request, path: str = "/"):
    """HTML 列表页；path 查询参数支持子目录导航（含中文，URL 编码由客户端处理）"""
    u = _auth_user(request, token)
    _check(u, "read")
    try:
        real, rel = resolve(u.root_dir, path)
    except PathEscape:
        raise HTTPException(403, "路径越界")
    if not os.path.isdir(real):
        raise HTTPException(404, "目录不存在")
    return _list_html(u, token, "/" + rel if rel else "/")


_PAGE_CSS = """
:root{--bg:#f5f5f7;--card:#fff;--primary:#0b3d62;--primary-light:#e8f0f7;--text:#1d1d1f;
--text-sec:#6e6e73;--line:#e8e8ed;--green:#34a853;--red:#e5484d;--radius:16px}
*{margin:0;padding:0;box-sizing:border-box;font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif}
body{background:var(--bg);color:var(--text);font-size:14px}
.wrap{max-width:960px;margin:0 auto;padding:32px 20px}
h1{font-family:'Noto Serif SC',serif;font-size:22px;color:var(--primary);margin-bottom:4px}
.sub{color:var(--text-sec);font-size:12px;margin-bottom:22px}
.card{background:var(--card);border-radius:var(--radius);padding:22px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.crumbs{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:12px 16px;background:var(--bg);
border:1px solid var(--line);border-radius:12px;margin-bottom:14px;font-size:13px}
.crumb{color:var(--primary);text-decoration:none}
.crumb:hover{text-decoration:underline}
.crumb.cur{color:var(--text);font-weight:600}
.sep{color:var(--text-sec)}
.up{margin-left:auto;color:var(--primary);text-decoration:none;font-size:13px;
padding:5px 12px;border-radius:8px;background:var(--primary-light);white-space:nowrap}
.bar{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.bar .sp{flex:1}
.count{color:var(--text-sec);font-size:12px}
.btn{height:34px;padding:0 16px;border-radius:9px;border:1px solid var(--line);background:#fff;
cursor:pointer;font-size:13px;color:var(--text)}
.btn:hover{border-color:var(--primary);color:var(--primary)}
.btn.pri{background:var(--primary);color:#fff;border-color:var(--primary)}
.btn.pri:hover{background:#0e4a75}
table{width:100%;border-collapse:collapse}
th{font-size:12px;color:var(--text-sec);font-weight:500;text-align:left;padding:10px 12px;
border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:12px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#fafafc}
.fname{color:var(--text);text-decoration:none;font-size:14px}
a.fname:hover{color:var(--primary)}
.num{font-family:'Noto Serif SC',serif;color:var(--text-sec);white-space:nowrap}
.acts{white-space:nowrap}
.act{height:28px;padding:0 12px;margin-right:6px;border-radius:8px;border:1px solid var(--line);
background:#fff;cursor:pointer;font-size:12px;color:var(--primary)}
.act:hover{border-color:var(--primary)}
.act.danger{color:var(--red)}
.act.danger:hover{border-color:var(--red)}
.empty{text-align:center;color:var(--text-sec);padding:44px 0;font-size:13px}
.foot{display:flex;justify-content:space-between;align-items:center;margin-top:16px;
color:var(--text-sec);font-size:12px}
.foot a{color:var(--text-sec)}
"""


def _list_html(u: SftpUser, token: str, path: str) -> HTMLResponse:
    """文件列表页（统一 UI：#f5f5f7 + 白卡片 + #0b3d62 主色）"""
    import json as _json
    import time as _time
    from urllib.parse import quote

    try:
        real, rel = resolve(u.root_dir, path)
    except PathEscape:
        raise HTTPException(403, "路径越界")
    parts = [p for p in rel.split("/") if p] if rel else []

    # 面包屑导航
    crumbs = [f'<a class="crumb" href="/f/{token}/">🏠 根目录</a>']
    acc = ""
    for i, p in enumerate(parts):
        acc = f"{acc}/{p}"
        if i == len(parts) - 1:
            crumbs.append(f'<span class="sep">/</span><span class="crumb cur">{p}</span>')
        else:
            crumbs.append(f'<span class="sep">/</span>'
                          f'<a class="crumb" href="/f/{token}/?path={quote(acc)}">{p}</a>')
    up = ""
    if parts:
        parent = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
        up = f'<a class="up" href="/f/{token}/?path={quote(parent)}">⬆ 返回上级</a>'

    # 文件行（目录优先，其次按名称）
    rows = []
    total_b = 0
    entries = sorted(os.listdir(real)) if os.path.isdir(real) else []
    for name in sorted(entries, key=lambda n: (not os.path.isdir(os.path.join(real, n)), n.lower())):
        full = os.path.join(real, name)
        rel_path = "/" + (rel + "/" + name if rel else name)
        q = quote(rel_path)
        is_dir = os.path.isdir(full)
        sz = 0 if is_dir else os.path.getsize(full)
        total_b += sz
        size = "—" if is_dir else f"{sz:,} B"
        mtime = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(os.path.getmtime(full)))
        name_json = _json.dumps(name, ensure_ascii=False)
        path_json = _json.dumps(rel_path, ensure_ascii=False)
        if is_dir:
            name_html = f'<a class="fname" href="/f/{token}/?path={q}">📁 {name}</a>'
        else:
            name_html = f'<span class="fname">📄 {name}</span>'
        acts = []
        if not is_dir:
            acts.append(f'<button class="act" onclick="location.href=\'/f/{token}/download?path={q}\'">下载</button>')
        if u.perm_rename:
            acts.append(f'<button class="act" onclick="doRename({path_json},{name_json})">改名</button>')
        if u.perm_delete:
            acts.append(f'<button class="act danger" onclick="doDelete({path_json},{name_json})">删除</button>')
        rows.append(
            f'<tr><td>{name_html}</td><td class="num">{size}</td>'
            f'<td class="num">{mtime}</td>'
            f'<td class="acts">{"".join(acts) or "—"}</td></tr>')

    upload_btn = (
        f'<button class="btn pri" onclick="document.getElementById(\'uf\').click()">⬆ 上传到当前目录</button>'
        f'<input id="uf" type="file" multiple hidden onchange="doUpload(this.files)">'
    ) if u.perm_write else ""
    body = "".join(rows) or \
        '<tr><td colspan="4" class="empty">空目录</td></tr>'
    cur_json = _json.dumps("/" + rel if rel else "/", ensure_ascii=False)
    tok_json = _json.dumps(token)

    return HTMLResponse(f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>我的文件 · {u.username}</title><style>{_PAGE_CSS}</style></head><body><div class="wrap">
<h1>我的文件</h1>
<div class="sub">{u.username} · 加密路径访问 · 与 SFTP 共享权限与配额</div>
<div class="card">
  <div class="crumbs">{''.join(crumbs)}{up}</div>
  <div class="bar">{upload_btn}<div class="sp"></div>
    <span class="count">{len(entries)} 项 · 共 {total_b:,} B</span></div>
  <table><thead><tr><th>名称</th><th>大小</th><th>修改时间</th><th>操作</th></tr></thead>
  <tbody>{body}</tbody></table>
  <div class="foot"><span>配额 {u.used_bytes or 0:,} / {u.quota_bytes or 0:,} B</span>
  <a href="#" onclick="doLogout();return false">退出登录</a></div>
</div></div>
<script>
const TOKEN={tok_json}, CUR={cur_json};
async function doUpload(files){{
  if(!files.length)return;
  const btn=event&&event.target; if(btn)btn.disabled=true;
  try{{
    for(const f of files){{
      const fd=new FormData();fd.append('file',f);
      const r=await fetch('/f/'+TOKEN+'/upload?path='+encodeURIComponent(CUR),{{method:'POST',body:fd}});
      if(!r.ok){{alert('上传失败：'+r.status+' '+(await r.text()).slice(0,60));return;}}
    }}
    location.reload();
  }}catch(e){{alert('网络错误：'+e);}}
}}
async function doDelete(p,name){{
  if(!confirm('确定删除「'+name+'」？此操作不可恢复。'))return;
  const r=await fetch('/f/'+TOKEN+'/delete?path='+encodeURIComponent(p),{{method:'POST'}});
  if(!r.ok){{alert('删除失败：'+(await r.text()).slice(0,80));return;}}
  location.reload();
}}
async function doRename(p,name){{
  const to=prompt('新名称：',name);if(!to||to===name)return;
  const dir=p.slice(0,p.lastIndexOf('/'));
  const r=await fetch('/f/'+TOKEN+'/rename?path='+encodeURIComponent(p)+'&to='+encodeURIComponent(dir+'/'+to),{{method:'POST'}});
  if(!r.ok){{alert('改名失败：'+(await r.text()).slice(0,80));return;}}
  location.reload();
}}
async function doLogout(){{
  await fetch('/web/logout',{{method:'POST'}});
  location.href='/web/login';
}}
</script></body></html>""")


@router.get("/f/{token}/api/list")
def web_list(token: str, request: Request, path: str = "/"):
    u = _auth_user(request, token)
    _check(u, "read")
    try:
        real, rel = resolve(u.root_dir, path)
    except PathEscape:
        audit("web", u.username, "deny", f"路径越界 {path}", "", result="deny")
        raise HTTPException(403, "路径越界")
    if not os.path.isdir(real):
        raise HTTPException(404, "目录不存在")
    items = []
    for name in sorted(os.listdir(real)):
        full = os.path.join(real, name)
        rel_path = "/" + (rel + "/" + name if rel else name)
        st = os.stat(full)
        items.append({"name": name, "path": rel_path,
                      "is_dir": os.path.isdir(full), "size": st.st_size})
    audit("web", u.username, "list", f"目录列表 {rel}")
    return {"path": rel, "items": items}


@router.get("/f/{token}/download")
def web_download(token: str, request: Request, path: str):
    u = _auth_user(request, token)
    _check(u, "read")
    try:
        real, rel = resolve(u.root_dir, path)
    except PathEscape:
        audit("web", u.username, "deny", f"下载越界 {path}", "", result="deny")
        raise HTTPException(403, "路径越界")
    if os.path.isdir(real) or not os.path.exists(real):
        raise HTTPException(404, "文件不存在")
    audit("web", u.username, "download", f"/{rel} ({os.path.getsize(real):,} B)")
    return FileResponse(real, filename=os.path.basename(real))


@router.post("/f/{token}/upload")
async def web_upload(token: str, request: Request, file: UploadFile, path: str = "/"):
    u = _auth_user(request, token)
    _check(u, "write")
    try:
        real, rel = resolve(u.root_dir, path)
    except PathEscape:
        raise HTTPException(403, "路径越界")
    if not os.path.isdir(real):
        # Web 面新建子目录：目标目录不存在时自动级联创建（mkdir -p 语义）
        try:
            os.makedirs(real, exist_ok=True)
            audit("web", u.username, "mkdir", f"/{rel}")
        except OSError:
            raise HTTPException(403, "目标目录创建失败（权限或路径非法）")
    dest = os.path.join(real, os.path.basename(file.filename))
    # 覆盖写账目：旧文件尺寸冲抵，文件数不重复计
    overwrite = os.path.isfile(dest)
    old_size = os.path.getsize(dest) if overwrite else 0
    base_used = (u.used_bytes or 0) - old_size
    # 配额预检（L1）
    if u.max_file_size and file.size and file.size > u.max_file_size:
        raise HTTPException(413, "超过单文件大小限制")
    if u.quota_files and not overwrite and ((u.used_files or 0) + 1) > u.quota_files:
        audit("web", u.username, "quota_deny", f"上传 {file.filename} 超文件数配额", "", result="deny")
        raise HTTPException(507, "超出文件数配额")
    if u.quota_bytes and (base_used + (file.size or 0)) > u.quota_bytes:
        audit("web", u.username, "quota_deny", f"上传 {file.filename} 超配额", "", result="deny")
        raise HTTPException(507, "超出空间配额")
    written = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 512):
            written += len(chunk)
            if u.quota_bytes and (base_used + written) > u.quota_bytes:
                out.close()
                os.remove(dest)
                audit("web", u.username, "quota_deny",
                      f"上传 {file.filename} 传输中超配额，已回滚", "", result="deny")
                raise HTTPException(507, "超出空间配额")
            out.write(chunk)
    with SessionLocal() as s:
        s.query(SftpUser).filter_by(id=u.id).update({
            "used_bytes": base_used + written,
            "used_files": (u.used_files or 0) + (0 if overwrite else 1),
        })
        s.commit()
    vpath = "/" + (f"{rel}/{os.path.basename(file.filename)}" if rel else os.path.basename(file.filename))
    audit("web", u.username, "upload", f"{vpath} ({written:,} B)", size_bytes=written)
    return {"ok": True, "size": written}


@router.post("/f/{token}/delete")
def web_delete(token: str, request: Request, path: str):
    u = _auth_user(request, token)
    _check(u, "delete")
    try:
        real, rel = resolve(u.root_dir, path)
    except PathEscape:
        raise HTTPException(403, "路径越界")
    if real == os.path.realpath(u.root_dir):
        raise HTTPException(403, "不能删除根目录")
    if not os.path.exists(real):
        raise HTTPException(404, "文件或目录不存在")
    is_dir = os.path.isdir(real)
    size = 0 if is_dir else os.path.getsize(real)
    try:
        if is_dir:
            os.rmdir(real)
        else:
            os.remove(real)
    except OSError as e:
        win_notempty = getattr(e, "winerror", None) == 145
        if isinstance(e, FileNotFoundError) or win_notempty:
            raise HTTPException(404 if isinstance(e, FileNotFoundError) else 409,
                                "目录不存在" if isinstance(e, FileNotFoundError) else "目录非空")
        raise HTTPException(500, "删除失败")
    # 同步扣减用量（文件数/字节数），避免账目漂移
    if not is_dir:
        with SessionLocal() as s:
            s.query(SftpUser).filter_by(id=u.id).update({
                "used_bytes": (u.used_bytes or 0) - size,
                "used_files": (u.used_files or 0) - 1,
            })
            s.commit()
    audit("web", u.username, "delete", "/" + rel if rel else "/")
    return {"ok": True}


@router.post("/f/{token}/rename")
def web_rename(token: str, request: Request, path: str, to: str):
    """Web 改名（PRD §3.3 W：列表/下载/上传/删除/改名）"""
    u = _auth_user(request, token)
    _check(u, "rename")
    try:
        real, rel = resolve(u.root_dir, path)
        new_real, new_rel = resolve(u.root_dir, to)
    except PathEscape:
        audit("web", u.username, "deny", f"改名越界 {path} -> {to}", "", result="deny")
        raise HTTPException(403, "路径越界")
    if not rel:
        raise HTTPException(403, "不能重命名根目录")
    if not os.path.exists(real):
        raise HTTPException(404, "文件或目录不存在")
    if os.path.exists(new_real):
        raise HTTPException(409, "目标名称已存在")
    os.rename(real, new_real)
    audit("web", u.username, "rename", f"/{rel} -> /{new_rel}")
    return {"ok": True, "path": "/" + new_rel}


@router.post("/web/logout")
def web_logout(request: Request):
    security.web_logout(request.cookies.get(WEB_COOKIE, ""))
    resp = HTMLResponse("已退出")
    resp.delete_cookie(WEB_COOKIE)
    return resp
