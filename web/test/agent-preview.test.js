import test from 'node:test';
import assert from 'node:assert/strict';
import { agentPreview } from '../src/agent-preview.js';

test('owner note wins over agent status and owner history is never a fallback', () => {
  const agent={owner_note:'  rhizome plan  ',summaries:[
    {source:'owner',text:'older owner note'},
    {source:'title',text:'latest runtime topic'},
    {source:'agent',text:'older agent update'},
  ]};
  assert.equal(agentPreview(agent),'📌 note: rhizome plan');
  assert.equal(agentPreview({...agent,owner_note:''}),'latest runtime topic');
  assert.equal(agentPreview({...agent,owner_note:'  '}),'latest runtime topic');
  assert.equal(agentPreview({summaries:[{source:'owner',text:'cleared note'}]}),'');
  assert.equal(agentPreview({}),'');
});
