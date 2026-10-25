"""Recorded commit-pair selection and a pinned offline diff viewer."""
from pathlib import Path
import hashlib


def vendor_file(name, digest):
    path = Path(__file__).with_name('vendor') / 'diff2html' / name
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Pinned diff2html asset fingerprint mismatch')
    return data.decode('utf-8')


DIFF_LICENSE = vendor_file('LICENSE.md', '6de794566a8feb4233594420299cec2dbfba51ae57201763541a5e7d627cb245')
DIFF_SCRIPT = ('/* diff2html 3.4.56 (MIT)\n' + DIFF_LICENSE + '\n*/\n'
    + vendor_file('diff2html.min.js', 'a2110a09cee157bd5466da77be02107ac81a0baa2bc1f3fe81aac8183314598e'))
DIFF_STYLE = vendor_file('diff2html.min.css', 'd3ecc0e9b2b1e5c8466c19de29bed052fd0863475d25829ecc858446efded372')
if '</script' in DIFF_SCRIPT.lower() or '</style' in DIFF_STYLE.lower():
    raise ValueError('Diff assets cannot close their HTML containers')

VERSION_LOGIC = r"""
  function versionInfo(id,arm){
    const exp=(source.experiments||[]).find(e=>e.id===id)||{},p=exp.commit_provenance||{};
    const runs=(source.trials||[]).filter(t=>experimentOf(t)===id&&t.arm===arm);
    if(!runs.length)return null;
    if(arm==='none')return {id:'none',commit:null,hash:null,label:'No skill',arm};
    const sha=arm==='candidate'?p.candidate_sha:p.previous_sha;
    const commit=typeof sha==='string'&&/^[0-9a-f]{40}$/.test(sha)?sha:null;
    const hash=(exp.arms||[]).find(a=>a.id===arm)?.skill_hash||runs[0].skill_hash||value(runs[0],'skill_hash')||null;
    return {id:commit?'commit:'+commit:'snapshot:'+(hash||id+':'+arm),commit,hash,arm,
      label:commit?'Commit '+commit:hash?'Snapshot '+hash:'Version identity not recorded'};
  }
  function versionOptions(state){
    const candidate=versionInfo(state.experiment,'candidate'),baseline=versionInfo(state.experiment,state.baseline);
    const candidates=new Map(),baselines=new Map();
    for(const id of experiments){const c=versionInfo(id,'candidate');if(!c)continue;candidates.set(c.id,c);
      if(candidate&&c.id===candidate.id)for(const arm of ['previous','none']){const b=versionInfo(id,arm);if(b)baselines.set(b.id,b);}}
    const runs=experiments.filter(id=>{const c=versionInfo(id,'candidate'),b=versionInfo(id,state.baseline);return candidate&&c?.id===candidate.id&&(!baseline||b?.id===baseline.id);});
    return {candidate,baseline,candidates:[...candidates.values()],baselines:[...baselines.values()],runs};
  }
  function chooseVersions(state,candidateId,baselineId,runId){
    const possible=[];
    for(const id of experiments){const c=versionInfo(id,'candidate');if(c?.id!==candidateId)continue;
      for(const arm of ['previous','none']){const b=versionInfo(id,arm);if(b&&(!baselineId||b.id===baselineId))possible.push({experiment:id,baseline:arm});}}
    // Candidate-only capability checks remain selectable without inventing a baseline.
    if(!possible.length&&!baselineId)for(const id of experiments)if(versionInfo(id,'candidate')?.id===candidateId)possible.push({experiment:id,baseline:''});
    const chosen=(runId?possible.find(p=>p.experiment===runId):null)||possible.find(p=>p.experiment===state.experiment)||possible.at(-1);
    if(!chosen||runId&&chosen.experiment!==runId)return null;
    const review_view=(source.ratings||[]).some(r=>experimentOf(r)===chosen.experiment&&judgeOf(r).view==='artifact-only')?'artifact-only':'';
    return {...defaults(),...chosen,review_view};
  }
"""

CHANGE_SCRIPT = r"""
function applyCommitChoice(candidate,baseline){
  let chosen=view.chooseVersions(state,candidate,baseline);
  if(!chosen&&!baseline)chosen=view.chooseVersions(state,candidate,'');
  if(chosen){state=chosen;refreshChoices();render();}
}
function refreshCommitChoices(){
  const versions=view.versionOptions(state),candidate=document.getElementById('candidate-commit-select'),baseline=document.getElementById('baseline-commit-select');
  for(const [select,items,current,empty] of [[candidate,versions.candidates,versions.candidate,'No candidate run recorded'],[baseline,versions.baselines,versions.baseline,'No baseline run recorded']]){
    select.replaceChildren();for(const item of items){option(select,item.id,item.label);select.lastChild.title=item.commit||item.hash||'No skill';}
    if(!items.length)option(select,'',empty);select.disabled=!items.length;select.value=current?.id||'';
  }
  const experiment=document.getElementById('experiment-select');experiment.replaceChildren();
  for(const id of versions.runs.length?versions.runs:view.experiments){const metadata=(data.experiments||[]).find(e=>e.id===id)||{};option(experiment,id,experimentLabel(id)+' · '+(metadata.backend||'backend not recorded'));experiment.lastChild.title=id;}
  experiment.value=state.experiment;
}
function setupCommitChoices(){
  document.getElementById('candidate-commit-select').addEventListener('change',event=>{
    const candidate=event.target.value,baseline=document.getElementById('baseline-commit-select').value;
    const chosen=view.chooseVersions(state,candidate,baseline)||view.chooseVersions(state,candidate,'');
    if(chosen){state=chosen;refreshChoices();render();}
  });
  document.getElementById('baseline-commit-select').addEventListener('change',event=>applyCommitChoice(document.getElementById('candidate-commit-select').value,event.target.value));
  document.getElementById('skill-diff').addEventListener('toggle',()=>{if(document.getElementById('skill-diff').open)renderSkillDiff();});
}
const diffSelections=new Map();
function renderSkillDiff(){
  const container=document.getElementById('skill-diff-content');container.replaceChildren();
  const exp=(data.experiments||[]).find(e=>e.id===state.experiment)||{},versions=view.versionOptions(state),change=exp.skill_changes;
  const pair=node('div',undefined,'commit-pair');
  for(const arm of [state.baseline,'candidate'])pair.append(versionCard(arm,state.experiment));
  container.append(pair);
  if(state.baseline==='none'){container.append(node('p','This comparison uses no skill as the baseline. There is no previous skill source to diff.','muted'));return;}
  if(!change){container.append(node('p','No frozen skill diff is available in this older export. Re-export the sealed run to include its verified input snapshots.','muted'));return;}
  const omitted=change.files.filter(f=>f.omitted_reason),shown=change.files.filter(f=>!f.omitted_reason);
  container.append(node('p',change.files.length+' changed files · '+shown.length+' displayed · '+omitted.length+' omitted','lead'),node('p','Diff of the exact frozen skill inputs used in this run. A source change is not a measured improvement. Commit IDs are shown only when recorded before evaluation.','caption'));
  if(!document.getElementById('skill-diff').open){container.append(node('p','Expand this panel to load the diff.','muted'));return;}
  const controls=node('div',undefined,'diff-controls'),layout=node('select'),file=node('select'),wrap=node('input');wrap.type='checkbox';wrap.id='diff-wrap';
  layout.id='diff-layout';layout.setAttribute('aria-label','Diff layout');option(layout,'side-by-side','Side by side');option(layout,'line-by-line','Unified');
  file.id='diff-file-select';file.setAttribute('aria-label','Changed skill file');option(file,'','All changed files');for(const f of shown)option(file,f.path,f.path+' · '+f.status);
  const selection=diffSelections.get(state.experiment)||{layout:innerWidth<700?'line-by-line':'side-by-side',file:''};
  layout.value=selection.layout;file.value=selection.file;
  wrap.checked=selection.wrap!==false;
  const save=()=>{diffSelections.set(state.experiment,{layout:layout.value,file:file.value,wrap:wrap.checked});renderSkillDiff();};
  for(const [control,name] of [[layout,'layout'],[file,'file']]){const label=node('label',name==='layout'?'Diff layout':'Changed file');label.append(control);controls.append(label);control.addEventListener('change',save);}
  const wrapLabel=node('label','Wrap long lines','diff-wrap');wrapLabel.prepend(wrap);controls.append(wrapLabel);wrap.addEventListener('change',save);
  const download=node('button','Download patch');download.addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([change.patch],{type:'text/plain'})),link=node('a');link.href=url;link.download='skill-changes.patch';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});controls.append(download);container.append(controls);
  const output=node('div',undefined,'skill-diff-body');output.id='diff-output';
  output.classList.toggle('wrap-lines',wrap.checked);
  if(change.patch){let files=Diff2Html.parse(change.patch);if(file.value)files=files.filter(f=>f.newName===file.value||f.oldName===file.value);
    output.innerHTML=Diff2Html.html(files,{outputFormat:layout.value,drawFileList:true,matching:'lines',colorScheme:'light',diffMaxChanges:10000,diffMaxLineLength:2000});
  }else output.append(node('p',change.files.length?'Changed file content is omitted; see the reasons below.':'The frozen skill snapshots have identical contents.','muted'));
  container.append(output);
  requestAnimationFrame(alignDiffRows);
  if(omitted.length)container.append(details('Files with omitted content',table(['File','Change','Reason'],omitted.map(f=>[f.path,f.status,({'private-content':'Private content withheld',binary:'Binary file','size-limit':'Text size limit','patch-limit':'Total patch size limit'}[f.omitted_reason]||f.omitted_reason)]))));
}
function alignDiffRows(){
  const output=document.getElementById('diff-output');if(!output?.classList.contains('wrap-lines'))return;
  for(const file of output.querySelectorAll('.d2h-file-wrapper')){const sides=file.querySelectorAll('.d2h-file-side-diff');if(sides.length!==2)continue;
    const rows=[...sides].map(side=>Array.from(side.querySelectorAll('tr')));
    for(const row of rows.flat())row.style.height='';
    for(let i=0;i<Math.min(rows[0].length,rows[1].length);i++){const height=Math.max(rows[0][i].getBoundingClientRect().height,rows[1][i].getBoundingClientRect().height);for(const side of rows)side[i].style.height=height+'px';}
  }
}
window.addEventListener('resize',()=>requestAnimationFrame(alignDiffRows));
"""
