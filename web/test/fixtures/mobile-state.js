export const now = Date.now()/1000;
export const names = ['stoat','numbat-claude-opus-karansmbp','hoopoe-codex-gpt5-karanslinux','ferret','hedgehog','smew','tapir','jerboa'];
export const image = 'b'.repeat(64)+'.png';
export const file = 'a'.repeat(64)+'.file.mobile-layout-review-with-a-long-filename.txt';
export function fixture() { return {
 now, recipients: names.map((user_id,i)=>({user_id, node:i%2?'karans-mbp':'karans-linux', flavor:i%2?'claude':'codex', model:i%2?'claude-opus-5-5':'gpt-6.1-sol', pane_alive:true, tmux_pane:`%${100+i}`, pane_label:'agent-swarm:0.'+i, registered_at:now-1000, team_id:i<3?1:null, activity:{status:['working','needs_attention','idle','unknown'][i%4]}, summaries:[{text:'Reviewing mobile dashboard navigation',ts:now,source:'agent'},{text:'Earlier: checking task controls',ts:now-50,source:'agent'}]})).concat([{user_id:'stopped-agent',node:'karans-mbp',flavor:'codex',pane_alive:false,registered_at:now-1000,summaries:[]}]),
 nodes:[{name:'karans-linux',connected:true,local:true,harnesses:['codex','claude']},{name:'karans-mbp',connected:true,harnesses:['codex','claude']}],
 teams:[{id:1,name:'agent-swarm',queen:'stoat',members:names.slice(0,3)}],
 tasks:[{id:73,title:'Make the dashboard mobile friendly',description:'Review phone and tablet layouts, task assignment, and attachments.',assignee:'stoat',status:'picked_up',created_at:now-1000,updated_at:now,depends_on:[],attachments:[file,image],worktree:'/Users/karan/agent-swarm-task-73'}, {id:74,title:'Long path regression',description:'/Users/karan/'+('very-long-path-component-'.repeat(8)),status:'open',created_at:now,updated_at:now,depends_on:[73],attachments:[]}, {id:72,title:'Preserve working halos',status:'done',assignee:names[2],created_at:now-2000,updated_at:now-500,note:'Verify green halos in both hive and roster.',depends_on:[],attachments:[]}],
 messages:[{id:1,sender:'owner',recipient:'stoat',content:'Please review mobile layouts.\n\n```\n'+('long_terminal_line_'.repeat(20))+'\n```',ts:now,status:'delivered',attachments:[file,image]},{id:2,sender:'stoat',recipient:'owner',content:'Testing phone and tablet navigation.',ts:now,status:'delivered',attachments:[]}]
}; }
// One page of an agent's conversation, mirroring the hub's
// /api/agents/<id>/messages: newest first without `after`, oldest first with
// it, and centred on the id with `around`. A test that needs a long
// conversation puts it in state.history; /api/state keeps state.messages, as
// the real activity feed only holds recent traffic.
export function historyPage(state, user, params) {
  const limit = Math.max(1, Math.min(500, Number(params.get('limit') || 300)));
  const mine = (state.history || state.messages).filter(m => m.sender === user || m.recipient === user);
  const around = Number(params.get('around') || 0);
  const before = Number(params.get('before') || Infinity);
  const after = Number(params.get('after') || 0);
  if (around) {
    const half = Math.max(1, Math.floor(limit / 2));
    const older = mine.filter(m => m.id <= around).sort((a, b) => b.id - a.id).slice(0, half + 1);
    const newer = mine.filter(m => m.id > around).sort((a, b) => a.id - b.id).slice(0, half);
    return { messages: [...older.slice(0, half).reverse(), ...newer], has_more: older.length > half };
  }
  if (after) {
    const rows = mine.filter(m => m.id > after).sort((a, b) => a.id - b.id).slice(0, limit + 1);
    return { messages: rows.slice(0, limit), has_more: rows.length > limit };
  }
  const rows = mine.filter(m => m.id < before).sort((a, b) => b.id - a.id).slice(0, limit + 1);
  return { messages: rows.slice(0, limit), has_more: rows.length > limit };
}

export async function mock(page,state=fixture()) {
 await page.route('**/api/state',r=>r.fulfill({json:state}));
 await page.route('**/api/agents/*/messages?*', r => {
   const url = new URL(r.request().url());
   const user = decodeURIComponent(url.pathname.split('/')[3]);
   return r.fulfill({json: historyPage(state, user, url.searchParams)});
 });
 // How many messages really sit between two ids: message ids are global, so a
 // conversation's ids are sparse and a distance between two pages is often
 // nothing at all.
 await page.route('**/api/agents/*/messages/count?*', r => {
   const url = new URL(r.request().url());
   const user = decodeURIComponent(url.pathname.split('/')[3]);
   const after = Number(url.searchParams.get('after'));
   const before = Number(url.searchParams.get('before'));
   const mine = (state.history || state.messages).filter(m => m.sender === user || m.recipient === user);
   return r.fulfill({json: {count: mine.filter(m => m.id > after && m.id < before).length}});
 });
 await page.route('**/api/peek/**',r=>r.fulfill({json:{pane_label:'agent-swarm:0.1',text:'Reviewing mobile layouts\n'+('long_output_'.repeat(45))}}));
 await page.route('**/attachments/**',r => r.request().url().endsWith('.png')
   ? r.fulfill({body:'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect width="640" height="480" fill="#f2a93b"/></svg>',contentType:'image/svg+xml'})
   : r.fulfill({body:'mobile QA attachment',contentType:'text/plain'}));
 return state;
}
