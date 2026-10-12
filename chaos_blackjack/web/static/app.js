"use strict";
const $=id=>document.getElementById(id);
const textNode=(tag,text,cls)=>{const el=document.createElement(tag);el.textContent=text;if(cls)el.className=cls;return el;};
let user=null,csrf='',registering=false,saveRevision=0,pendingSave=null,saving=false,conflicted=false;
let saveKey='',launchVersion=0;
let saveWaiters=[];
let nameState=null,nameCommand='',nameSequence=0,namePending=0,nameComposing=false;
function closeNameInput(){nameState=null;nameCommand='';namePending=0;nameComposing=false;if($('player-name-dialog').open)$('player-name-dialog').close();}
window.chaosNameInput=raw=>{
 const state=JSON.parse(raw);
 if(!state||!user||$('pygame').hidden){closeNameInput();return;}
 const changed=nameState?.id!==state.id;
 nameState=state;
 $('player-name-title').textContent=state.title;$('player-name-error').textContent=state.message;
 if(changed){namePending=0;nameComposing=false;$('player-name-input').value=state.value;$('player-name-input').maxLength=state.maxLength;}
 if(state.ack>=namePending){namePending=0;$('player-name-save').disabled=false;}
 if(!$('player-name-dialog').open){$('player-name-dialog').showModal();$('player-name-title').focus();}
};
function queueNameInput(action){
 if(!nameState)return;
 const seq=++nameSequence;
 nameCommand=JSON.stringify({id:nameState.id,seq,action,value:$('player-name-input').value});
 if(action==='submit'){namePending=seq;$('player-name-save').disabled=true;}
}
window.chaosNameNext=()=>{const command=nameCommand;nameCommand='';return command;};
$('player-name-input').oninput=event=>{if(!event.isComposing)queueNameInput('input');};
$('player-name-input').addEventListener('compositionstart',()=>{nameComposing=true;});
$('player-name-input').addEventListener('compositionend',()=>{nameComposing=false;queueNameInput('input');});
$('player-name-input').onkeydown=event=>{if(event.key==='Enter'&&!event.isComposing&&!nameComposing){event.preventDefault();queueNameInput('submit');}};
$('player-name-form').onsubmit=event=>{event.preventDefault();if(!nameComposing)queueNameInput('submit');};
$('player-name-cancel').onclick=()=>queueNameInput('cancel');
$('player-name-dialog').oncancel=event=>{event.preventDefault();queueNameInput('cancel');};
window.chaosInitialSave='';
async function api(path,data){
 const options={credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(15000)};
 if(data!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-CSRF-Token':csrf};options.body=JSON.stringify(data);}
 const response=await fetch(path,options),result=await response.json();
 if(!response.ok||!result.ok){const err=new Error(result.error?.message||'Request failed.');err.status=response.status;throw err;}
 return result;
}
function setAuthMode(register){registering=register;$('token-field').hidden=!register;$('auth-token').required=register;$('login-tab').classList.toggle('selected',!register);$('register-tab').classList.toggle('selected',register);$('auth-title').textContent=register?'Join the table':'Welcome back';$('auth-password').autocomplete=register?'new-password':'current-password';$('auth-submit').textContent=register?'Create account':'Take your seat';$('auth-error').textContent='';}
$('login-tab').onclick=()=>setAuthMode(false);$('register-tab').onclick=()=>setAuthMode(true);
function stopGame(){closeNameInput();launchVersion++;$('pygame').removeAttribute('src');$('pygame').hidden=true;}
function signedOut(){stopGame();user=null;csrf='';pendingSave=null;$('auth').hidden=false;$('game').hidden=true;$('identity').hidden=true;document.querySelectorAll('dialog[open]').forEach(d=>d.close());}
async function signedIn(result){
 user=result.user;csrf=result.csrf;saveKey='chaos-save:'+user.id;
 $('username').textContent=user.username;$('auth').hidden=true;$('game').hidden=false;$('identity').hidden=false;$('admin-panel').hidden=!user.admin;$('auth-password').value='';$('auth-token').value='';
 const cloud=await api('/api/browser-save');saveRevision=cloud.revision;window.chaosInitialSave=cloud.snapshot;pendingSave=null;conflicted=false;
 try{const local=JSON.parse(localStorage.getItem(saveKey));if(local&&local.snapshot!==cloud.snapshot){if(local.revision===cloud.revision){window.chaosInitialSave=local.snapshot;pendingSave=local.snapshot;}else{localStorage.setItem(saveKey+':conflict:'+Date.now(),JSON.stringify(local));}}}catch(e){}
 $('save-status').textContent='Your save is ready. Click Play to start.';$('launch').hidden=false;$('launch').disabled=false;
}
$('auth-form').onsubmit=async event=>{event.preventDefault();$('auth-error').textContent='';$('auth-submit').disabled=true;try{await signedIn(await api(registering?'/api/register':'/api/login',{username:$('auth-username').value,password:$('auth-password').value,token:$('auth-token').value}));}catch(e){signedOut();$('auth-error').textContent=e.message;}finally{$('auth-submit').disabled=false;}};
window.chaosSave=snapshot=>{
 if(!user||conflicted)return;
 pendingSave=snapshot;
 try{localStorage.setItem(saveKey,JSON.stringify({revision:saveRevision,snapshot}));}catch(e){$('game-error').textContent='Local backup unavailable. Keep this tab open until the save syncs.';}
 $('save-status').textContent='Saving…';
};
async function flushSave(){
 if(saving){await new Promise(resolve=>saveWaiters.push(resolve));return flushSave();}
 if(pendingSave===null||!user||conflicted)return;
 saving=true;const snapshot=pendingSave,uid=user.id,version=launchVersion;
 try{
  const reply=await api('/api/browser-save',{revision:saveRevision,snapshot});
  if(!user||user.id!==uid||version!==launchVersion)return;
  saveRevision=reply.revision;window.chaosInitialSave=snapshot;
  if(pendingSave===snapshot)pendingSave=null;
  try{localStorage.setItem(saveKey,JSON.stringify({revision:saveRevision,snapshot:pendingSave??snapshot}));}catch(e){}
  $('save-status').textContent=pendingSave===null?'Saved to your account':'Saving…';
 }catch(e){
  if(e.status===409){conflicted=true;try{localStorage.setItem(saveKey+':conflict:'+Date.now(),localStorage.getItem(saveKey));}catch(error){}stopGame();$('game-error').textContent='Your save changed in another tab. Reload this page to continue with the latest save. This tab’s backup remains on this device.';}
  else if(e.status===401){stopGame();$('game-error').textContent='Your session expired. Reload and sign in again. Your local backup is retained.';conflicted=true;}
  else $('save-status').textContent='Sync unavailable. A local backup is retained; retrying…';
 }finally{saving=false;saveWaiters.splice(0).forEach(resolve=>resolve());}
}
setInterval(flushSave,1000);
window.chaosClosed=()=>{closeNameInput();flushSave();$('launch').textContent='Play again';$('launch').hidden=false;};
window.chaosLoading=info=>{
 if(!user||$('pygame').hidden)return;
 if(info.stage==='running'){if(pendingSave===null&&!saving)$('save-status').textContent='Game ready. Saves sync to your account.';}
 else if(info.stage==='ready')$('save-status').textContent='Download complete. Tap Start game to continue.';
 else if(info.stage==='starting')$('save-status').textContent='Starting game…';
 else $('save-status').textContent=`Loading game files… ${info.elapsed}s elapsed. First load can take a few minutes on a slow connection.`;
};
window.chaosFailed=()=>{closeNameInput();$('save-status').textContent='Game startup failed.';$('game-error').textContent='The game could not load or continue. Check your connection and retry, or reload your latest account save.';$('launch').textContent='Retry';$('launch').hidden=false;};
$('launch').onclick=async()=>{try{await flushSave();if(conflicted)return;closeNameInput();$('game-error').textContent='';$('pygame').src='/play/?v='+Date.now();$('pygame').hidden=false;$('launch').hidden=true;$('save-status').textContent='Loading game files. First load can take a few minutes on a slow connection.';}catch(e){$('game-error').textContent=e.message;}};
$('fullscreen').onclick=()=>$('game-container').requestFullscreen().catch(e=>{$('game-error').textContent=e.message;});
$('logout').onclick=async()=>{try{await flushSave();await api('/api/logout',{});signedOut();}catch(e){$('game-error').textContent=e.message;}};
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
async function accounts(){const result=await api('/api/admin/accounts');$('accounts').replaceChildren();for(const account of result.accounts){const row=textNode('div','','account-row');row.append(textNode('span',`${account.username}${account.admin?' · Admin':''}${account.enabled?'':' · Disabled'}`));if(!account.admin){const button=textNode('button',account.enabled?'Disable':'Enable','outline');button.onclick=async()=>{try{await api('/api/admin/account',{id:account.id,enabled:!account.enabled});await accounts();}catch(e){$('account-error').textContent=e.message;}};row.append(button);}$('accounts').append(row);}}
$('account-open').onclick=async()=>{$('account-error').textContent='';$('account-dialog').showModal();try{if(user.admin)await accounts();}catch(e){$('account-error').textContent=e.message;}};
$('password-form').onsubmit=async e=>{e.preventDefault();try{await flushSave();await api('/api/password',{current_password:$('current-password').value,password:$('new-password').value});e.target.reset();signedOut();$('auth-error').textContent='Password changed. Sign in again.';}catch(err){$('account-error').textContent=err.message;}};
$('rotate-token').onclick=async()=>{if(!confirm('Replace the invitation token? The previous token will stop working.'))return;try{const result=await api('/api/admin/invitation',{});$('invitation-output').textContent=`New invitation: ${result.token}`;}catch(e){$('account-error').textContent=e.message;}};
$('auth-submit').disabled=true;
api('/api/me').then(signedIn).catch(e=>{signedOut();if(e.status!==401)$('auth-error').textContent=e.message;}).finally(()=>{$('auth-submit').disabled=false;});
