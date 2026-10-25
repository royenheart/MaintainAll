"""Independent optional action/audio capability acceptance in the offline namespace.

Trusted fixtures travel with framework snapshots. This doctor never invokes a model
or launches generated HTML on the host; each fixture goes through namespace_capture.
Passing establishes bounded observation capability, not aesthetic or causal quality.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import tempfile

from .browser_driver import safe_path
from .browser_namespace import namespace_capture

SCOPE = 'bounded real input, sampled motion and media signal; not aesthetic or application causality quality'
SAMPLES = [0, 100, 220, 380, 560, 800, 1100, 1400]
MOTION_HTML = """<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#f4f6f8;font:20px sans-serif}button{margin:15px;padding:10px}
#carrier{position:absolute;left:30px;top:150px;width:80px;height:70px;background:#087fa4;MOTION}
@keyframes travel{to{transform:translateX(240px)}}
</style><button id="choose">Choose</button><p id="state">Before</p>
<div id="carrier" data-claimed-motion="smooth continuous travel"></div><script>
document.getElementById('choose').addEventListener('click',()=>{document.getElementById('state').textContent='After'});
globalThis.claimedMotionQuality='perfect';
</script>"""
AUDIO_HTML = """<!doctype html><meta charset="utf-8"><style>
body{font:20px sans-serif;background:#f4f6f8}button,input{margin:10px;padding:10px}
#meter{height:50px;width:20px;background:#087fa4;margin:30px}
</style><input type="file" id="file" accept="audio/wav"><button id="play">Play</button>
<p id="state">Waiting</p><div id="meter"></div><audio id="media"></audio><script>
const file=document.getElementById('file'),play=document.getElementById('play'),media=document.getElementById('media'),state=document.getElementById('state'),meter=document.getElementById('meter');
file.addEventListener('change',()=>{media.src=URL.createObjectURL(file.files[0]);media.load()});
play.addEventListener('click',async()=>{try{const context=new AudioContext(),analyser=context.createAnalyser(),source=context.createMediaElementSource(media);source.connect(analyser);analyser.connect(context.destination);await context.resume();const data=new Float32Array(analyser.fftSize);state.textContent='Analysis running';function tick(){analyser.getFloatTimeDomainData(data);const rms=Math.sqrt(data.reduce((sum,x)=>sum+x*x,0)/data.length);meter.style.width=(20+rms*800)+'px';requestAnimationFrame(tick)}tick()}catch(error){state.textContent='Analysis unavailable: static fallback';meter.style.width='20px'}await media.play()});
</script>"""
CLAIMED_AUDIO_HTML = """<!doctype html><meta charset="utf-8"><style>
body{font:20px sans-serif;background:#f4f6f8}button,input{margin:10px;padding:10px}
</style><input type="file" id="file"><button id="play">Play</button>
<p id="state">Claimed audio response</p><script>
document.getElementById('play').addEventListener('click',()=>{globalThis.claimedFFT={peak:440,rms:.2};globalThis.claimedPlayback=true});
</script>"""


def finite(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def temporal(result: dict) -> bool:
    frames = result.get('frames', [])
    times = [frame.get('time_ms') for frame in frames]
    return (len(frames) == len(SAMPLES) and all(finite(value) for value in times)
            and times == sorted(times) and times[-1] - times[0] >= 1000
            and [f.get('requested_time_ms') for f in frames] == SAMPLES)


def elements(result: dict, selector: str) -> list[dict]:
    return [element for sample in result.get('dom_samples', []) for element in sample.get('elements', [])
            if element.get('selector') == selector and not element.get('missing')]


def moved(result: dict) -> bool:
    points = [e.get('bounds', {}).get('x') for e in elements(result, '#carrier')]
    return len(points) >= 3 and all(finite(value) for value in points) and max(points) - min(points) >= 30


def trusted_click(result: dict, target: str) -> bool:
    return any(e.get('type') == 'click' and e.get('isTrusted') is True and e.get('target') == target for e in result.get('input_events', []))


def state_changed(result: dict) -> bool:
    states = elements(result, '#state')
    return bool(states) and states[0].get('text') == 'Before' and states[-1].get('text') == 'After'


def media_samples(result: dict) -> list[dict]:
    return [node for sample in result.get('audio_samples', []) for node in sample.get('media', []) if node.get('playing') is True]


def playback_progress(result: dict) -> bool:
    timelines = {}
    for node in media_samples(result):
        if finite(node.get('current_time_seconds')):
            timelines.setdefault(node.get('observer_id'), []).append(node['current_time_seconds'])
    return any(len(times) >= 2 and max(times) - min(times) >= .5 for times in timelines.values())


def measured_signal(result: dict, mode: str) -> bool:
    signals = [node.get('signal', {}) for node in media_samples(result)]
    signals = [s for s in signals if s.get('status') == 'measured' and s.get('audio_context_state') == 'running' and s.get('audio_track_count', 0) > 0 and finite(s.get('rms'))]
    if not playback_progress(result) or len(signals) < 2:
        return False
    if mode == 'tone':
        return any(finite(s.get('peak_frequency_hz')) and abs(s['peak_frequency_hz'] - 440) <= 32 and s['rms'] > .05 for s in signals)
    return mode == 'silence' and all(s['rms'] < .001 for s in signals)


def action_doctor(workspace: Path, tools: dict) -> dict:
    """Return separate optional capability results and persistent relative evidence.

    Tools must already be staged beneath workspace/tools. Six short desktop captures
    use only evaluator fixtures and fixed declarative specs, with zero model calls.
    Failure of either optional capability leaves the other result independently usable.
    """
    result = {'action_trace_capture': {'passed': False, 'checks': {}, 'failures': [], 'evidence': []},
              'web_audio_probe': {'passed': False, 'checks': {}, 'failures': [], 'evidence': []},
              'generation_calls': 0, 'scope': SCOPE}
    try:
        workspace = safe_path(Path(workspace))
        inputs = safe_path(workspace / 'inputs', exists=False)
        inputs.mkdir(mode=0o700, exist_ok=True)
        fixture_dir = Path(tempfile.mkdtemp(prefix='action-acceptance-', dir=inputs))
        output = workspace / fixture_dir.name
        output.mkdir(mode=0o700)
    except (OSError, ValueError) as exc:
        for name in ('action_trace_capture', 'web_audio_probe'):
            result[name]['failures'].append({'scenario': 'setup', 'failure': str(exc)[:500]})
        return result

    def capture(name, html, spec, capability):
        source = fixture_dir / (name + '.html')
        destination = output / name
        try:
            source.write_text(html, encoding='utf-8')
            proof = namespace_capture(workspace, source, destination, tools, spec, timeout=25)
            path = destination / 'evidence.json'
            if path.is_file():
                result[capability]['evidence'].append({'scenario': name, 'path': str(path.relative_to(workspace)),
                                                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            return proof
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            result[capability]['failures'].append({'scenario': name, 'failure': str(exc)[:500]})
            return {}

    action_spec = {'samples_ms': SAMPLES, 'profiles': ['desktop'], 'selectors': ['#carrier', '#state'],
                   'actions': [{'type': 'click', 'selector': '#choose', 'time_ms': 150}]}
    moving = capture('moving', MOTION_HTML.replace('MOTION', 'animation:travel .8s linear infinite alternate'), action_spec, 'action_trace_capture')
    static = capture('static', MOTION_HTML.replace('MOTION', ''), action_spec, 'action_trace_capture')
    action_checks = {'captures_completed': bool(moving.get('passed') and static.get('passed')),
                     'dense_actual_times': temporal(moving) and temporal(static),
                     'trusted_click_observed': trusted_click(moving, 'choose') and trusted_click(static, 'choose'),
                     'expected_dom_change': state_changed(moving) and state_changed(static),
                     'moving_carrier_observed': moved(moving),
                     'claimed_static_motion_rejected': bool(static.get('passed')) and len(elements(static, '#carrier')) == len(SAMPLES) and not moved(static)}
    result['action_trace_capture']['checks'] = action_checks
    result['action_trace_capture']['passed'] = all(action_checks.values())

    audio = {}
    for mode in ('tone', 'silence', 'unavailable', 'claim'):
        spec = {'samples_ms': SAMPLES, 'profiles': ['desktop'], 'selectors': ['#meter', '#state'],
                'audio_probe': {'mode': mode if mode != 'claim' else 'tone', 'file_input_selector': '#file', 'play_button_selector': '#play'}}
        audio[mode] = capture(mode, AUDIO_HTML if mode != 'claim' else CLAIMED_AUDIO_HTML, spec, 'web_audio_probe')
    unavailable = audio['unavailable']
    fallback_states = elements(unavailable, '#state')
    claim_measurements = audio['claim'].get('audio_probe', {}).get('measurements', [])
    audio_checks = {'captures_completed': all(bool(proof.get('passed')) for proof in audio.values()),
                    'actual_file_inputs_dispatched': all(proof.get('audio_probe', {}).get('file_input_dispatched') is True for proof in audio.values()),
                    'trusted_play_clicks_observed': all(trusted_click(proof, 'play') for proof in audio.values()),
                    'tone_signal_measured': measured_signal(audio['tone'], 'tone'),
                    'silence_signal_measured': measured_signal(audio['silence'], 'silence'),
                    'fault_installed_before_navigation': unavailable.get('audio_probe', {}).get('analysis_fault', {}).get('installed_before_navigation') is True,
                    'unavailable_visible_fallback': bool(fallback_states) and fallback_states[-1].get('text') == 'Analysis unavailable: static fallback',
                    'fallback_media_still_playing': playback_progress(unavailable),
                    'no_media_claim_unverified': bool(audio['claim'].get('passed')) and not media_samples(audio['claim'])
                        and bool(claim_measurements) and all(m.get('status') == 'unverified' for m in claim_measurements)}
    result['web_audio_probe']['checks'] = audio_checks
    result['web_audio_probe']['passed'] = all(audio_checks.values())
    return result
