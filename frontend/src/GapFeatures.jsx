import React, {useEffect, useState} from 'react';
import {apiFetch, apiJson} from './api';

export function Skeleton({label='Loading records'}) {return <div className="skeleton-grid" role="status" aria-label={label}><span className="sr-only">{label}</span>{[1,2,3].map(i=><div className="skeleton-card" key={i}><i/><i/><i/></div>)}</div>}

export function useAccessibleValidation() {
  useEffect(()=>{
    function clear(event){const field=event.target;if(!field.matches?.('input,select,textarea'))return;const id=field.dataset.validationId;if(id){document.getElementById(id)?.remove();field.removeAttribute('aria-invalid');field.setAttribute('aria-describedby',(field.getAttribute('aria-describedby')||'').split(' ').filter(x=>x!==id).join(' '));delete field.dataset.validationId}}
    function invalid(event){const field=event.target;if(!field.matches?.('input,select,textarea'))return;event.preventDefault();clear(event);const id='validation-'+crypto.randomUUID();const error=document.createElement('span');error.id=id;error.className='field-error';error.textContent=field.validationMessage;field.insertAdjacentElement('afterend',error);field.dataset.validationId=id;field.setAttribute('aria-invalid','true');field.setAttribute('aria-describedby',`${field.getAttribute('aria-describedby')||''} ${id}`.trim());if(field.form?.querySelector(':invalid')===field)field.focus()}
    document.addEventListener('invalid',invalid,true);document.addEventListener('input',clear,true);document.addEventListener('change',clear,true);
    return()=>{document.removeEventListener('invalid',invalid,true);document.removeEventListener('input',clear,true);document.removeEventListener('change',clear,true)};
  },[]);
}

export async function downloadFile(path,token,filename) {
  const response=await apiFetch(path,{headers:{Authorization:'Bearer '+token}});
  const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function IdentityDocuments({resident,api,token}) {
  const [info,setInfo]=useState(null),[error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState(false);
  const path=`/residents/${resident.id}/identity-document`;
  const reload=()=>api(path).then(setInfo).catch(e=>setError(e.message));
  useEffect(()=>{reload()},[resident.id]);
  async function upload(event){event.preventDefault();const file=new FormData(event.currentTarget).get('document');if(!file?.size)return;if(file.size>5*1024*1024){setError('Choose a document smaller than 5 MB.');return}setBusy(true);setError('');try{await apiFetch(path,{method:'PUT',headers:{Authorization:'Bearer '+token,'Content-Type':file.type},body:file});setMessage('Document stored privately. Manual review is pending.');await reload()}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <section className="identity-panel"><h3>Identity document</h3><p>Upload a JPG, PNG or simple PDF up to 5 MB. Only you and authorized branch staff can access it.</p>{error&&<p className="alert error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}{!info?<Skeleton/>:<>{!info.configured&&<p>Private document storage must be configured by management before uploading.</p>}{info.present&&<><p>Stored on {new Date(info.uploaded_at).toLocaleString('en-IN')}</p><button className="secondary" type="button" onClick={()=>downloadFile(path+'/download',token,'identity-document.'+({'application/pdf':'pdf','image/png':'png','image/jpeg':'jpg'}[info.content_type])).catch(e=>setError(e.message))}>Download document</button>{confirm?<button className="secondary" disabled={busy} type="button" onClick={async()=>{setBusy(true);try{await api(path,{method:'DELETE'});setMessage('Stored document removed.');setConfirm(false);await reload()}catch(e){setError(e.message)}finally{setBusy(false)}}}>Confirm removal</button>:<button className="text-btn" type="button" onClick={()=>setConfirm(true)}>Remove stored document</button>}</>}{info.configured&&<form onSubmit={upload}><label className="field">{info.present?'Replace document':'Choose document'}<input type="file" name="document" accept="image/jpeg,image/png,application/pdf" required/></label><button className="primary" disabled={busy}>{busy?'Uploading…':'Upload privately'}</button></form>}</>}</section>;
}

export function LifecycleForm({kind,item,api,onDone}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const active=kind==='rooms'?!item.active:item.status==='inactive';
  return <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{await api(`/${kind}/${item.id}/status`,{method:'PUT',body:JSON.stringify({active,reason:new FormData(e.currentTarget).get('reason')})});await onDone()}catch(e){setError(e.message)}finally{setBusy(false)}}}><h3>{active?'Reactivate':kind==='rooms'?'Decommission room':'Deactivate resident'}</h3><p>{item.name||'Room '+item.number}</p><p>{kind==='rooms'?'Decommissioned rooms remain in history and cannot accept allocations.':'Deactivation disables sign-in and releases the room after all financial balances are settled. Reactivation requires a new room allocation.'}</p>{error&&<p role="alert" className="alert error">{error}</p>}<label className="field">Reason<textarea name="reason" minLength={5} maxLength={500} required/></label><button className="primary" disabled={busy}>{busy?'Saving…':'Confirm change'}</button></form>;
}

export function BranchFAQs({branch,api,onDone}) {
  const [rows,setRows]=useState(branch.faqs||[]),[busy,setBusy]=useState(false),[error,setError]=useState('');
  function update(index,key,value){setRows(rows.map((r,i)=>i===index?{...r,[key]:value}:r))}
  return <form onSubmit={async e=>{e.preventDefault();setBusy(true);try{await api(`/branches/${branch.id}/faqs`,{method:'PUT',body:JSON.stringify(rows)});await onDone()}catch(e){setError(e.message)}finally{setBusy(false)}}}><h3>{branch.name} · FAQs</h3><p>These questions appear on the public site when this branch is selected.</p>{error&&<p role="alert">{error}</p>}{rows.map((r,i)=><fieldset key={i}><legend>Question {i+1}</legend><label className="field">Question<input value={r.question} onChange={e=>update(i,'question',e.target.value)} minLength={3} maxLength={200} required/></label><label className="field">Answer<textarea value={r.answer} onChange={e=>update(i,'answer',e.target.value)} minLength={3} maxLength={2000} required/></label><button className="text-btn" type="button" onClick={()=>setRows(rows.filter((_,j)=>j!==i))}>Remove question</button></fieldset>)}<div className="button-row"><button className="secondary" type="button" disabled={rows.length>=20} onClick={()=>setRows([...rows,{question:'',answer:''}])}>Add question</button><button className="primary" disabled={busy}>Save FAQs</button></div></form>;
}

export function AdmissionTracking({receipt}) {
  const [result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  return <section className="ch-tracking" id="track-enquiry"><h3>Track your enquiry</h3><p>Use your email and the private tracking key shown after submission.</p>{receipt&&<p className="tracking-key">Save your tracking key: <strong>{receipt.key}</strong></p>}<form key={receipt?.key||'lookup'} onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');setResult(null);try{setResult(await apiJson('/public/admissions/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(e.currentTarget)))}))}catch(e){setError(e.message)}finally{setBusy(false)}}}><label>Email<input type="email" name="email" defaultValue={receipt?.email||''} required/></label><label>Private tracking key<input name="submission_key" defaultValue={receipt?.key||''} minLength={32} maxLength={64} required autoComplete="off"/></label><button className="ch-button" disabled={busy}>{busy?'Checking…':'Check status'}</button></form>{error&&<p role="alert">{error}</p>}{result&&<div role="status"><h4>Enquiry #{result.id} · {result.status.replaceAll('_',' ')}</h4><ol>{result.history.map((e,i)=><li key={i}>{e.status.replaceAll('_',' ')} · {new Date(e.at).toLocaleString('en-IN')}</li>)}</ol></div>}</section>;
}
