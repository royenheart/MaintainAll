"""Independent CDP action timing, ordering and cleanup in the offline namespace."""
from pathlib import Path
import hashlib,json,os,shutil,sys,tempfile,unittest
SRC=Path(__file__).resolve().parents[1]/'src'
sys.path.insert(0,str(SRC))
DRIVER=SRC/'skill_bench/browser_driver.py'
from skill_bench.browser_namespace import command,run
from runtime_support import CHROME
HTML='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font:18px sans-serif}button{padding:10px;margin:10px}#carrier{position:absolute;left:20px;top:150px;width:80px;height:50px;background:#087fa4;transition:transform 600ms linear}body.a #carrier{transform:translateX(180px)}</style><button id="a">A</button><button id="b">B</button><p id="state">Before</p><div id="carrier"></div><script>for(const name of ['a','b'])document.getElementById(name).addEventListener('click',()=>{document.body.classList.toggle('a',name==='a');document.getElementById('state').textContent=name.toUpperCase()})</script>'''
HARNESS='''from pathlib import Path
import importlib.util,json,os,sys,threading,time
work=Path(sys.argv[1]);cfg=json.loads((work/'inputs/config.json').read_text())
spec=importlib.util.spec_from_file_location('timing_driver',work/'tools/browser_driver.py');D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)
pids=[];original=D.PipeBrowser
class RecordingBrowser(original):
 def __init__(self,*args):super().__init__(*args);pids.append(self.process.pid)
 def command(self,method,*args,**kwargs):
  if cfg.get('actor_delay') and 'perform_actions' in threading.current_thread().name:time.sleep(.03)
  if cfg.get('screenshot_delay') and method=='Page.captureScreenshot':time.sleep(cfg['screenshot_delay'])
  return super().command(method,*args,**kwargs)
D.PipeBrowser=RecordingBrowser
proof=D.capture(work/'inputs/source.html',Path('/capture/evidence'),Path(sys.argv[2]),cfg['spec'],timeout=cfg.get('driver_timeout',10))
def alive(pid):
 try:os.kill(pid,0);return True
 except ProcessLookupError:return False
summary={'capture':proof,'live_threads_after_capture':[t.name for t in threading.enumerate() if t is not threading.main_thread()],'browser_pids':pids,'live_browser_pids_after_capture':[p for p in pids if alive(p)]}
Path('/capture/summary.json').write_text(json.dumps(summary,indent=2)+'\\n')
print(json.dumps({'passed':proof['passed'],'live_threads_after_capture':summary['live_threads_after_capture'],'live_browser_pids_after_capture':summary['live_browser_pids_after_capture']}))
'''

def exercise(root,name,cfg,html=HTML,outer_timeout=20):
    case=root/name
    version=1
    while case.exists():
        case=root/(name+'-v'+str(version));version+=1
    case.mkdir();workspace=case/'workspace';(workspace/'inputs').mkdir(parents=True);(workspace/'tools').mkdir()
    (workspace/'inputs/source.html').write_text(html);(workspace/'inputs/config.json').write_text(json.dumps(cfg))
    shutil.copyfile(DRIVER,workspace/'tools/browser_driver.py')
    stage=case/'stage';stage.mkdir();(stage/'output').mkdir();frozen=stage/'frozen';shutil.copytree(workspace,frozen)
    harness=case/'exercise.py';harness.write_text(HARNESS)
    try:
        stdout=run(command(stage,frozen,workspace,CHROME.parent,['/usr/bin/python3','-I','/timing-exercise.py',str(workspace),str(CHROME)],extra_mounts=[(harness,'/timing-exercise.py')]),outer_timeout)
        summary=json.loads((stage/'output/summary.json').read_text())
        summary['resource_boundary']=stdout.resource_boundary
    except TimeoutError as exc:
        summary={'outer_timeout':True,'resource_boundary':exc.resource_boundary}
    (case/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

def spec(profiles=None,actions=None,samples=None):
    return {'samples_ms':samples or [0,200,800],'profiles':profiles or ['desktop'],'selectors':['#carrier','#state'],
            'actions':actions or [{'type':'click','selector':'#a','time_ms':0},{'type':'click','selector':'#b','time_ms':800}]}

@unittest.skipUnless(CHROME.is_file() and Path('/usr/bin/bwrap').is_file() and (Path('/run/user')/str(os.getuid())/'bus').is_socket(), 'Optional offline Chromium/user-scope runtimes are unavailable.')
class BrowserActionTiming(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='skill-action-timing-')
        self.root=Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def test_geometry_trace_samples_continue_while_screenshot_is_slow(self):
        capture_spec = spec(actions=[{'type':'click','selector':'#a','time_ms':100}], samples=[0,500,1000])
        capture_spec['trace_samples_ms'] = list(range(0,1001,50))
        result = exercise(self.root,'independent-trace',{'spec':capture_spec,'screenshot_delay':.7})
        self.assertTrue(result['capture']['passed'],result)
        trace = result['capture']['trace_samples']
        self.assertEqual(len(trace),21,result)
        self.assertEqual([row['requested_time_ms'] for row in trace],capture_spec['trace_samples_ms'])
        self.assertLess(trace[-1]['sample_completed_ms'],1400,result)
        middle = [row for row in trace if 200 <= row['requested_time_ms'] <= 400]
        self.assertTrue(all(20 < row['elements'][0]['bounds']['x'] < 200 for row in middle),result)
        self.assertTrue(all(row['time_ms'] <= row['sample_completed_ms'] for row in trace),result)
        self.assertEqual(result['capture']['scope_version'],3)
        self.assertEqual(result['live_threads_after_capture'],[],result)
        self.assertEqual(result['live_browser_pids_after_capture'],[],result)

    def test_slow_screenshots_do_not_delay_trusted_interruption(self):
        actions=[{'type':'click','selector':'#a','time_ms':100},{'type':'click','selector':'#b','time_ms':220}]
        result=exercise(self.root,'slow-screenshot',{'spec':spec(actions=actions,samples=[0,80,150,220,400,700]),'screenshot_delay':.7})
        self.assertTrue(result['capture']['passed'],result)
        clicks=[e for e in result['capture']['input_events'] if e['type']=='click']
        self.assertEqual([e['target'] for e in clicks],['a','b'],result)
        self.assertLess(abs(clicks[1]['time_ms']-clicks[0]['time_ms']-120),50,result)
        before=next(s for s in result['capture']['action_snapshots'] if s['requested_time_ms']==220)
        carrier=next(e for e in before['elements'] if e['selector']=='#carrier')
        self.assertGreater(carrier['bounds']['x'],20,result)
        self.assertLess(carrier['bounds']['x'],200,result)
        self.assertEqual(result['live_threads_after_capture'],[],result)
        self.assertEqual(result['live_browser_pids_after_capture'],[],result)

    def test_final_sample_waits_for_due_action_and_records_final_trusted_event(self):
        result=exercise(self.root,'boundary-last-sample',{'spec':spec(),'actor_delay':True})
        self.assertTrue(result['capture']['passed'],result)
        self.assertEqual(result['capture']['dom_samples'][0]['elements'][1]['text'],'A',result)
        self.assertEqual(result['capture']['dom_samples'][-1]['elements'][1]['text'],'B',result)
        self.assertEqual([e['target'] for e in result['capture']['input_events'] if e['type']=='click'],['a','b'],result)
        self.assertEqual(result['live_threads_after_capture'],[],result)
        self.assertEqual(result['live_browser_pids_after_capture'],[],result)
    def test_missing_selector_cancels_future_actions_and_cleans_all_threads(self):
        actions=[{'type':'click','selector':'#missing','time_ms':100},{'type':'click','selector':'#b','time_ms':4000}]
        result=exercise(self.root,'boundary-missing-selector',{'spec':spec(actions=actions,samples=[0,5000])})
        self.assertFalse(result['capture']['passed'],result)
        self.assertIn('missing',result['capture']['failure'],result)
        self.assertEqual(result['capture']['actions'],[],result)
        self.assertEqual(result['live_threads_after_capture'],[],result)
        self.assertEqual(result['live_browser_pids_after_capture'],[],result)
    def test_multi_profile_order_and_mobile_fault_do_not_cross_navigation(self):
        actions=[{'type':'click','selector':'#a','time_ms':100},{'type':'click','selector':'#b','time_ms':450}]
        common={'spec':spec(profiles=['desktop','mobile','reduced_motion'],actions=actions,samples=[0,200,450])}
        positive=exercise(self.root,'boundary-multi-profile',common)
        self.assertTrue(positive['capture']['passed'],positive)
        self.assertEqual([a['profile'] for a in positive['capture']['actions']],['desktop','desktop','mobile','mobile','reduced_motion','reduced_motion'],positive)
        for p in ['desktop','mobile','reduced_motion']:
            states=[s['elements'][1]['text'] for s in positive['capture']['dom_samples'] if s['profile']==p]
            self.assertEqual(states,['Before','A','B'],positive)
            clicks=[e['target'] for e in positive['capture']['input_events'] if e['type']=='click' and e['profile']==p]
            self.assertEqual(clicks,['a','b'],positive)
        negative=exercise(self.root,'boundary-mobile-fault',common,HTML+'<style>@media(max-width:500px){#b{display:none}}</style>')
        self.assertFalse(negative['capture']['passed'],negative)
        self.assertEqual([a['profile'] for a in negative['capture']['actions']],['desktop','desktop','mobile'],negative)
        self.assertEqual(negative['live_threads_after_capture'],[],negative)
        self.assertEqual(negative['live_browser_pids_after_capture'],[],negative)
    def test_inner_deadline_and_outer_scope_timeout_leave_no_children(self):
        inner=exercise(self.root,'boundary-inner-timeout',{'spec':spec(actions=[{'type':'click','selector':'#a','time_ms':4000}],samples=[0,5000]),'driver_timeout':3,'screenshot_delay':3.3})
        self.assertFalse(inner['capture']['passed'],inner)
        self.assertIn('deadline',inner['capture']['failure'],inner)
        self.assertEqual(inner['live_threads_after_capture'],[],inner)
        self.assertEqual(inner['live_browser_pids_after_capture'],[],inner)
        outer=exercise(self.root,'boundary-outer-timeout',{'spec':spec(actions=[{'type':'click','selector':'#a','time_ms':4000}],samples=[0,5000]),'driver_timeout':10},outer_timeout=1.5)
        self.assertTrue(outer['outer_timeout'],outer)
        self.assertTrue(outer['resource_boundary']['cleanup_verified'],outer)

if __name__=='__main__':unittest.main(verbosity=2)
