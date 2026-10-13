"use strict";
const $=id=>document.getElementById(id);
const qsa=s=>Array.from(document.querySelectorAll(s));

// EN: Page navigation. RU: Навигация по разделам.
qsa("#nav button").forEach(b=>b.onclick=()=>{
  qsa("#nav button").forEach(x=>x.classList.toggle("active",x===b));
  qsa("[data-view]").forEach(x=>x.hidden=x.dataset.view!==b.dataset.page);
  $("nav").classList.remove("open");
  history.replaceState(null,"","#"+b.dataset.page);
  if(b.dataset.page==="video") loadVideo();
});
$("menuBtn").onclick=()=>$("nav").classList.toggle("open");

// EN: Live view controls. RU: Управление live-просмотром.
$("fullscreen").onclick=()=>{const el=$("frame"); if(document.fullscreenElement) document.exitFullscreen(); else el.requestFullscreen?.();};
$("snapshot").onclick=()=>{
  const v=$("fmp4-video"); if(!v.videoWidth)return;
  const c=document.createElement("canvas"); c.width=v.videoWidth;c.height=v.videoHeight;
  c.getContext("2d").drawImage(v,0,0,c.width,c.height);
  const a=document.createElement("a");a.href=c.toDataURL("image/jpeg",.92);a.download="myipcam.jpg";a.click();
};
setTimeout(()=>{ if($("fmp4-ch0")) $("fmp4-ch0").click(); },250);

const host=location.hostname;
$("rtspUrl").textContent=`rtsp://${host}:554/ch0`;

// EN: PTZ jog commands. RU: Команды пошагового PTZ.
const DIR={u:[0,1],d:[0,-1],l:[-1,0],r:[1,0],ul:[-1,1],ur:[1,1],dl:[-1,-1],dr:[1,-1]};
let ptzTimer=null;
function ptzFetch(q){return fetch("/x/json-motor.cgi?"+q,{cache:"no-store",credentials:"same-origin"}).catch(()=>null)}
function ptzStop(){if(ptzTimer){clearInterval(ptzTimer);ptzTimer=null}ptzFetch("d=s")}
function ptzJog(dir){const d=DIR[dir];if(!d)return;const n=Number($("ptzSpeed").value)||50;ptzFetch(`d=g&x=${n*d[0]}&y=${n*d[1]}`)}
qsa("#ptzPad button").forEach(b=>{
  const dir=b.dataset.dir;
  b.addEventListener("pointerdown",e=>{e.preventDefault();b.setPointerCapture?.(e.pointerId);if(dir==="s"){ptzStop();return}ptzJog(dir);ptzTimer=setInterval(()=>ptzJog(dir),110)});
  const release=()=>{b.classList.remove("active");if(dir!=="s")ptzStop()};
  b.addEventListener("pointerup",release);
  b.addEventListener("pointercancel",release);
  b.addEventListener("lostpointercapture",release);
  b.addEventListener("contextmenu",e=>e.preventDefault());
});
$("ptzHome").onclick=()=>ptzFetch("d=r");
$("ptzStop").onclick=ptzStop;
$("ptzSpeed").oninput=()=>$("ptzSpeedOut").textContent=$("ptzSpeed").value;

// EN: Prudynt configuration proxy. RU: Прокси настройки Prudynt.
const API_BASE="/x/json-prudynt-proxy.cgi?upstream_path=/api/v1/config";
const keyPromise=fetch("/x/api-key.cgi",{cache:"no-store",credentials:"same-origin"}).then(r=>r.ok?r.json():{}).then(j=>j.exists&&j.api_key?j.api_key:"").catch(()=>"");
async function apiFetch(url,opt={}){const key=await keyPromise;opt.credentials="same-origin";opt.headers=Object.assign({},opt.headers||{},key?{"X-API-Key":key}:{});return fetch(url,opt)}
async function getStream0(){const r=await apiFetch(API_BASE+"/stream0",{cache:"no-store"});if(!r.ok)throw Error("HTTP "+r.status);return r.json()}
async function postConfig(payload){const r=await apiFetch(API_BASE,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),cache:"no-store"});let j={};try{j=await r.json()}catch{}if(!r.ok)throw Error(j.error||"HTTP "+r.status);return j}

const fields={width:"vWidth",height:"vHeight",fps:"vFps",bitrate:"vBitrate",gop:"vGop",mode:"vMode",format:"vFormat",profile:"vProfile"};
let current={};
async function loadVideo(){
  const msg=$("videoMsg");msg.textContent="чтение…";
  try{
    current=await getStream0();
    for(const [k,id] of Object.entries(fields)){if(current[k]!==undefined&&$(id))$(id).value=current[k]}
    msg.textContent=`${current.width||"?"}×${current.height||"?"} @ ${current.fps||"?"} fps · ${current.bitrate||"?"} кбит/с`;
  }catch(e){msg.textContent="ошибка: "+e.message}
}
function readVideo(){
  const out={};
  for(const [k,id] of Object.entries(fields)){
    const el=$(id);if(!el||el.value==="")continue;
    out[k]=["width","height","fps","bitrate","gop"].includes(k)?Number(el.value):el.value;
  }
  return out;
}
async function applyVideo(save){
  const msg=$("videoMsg");msg.textContent="применение…";
  try{
    const stream0=readVideo();
    await postConfig({stream0,action:{restart_thread:0}});
    if(save)await postConfig({action:{save_config:null}});
    msg.textContent=save?"применено и сохранено":"применено";
    setTimeout(loadVideo,900);
  }catch(e){msg.textContent="ошибка: "+e.message}
}
$("videoReload").onclick=loadVideo;
$("videoApply").onclick=()=>applyVideo(false);
$("videoSave").onclick=()=>applyVideo(true);

const PRESETS={
 balanced:{width:1920,height:1080,fps:15,bitrate:2000,gop:15,mode:"VBR",format:"H264"},
 ai:{width:1920,height:1080,fps:15,bitrate:2200,gop:15,mode:"CBR",format:"H264"},
 lowlat:{width:1920,height:1080,fps:20,bitrate:2800,gop:10,mode:"CBR",format:"H264"},
 quality:{width:1920,height:1080,fps:25,bitrate:4000,gop:25,mode:"VBR",format:"H264"},
 economy:{width:1280,height:720,fps:12,bitrate:900,gop:12,mode:"VBR",format:"H264"}
};
$("profileFill").onclick=()=>{
  const p=PRESETS[$("profile").value];if(!p)return;
  qsa('#nav button').find(b=>b.dataset.page==='video')?.click();
  for(const [k,v] of Object.entries(p)){const id=fields[k];if(id&&$(id))$(id).value=v}
  $("videoMsg").textContent="значения профиля подставлены — проверь и нажми Применить";
};

loadVideo();
