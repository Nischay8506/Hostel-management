import React, {useEffect, useRef, useState} from 'react';
import {Skeleton} from './GapFeatures';

export function useDialogFocus(open, busy, close) {
  const current = useRef({busy, close}); current.current = {busy, close};
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog) return;
    const controls = () => [...dialog.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')].filter(el => el.getClientRects().length);
    controls()[0]?.focus();
    const keydown = event => {
      if (event.key === 'Escape' && !current.current.busy) current.current.close();
      if (event.key !== 'Tab') return;
      const all = controls(), first = all[0], last = all.at(-1);
      if (!first) {event.preventDefault(); return;}
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {event.preventDefault(); last.focus();}
      else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {event.preventDefault(); first.focus();}
    };
    document.addEventListener('keydown', keydown);
    const oldOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => {document.removeEventListener('keydown', keydown); document.body.style.overflow = oldOverflow; previous?.focus();};
  }, [open]);
}

function useRecords(path, api) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [version, setVersion] = useState(0);
  useEffect(() => {let live = true; setData(null); setError(''); api(path).then(v => {if(live) setData(v)}).catch(e => {if(live) setError(e.message)}); return () => {live = false}}, [path, version]);
  return {data, error, reload: () => setVersion(v => v + 1)};
}
function Pending({error, reload}) {return error ? <div role="alert"><p>{error}</p><button className="secondary" onClick={reload}>Try again</button></div> : <Skeleton/>}

export function Notifications({api}) {
  const {data, error, reload} = useRecords('/my/notifications', api);
  return <section className="card"><div className="card-heading"><div><h2>Your notifications</h2><p>Recent payment receipts and reminders. Manage WhatsApp consent in Account.</p></div><button className="secondary" onClick={reload}>Refresh</button></div>{!data ? <Pending error={error} reload={reload}/> : !data.length ? <p className="empty">There are no notifications for your account yet.</p> : data.map(item => <article className="notification-entry" key={item.id}><div className="complaint-head"><h3>{item.subject}</h3><span className="badge">{item.status}</span></div><small>{item.channel}{item.sent_at ? ` · ${new Date(item.sent_at).toLocaleString('en-IN')}` : ''}</small><p className="preline">{item.body}</p></article>)}</section>;
}

export function AdmissionHistory({id, api}) {
  const {data, error, reload} = useRecords(`/admissions/${id}/history`, api);
  return <section className="card"><h3>Admission #{id} · history</h3>{!data ? <Pending error={error} reload={reload}/> : data.map((row, i) => <article className="stay-history" key={i}><div><strong>{row.new_status.replaceAll('_', ' ')}</strong><small>{new Date(row.created_at).toLocaleString('en-IN')}</small>{row.note && <p>{row.note}</p>}</div></article>)}</section>;
}

export function DeploymentPanel({api}) {
  const {data, error, reload} = useRecords('/deployment-status', api);
  return <section className="card"><div className="card-heading"><div><h2>Service configuration</h2><p>Configuration status is separate from verified delivery. Confirm the most recent successful worker run.</p></div><button className="secondary" onClick={reload}>Refresh</button></div>{!data ? <Pending error={error} reload={reload}/> : <dl className="service-grid">{[
    ['Release', data.release], ['Environment', data.environment], ['Database engine', data.database_engine], ['Schema', `${data.schema_revision} / expected ${data.expected_revision}`],
    ['WhatsApp', data.whatsapp.status==='test_only' ? 'Local test provider; no real phone delivery' : data.whatsapp.status==='ready' ? 'Configured; live delivery still requires provider verification' : 'Configuration incomplete'], ['Email', `${data.smtp.configured ? 'Host configured' : 'Local or missing host'} · ${data.smtp.security}`],
    ['Worker', `${data.scheduler.status} · ${data.scheduler.mode.replaceAll('_',' ')}`], ['Last completed run', data.scheduler.last_succeeded_at ? new Date(data.scheduler.last_succeeded_at).toLocaleString('en-IN') : 'No successful run recorded'],
    ['SMS verification',data.sms_configured?'Configured':'Not configured'],['Private identity storage',data.identity_documents_configured?'Configured':'Not configured'],['Scheduled billing',data.automatic_billing_enabled?'Enabled':'Disabled'],
    ['Percentage discounts', data.percentage_discounts_enabled ? 'Enabled for staff approval' : 'Disabled by management configuration'],
  ].map(([key,value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>}</section>;
}

export function Discounts({resident, api, admin}) {
  const {data, error, reload} = useRecords(`/residents/${resident.id}/discounts`, api);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [failure, setFailure] = useState(''), [revoke, setRevoke] = useState(null);
  async function save(path, body, method='POST') {
    if(busy) return; setBusy(true); setFailure(''); setMessage('');
    try {await api(path, {method, body: JSON.stringify(body)}); setMessage('Discount approval history updated. Issued invoices retain their saved amounts.'); setRevoke(null); reload()}
    catch(e) {setFailure(e.message)} finally {setBusy(false)}
  }
  return <section className="discount-panel"><h3>Approved percentage discounts</h3><p>Fixed allocation discounts and percentage approvals cannot overlap. Each approval applies to complete billing months.</p>{message && <p role="status">{message}</p>}{failure && <p role="alert" className="alert error">{failure}</p>}{!data ? <Pending error={error} reload={reload}/> : <>
    {!data.enabled && <div className="info-strip">New percentage approvals are disabled in the service configuration. Existing invoice snapshots are preserved.</div>}
    {data.rules.map(rule => <article className="notification-entry" key={rule.id}><strong>{rule.percentage}% · {rule.charge_scope.replaceAll('_',' ')}</strong><p>{rule.effective_from} through {rule.effective_until}{rule.max_amount !== null ? ` · INR ${rule.max_amount} monthly cap` : ' · No additional cap'}</p><p>{rule.reason}</p><small>Approved by staff #{rule.approved_by} · {rule.revoked_at ? 'Revoked for future billing' : 'Approved'}</small>{admin && !rule.revoked_at && <div>{revoke === rule.id ? <><p>Stop this approval for future invoices? Issued invoices remain unchanged.</p><button className="secondary" disabled={busy} onClick={()=>save(`/discounts/${rule.id}/revoke`,{},'PUT')}>Confirm revocation</button><button className="text-btn" onClick={()=>setRevoke(null)}>Cancel</button></> : <button className="text-btn" onClick={()=>setRevoke(rule.id)}>Revoke future application</button>}</div>}</article>)}
    {!data.rules.length && <p>No percentage approvals have been recorded.</p>}
    {admin && data.enabled && <form onSubmit={event => {event.preventDefault(); const form = Object.fromEntries(new FormData(event.currentTarget)); save(`/residents/${resident.id}/discounts`, {...form, max_amount:form.max_amount||null, effective_from:form.effective_from+'-01', effective_until:form.effective_until+'-01'})}}><h4>Approve a discount</h4><div className="form-grid"><label className="field">Percentage<input name="percentage" type="number" min="0.01" max="100" step="0.01" required/></label><label className="field">Eligible charges<select name="charge_scope"><option value="accommodation">Accommodation only</option><option value="all_monthly">Accommodation and configured monthly extras</option></select></label><label className="field">Maximum discount per month (INR, optional)<input name="max_amount" type="number" min="0" step="0.01"/></label><label className="field">First billing month<input name="effective_from" type="month" required/></label><label className="field">Last billing month, inclusive<input name="effective_until" type="month" required/></label></div><label className="field">Approval reason<textarea name="reason" minLength={5} maxLength={500} required/></label><button className="primary" disabled={busy}>{busy?'Saving…':'Record approval'}</button></form>}
  </>}</section>;
}
