"""Compact, aligned evidence presentation without changing frozen judgments."""

EVIDENCE_LOGIC = r"""
  function evidenceRows(state,slots,turn,context){
    const columns=slots.map(slot=>({...slot,media:slot.trial&&context?.visibility!=='private'&&slot.trial.privacy!=='private'?mediaFor(slot.trial.id,turn):[]}));
    const declared=context?.visibility==='public'?(context.turns||[]).find(t=>t.turn===turn)?.artifacts||[]:[];
    const names=list(declared.filter(a=>a.kind==='preview'&&['png','jpg','jpeg','webp','gif'].includes(a.format)).map(a=>a.path));
    if(!names.length)names.push(...list(columns.flatMap(c=>c.media.map(m=>m.name)).filter(name=>name&&name!=='additional-preview')).sort());
    const outputs=names.map(name=>({name,cells:columns.map(c=>({arm:c.arm,trial_id:c.trial?.id||null,media:c.media.filter(m=>m.name===name)}))}));
    const extras=columns.map(c=>({arm:c.arm,trial_id:c.trial?.id||null,media:c.media.filter(m=>!names.includes(m.name))}));
    const ids=new Set(columns.map(c=>c.trial?.id).filter(Boolean));
    const records=select(state).ratings.filter(r=>ids.has(r.trial_id)&&r.turn===turn);
    const definitions=context?.visibility==='public'?context.atoms||[]:[];
    const active=definitions.filter(a=>(a.active_turns||[]).includes(turn));
    const atomIds=list([...active.map(a=>a.id),...records.filter(r=>!definitions.some(a=>a.id===r.atom)).map(r=>r.atom)]);
    const atoms=atomIds.map(id=>({id,definition:active.find(a=>a.id===id)||null,cells:columns.map(c=>({arm:c.arm,trial_id:c.trial?.id||null,records:records.filter(r=>r.trial_id===c.trial?.id&&r.atom===id)}))}));
    return {outputs,extras,atoms};
  }
"""

EVIDENCE_STYLE = r"""
.evidence-headers,.matched-output,.extra-image-columns,.source-check-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.evidence-headers.single-version,.matched-output.single-version,.extra-image-columns.single-version,.source-check-columns.single-version{grid-template-columns:1fr}
.evidence-headers{margin:16px 0}.evidence-headers .evidence-heading{margin:0;padding:0}.evidence-headers .version-card{min-width:0}
.atom-section{margin:18px 0 24px}.atom-section h4{font-size:16px;margin:0 0 6px}.atom-section>.caption{font-size:12px;margin-bottom:10px}
.atom-table{table-layout:fixed;min-width:610px;background:var(--ivory);border:1px solid #d5dbe3;font-size:13px}
.atom-table th,.atom-table td{padding:10px 12px;min-width:0}.atom-table thead th{font-weight:600;border-bottom:2px solid #d5dbe3}
.atom-table th:first-child{width:40%}.atom-table th[scope=row]{font-weight:400;background:transparent}
.atom-table .atom-title{font-weight:600;display:block}.atom-table .atom-id{font-size:11px;color:var(--muted);display:block;margin:2px 0}
.atom-table .version-baseline{background:#f5f2f766;border-left:1px solid #ded7e6}.atom-table .version-candidate{background:#eef4f866;border-left:1px solid #d2e0e9}
.atom-table .rating-entry+.rating-entry{margin-top:10px;border-top:1px dashed #d5dbe3;padding-top:10px}.atom-table .badge{font-family:var(--mono-font);font-size:12px}
.atom-table details{margin:5px 0 0;padding:0;border:0;font-size:12px}.atom-table details>div{margin-top:8px}
.atom-table details p{font-size:12px;margin-bottom:8px}.atom-table details pre{font-size:11px;padding:8px;margin:8px 0 0}
.atom-table .review-identity{display:block;font-size:11px;color:var(--muted);margin-top:3px}.atom-table .missing-rating{font-size:12px;color:var(--muted)}
.output-evidence,.additional-evidence,.delivery-evidence{margin:18px 0;padding:12px;border:1px solid #d5dbe3;border-radius:4px;background:var(--ivory)}
.output-evidence>summary,.additional-evidence>summary,.delivery-evidence>summary{font-size:14px;font-weight:600}
.evidence-count{font-family:var(--mono-font);font-size:11px;font-weight:400;color:var(--muted);margin-left:12px}
.output-row{margin-top:12px;border-top:1px solid var(--border);padding-top:10px}.output-name{font-size:12px;font-weight:600;margin:0 0 8px}
.output-cell,.extra-image-column,.source-check-column{min-width:0}.output-cell{padding:10px;border:1px solid #ded7e6;background:#f5f2f733;border-radius:3px}
.output-cell.version-candidate{border-color:#d2e0e9;background:#eef4f833}.output-cell>.version-role{margin-bottom:6px}
.output-cell figure{margin:0}.output-cell img{display:block;width:100%;height:auto;max-height:300px;object-fit:contain}
.output-cell figcaption{display:none}.output-cell .image-actions{margin-top:7px}.output-cell .empty-evidence{padding:14px;font-size:12px;min-height:80px}
.additional-evidence .preview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.additional-evidence figure{margin:0}
.additional-evidence img,.source-check-column img{max-height:220px;object-fit:contain}.source-check-column pre{font-size:11px;padding:10px}
.extra-image-column>.caption,.source-check-column>.caption{font-size:12px}.source-check-column figure{margin:10px 0}
@media(max-width:600px){.evidence-headers,.matched-output,.extra-image-columns,.source-check-columns{grid-template-columns:1fr}.atom-table{min-width:580px}.atom-table th,.atom-table td{padding:8px 10px}.output-evidence,.additional-evidence,.delivery-evidence{padding:10px}.evidence-count{display:block;margin:3px 0 0}.output-cell img{max-height:260px}}
"""

EVIDENCE_SCRIPT = r"""
function dimensionLabel(value){return ({reference_transfer:'Reference interpretation',alternatives:'Distinct alternatives',hierarchy:'Visual hierarchy',legibility:'Legibility',construction:'Garment structure',motion_scope:'Movement room',layout:'Layout',preservation:'Preserving earlier work'}[value]||String(value||'Requirement').replaceAll('_',' ').replaceAll('-',' ').replace(/^./,c=>c.toUpperCase()));}
function evidenceMissing(trial,turn){
  if(!trial)return 'No run was planned for this version.';
  const record=(trial.turns||[]).find(t=>t.turn===turn);
  return trial.privacy==='private'?'Private inputs and their derived outputs are withheld from the public report.':view.experimentOf(trial)!==(data.current_experiment||data.experiment)?'These historical images remain in their original report bundle. No image from another experiment is substituted.':!record||record.evidence_status==='missing-result'?'No execution result or image evidence was recorded for this turn.':'No verified preview is available for this turn.';
}
function scoringRule(row,context){
  const body=node('div'),atom=row.definition;
  body.append(node('code','Atom ID: '+row.id));
  if(atom){body.append(node('p',atom.criterion,'requirement'));for(const requirement of (context?.requirements||[]).filter(r=>(atom.requirement_ids||[]).includes(r.id)))body.append(node('p','Original requirement: '+requirement.quote,'requirement'));for(const [score,anchor] of Object.entries(atom.anchors||{}))body.append(node('p',score+': '+anchor));}
  else body.append(node('p','The original criterion and score definitions are not included in this report; none are inferred.','caption'));
  return details('Scoring rule',body);
}
function ratingCell(cell){
  const box=node('div');
  if(!cell.records.length){box.append(node('span',cell.trial_id?'No review':'No run','missing-rating'));return box;}
  for(const rating of cell.records){
    const entry=node('div',undefined,'rating-entry');entry.dataset.score=String(rating.score);entry.append(badge(scoreLabel(rating.score),scoreTone(rating.score)));
    const identity=view.value(rating,'judge')+' · v'+(view.value(rating,'review_version')||'Not recorded')+' · '+(view.value(rating,'review_view')||'View not recorded');
    if(cell.records.length>1)entry.append(node('span',identity,'review-identity'));
    const body=node('div');body.append(node('p',rating.reason||'No reason was recorded.','reason'),node('p',identity,'caption'),node('pre',JSON.stringify({judge:rating.judge,review_version:rating.review_version,evidence:rating.evidence},null,2)));
    entry.append(details('Reason and evidence',body));box.append(entry);
  }
  return box;
}
function renderAtomTable(projection,slots,context){
  const section=node('div',undefined,'atom-section');section.append(node('h4','Requirement ratings'));
  const count=projection.atoms.reduce((n,row)=>n+row.cells.reduce((m,cell)=>m+cell.records.length,0),0);
  section.append(node('p',projection.atoms.length+' requirements · '+count+' recorded ratings for this turn. Open Scoring rule or Reason and evidence for details. No review is neither zero nor a pass.','caption'));
  if(!projection.atoms.length){section.append(node('p','No requirement definitions or ratings are available for this turn.','muted'));return section;}
  const wrap=node('div',undefined,'table-scroll'),table=node('table',undefined,'atom-table'),head=node('thead'),tr=node('tr');
  tr.append(node('th','Requirement'));for(const slot of slots){const th=node('th',roleLabel(slot.arm),'version-'+(slot.arm==='candidate'?'candidate':'baseline'));th.scope='col';th.dataset.arm=slot.arm;tr.append(th);}tr.firstChild.scope='col';head.append(tr);table.append(head);
  const body=node('tbody');
  for(const row of projection.atoms){const tr=node('tr');tr.dataset.atom=row.id;const heading=node('th');heading.scope='row';const dimension=row.definition?.dimension||row.cells.flatMap(c=>c.records)[0]?.dimension||row.id,repeated=projection.atoms.filter(a=>(a.definition?.dimension||a.cells.flatMap(c=>c.records)[0]?.dimension)===dimension).length>1;heading.append(node('span',dimensionLabel(repeated?row.id:dimension),'atom-title'),scoringRule(row,context));tr.append(heading);for(const cell of row.cells){const td=node('td',undefined,'version-'+(cell.arm==='candidate'?'candidate':'baseline'));td.dataset.arm=cell.arm;td.dataset.trial=cell.trial_id||'';td.append(ratingCell(cell));tr.append(td);}body.append(tr);}
  table.append(body);wrap.append(table);section.append(wrap);return section;
}
function renderOutputEvidence(projection,slots,turn){
  const box=details('Matched output images');box.className='output-evidence';box.open=true;
  if(!projection.outputs.length){for(const slot of slots)box.append(node('p',roleLabel(slot.arm)+': '+evidenceMissing(slot.trial,turn),'empty-evidence'));return box;}
  for(const row of projection.outputs){
    const item=node('div',undefined,'output-row');item.dataset.output=row.name;item.append(node('div',row.name,'output-name'));
    const grid=node('div',undefined,'matched-output'+(slots.length===1?' single-version':''));
    for(const [index,cell] of row.cells.entries()){const column=node('div',undefined,'output-cell version-'+(cell.arm==='candidate'?'candidate':'baseline'));column.dataset.arm=cell.arm;column.dataset.trial=cell.trial_id||'';column.append(node('span',roleLabel(cell.arm),'version-role'));if(cell.media.length){for(const media of cell.media)column.append(imageFigure(media));}else column.append(node('p',evidenceMissing(slots[index].trial,turn),'empty-evidence'));grid.append(column);}
    item.append(grid);box.append(item);
  }
  return box;
}
function renderAdditionalEvidence(projection,slots){
  if(!projection.extras.some(c=>c.media.length))return null;
  const box=details('Additional images');box.className='additional-evidence';box.querySelector('summary').append(node('span',projection.extras.map(c=>roleLabel(c.arm)+' '+c.media.length).join(' · '),'evidence-count'));
  let loaded=false;box.addEventListener('toggle',()=>{if(!box.open||loaded)return;loaded=true;const columns=node('div',undefined,'extra-image-columns'+(slots.length===1?' single-version':''));for(const cell of projection.extras){const col=node('div',undefined,'extra-image-column');col.dataset.arm=cell.arm;col.append(node('span',roleLabel(cell.arm),'version-role'));if(cell.media.length){const grid=node('div',undefined,'preview-grid');for(const media of cell.media)grid.append(imageFigure(media));col.append(grid);}else col.append(node('p','No additional images.','caption'));columns.append(col);}box.append(columns);});return box;
}
function renderSourceChecks(slots,turn){
  const proof=details('Delivery and source checks');proof.className='delivery-evidence';const body=node('div');body.append(node('p','These mechanical checks retain their exact scope and are separate from visual judgments. They do not establish complete motion quality, procedural-rule correctness, rigging or target-application acceptance.','caption'));proof.append(body);
  let loaded=false;proof.addEventListener('toggle',()=>{if(!proof.open||loaded)return;loaded=true;const columns=node('div',undefined,'source-check-columns'+(slots.length===1?' single-version':''));for(const slot of slots){const col=node('div',undefined,'source-check-column');col.dataset.arm=slot.arm;col.append(node('span',roleLabel(slot.arm),'version-role'));if(slot.trial){const record=(slot.trial.turns||[]).find(t=>t.turn===turn);col.append(node('pre',JSON.stringify({status:record?.status||'missing-result',delivery_pass:record?.delivery_pass??null,preservation_pass:record?.preservation_pass??null,source_proofs:record?.source_proofs||[]},null,2)));for(const item of view.proofsFor(slot.trial.id,turn))col.append(imageFigure(item));}else col.append(node('p','No run was planned for this version.','caption'));columns.append(col);}body.append(columns);});return proof;
}
function renderAlignedEvidence(body,slots,turn,context){
  const headers=node('div',undefined,'evidence-headers'+(slots.length===1?' single-version':''));
  for(const slot of slots){const heading=node('div',undefined,'evidence-heading');heading.dataset.arm=slot.arm;heading.dataset.trial=slot.trial?.id||'';heading.append(versionCard(slot.arm,slot.trial?view.experimentOf(slot.trial):state.experiment));if(slot.trial)heading.append(badge(statusLabel(slot.trial.status),statusTone(slot.trial.status)));else heading.append(badge('No run','unknown'));headers.append(heading);}
  const projection=view.evidenceRows(state,slots,turn,context);body.append(headers,renderAtomTable(projection,slots,context),renderOutputEvidence(projection,slots,turn));const extras=renderAdditionalEvidence(projection,slots);if(extras)body.append(extras);body.append(renderSourceChecks(slots,turn));
}
"""
