"use strict";

const gate = document.getElementById("loginGate");
const appRoot = document.getElementById("appRoot");
const form = document.getElementById("loginForm");
const password = document.getElementById("loginPassword");
const submit = document.getElementById("loginSubmit");
const msg = document.getElementById("loginMsg");

async function sessionStatus(){
  try{
    const r=await fetch("/x/session-status.cgi",{cache:"no-store",credentials:"same-origin"});
    return r.ok?await r.json():{authenticated:false};
  }catch(_){return {authenticated:false};}
}

async function loginRoot(pass){
  const r=await fetch("/x/login.cgi",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({username:"root",password:pass}),
    cache:"no-store",
    credentials:"same-origin"
  });
  let data={};
  try{data=await r.json();}catch(_){}
  if(!r.ok || !data.success) throw new Error(data?.error?.message||("HTTP "+r.status));
  return data;
}

function loadScript(src){
  return new Promise((resolve,reject)=>{
    const s=document.createElement("script");
    s.src=src+"?v=stage2";
    s.onload=resolve;
    s.onerror=()=>reject(new Error("Не загрузился "+src));
    document.body.appendChild(s);
  });
}

async function startApp(){
  gate.hidden=true;
  appRoot.hidden=false;
  const status=document.getElementById("status");
  if(status) status.textContent="сессия активна";
  await loadScript("/a/preview-fmp4.js");
  await loadScript("/myipcam/app.js");
  const logout=document.getElementById("logoutBtn");
  if(logout) logout.onclick=async()=>{
    try{await fetch("/x/logout.cgi",{cache:"no-store",credentials:"same-origin"});}catch(_){}
    location.reload();
  };
}

async function init(){
  const st=await sessionStatus();
  if(st.authenticated){
    try{await startApp();}catch(e){msg.textContent=e.message;gate.hidden=false;appRoot.hidden=true;}
    return;
  }
  gate.hidden=false;
  appRoot.hidden=true;
  password.focus();
}

form.addEventListener("submit",async e=>{
  e.preventDefault();
  submit.disabled=true;
  msg.textContent="вход…";
  try{
    const result=await loginRoot(password.value);
    msg.textContent=result.is_default_password?"Вход выполнен. Рекомендуется сменить пароль root.":"";
    await startApp();
  }catch(e){
    msg.textContent="Ошибка входа: "+e.message;
    password.select();
  }finally{submit.disabled=false;}
});

init();
