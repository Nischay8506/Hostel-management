import test from 'node:test';
import assert from 'node:assert/strict';
import {filterInvoices,sortPerformance} from '../src/features.js';

test('ledger filters combine month range, status and search',()=>{
  const rows=[{id:1,month:'2026-01-01',status:'paid',resident_name:'Asha',invoice_number:'SW-1',room_number:'101'},
    {id:2,month:'2026-02-01',status:'overdue',resident_name:'Asha',invoice_number:'SW-2',room_number:'101'},
    {id:3,month:'2026-03-01',status:'due',resident_name:'Bala',invoice_number:'SW-3',room_number:'201'}];
  assert.deepEqual(filterInvoices(rows,{from:'2026-02',to:'2026-02',status:'overdue',search:'ASHA'}).map(r=>r.id),[2]);
  assert.equal(filterInvoices(rows,{from:'2026-04',to:'2026-01'}).length,0);
  assert.equal(filterInvoices(rows).length,3);
});
test('performance sorting compares amounts numerically and retains missing delay last',()=>{
  const rows=[{resident_name:'A',outstanding:'90',average_settlement_delay_days:null},
    {resident_name:'B',outstanding:'1000',average_settlement_delay_days:12},
    {resident_name:'C',outstanding:'200',average_settlement_delay_days:2}];
  assert.deepEqual(sortPerformance(rows).map(r=>r.resident_name),['B','C','A']);
  assert.deepEqual(sortPerformance(rows,'average_settlement_delay_days','asc').map(r=>r.resident_name),['C','B','A']);
  assert.deepEqual(rows.map(r=>r.resident_name),['A','B','C']);
});
