'use strict';
const $ = id => document.getElementById(id);
let user = null, csrf = '', revision = 0, obs = null, registering = false, busy = false;
const names = {hit:'Hit',stand:'Stand',double:'Double',surrender:'Surrender'};
const friendly = value => value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
function textNode(tag, text, cls) {const el=document.createElement(tag);el.textContent=text;if(cls)el.className=cls;return el;}
async function api(path, data) {
  const options={credentials:'same-origin',cache:'no-store'};
  if(data !== undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-CSRF-Token':csrf};options.body=JSON.stringify(data);}
  const response=await fetch(path,options);
  const result=await response.json();
  if(!response.ok || !result.ok){const err=new Error(result.error?.message || 'Request failed.');err.status=response.status;throw err;}
  return result;
}
function setAuthMode(register){registering=register;$('token-field').hidden=!register;$('auth-token').required=register;$('login-tab').classList.toggle('selected',!register);$('register-tab').classList.toggle('selected',register);$('auth-title').textContent=register?'Join the table':'Welcome back';$('auth-password').autocomplete=register?'new-password':'current-password';$('auth-submit').textContent=register?'Create account':'Take your seat';$('auth-error').textContent='';}
$('login-tab').onclick=()=>setAuthMode(false);$('register-tab').onclick=()=>setAuthMode(true);
function signedOut(){user=null;csrf='';obs=null;revision=0;$('auth').hidden=false;$('game').hidden=true;$('identity').hidden=true;document.querySelectorAll('dialog[open]').forEach(d=>d.close());}
async function signedIn(result){user=result.user;csrf=result.csrf;$('username').textContent=user.username;$('auth').hidden=true;$('game').hidden=false;$('identity').hidden=false;$('admin-panel').hidden=!user.admin;$('auth-password').value='';$('auth-token').value='';await loadGame();}
$('auth-form').onsubmit=async event=>{event.preventDefault();$('auth-error').textContent='';$('auth-submit').disabled=true;try{await signedIn(await api(registering?'/api/register':'/api/login',{username:$('auth-username').value,password:$('auth-password').value,token:$('auth-token').value}));}catch(e){$('auth-error').textContent=e.message;}finally{$('auth-submit').disabled=false;}};
$('logout').onclick=async()=>{try{await api('/api/logout',{});signedOut();}catch(e){$('game-error').textContent=e.message;}};
function cards(target, values){target.replaceChildren();for(const value of values||[]){const card=textNode('div',value==='??'?'♠':value.slice(0,-1),'card');if(value==='??')card.classList.add('back');else{const suit=value.slice(-1);card.append(textNode('span',suit));if('♥♦'.includes(suit))card.classList.add('red');}target.append(card);}}
function update(reply){obs=reply.obs;revision=reply.revision;$('game-error').textContent='';
  if(!obs){$('new-dialog').showModal();return;}
  $('mode-label').textContent=obs.chaos.enabled?'CHAOS TABLE · EXPECT THE UNEXPECTED':'CLASSIC TABLE · PLAY YOUR HAND';
  $('bankroll').textContent=obs.bankroll;$('target').textContent=obs.target;$('round').textContent=obs.round;$('bet-value').textContent=obs.bet??'—';$('progress').max=obs.target;$('progress').value=obs.bankroll;
  const settled=obs.last_round;
  cards($('you-cards'),obs.you?.cards||settled?.your_cards);cards($('dealer-cards'),obs.dealer?.cards||settled?.dealer_cards);
  $('you-total').textContent=obs.you?.total??settled?.player_total??'—';$('dealer-total').textContent=obs.dealer?.total??settled?.dealer_total??'—';
  $('result').textContent=obs.run_end?.message||(settled?`${friendly(settled.outcome)} · ${settled.delta>=0?'+':''}${settled.delta} chips. Place your next bet.`:obs.phase==='betting'?'The deck is ready. Place your bet.':'Your move. Check the house rules before you draw.');
  $('betting').hidden=obs.phase!=='betting';if(obs.bet_range){const [min,max]=obs.bet_range;$('bet-amount').min=min;$('bet-amount').max=max;$('bet-amount').value=Math.max(min,Math.min(max,Number($('bet-amount').value)||10));$('bet-help').textContent=`Bet ${min}–${max} chips`;} 
  $('actions').replaceChildren();for(const action of obs.legal_actions.filter(a=>names[a])){const btn=textNode('button',names[action],action==='hit'?'primary':'outline');btn.title=obs.action_help[action];btn.onclick=()=>command({cmd:'act',action});$('actions').append(btn);}
  if(obs.phase==='run_over'){const btn=textNode('button','Play another run','primary');btn.onclick=()=>$('new-dialog').showModal();$('actions').append(btn);}
  $('rules').replaceChildren();if(!obs.chaos.enabled)$('rules').append(textNode('p','Standard blackjack. Bust above 21. Dealer stands on 17.'));else if(!obs.chaos.active_rules.length)$('rules').append(textNode('p','No active changes. The dealer is waiting.'));for(const rule of obs.chaos.active_rules)$('rules').append(textNode('p',rule.help));
  $('items').replaceChildren();if(!obs.items.length)$('items').append(textNode('p','Empty for now. Visit the shop between rounds.'));for(const item of obs.items){const row=textNode('div','','offer');row.append(textNode('b',`${friendly(item.id)} ×${item.count}`),textNode('small',item.help));const btn=textNode('button','Use','outline');btn.disabled=!obs.legal_actions.includes('use_item');btn.onclick=()=>command({cmd:'act',action:'use_item',item:item.id});row.append(btn);$('items').append(row);}
  $('shop-panel').hidden=!obs.shop;$('shop').replaceChildren();if(obs.shop)for(const offer of obs.shop.offers){const row=textNode('div','','offer');row.append(textNode('b',friendly(offer.item)),textNode('small',offer.help));const btn=textNode('button',offer.sold?'Sold':`Buy · ${offer.price} chips`,'outline');btn.disabled=offer.sold||!offer.affordable;btn.onclick=()=>command({cmd:'buy',item:offer.item});row.append(btn);$('shop').append(row);}
  for(const event of reply.events||[]){$('journal').prepend(textNode('li',event));}while($('journal').children.length>30)$('journal').lastChild.remove();
}
async function loadGame(){update(await api('/api/game'));}
async function mutate(path,data){if(busy)return;busy=true;document.querySelectorAll('#game button,#new-form button').forEach(b=>b.disabled=true);try{update(await api(path,{...data,revision}));if(path.endsWith('/new')){$('new-dialog').close();$('journal').replaceChildren();}}catch(e){if(e.status===401)signedOut();else{if(e.status===409)await loadGame();$('game-error').textContent=e.message;}}finally{busy=false;document.querySelectorAll('#game button,#new-form button').forEach(b=>b.disabled=false);if(obs){const error=$('game-error').textContent;update({obs,revision,events:[]});$('game-error').textContent=error;}}}
function command(cmd){$('game-error').textContent='';return mutate('/api/game/command',{command:cmd});}
$('bet-form').onsubmit=e=>{e.preventDefault();command({cmd:'bet',amount:Number($('bet-amount').value)});};$('bet-max').onclick=()=>{if(obs?.bet_range)$('bet-amount').value=obs.bet_range[1];};
$('new-open').onclick=()=>$('new-dialog').showModal();$('new-form').onsubmit=e=>{e.preventDefault();$('game-error').textContent='';mutate('/api/game/new',{chaos:new FormData(e.target).get('mode')==='chaos'});};
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
async function accounts(){const result=await api('/api/admin/accounts');$('accounts').replaceChildren();for(const account of result.accounts){const row=textNode('div','','account-row');row.append(textNode('span',`${account.username}${account.admin?' · Admin':''}${account.enabled?'':' · Disabled'}`));if(!account.admin){const button=textNode('button',account.enabled?'Disable':'Enable','outline');button.onclick=async()=>{try{await api('/api/admin/account',{id:account.id,enabled:!account.enabled});await accounts();}catch(e){$('account-error').textContent=e.message;}};row.append(button);}$('accounts').append(row);}}
$('account-open').onclick=async()=>{$('account-error').textContent='';$('account-dialog').showModal();try{const result=await api('/api/history');$('history').replaceChildren();if(!result.history.length)$('history').append(textNode('small','Complete a run to see it here.'));for(const h of result.history){const row=textNode('div','','history-row');row.append(textNode('span',`${h.chaos?'Chaos':'Classic'} · ${friendly(h.result)}`),textNode('small',`${h.bankroll} chips · ${h.rounds} rounds`));$('history').append(row);}if(user.admin)await accounts();}catch(e){$('account-error').textContent=e.message;}};
$('password-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/password',{current_password:$('current-password').value,password:$('new-password').value});e.target.reset();signedOut();$('auth-error').textContent='Password changed. Sign in again.';}catch(err){$('account-error').textContent=err.message;}};
$('rotate-token').onclick=async()=>{if(!confirm('Replace the invitation token? The previous token will stop working.'))return;try{const result=await api('/api/admin/invitation',{});$('invitation-output').textContent=`New invitation: ${result.token}`;}catch(e){$('account-error').textContent=e.message;}};
$('auth-submit').disabled=true;
api('/api/me').then(signedIn).catch(e=>{signedOut();if(e.status!==401)$('auth-error').textContent=e.message;}).finally(()=>{$('auth-submit').disabled=false;});
