"""Loopback-only management API + page: start pairing (QR), approve/deny, list/revoke devices."""
from __future__ import annotations

import segno
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..errors import MConnError
from ..pairing.service import PairingService

PAGE = """<!doctype html><meta charset=utf-8><title>MConn admin</title>
<style>body{font:16px system-ui;max-width:640px;margin:2rem auto;padding:0 1rem}
button{padding:.4rem .8rem;margin:.2rem}.card{border:1px solid #8884;border-radius:8px;padding:1rem;margin:1rem 0}
svg{max-width:280px;background:#fff;padding:8px}</style>
<h1>MConn</h1>
<div class=card><button id=pair>Pair new phone</button><div id=qr></div>
<label for=payload>Pairing payload (temporary manual pairing)</label>
<textarea id=payload readonly rows=5 style="width:100%;box-sizing:border-box"></textarea>
<button id=copy type=button>Copy pairing payload</button><div id=pending></div></div>
<div class=card><h3>Paired phones</h3><div id=devices></div></div>
<script>
const H={'X-MConn-Admin':'1','Content-Type':'application/json'};
const api=(m,p)=>fetch('/admin/api'+p,{method:m,headers:H}).then(r=>r.json());
const esc=s=>String(s).replace(/[&<>"']/g,c=>'&#'+c.charCodeAt(0)+';');
document.getElementById('pair').onclick=async()=>{
  const r=await api('POST','/pairing');
  document.getElementById('qr').innerHTML=r.svg+'<p>Scan with MConn or copy the payload. Expires in 5 minutes.</p>';
  document.getElementById('payload').value=r.payload;};
document.getElementById('copy').onclick=async()=>{
  const p=document.getElementById('payload'); if(!p.value)return;
  try{await navigator.clipboard.writeText(p.value)}catch(_){p.select();document.execCommand('copy')}};
async function refresh(){
  const p=await api('GET','/pairing/pending');
  document.getElementById('pending').innerHTML=p.map(x=>'<p><b>'+esc(x.device_name)+'</b> wants to pair '+
   '<button onclick="act(\\''+x.session_id+'\\',\\'approve\\')">Approve</button>'+
   '<button onclick="act(\\''+x.session_id+'\\',\\'deny\\')">Deny</button></p>').join('');
  const d=await api('GET','/devices');
  document.getElementById('devices').innerHTML=d.map(x=>'<p>'+esc(x.name)+' ('+x.status+') '+
   (x.status=='ACTIVE'?'<button onclick="rev(\\''+x.device_id+'\\')">Revoke</button>':'')+'</p>').join('')||'None yet';}
async function act(id,a){await api('POST','/pairing/'+id+'/'+a);refresh();}
async function rev(id){if(confirm('Revoke this phone?')){await api('POST','/devices/'+id+'/revoke');refresh();}}
refresh();setInterval(refresh,1500);
</script>"""


def build_admin_router(pairing: PairingService, allowed_hosts: set[str]) -> APIRouter:
    def guard(request: Request) -> None:
        host = request.client.host if request.client else ""
        if host not in allowed_hosts:
            raise MConnError(403, "FORBIDDEN", "Admin is available from this PC only")
        # A custom header forces a CORS preflight, which we never grant: blocks cross-site (CSRF) calls.
        if request.url.path.startswith("/admin/api") and request.headers.get("x-mconn-admin") != "1":
            raise MConnError(403, "FORBIDDEN", "Missing admin header")

    r = APIRouter(dependencies=[Depends(guard)])

    @r.get("/admin", response_class=HTMLResponse)
    def page() -> str:
        return PAGE

    @r.post("/admin/api/pairing")
    def start() -> dict:
        s = pairing.create_session()
        svg = segno.make(s["payload"], error="m").svg_inline(scale=5, border=2)
        return {"session_id": s["session_id"], "expires_at": s["expires_at"], "payload": s["payload"], "svg": svg}

    @r.get("/admin/api/pairing/pending")
    def pending() -> list[dict]:
        return pairing.pending()

    @r.post("/admin/api/pairing/{session_id}/approve")
    def approve(session_id: str) -> dict:
        return {"device_id": pairing.approve(session_id)}

    @r.post("/admin/api/pairing/{session_id}/deny")
    def deny(session_id: str) -> dict:
        pairing.deny(session_id)
        return {"ok": True}

    @r.get("/admin/api/devices")
    def devices() -> list[dict]:
        return pairing.list_devices()

    @r.post("/admin/api/devices/{device_id}/revoke")
    def revoke(device_id: str) -> dict:
        pairing.revoke(device_id)
        return {"ok": True}

    return r
