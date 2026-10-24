import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveApiBase,resourcePaths,apiJson,apiFetch} from '../src/api.js';

test('API configuration validates public production URLs',()=>{
  assert.equal(resolveApiBase(undefined,true),'/api');
  assert.equal(resolveApiBase('https://api.example.test/api/',true),'https://api.example.test/api');
  for(const url of ['http://api.example.test/api','https://localhost:8000/api','https://127.0.0.1/api','https://[::1]/api','https://user:secret@api.example.test/api','https://api.example.test/api?token=x','https://api.example.test/']) assert.throws(()=>resolveApiBase(url,true));
});
test('dashboard paths match the established API route names',()=>{
  assert.equal(resourcePaths.gatePasses,'/gate-passes');
  assert.equal(resourcePaths.feePlans,'/fee-plans');
  assert.equal(resourcePaths.complaintAssignees,'/complaint-assignees');
  assert.equal(resourcePaths.branches,'/managed-branches');
  assert.equal(resourcePaths.branchAdmins,'/branch-admins');
});
test('HTML fallback cannot masquerade as a successful API response',async t=>{
  t.mock.method(globalThis,'fetch',async()=>new Response('<!doctype html>',{headers:{'Content-Type':'text/html'}}));
  await assert.rejects(apiJson('/branches'),/temporarily unavailable/);
});
test('JSON errors preserve HTTP status without reflecting validation input',async t=>{
  t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify({detail:[{loc:['body','email'],msg:'Invalid email',input:'private@example.test'}]}),{status:422,headers:{'Content-Type':'application/json'}}));
  await assert.rejects(apiJson('/admissions'),error=>error.status===422&&error.message==='email: Invalid email');
});
test('downloads and JSON use the same configured base',async t=>{
  const paths=[]; t.mock.method(globalThis,'fetch',async url=>{paths.push(url);return new Response('binary',{headers:{'Content-Type':'application/pdf'}})});
  assert.equal((await apiFetch('/payments/1/receipt.pdf')).headers.get('content-type'),'application/pdf');
  assert.deepEqual(paths,['/api/payments/1/receipt.pdf']);
  await assert.rejects(apiFetch('//untrusted.test'),/Invalid API path/);
});
test('network failure shows a safe recoverable message',async t=>{
  t.mock.method(globalThis,'fetch',async()=>{throw new Error('private network details')});
  await assert.rejects(apiJson('/health'),/could not connect to Cityhive/);
});
