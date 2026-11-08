import test from 'node:test';
import assert from 'node:assert/strict';
import { replySnippet } from '../src/replies.js';
import { draftClientId } from '../src/outcome.js';

test('reply snippets collapse whitespace and truncate long text', () => {
  assert.equal(replySnippet({content:'  words\n more words'},7),'words m…');
  assert.equal(replySnippet({content:''}),'(files)');
});

test('changing a reply target gives a retry a new id', () => {
  const draft = {text:'yes',context:'',images:[],reply_to:2};
  const retry = {...draft,clientId:'first'};
  assert.equal(draftClientId(draft,retry,()=>'new'),'first');
  assert.equal(draftClientId({...draft,reply_to:3},retry,()=>'new'),'new');
  assert.equal(draftClientId({...draft,reply_to:null},retry,()=>'new'),'new');
});
