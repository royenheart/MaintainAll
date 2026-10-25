"""Fixed English definitions for report labels, separate from frozen evidence."""
from __future__ import annotations

import html
import json

TERMS = {
    'Evaluation setup': 'Choose the recorded versions, evaluation and case to inspect. Filters change this view without executing a model.',
    'Execution and review coverage': 'How much of the planned evaluation was executed, recorded and reviewed. These counts do not by themselves measure requirement fulfillment.',
    'Candidate versus baseline': 'Frozen judgments comparing the tested candidate with the selected reference on matching tasks and repeats.',
    'Inspect the case evidence': 'Inspect the actual reference inputs, output images, scoring anchors and review reasons for the selected case, repeat and turn.',
    'Skill changes': 'A read-only diff of the exact frozen previous and candidate skill inputs. A source change is not evidence of a measured improvement.',
    'Versions and filters': 'Choose the exact candidate, baseline, evaluation and task whose recorded results are displayed. Filtering does not start a new evaluation.',
    'More filters': 'Optional filters for recorded execution and review conditions. These narrow the same frozen results without adding observations.',
    'Rating distributions by evaluated condition': 'Counts of 0, 1, 2 and unknown requirement ratings for each exact evaluation condition. Changed tasks or review conditions stay separate.',
    'Version comparison': 'The exact tested versions and candidate-oriented Better, Similar, Worse or insufficient-evidence counts for the chosen baseline.',
    'Actual reference inputs through this turn': 'The actual input images available by the selected turn, including earlier references retained in that attempt.',
    'Matched output images': 'Declared output images are aligned by artifact name for the same repeat and turn. A missing image has its own placeholder; extra images do not shift the comparison.',
    'Additional images': 'Other verified images retained in the selected turn, separate from its declared outputs. Counts may differ between versions; opening this disclosure loads the images without adding ratings.',
    'All submitted experiments': 'The separately submitted evaluations retained in this benchmark. Open an experiment to inspect its own versions and evidence.',
    'Recorded ratings with matching conditions': 'Existing requirement ratings across repeated evaluations with identical task, skill, runtime and review conditions. Different conditions produce separate histories.',
    'Withheld previews': 'Artifact identities whose previews were excluded because the format, content or privacy checks did not permit publication. Their bytes are not displayed.',
    'Full public JSON': 'The validated public records used to build this report, available for inspection and download. Private execution logs and authentication are excluded.',
    'Time and usage': 'Recorded execution time and available usage observations. Missing records remain unknown and token counts are not subscription cash costs.',
    'Runs by tested version': 'Execution-status counts for each tested version, separate from requirement ratings.',
    'Comparisons by case': 'Candidate-oriented paired outcomes grouped by task, using the currently selected baseline.',
    'Comparison by case': 'Candidate-oriented paired outcomes grouped by task, using the currently selected baseline.',
    'Requirement ratings by evaluated condition': 'Ordinal requirement-rating counts grouped by exact task, runtime and review conditions. These related observations are not an overall score.',
    'Known token subtotals': 'Only available token observations are summed, with recorded-turn coverage shown separately. Cached and uncached input are components of input, and missing usage stays unknown.',
    'Case': 'A complete task with its inputs, feedback turns and scoring rules. Repeating the same case does not create a new task.',
    'Run': 'One attempt by one tested version on one case. A run can contain several consecutive turns.',
    'Repeat': 'An independent restart of the same case and version to observe variation between attempts.',
    'Turn': 'One step inside a run: an initial request or a later feedback request continuing that attempt.',
    'Candidate': 'The exact frozen skill version being evaluated. It may differ from the current working copy.',
    'Baseline': 'The selected comparison version, such as an earlier skill snapshot or the no-skill condition.',
    'No skill': 'The same task is attempted without providing a skill snapshot. This condition has no skill hash.',
    'Requirement rating': 'One judgment of one applicable requirement on one turn. Several ratings may refer to the same output, so they are related observations rather than independent samples.',
    'Snapshot hash': 'A SHA-256 identity of the frozen skill contents. It identifies the tested bytes but does not establish which Git commit they came from.',
    'Git commit SHA': 'The Git revision recorded when the tested skill input was prepared. A later report-upload commit is not a substitute.',
    'Candidate commit': 'Select the tested candidate Git revision, or its explicitly labeled snapshot hash when no commit was recorded.',
    'Baseline commit': 'Select the tested reference revision or snapshot. No skill is a separate reference condition.',
    'Evaluation run': 'A separately recorded evaluation experiment with its own versions, cases, repeats and execution settings. Selecting it does not pool other experiments.',
    'Skill version': 'Filter to the exact tested intervention identified by its full commit or snapshot hash.',
    'Model': 'The model identifier recorded for the generating agent. It does not identify every provider-side service revision.',
    'Reasoning effort': 'The recorded reasoning setting used for generation, separate from the model identifier.',
    'Execution backend': 'The runner and environment used to execute the task, such as Harbor. Changing it can change comparison conditions.',
    'Scoring rules': 'The task-specific criteria and anchors defining each requirement rating. Different rule sets remain separate.',
    'Reviewer': 'The agent or person supplying the frozen judgments. A reviewer identity is not a count of independent task samples.',
    'Review version': 'An immutable revision of a review. A correction creates a new review version instead of changing the earlier record.',
    'Review view': 'The evidence available to the reviewer. Artifact-only and process-assisted reviews have different information and are kept separate.',
    'Artifact-only': 'The reviewer uses reference inputs, output artifacts and allowed status evidence, without the generating conversation or self-assessment.',
    'Notes-process': 'The reviewer additionally receives explicitly permitted process notes. It is a different review condition from artifact-only.',
    'Independent agent review': 'A separate reviewing agent supplied judgments. These exploratory judgments do not establish human consensus.',
    'Completed runs': 'Runs whose execution reached the required end state. Completion does not by itself establish design quality.',
    'Failed or stopped runs': 'Runs that failed or were interrupted during execution. Their available evidence remains visible; execution failure is not automatically a zero quality rating.',
    'Recorded / planned turns': 'Recorded execution observations divided by scheduled turns. Recorded turns can include failed turns; unobserved turns remain missing and unscored.',
    'Runs with independent reviews': 'Runs with at least one judgment from a separate agent or person, divided by all selected planned runs. A judgment can still say that evidence is insufficient.',
    'Review coverage': 'Runs with at least one recorded rating. Ratings with insufficient evidence still count as review records.',
    '0 · Not met': 'Available evidence establishes that this requirement was not met under its own task-specific scoring anchors.',
    '1 · Partly met': 'Available evidence establishes partial fulfillment under this requirement\'s scoring anchors.',
    '2 · Met': 'Available evidence establishes fulfillment under this requirement\'s scoring anchors. It is not an overall task score.',
    'Not enough evidence': 'A reliable rating or comparison cannot be assigned from the available evidence. Missing evidence is neither zero nor a pass.',
    'Better': 'A frozen matched-pair review prefers the candidate result over the selected baseline. The direction always refers to the candidate.',
    'Similar': 'The matched-pair reviewer found no clear preference between candidate and baseline. This does not establish statistical equivalence.',
    'Worse': 'A frozen matched-pair review prefers the baseline result over the candidate.',
    'Conditions match': 'The recorded task, runtime, scoring and review conditions match apart from the intended skill intervention. This does not establish statistical significance.',
    'Paired judgments': 'Each comparison matches the same case and repeat across two tested versions. Outcomes come from frozen reviews, not subtraction of requirement ratings.',
    'Known subtotal': 'The sum of available usage records only. If some turns lack usage, this subtotal is not the full experiment total.',
    'Usage recorded / recorded turns': 'Turns with a valid record for this usage field divided by all recorded execution turns.',
    'Input tokens': 'Recorded input volume, including cached input. Cached and uncached input are components of this total and must not be added to it again.',
    'Cached input tokens': 'The recorded portion of input served from cache. It is already included in input tokens.',
    'Uncached input tokens': 'The recorded input portion not served from cache. Together with cached input it forms the known input total.',
    'Output tokens': 'Recorded generated output volume. Token counts do not directly establish subscription spending.',
    'Shell commands': 'Recorded command executions. This is not a count of every tool action or provider request.',
    'Nonzero command exits': 'Recorded commands returning a nonzero exit code. A command error does not automatically mean the task failed.',
    'Delivery and source checks': 'Mechanical checks of declared deliverables and supported source files. They are separate from visual quality judgments.',
    'Source scope': 'The specific source operation verified: a static SVG fill edit, sampled browser playback, or a native Blender object edit. The scope does not establish whole-project editability, procedural-rule correctness, rigging or target-application acceptance.',
    'Ratings with enough evidence (%)': 'Recorded ratings assigned 0, 1 or 2 divided by all recorded ratings, including unknowns. An unmet requirement counts as known evidence, so this is not a success percentage.',
    'Rating counts': 'Counts of requirement ratings at 0, 1, 2 and insufficient evidence. They are not averaged into an overall score.',
    'Evaluation history': 'Earlier submitted evaluations of this benchmark. Comparing tested commits can show changes after skill edits when tasks, execution and review conditions match. Unevaluated commits have no point.',
    'Commit chart': 'Multiple recorded evaluations grouped by comparable conditions, with tested skill commits on the horizontal axis. An upload commit or an unmeasured change supplies no result.',
    'Technical provenance, verification and full records': 'Frozen identities, execution details and public JSON used to audit this report. Private logs, credentials and session identities are excluded.',
    'Scope and limitations': 'The measured capabilities and evidence gaps that bound the conclusions. A narrowly verified operation is not a general quality certification.',
    'Completed': 'The recorded execution finished. Review quality is reported separately.',
    'Failed': 'The execution record reports a failure. Partial output evidence may still be reviewed.',
    'Stopped': 'Execution was interrupted. Missing later turns remain unscored.',
    'Not started': 'No execution attempt was recorded for this planned run. It remains in the coverage denominator.',
    'Unreviewed': 'No applicable frozen review is available. This is not a zero or a pass.',
}

ALIASES = {
    'Runs': 'Run', 'Trial': 'Run', 'Requirement ratings': 'Requirement rating',
    'Recorded requirement ratings': 'Requirement rating', 'Effort': 'Reasoning effort',
    'Backend': 'Execution backend', 'artifact-only': 'Artifact-only', 'notes-process': 'Notes-process',
    'Frozen snapshot SHA-256 · commit not recorded': 'Snapshot hash',
    'Cached input': 'Cached input tokens', 'Uncached input': 'Uncached input tokens',
    'Command executions': 'Shell commands', 'Nonzero commands': 'Nonzero command exits',
    'View skill changes': 'Skill changes', 'Version comparison': 'Candidate versus baseline',
    '0 Not met': '0 · Not met', '1 Partly met': '1 · Partly met', '2 Met': '2 · Met',
    'Ratings with enough evidence': 'Ratings with enough evidence (%)',
}

GLOSSARY_GROUPS = (
    ('Core terms', ('Case', 'Run', 'Repeat', 'Turn', 'Candidate', 'Baseline',
                    'Requirement rating', 'Not enough evidence', 'Snapshot hash', 'Git commit SHA')),
    ('Report headings', (
        'Evaluation setup', 'Versions and filters', 'More filters', 'Skill changes',
        'Execution and review coverage', 'Runs by tested version', 'Comparison by case',
        'Rating distributions by evaluated condition', 'Requirement ratings by evaluated condition',
        'Time and usage', 'Known token subtotals',
        'Candidate versus baseline', 'Version comparison', 'Paired judgments',
        'Inspect the case evidence', 'Actual reference inputs through this turn',
        'Matched output images', 'Additional images',
        'Delivery and source checks', 'Evaluation history', 'All submitted experiments',
        'Recorded ratings with matching conditions',
        'Technical provenance, verification and full records', 'Withheld previews',
        'Full public JSON', 'Scope and limitations',
    )),
)
GLOSSARY_TERMS = {key: TERMS[key] for _, keys in GLOSSARY_GROUPS for key in keys}


def render_glossary() -> str:
    tables = []
    for index, (label, keys) in enumerate(GLOSSARY_GROUPS):
        rows = ''.join('<tr><th scope="row">' + html.escape(key) + '</th><td>'
                       + html.escape(GLOSSARY_TERMS[key]) + '</td></tr>' for key in keys)
        extra = '<tbody id="glossary-extra-headings"></tbody>' if index == 1 else ''
        tables.append('<h4>' + html.escape(label) + '</h4><div class="table-scroll"><table>'
                      '<thead><tr><th>Term or heading</th><th>Meaning</th></tr></thead><tbody>'
                      + rows + '</tbody>' + extra + '</table></div>')
    return ('<aside id="glossary" aria-label="Report glossary"><details><summary>Glossary</summary>'
            + ''.join(tables) + '</details><p class="caption">Only core terms and report headings '
            'listed here use dotted-underlined help. Hover, focus or tap to read the same definition.</p></aside>')


HELP_STYLE = r"""
[hidden]{display:none!important}#glossary{margin:12px 0 20px;background:var(--ivory);border:1px solid var(--border);border-radius:4px;padding:10px 14px}
#glossary details{margin:0;padding:0;border:0}#glossary p{margin:6px 0 0;font-size:12px}#glossary h4{font-size:14px;margin:14px 0 6px}#glossary th:first-child{width:32%}#glossary table{font-size:13px}
.term-help{display:inline;border-bottom:1px dotted currentColor;background:#24587708;cursor:help;text-decoration:none;border-radius:2px}
.term-help:hover,.term-help:focus-visible{background:#24587718;outline-offset:3px}.help-tooltip{position:fixed;z-index:1000;max-width:min(340px,calc(100vw - 24px));width:max-content;padding:12px 14px;border:1px solid #b5c8d7;border-radius:5px;background:#f8fbfd;color:#21354a;box-shadow:0 4px 16px #14141320;font:13px/1.55 var(--ui-font);overflow:auto;max-height:calc(100vh - 24px)}
.help-tooltip strong{display:block;margin-bottom:5px}.help-tooltip p{margin:0;font-size:13px}.footer>details{font-size:13px}.footer .technical{font-size:13px}
"""

HELP_SCRIPT = 'const HELP_TERMS=' + json.dumps(GLOSSARY_TERMS, ensure_ascii=True) + ';\nconst HELP_ALIASES=' + json.dumps({alias: key for alias, key in ALIASES.items() if key in GLOSSARY_TERMS}, ensure_ascii=True) + r""";
const helpDefinitions=new Map(Object.entries(HELP_TERMS).map(([key,value])=>[key.toLowerCase(),{label:key,definition:value}]));
for(const [alias,key] of Object.entries(HELP_ALIASES))if(!helpDefinitions.has(alias.toLowerCase()))helpDefinitions.set(alias.toLowerCase(),helpDefinitions.get(key.toLowerCase()));
function helpDefinition(text){
  const label=text.trim().replace(/^\d+(?:\.\d+)*\.\s*/, '').replace(/\s+/g,' ');
  return helpDefinitions.get(label.toLowerCase())||null;
}
let helpDynamicHeadingKeys=[];
function syncHeadingGlossary(){
  const body=document.getElementById('glossary-extra-headings');if(!body)return;
  for(const key of helpDynamicHeadingKeys)helpDefinitions.delete(key);
  helpDynamicHeadingKeys=[];body.replaceChildren();
  for(const heading of document.querySelectorAll('.case-title,[id="history-timeline"] h3,[id="commit-chart"] h3')){
    if(heading.closest('[hidden]'))continue;
    const label=heading.textContent.trim().replace(/^\d+(?:\.\d+)*\.\s*/, '').replace(/\s+/g,' ');
    if(!label||helpDefinition(label))continue;
    const definition=heading.classList.contains('case-title')
      ?'References, outputs and frozen judgments for this task. Select the same repeat and turn to compare tested versions.'
      :heading.closest('#history-timeline')
        ?HELP_TERMS['All submitted experiments']:HELP_TERMS['Evaluation history'];
    helpDefinitions.set(label.toLowerCase(),{label,definition});helpDynamicHeadingKeys.push(label.toLowerCase());
    const row=document.createElement('tr'),name=document.createElement('th'),meaning=document.createElement('td');
    name.setAttribute('scope','row');name.textContent=label;meaning.textContent=definition;row.append(name,meaning);body.append(row);
  }
}
let helpActive=null,helpPinned=false,helpHideTimer=null;
function hideHelp(){
  clearTimeout(helpHideTimer);
  const tooltip=document.getElementById('term-tooltip');if(tooltip)tooltip.hidden=true;
  if(helpActive)helpActive.removeAttribute('aria-describedby');helpActive=null;helpPinned=false;
}
function showHelp(target,pinned=false){
  clearTimeout(helpHideTimer);
  const explanation=helpDefinition(target.dataset.helpLabel||target.textContent);if(!explanation)return;
  if(helpActive&&helpActive!==target)helpActive.removeAttribute('aria-describedby');helpActive=target;helpPinned=pinned;
  const tooltip=document.getElementById('term-tooltip');document.getElementById('term-tooltip-label').textContent=explanation.label;document.getElementById('term-tooltip-definition').textContent=explanation.definition;
  tooltip.hidden=false;target.setAttribute('aria-describedby','term-tooltip');
  const anchor=target.getBoundingClientRect(),box=tooltip.getBoundingClientRect();
  const left=Math.max(12,Math.min(anchor.left,innerWidth-box.width-12));
  const below=anchor.bottom+8,top=below+box.height<=innerHeight-12?below:Math.max(12,anchor.top-box.height-8);
  tooltip.style.left=left+'px';tooltip.style.top=top+'px';
}
function decorateHelp(){
  if(helpActive&&!helpActive.isConnected)hideHelp();
  syncHeadingGlossary();
  const selector='main>section h2,main>section h3,main>section summary,.case-title,.reference-strip h4,.atom-section h4,.footer summary,.footer h4,.primary-filters>label,.case-controls label,.version-role';
  for(const element of document.querySelectorAll(selector)){
    if(element.closest('.term-help,#glossary,#term-tooltip,pre,code,.task-text,.reason,.requirement,.skill-diff-body,.atom-table,.output-cell,.extra-image-column,.source-check-column'))continue;
    for(const child of Array.from(element.childNodes)){
      if(child.nodeType!==Node.TEXT_NODE||!child.textContent.trim())continue;
      const explanation=helpDefinition(child.textContent);if(!explanation)continue;
      const term=document.createElement('span');term.className='term-help';term.tabIndex=0;term.setAttribute('role','button');term.setAttribute('aria-label','Explain '+explanation.label);term.dataset.helpLabel=explanation.label;term.textContent=child.textContent;
      child.replaceWith(term);
    }
  }
}
document.addEventListener('pointerover',event=>{const term=event.target.closest?.('.term-help');if(term&&!helpPinned)showHelp(term);});
document.addEventListener('pointerout',event=>{
  if(helpPinned)return;const term=event.target.closest?.('.term-help'),next=event.relatedTarget;
  if(term&&(!next||!term.contains(next))&&!document.getElementById('term-tooltip').contains(next))helpHideTimer=setTimeout(hideHelp,150);
});
document.getElementById('term-tooltip').addEventListener('pointerenter',()=>clearTimeout(helpHideTimer));
document.getElementById('term-tooltip').addEventListener('pointerleave',()=>{if(!helpPinned)helpHideTimer=setTimeout(hideHelp,150);});
document.addEventListener('focusin',event=>{const term=event.target.closest?.('.term-help');if(term)showHelp(term);});
document.addEventListener('focusout',event=>{if(helpActive&&!helpPinned&&!helpActive.contains(event.relatedTarget))hideHelp();});
document.addEventListener('click',event=>{
  const term=event.target.closest?.('.term-help');if(term){
    if(term.closest('summary,label,a,button')){showHelp(term);return;}
    event.preventDefault();event.stopPropagation();if(helpActive===term&&helpPinned)hideHelp();else showHelp(term,true);
  }
  else if(!event.target.closest?.('#term-tooltip'))hideHelp();
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){hideHelp();return;}
  const term=event.target.closest?.('.term-help');if(term&&(event.key==='Enter'||event.key===' ')){event.preventDefault();if(helpActive===term&&helpPinned)hideHelp();else showHelp(term,true);}
});
window.addEventListener('resize',hideHelp);
window.addEventListener('scroll',event=>{if(!event.target.closest?.('#term-tooltip'))hideHelp();},{capture:true,passive:true});
"""
