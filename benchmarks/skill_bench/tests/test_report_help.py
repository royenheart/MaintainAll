"""Context help preserves evidence semantics and uses fixed English definitions."""
import json
import re
import shutil
import subprocess
import unittest

from skill_bench.report_help import ALIASES, GLOSSARY_TERMS, HELP_SCRIPT, TERMS, render_glossary


class ReportHelpTests(unittest.TestCase):
    def test_aliases_resolve_and_core_terms_have_plain_definitions(self):
        for key in ALIASES.values():
            self.assertIn(key, TERMS)
        for key in ('Case', 'Run', 'Repeat', 'Turn', 'Candidate', 'Baseline',
                    'Requirement rating', 'Snapshot hash', 'Git commit SHA'):
            self.assertTrue(TERMS[key])
        self.assertIn('not a success percentage', TERMS['Ratings with enough evidence (%)'])
        self.assertIn('not automatically a zero', TERMS['Failed or stopped runs'])
        self.assertIn('neither zero nor a pass', TERMS['Not enough evidence'])
        self.assertIn('at least one judgment', TERMS['Runs with independent reviews'])

    def test_glossary_is_a_compact_disclosure_with_a_real_table(self):
        document = render_glossary()
        self.assertIn('<aside id="glossary"', document)
        self.assertIn('<summary>Glossary</summary>', document)
        self.assertIn('<table>', document)
        self.assertNotIn('<details open', document)
        self.assertEqual(document.count('<th scope="row">'), len(GLOSSARY_TERMS))
        for key in GLOSSARY_TERMS:
            self.assertIn('<th scope="row">' + key + '</th>', document)
        self.assertIn('Report headings', document)
        self.assertIn('glossary-extra-headings', document)
        self.assertNotRegex(document, r'[\u4e00-\u9fff]')

    @unittest.skipUnless(shutil.which('node'), 'Node is required for help decoration checks')
    def test_rerender_does_not_nest_help_and_new_labels_receive_definitions(self):
        # Minimal DOM boundary: repeated selectors also return the newly added spans.
        dom = r"""
const Node={TEXT_NODE:3};
class Text {
  constructor(text){this.nodeType=3;this.textContent=text;}
  replaceWith(next){const p=this.parent;next.parent=p;p.childNodes[p.childNodes.indexOf(this)]=next;}
}
class Element {
  constructor(text='',className=''){this.className=className;this.dataset={};this.childNodes=[];this.textContent=text;}
  set textContent(text){const child=new Text(text);child.parent=this;this.childNodes=[child];}
  get textContent(){return this.childNodes.map(child=>child.textContent).join('');}
  closest(selectors){
    for(let n=this;n;n=n.parent)
      if(selectors.split(',').some(s=>s.trim()==='.'+n.className))return n;
    return null;
  }
  setAttribute(){}
  addEventListener(){}
}
const roots=[new Element('Candidate'),new Element('Turn','reason'),new Element('Completed runs'),new Element('Model: model'),new Element('Better'),new Element('1.1. Versions and filters'),new Element('Version comparison')];
const walk=n=>[n,...n.childNodes.filter(c=>c instanceof Element).flatMap(walk)];
const tooltip=new Element();
const document={querySelectorAll:()=>roots.flatMap(walk),createElement:()=>new Element(),
  getElementById:id=>id==='term-tooltip'?tooltip:null,addEventListener(){}};
const window={addEventListener(){}};
"""
        exercise = r"""
decorateHelp();decorateHelp();
roots.push(new Element('Turn'));
decorateHelp();decorateHelp();
const terms=roots.flatMap(walk).filter(n=>n.className==='term-help');
console.log(JSON.stringify({labels:terms.map(n=>n.dataset.helpLabel),
  nested:terms.some(n=>n.parent.className==='term-help'),
  protectedText:roots[1].textContent,protectedTerms:walk(roots[1]).length-1,
  originalLabels:[roots[0].textContent,roots.at(-1).textContent]}));
"""
        result = subprocess.run([shutil.which('node'), '-e', dom + HELP_SCRIPT + exercise],
                                capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(json.loads(result.stdout), {
            'labels': ['Candidate', 'Versions and filters', 'Version comparison', 'Turn'], 'nested': False,
            'protectedText': 'Turn', 'protectedTerms': 0, 'originalLabels': ['Candidate', 'Turn'],
        })

    def test_tooltip_definitions_are_exactly_the_glossary_allowlist(self):
        exported, _ = json.JSONDecoder().raw_decode(HELP_SCRIPT.split('const HELP_TERMS=', 1)[1])
        self.assertEqual(exported, GLOSSARY_TERMS)
        for label in ('Completed runs', 'Failed', 'Better', 'Input tokens', 'Model'):
            self.assertNotIn(label, exported)

    def test_chart_heading_labels_have_glossary_definitions(self):
        from skill_bench.report_charts import CHART_SCRIPT
        titles = re.findall(r"stackedChart\('([^']+)'", CHART_SCRIPT)
        self.assertGreaterEqual(len(titles), 4)
        self.assertTrue(set(titles).issubset(GLOSSARY_TERMS), set(titles) - GLOSSARY_TERMS.keys())
