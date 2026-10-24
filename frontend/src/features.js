export function filterInvoices(rows, {search='', status='', from='', to=''}={}) {
  const query=search.trim().toLowerCase();
  return rows.filter(i=>(!status||i.status===status)&&(!from||i.month>=from+'-01')&&(!to||i.month.slice(0,7)<=to)&&
    `${i.invoice_number} ${i.resident_name} ${i.resident_id} ${i.room_number}`.toLowerCase().includes(query));
}
export function sortPerformance(rows, key='outstanding', direction='desc') {
  const sign=direction==='asc'?1:-1;
  return [...rows].sort((a,b)=>{
    const av=a[key],bv=b[key];
    if(av==null&&bv==null)return 0;
    if(av==null)return 1;
    if(bv==null)return -1;
    return sign*(Number(av)-Number(bv))||String(a.resident_name||a.room_number).localeCompare(String(b.resident_name||b.room_number));
  });
}
