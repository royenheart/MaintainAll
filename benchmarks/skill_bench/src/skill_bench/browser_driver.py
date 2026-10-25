#!/usr/bin/env python3
"""Replay frozen local HTML through bounded Chromium CDP pipe evidence.

Run generated pages only inside the enclosing network-disabled namespace sandbox.
This driver does not create that sandbox. Browser --no-sandbox is required inside
the enclosing sandbox; no HTTP server, network debug port, host browser profile,
credentials, third-party Python package, or model call is used.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import select
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import wave

MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_FRAME_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_MESSAGE_BYTES = 16 * 1024 * 1024
MAX_SPEC_BYTES = 16 * 1024
MAX_SAMPLES = 48
MAX_TIMELINE_MS = 15000
AUDIO_SAMPLE_RATE = 16000
AUDIO_DURATION_SECONDS = 17
PROFILES = {'desktop': (1280, 800, False), 'mobile': (390, 844, False), 'reduced_motion': (1280, 800, True)}
SCOPE = 'sampled playback not full motion quality'
WORLD = 'maintainall-browser-evidence'
INPUT_OBSERVER = """(() => {
  globalThis.__maintainallEvents = [];
  for (const type of ['pointermove','pointerdown','pointerup','click','keydown','keyup','wheel']) {
    window.addEventListener(type, e => {
      if (!e.isTrusted) return;
      const a = globalThis.__maintainallEvents;
      if (a.length < 80) a.push({type:e.type,isTrusted:e.isTrusted,key:(e.key || '').slice(0,24),time_ms:performance.now(),target:(e.target?.id || e.target?.tagName || '').slice(0,160)});
    }, {capture:true,passive:true});
  }
})()"""
AUDIO_FAULT = """(() => {
  const seen=new Set();
  for (const name of ['AudioContext','webkitAudioContext']) {
    const Context=globalThis[name];
    if (!Context) continue;
    if(!seen.has(Context)){
      seen.add(Context);
      Object.defineProperty(Context.prototype,'createAnalyser',{configurable:false,writable:false,
        value:function(){throw new DOMException('Evaluator audio analysis unavailable','NotSupportedError')}});
    }
    Object.defineProperty(globalThis,name,{configurable:false,writable:false,value:Context});
  }
})()"""
AUDIO_OBSERVER = """(() => {
  const state=globalThis.__maintainallAudio ||= {context:null,nodes:new WeakMap(),identities:new WeakMap(),nextId:0};
  const get=(node,key)=>Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,key).get.call(node);
  return {scope:'sampled media-element captureStream, not application FFT correctness',media:
    Array.from(document.querySelectorAll('audio,video')).slice(0,16).map(node=>{
      if(!state.identities.has(node))state.identities.set(node,++state.nextId);
      const current=get(node,'currentTime'),duration=get(node,'duration');
      const record={observer_id:state.identities.get(node),tag:node.tagName,id:node.id.slice(0,160),playing:!get(node,'paused')&&!get(node,'ended')&&get(node,'readyState')>=2,
        current_time_seconds:Number.isFinite(current)?current:null,duration_seconds:Number.isFinite(duration)?duration:null,
        ready_state:get(node,'readyState'),muted:get(node,'muted'),volume:get(node,'volume'),
        signal:{status:'unverified',reason:'media is not playing'}};
      if(!record.playing)return record;
      try {
        let binding=state.nodes.get(node);
        if(!binding){
          const capture=HTMLMediaElement.prototype.captureStream || HTMLMediaElement.prototype.mozCaptureStream;
          if(!capture){record.signal.reason='captureStream unavailable';return record}
          const stream=capture.call(node);
          if(!stream.getAudioTracks().length){stream.getTracks().forEach(track=>track.stop());record.signal.reason='captured stream has no audio track';return record}
          state.context ||= new AudioContext();
          state.context.resume().catch(()=>{});
          const analyser=state.context.createAnalyser();analyser.fftSize=2048;analyser.smoothingTimeConstant=0;
          const source=state.context.createMediaStreamSource(stream),silent=state.context.createGain();silent.gain.value=0;
          source.connect(analyser);analyser.connect(silent);silent.connect(state.context.destination);
          binding={stream,source,analyser,silent};state.nodes.set(node,binding);
        }
        if(state.context.state!=='running'){record.signal.reason='isolated audio context '+state.context.state;return record}
        const wave=new Float32Array(binding.analyser.fftSize),bins=new Float32Array(binding.analyser.frequencyBinCount);
        binding.analyser.getFloatTimeDomainData(wave);binding.analyser.getFloatFrequencyData(bins);
        const rms=Math.sqrt(wave.reduce((sum,x)=>sum+x*x,0)/wave.length);
        let index=0;for(let i=1;i<bins.length;i++)if(bins[i]>bins[index])index=i;
        const peak=Number.isFinite(bins[index])?bins[index]:null;
        record.signal={status:'measured',method:'isolated AudioContext captureStream analyser',audio_track_count:binding.stream.getAudioTracks().length,
          audio_context_state:state.context.state,sample_rate_hz:state.context.sampleRate,fft_size:binding.analyser.fftSize,
          rms:Number.isFinite(rms)?rms:null,peak_db:peak,peak_frequency_hz:peak===null?null:index*state.context.sampleRate/binding.analyser.fftSize};
      }catch(error){record.signal={status:'unverified',reason:('Audio observation unavailable: '+error.name).slice(0,160)}}
      return record;
    })};
})()"""


def safe_path(path: Path, *, exists: bool = True) -> Path:
    """Reject traversal and symlinks before resolving an explicit local path."""
    path = Path(path).expanduser()
    if '..' in path.parts:
        raise ValueError('Parent traversal is not allowed')
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('Symbolic paths are not allowed')
    if exists and not path.exists():
        raise ValueError(f'Missing local path: {path}')
    return path


def number(value, lower: float, upper: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'{name} must be between {lower} and {upper}')
    return value


def validate_spec(spec: dict | None = None) -> dict:
    """Validate a bounded declarative timeline; JavaScript actions are forbidden."""
    spec = {} if spec is None else spec
    if not isinstance(spec, dict) or set(spec) - {'samples_ms', 'actions', 'selectors', 'profiles', 'audio_probe', 'trace_samples_ms'}:
        raise ValueError('Capture spec accepts only samples_ms, actions, selectors, profiles, audio_probe, trace_samples_ms')
    samples = spec.get('samples_ms', [0, 250, 700])
    if not isinstance(samples, list) or not 2 <= len(samples) <= MAX_SAMPLES:
        raise ValueError('samples_ms must contain between 2 and 48 samples')
    for value in samples:
        number(value, 0, MAX_TIMELINE_MS, 'Sample time')
    if samples != sorted(set(samples)):
        raise ValueError('Sample times must be strictly increasing')
    profiles = spec.get('profiles', list(PROFILES))
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 3 or any(not isinstance(p, str) or p not in PROFILES for p in profiles) or len(set(profiles)) != len(profiles):
        raise ValueError('profiles must be a unique subset of desktop, mobile, reduced_motion')
    selectors = spec.get('selectors', [])
    if not isinstance(selectors, list) or len(selectors) > 24 or any(not isinstance(s, str) or not 1 <= len(s) <= 160 for s in selectors):
        raise ValueError('selectors must contain at most 24 bounded CSS selectors')
    actions = spec.get('actions', [])
    if not isinstance(actions, list) or len(actions) > 12:
        raise ValueError('actions must contain at most 12 real input actions')
    allowed = {'click', 'hover', 'key', 'scroll'}
    for action in actions:
        if not isinstance(action, dict) or action.get('type') not in allowed:
            raise ValueError('Only click, hover, key, scroll actions are supported')
        kind = action['type']
        keys = {'time_ms', 'type'} | ({'key'} if kind == 'key' else {'selector', 'x', 'y'}) | ({'delta_y'} if kind == 'scroll' else set())
        if set(action) - keys:
            raise ValueError('Unknown input action properties')
        number(action.get('time_ms'), 0, samples[-1], 'Action time')
        if kind == 'key':
            if not isinstance(action.get('key'), str) or not 1 <= len(action['key']) <= 24:
                raise ValueError('key actions require a bounded key name')
        else:
            selector = action.get('selector')
            if selector is not None:
                if not isinstance(selector, str) or not 1 <= len(selector) <= 160 or 'x' in action or 'y' in action:
                    raise ValueError('Pointer actions use one bounded selector OR x/y coordinates')
            else:
                number(action.get('x'), 0, 1279, 'Pointer x')
                number(action.get('y'), 0, 843, 'Pointer y')
        if kind == 'scroll':
            number(action.get('delta_y'), -1000, 1000, 'Wheel delta_y')
    if [a['time_ms'] for a in actions] != sorted(a['time_ms'] for a in actions):
        raise ValueError('Input actions must be ordered by time_ms')
    result = {'samples_ms': samples, 'profiles': profiles, 'selectors': selectors, 'actions': actions}
    if 'trace_samples_ms' in spec:
        trace = spec['trace_samples_ms']
        if not isinstance(trace, list) or not 2 <= len(trace) <= 128:
            raise ValueError('trace_samples_ms must contain between 2 and 128 samples')
        for value in trace:
            number(value, 0, samples[-1], 'Trace sample time')
        if trace != sorted(set(trace)):
            raise ValueError('Trace sample times must be strictly increasing')
        if not selectors:
            raise ValueError('Geometry traces require explicit bounded selectors')
        result['trace_samples_ms'] = trace
    if 'audio_probe' in spec:
        probe = spec['audio_probe']
        if not isinstance(probe, dict) or set(probe) != {'mode', 'file_input_selector', 'play_button_selector'}:
            raise ValueError('audio_probe requires only mode, file_input_selector, play_button_selector')
        if not isinstance(probe['mode'], str) or probe['mode'] not in {'tone', 'silence', 'unavailable'}:
            raise ValueError('audio_probe mode must be tone, silence, or unavailable')
        for key in ('file_input_selector', 'play_button_selector'):
            if not isinstance(probe[key], str) or not 1 <= len(probe[key]) <= 160:
                raise ValueError('Audio probe selectors must be bounded CSS selectors')
        result['audio_probe'] = dict(probe)
    return result


def write_audio_probe(output: Path, mode: str) -> dict:
    """Create one fixed evaluator-owned mono PCM stimulus, never supplied audio."""
    if mode not in {'tone', 'silence', 'unavailable'}:
        raise ValueError('Unknown audio stimulus mode')
    sample_count = AUDIO_SAMPLE_RATE * AUDIO_DURATION_SECONDS
    pcm = bytearray(sample_count * 2)
    if mode != 'silence':
        for index in range(sample_count):
            struct.pack_into('<h', pcm, index * 2, round(8192 * math.sin(2 * math.pi * 440 * index / AUDIO_SAMPLE_RATE)))
    path = output / 'audio-probe.wav'
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(AUDIO_SAMPLE_RATE)
        handle.writeframes(pcm)
    content = path.read_bytes()
    return {'path': path.name, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
            'format': 'PCM signed 16-bit little-endian', 'channels': 1, 'sample_rate_hz': AUDIO_SAMPLE_RATE,
            'sample_count': sample_count, 'duration_seconds': AUDIO_DURATION_SECONDS,
            'requested_signal': 'silence' if mode == 'silence' else 'tone', 'frequency_hz': None if mode == 'silence' else 440}


def png_dimensions(content: bytes) -> tuple[int, int]:
    if len(content) < 33 or content[:8] != b'\x89PNG\r\n\x1a\n' or content[12:16] != b'IHDR':
        raise ValueError('Browser did not return a valid PNG header')
    return struct.unpack('>II', content[16:24])


class PipeBrowser:
    """Multiplexed null-delimited CDP, with bounded events and process lifetime."""

    def __init__(self, browser: Path, root: Path, deadline: float):
        self.deadline = deadline
        self.next_id = 0
        self.buffer = b''
        self.events = []
        self.resource_requests = {}
        self.resource_failures = []
        self.resource_tracking_truncated = False
        self.stderr = bytearray()
        request_read, self.request_write = os.pipe()
        self.response_read, response_write = os.pipe()
        self.profile = root / 'profile'
        self.profile.mkdir(mode=0o700)
        temporary = root / 'tmp'; temporary.mkdir(mode=0o700)
        self.temporary_fd = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        launcher = ('import os,sys; a=int(sys.argv[1]); b=int(sys.argv[2]); '
                    'os.dup2(a,3); os.dup2(b,4); '
                    '[os.close(fd) for fd in {a,b} if fd not in {3,4}]; '
                    'os.execv(sys.argv[3],sys.argv[3:])')
        flags = ['--headless=new', '--no-sandbox', '--no-zygote', '--single-process', '--disable-gpu', '--in-process-gpu', '--use-gl=disabled', '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check',
                 '--disable-background-networking', '--disable-component-update', '--disable-default-apps', '--disable-extensions',
                 '--disable-sync', '--disable-breakpad', '--disable-crashpad-for-testing', '--metrics-recording-only', '--password-store=basic',
                 '--disable-features=Translate,MediaRouter,OptimizationHints,AutofillServerCommunication',
                 '--host-resolver-rules=MAP * ~NOTFOUND', '--force-device-scale-factor=1', '--remote-debugging-pipe',
                 f'--user-data-dir={self.profile}', 'about:blank']
        # Use a stable parent descriptor alias only when a long path would exceed
        # AF_UNIX's socket limit. /proc/self/cwd is unsuitable for child processes
        # that change cwd; this descriptor stays open until browser shutdown.
        temporary_name = str(temporary) if len(str(temporary)) <= 55 else f'/proc/{os.getpid()}/fd/{self.temporary_fd}'
        environment = {'PATH': '/usr/bin:/bin', 'HOME': str(self.profile), 'LANG': 'C.UTF-8', 'TMPDIR': temporary_name,
                       'XDG_CONFIG_HOME': str(self.profile), 'XDG_CACHE_HOME': str(self.profile)}
        try:
            self.process = subprocess.Popen([sys.executable, '-c', launcher, str(request_read), str(response_write), str(browser), *flags],
                                            pass_fds=(request_read, response_write), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.PIPE, env=environment, cwd=temporary, start_new_session=True)
        except BaseException:
            os.close(self.request_write); os.close(self.response_read)
            os.close(self.temporary_fd)
            raise
        finally:
            os.close(request_read); os.close(response_write)
        self.thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self.thread.start()
        self.condition = threading.Condition()
        self.write_lock = threading.Lock()
        self.responses = {}
        self.reader_failure = None
        self.reader_stop = threading.Event()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _drain_stderr(self):
        while data := self.process.stderr.read1(4096):
            room = 65536 - len(self.stderr)
            if room > 0:
                self.stderr.extend(data[:room])

    def _track(self, message):
        if message.get('method') == 'Runtime.exceptionThrown' and len(self.events) < 20:
            self.events.append({'method':message['method'],'params':{'exceptionDetails':{'text':message.get('params',{}).get('exceptionDetails',{}).get('text','')[:200]}}})
        if message.get('method') == 'Network.requestWillBeSent':
            p=message.get('params',{})
            if len(self.resource_requests)<256:self.resource_requests[p.get('requestId')]=p.get('request',{}).get('url','')[:1024]
            else:self.resource_tracking_truncated=True
        if message.get('method') == 'Network.loadingFailed':
            p=message.get('params',{});url=self.resource_requests.get(p.get('requestId'),'')
            if len(self.resource_failures)<80:self.resource_failures.append({'url':url,'local':url.startswith('file:'),'blocked_external':url.startswith(('http:','https:','ws:','wss:','ftp:')) and p.get('blockedReason')=='inspector','error':p.get('errorText','')[:160],'resource_type':p.get('type','')[:40],'blocked_reason':p.get('blockedReason','')[:40]})
            else:self.resource_tracking_truncated=True

    def _read(self):
        try:
            while not self.reader_stop.is_set():
                if not select.select([self.response_read],[],[],.05)[0]:continue
                data=os.read(self.response_read,65536)
                if not data:raise RuntimeError('CDP pipe closed')
                self.buffer+=data
                if len(self.buffer)>MAX_MESSAGE_BYTES:raise ValueError('CDP response exceeds message limit')
                while b'\0' in self.buffer:
                    encoded,self.buffer=self.buffer.split(b'\0',1)
                    message=json.loads(encoded)
                    with self.condition:
                        if 'id' in message:self.responses[message['id']]=message
                        else:self._track(message)
                        self.condition.notify_all()
        except BaseException as exc:
            with self.condition:self.reader_failure=exc;self.condition.notify_all()

    def command(self, method: str, params: dict | None = None, session: str | None = None) -> dict:
        with self.write_lock:
            if self.reader_failure:raise RuntimeError('CDP connection is closed')
            self.next_id+=1;request_id=self.next_id
            request={'id':request_id,'method':method,'params':params or {}}
            if session:request['sessionId']=session
            payload=json.dumps(request,separators=(',',':')).encode()+b'\0'
            if len(payload)>MAX_MESSAGE_BYTES:raise ValueError('CDP request exceeds message limit')
            offset=0
            while offset<len(payload):
                if time.monotonic()>=self.deadline:raise TimeoutError('CDP deadline exceeded')
                offset+=os.write(self.request_write,payload[offset:])
        with self.condition:
            while request_id not in self.responses:
                if self.reader_failure:raise RuntimeError('CDP reader failed: '+str(self.reader_failure))
                remaining=self.deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('CDP deadline exceeded during '+method)
                self.condition.wait(remaining)
            message=self.responses.pop(request_id)
        if 'error' in message:raise RuntimeError('CDP '+method+' failed: '+message['error'].get('message','unknown')[:300])
        return message.get('result',{})

    def close(self):
        self.reader_stop.set()
        with self.condition:
            self.reader_failure = RuntimeError('CDP connection closed')
            self.condition.notify_all()
        for descriptor in (self.request_write, self.response_read):
            try:
                os.close(descriptor)
            except OSError:
                pass
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=2)
        self.thread.join(timeout=2)
        self.process.stderr.close()
        os.close(self.temporary_fd)
        self.reader.join(timeout=2)


def evaluate(browser: PipeBrowser, session: str, context: int, expression: str):
    result = browser.command('Runtime.evaluate', {'expression': expression, 'contextId': context, 'returnByValue': True}, session)
    if 'exceptionDetails' in result:
        raise ValueError('Trusted DOM query failed; check CSS selectors')
    return result.get('result', {}).get('value')


def diagnostics(browser: PipeBrowser, session: str, context: int, selectors: list[str]) -> dict:
    expression = """(() => {
      const selectors = SELECTORS;
      const nodes = selectors.length ? selectors.flatMap(s => { const e=document.querySelector(s); return e ? [{selector:s,e}] : [{selector:s,e:null}]; }) : Array.from(document.querySelectorAll('body,main,section,article,header,nav,footer,button,input,a,h1,h2,h3,p,img,svg,canvas,[id]')).slice(0,120).map((e,i)=>({selector:e.id ? '#'+e.id : e.tagName.toLowerCase()+':index('+i+')',e}));
      return {ready_state:document.readyState, title:document.title.slice(0,200), viewport:[innerWidth,innerHeight], reduced_motion:matchMedia('(prefers-reduced-motion:reduce)').matches, page_bounds:{width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight}, elements:nodes.map(({selector,e})=>{
        if(!e) return {selector,missing:true};
        const b=e.getBoundingClientRect(),s=getComputedStyle(e);
        const computed={}; for(const key of ['display','visibility','position','transform','opacity','color','backgroundColor','borderTopWidth','borderTopColor','fontFamily','fontSize','animationName','animationDuration','animationPlayState','transitionProperty','transitionDuration']) computed[key]=s[key];
        for(const key in computed) computed[key]=computed[key].slice(0,512);
        return {selector,tag:e.tagName,text:(e.innerText || '').slice(0,256),bounds:{x:b.x,y:b.y,width:b.width,height:b.height},computed,focused:e===document.activeElement,hidden:e.hidden,checked:e.checked===true,disabled:e.disabled===true,image:e.tagName==='IMG' ? {complete:e.complete,natural_width:e.naturalWidth,natural_height:e.naturalHeight} : null};
      }),input_events:globalThis.__maintainallEvents || []};
    })()""".replace('SELECTORS', json.dumps(selectors))
    result = evaluate(browser, session, context, expression)
    if not isinstance(result, dict):
        raise RuntimeError('Browser did not return DOM diagnostics')
    return result


def geometry_trace(browser: PipeBrowser, session: str, context: int, selectors: list[str]) -> dict:
    """Observe bounded geometry without screenshots or application-owned metrics."""
    expression = """(() => ({elements:SELECTORS.map(selector=>{
      const e=document.querySelector(selector);if(!e)return {selector,missing:true};
      const r=e.getBoundingClientRect(),s=getComputedStyle(e);
      return {selector,bounds:{x:r.x,y:r.y,width:r.width,height:r.height},
        transform:s.transform.slice(0,256),opacity:s.opacity.slice(0,32),
        visibility:s.visibility.slice(0,32),display:s.display.slice(0,32)};
    })}))()""".replace('SELECTORS', json.dumps(selectors))
    result = evaluate(browser, session, context, expression)
    if not isinstance(result, dict) or not isinstance(result.get('elements'), list):
        raise RuntimeError('Browser did not return bounded geometry observations')
    return result


def dispatch(browser: PipeBrowser, session: str, context: int, action: dict, viewport: tuple[int, int]):
    kind = action['type']
    if kind == 'key':
        key = action['key']
        keys = {'Tab': (9, 'Tab'), 'Enter': (13, 'Enter'), 'Escape': (27, 'Escape'), 'ArrowLeft': (37, 'ArrowLeft'),
                'ArrowUp': (38, 'ArrowUp'), 'ArrowRight': (39, 'ArrowRight'), 'ArrowDown': (40, 'ArrowDown'), ' ': (32, 'Space')}
        if key not in keys and len(key) != 1:
            raise ValueError('Unsupported keyboard key; use Tab, Enter, Escape, arrows, or one character')
        code, name = keys[key] if key in keys else (ord(key.upper()) if len(key.upper()) == 1 else ord(key), 'Key' + key.upper())
        params = {'key': key, 'code': name, 'windowsVirtualKeyCode': code, 'nativeVirtualKeyCode': code}
        if len(key) == 1 or key == 'Enter':
            params['text'] = '\r' if key == 'Enter' else key
        browser.command('Input.dispatchKeyEvent', {**params, 'type': 'keyDown'}, session)
        browser.command('Input.dispatchKeyEvent', {**params, 'type': 'keyUp'}, session)
        return
    if 'selector' in action:
        point = evaluate(browser, session, context, "(() => {const e=document.querySelector(" + json.dumps(action['selector']) + ");if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,width:r.width,height:r.height}})()")
        if not point or point['width'] <= 0 or point['height'] <= 0:
            raise ValueError('Pointer target selector is missing or has no rendered area')
        x, y = point['x'], point['y']
    else:
        x, y = action['x'], action['y']
    if not 0 <= x < viewport[0] or not 0 <= y < viewport[1]:
        raise ValueError('Pointer target is outside the actual viewport')
    browser.command('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y}, session)
    if kind == 'click':
        for event in ('mousePressed', 'mouseReleased'):
            browser.command('Input.dispatchMouseEvent', {'type': event, 'x': x, 'y': y, 'button': 'left', 'clickCount': 1}, session)
    elif kind == 'scroll':
        browser.command('Input.dispatchMouseEvent', {'type': 'mouseWheel', 'x': x, 'y': y, 'deltaX': 0, 'deltaY': action['delta_y']}, session)


def dispatch_audio_probe(browser: PipeBrowser, session: str, context: int, probe: dict, stimulus: Path, viewport: tuple[int, int]):
    """Attach the trusted WAV through CDP's file-input API, then send actual input."""
    document = browser.command('DOM.getDocument', {'depth': 0}, session)['root']['nodeId']
    node_id = browser.command('DOM.querySelector', {'nodeId': document, 'selector': probe['file_input_selector']}, session).get('nodeId')
    if not node_id:
        raise ValueError('Audio file input selector is missing')
    node = browser.command('DOM.describeNode', {'nodeId': node_id}, session)['node']
    attributes = node.get('attributes', [])
    attributes = dict(zip(attributes[::2], attributes[1::2]))
    if node.get('nodeName') != 'INPUT' or attributes.get('type', '').lower() != 'file':
        raise ValueError('Audio file input selector must identify an actual input type=file')
    browser.command('DOM.setFileInputFiles', {'nodeId': node_id, 'files': [str(stimulus)]}, session)
    is_button = evaluate(browser, session, context, "(() => {const e=document.querySelector(" + json.dumps(probe['play_button_selector']) + ");return !!e && (e.tagName==='BUTTON' || (e.tagName==='INPUT' && ['button','submit'].includes(e.type)))})()")
    if not is_button:
        raise ValueError('Audio play button selector must identify an actual button')
    dispatch(browser, session, context, {'type': 'click', 'selector': probe['play_button_selector']}, viewport)


def audio_measurements(samples: list[dict], profiles: list[str], requested_signal: str) -> list[dict]:
    """Describe observed stimulus evidence only, never application correctness."""
    observations = []
    for profile in profiles:
        media = [node for sample in samples if sample['profile'] == profile for node in sample['media'] if node['playing']]
        signals = [node['signal'] for node in media if node['signal']['status'] == 'measured']
        timelines = {}
        for node in media:
            if node['current_time_seconds'] is not None:
                timelines.setdefault(node['observer_id'], []).append(node['current_time_seconds'])
        progress = max((max(times) - min(times) for times in timelines.values()), default=0)
        status = 'unverified'
        if progress >= .1 and len(signals) >= 2:
            if requested_signal == 'tone' and any(s['peak_frequency_hz'] is not None and abs(s['peak_frequency_hz'] - 440) <= 32 and s['rms'] is not None and s['rms'] > .05 for s in signals):
                status = 'observed-tone'
            elif requested_signal == 'silence' and all(s['rms'] is not None and s['rms'] < .001 for s in signals):
                status = 'observed-silence'
        observations.append({'profile': profile, 'status': status, 'playing_samples': len(media), 'measured_samples': len(signals),
                             'playback_time_progress_seconds': round(progress, 6),
                             'scope': 'sampled captured media signal, not application FFT or audio response correctness'})
    return observations


def capture(source: Path, output: Path, browser: Path, spec: dict | None = None, *, timeout: float = 35) -> dict:
    """Replay one immutable source, writing only a new evidence directory."""
    source, output = safe_path(source), safe_path(output, exists=False)
    browser = Path(browser).expanduser().absolute()
    if not browser.is_file() or not os.access(browser, os.X_OK):
        raise ValueError('An existing executable browser is required')
    if source.suffix.lower() not in {'.html', '.htm'} or not source.is_file():
        raise ValueError('Source must be one local self-contained HTML file')
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('HTML source exceeds source byte limit')
    if output.exists():
        raise ValueError('Refusing existing output directory')
    if not output.parent.is_dir():
        raise ValueError('Output parent must be an existing safe directory')
    number(timeout, 3, 90, 'Timeout')
    specification = validate_spec(spec)
    content = source.read_bytes()
    content.decode('utf-8-sig', errors='strict')
    output.mkdir(mode=0o700)
    (output / 'source.html').write_bytes(content)
    result = {'schema_version': 1, 'passed': False, 'source_sha256': hashlib.sha256(content).hexdigest(),
              'navigation_source': str(source), 'local_asset_base': source.parent.as_uri(),
              'transport': 'remote-debugging-pipe', 'scope': SCOPE, 'rendering_backend': 'software 2D; WebGL/GPU behavior not assessed',
              'sandbox_requirement': 'enclosing network-disabled namespace',
              'frames': [], 'dom_samples': [], 'input_events': [], 'actions': [], 'interactions': False,
              'resource_failures': [], 'source_reopen_verified': False, 'spec': specification}
    result['scope_version'] = 2
    if 'trace_samples_ms' in specification:
        result['scope_version'] = 3
        result['trace_samples'] = []
        result['trace_scope'] = 'independently timed sampled DOM geometry; not pixel continuity or application state'
    if 'audio_probe' in specification:
        stimulus = write_audio_probe(output, specification['audio_probe']['mode'])
        result['audio_probe'] = {'mode': specification['audio_probe']['mode'], 'stimulus': stimulus,
                                'file_input_dispatched': False, 'play_click_dispatched': False,
                                'scope': 'requested evaluator stimulus is distinct from independently measured media signal'}
        result['audio_samples'] = []
    connection = None
    action_worker = None
    trace_worker = None
    action_stop = None
    action_progress = None
    try:
        connection = PipeBrowser(browser, output, time.monotonic() + timeout)
        result['browser_version'] = connection.command('Browser.getVersion')
        target = connection.command('Target.createTarget', {'url': 'about:blank'})['targetId']
        session = connection.command('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
        connection.command('Page.enable', session=session)
        connection.command('Network.enable', session=session)
        connection.command('Runtime.enable', session=session)
        connection.command('Network.setBlockedURLs', {'urls': ['http://*', 'https://*', 'ws://*', 'wss://*', 'ftp://*']}, session)
        connection.command('Page.addScriptToEvaluateOnNewDocument', {'source': INPUT_OBSERVER, 'worldName': WORLD}, session)
        if specification.get('audio_probe', {}).get('mode') == 'unavailable':
            connection.command('Page.addScriptToEvaluateOnNewDocument', {'source': AUDIO_FAULT}, session)
            result['audio_probe']['analysis_fault'] = {'target': 'main-world AudioContext.prototype.createAnalyser',
                'installed_before_navigation': True, 'script_sha256': hashlib.sha256(AUDIO_FAULT.encode()).hexdigest(),
                'scope': 'fixed main-world API fault, not comprehensive hardware unavailability'}
        connection.command('Browser.setDownloadBehavior', {'behavior': 'deny'})
        total_bytes = len(content) + result.get('audio_probe', {}).get('stimulus', {}).get('bytes', 0)
        for profile in specification['profiles']:
            width, height, reduced = PROFILES[profile]
            connection.command('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': profile == 'mobile'}, session)
            connection.command('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce' if reduced else 'no-preference'}]}, session)
            navigation = connection.command('Page.navigate', {'url': source.as_uri()}, session)
            if navigation.get('errorText'):
                raise RuntimeError('Local HTML navigation failed: ' + navigation['errorText'])
            frame_id = navigation['frameId']
            while True:
                context = connection.command('Page.createIsolatedWorld', {'frameId': frame_id, 'worldName': WORLD}, session)['executionContextId']
                state = evaluate(connection, session, context, 'document.readyState')
                if state == 'complete':
                    break
                if time.monotonic() >= connection.deadline:
                    raise TimeoutError('HTML load deadline exceeded')
                time.sleep(0.01)
            if any(item['local'] for item in connection.resource_failures):
                raise RuntimeError('Local resource reopening failed; inspect resource_failures')
            if 'audio_probe' in specification:
                dispatch_audio_probe(connection, session, context, specification['audio_probe'], output / stimulus['path'], (width, height))
                result['audio_probe']['file_input_dispatched'] = True
                result['audio_probe']['play_click_dispatched'] = True
                result['actions'].append({'type': 'audio_probe', 'profile': profile, 'mode': specification['audio_probe']['mode'],
                    'file_input_selector': specification['audio_probe']['file_input_selector'],
                    'play_button_selector': specification['audio_probe']['play_button_selector'], 'dispatched': True})
            started = time.monotonic()
            action_stop = threading.Event()
            action_failures = []
            action_progress = threading.Condition()
            completed_actions = 0
            def wait_for_actions(requested):
                with action_progress:
                    due = sum(a['time_ms'] <= requested for a in specification['actions'])
                    while completed_actions < due and not action_failures:
                        if action_stop.is_set():raise RuntimeError('Capture cancelled while awaiting an action')
                        remaining = connection.deadline - time.monotonic()
                        if remaining <= 0:raise TimeoutError('Action ordering deadline exceeded')
                        action_progress.wait(remaining)
                    if action_failures:raise RuntimeError('Independent action scheduling failed: '+str(action_failures))
                    if action_stop.is_set():raise RuntimeError('Capture cancelled before observation')
            def perform_actions():
                nonlocal completed_actions
                try:
                    for action in specification['actions']:
                        if action_stop.wait(max(0, started + action['time_ms'] / 1000 - time.monotonic())): return
                        if specification['selectors']:
                            snapshot = diagnostics(connection, session, context, specification['selectors'])
                            result.setdefault('action_snapshots', []).append({**snapshot, 'profile':profile, 'requested_time_ms':action['time_ms'], 'time_ms':round((time.monotonic()-started)*1000,3)})
                        dispatch(connection, session, context, action, (width, height))
                        result['actions'].append({**action, 'profile':profile, 'dispatched':True, 'observed_time_ms':round((time.monotonic()-started)*1000,3)})
                        with action_progress:
                            completed_actions += 1
                            action_progress.notify_all()
                except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
                    with action_progress:
                        action_failures.append(str(exc))
                        action_stop.set()
                        action_progress.notify_all()
            action_worker = threading.Thread(target=perform_actions, daemon=True)
            action_worker.start()
            def perform_trace():
                try:
                    for requested in specification['trace_samples_ms']:
                        if action_stop.wait(max(0, started + requested / 1000 - time.monotonic())): return
                        wait_for_actions(requested)
                        observed = round((time.monotonic() - started) * 1000, 3)
                        snapshot = geometry_trace(connection, session, context, specification['selectors'])
                        result['trace_samples'].append({**snapshot, 'profile':profile,
                            'requested_time_ms':requested, 'time_ms':observed,
                            'sample_completed_ms':round((time.monotonic()-started)*1000,3)})
                except BaseException as exc:
                    with action_progress:
                        action_failures.append('Geometry trace: '+str(exc))
                        action_stop.set()
                        action_progress.notify_all()
            if 'trace_samples_ms' in specification:
                trace_worker = threading.Thread(target=perform_trace, daemon=True)
                trace_worker.start()
            timeline = [(value, 1, None) for value in specification['samples_ms']]
            for requested, kind, action in sorted(timeline, key=lambda item: (item[0], item[1])):
                delay = started + requested / 1000 - time.monotonic()
                if delay > 0:
                    if time.monotonic() + delay >= connection.deadline:
                        raise TimeoutError('Playback timeline exceeds replay deadline')
                    action_stop.wait(delay)
                wait_for_actions(requested)
                observed = round((time.monotonic() - started) * 1000, 3)
                dom = diagnostics(connection, session, context, specification['selectors'])
                if 'audio_probe' in specification:
                    audio = evaluate(connection, session, context, AUDIO_OBSERVER)
                    if not isinstance(audio, dict) or not isinstance(audio.get('media'), list):
                        raise RuntimeError('Isolated audio observer did not return bounded records')
                    result['audio_samples'].append({**audio, 'time_ms': observed, 'requested_time_ms': requested, 'profile': profile})
                events = dom.pop('input_events')
                capture_started = round((time.monotonic() - started) * 1000, 3)
                encoded = connection.command('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False}, session)['data']
                capture_completed = round((time.monotonic() - started) * 1000, 3)
                if len(encoded) > (MAX_FRAME_BYTES * 4 // 3) + 4:
                    raise ValueError('Screenshot exceeds per-frame byte limit')
                png = base64.b64decode(encoded, validate=True)
                if len(png) > MAX_FRAME_BYTES or total_bytes + len(png) > MAX_OUTPUT_BYTES:
                    raise ValueError('Screenshot evidence exceeds artifact byte limit')
                dimensions = png_dimensions(png)
                if dimensions != (width, height):
                    raise ValueError('Screenshot dimensions do not match requested viewport')
                label = f'{profile}-{len(result["frames"]):02d}-{requested:g}ms'
                relative = label + '.png'; (output / relative).write_bytes(png)
                total_bytes += len(png)
                result['frames'].append({'path': relative, 'sha256': hashlib.sha256(png).hexdigest(), 'bytes': len(png), 'width': width, 'height': height,
                                         'time_ms': observed, 'capture_started_ms': capture_started, 'capture_completed_ms': capture_completed,
                                         'requested_time_ms': requested, 'viewport': [width, height], 'profile': profile, 'label': label})
                result['dom_samples'].append({**dom, 'time_ms': observed, 'requested_time_ms': requested, 'profile': profile})
                result['input_events'] = [e for e in result['input_events'] if e['profile'] != profile] + [{**e, 'profile': profile} for e in events]
            action_worker.join(timeout=max(0, connection.deadline-time.monotonic()))
            if trace_worker:
                trace_worker.join(timeout=max(0, connection.deadline-time.monotonic()))
                if trace_worker.is_alive():raise RuntimeError('Independent geometry trace did not finish')
            action_stop.set()
            if action_worker.is_alive() or action_failures:raise RuntimeError('Independent action scheduling failed: '+str(action_failures))
        if any(item['local'] for item in connection.resource_failures):
            raise RuntimeError('Local resource reopening failed; inspect resource_failures')
        if connection.resource_tracking_truncated:
            raise ValueError('Browser resource diagnostics exceeded tracking limits')
        result['interactions'] = bool(result['actions']) and any(e['isTrusted'] for e in result['input_events'])
        if 'audio_probe' in specification:
            result['audio_probe']['measurements'] = audio_measurements(result['audio_samples'], specification['profiles'], stimulus['requested_signal'])
        result['runtime_errors'] = [e['params'].get('exceptionDetails', {}).get('text', '')[:200] for e in connection.events if e['method'] == 'Runtime.exceptionThrown'][:20]
        result['passed'] = True
        result['source_reopen_verified'] = not connection.resource_failures and not result['runtime_errors']
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        result['failure'] = f'{type(exc).__name__}: {exc}'[:1000]
    finally:
        if action_stop:
            action_stop.set()
        if action_progress:
            with action_progress:
                action_progress.notify_all()
        if connection:
            result['resource_failures'] = connection.resource_failures
            result['resource_tracking_truncated'] = connection.resource_tracking_truncated
            connection.close()
            (output / 'browser.log').write_bytes(bytes(connection.stderr))
        if action_worker:
            action_worker.join(timeout=2)
        if trace_worker:
            trace_worker.join(timeout=2)
        if any(worker and worker.is_alive() for worker in (action_worker, trace_worker)):
            raise RuntimeError('Capture worker cleanup did not finish; evidence was not sealed')
        for name in ('profile', 'tmp'):
            shutil.rmtree(output / name, ignore_errors=True)
        (output / 'evidence.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Evidence scope: sampled playback not full motion quality. Requires an enclosing network-disabled namespace sandbox.\n'
               'Transport: remote-debugging-pipe, no server or network debug port. Creates a NEW output directory with\n'
               'source.html, timed PNGs, evidence.json and bounded browser.log; deletes browser profiles.\n'
               'Navigates the ORIGINAL file so relative local assets keep their base; the enclosing sandbox must confine file reads.\n'
               'Spec keys: samples_ms (2..48 increasing values, 0..15000), profiles (desktop/mobile/reduced_motion),\n'
               'Fixed viewports: desktop and reduced_motion 1280x800, mobile 390x844; device scale 1.\n'
               'selectors (0..24 CSS selectors), actions (0..12, sorted time_ms). Actions: click/hover with selector OR x/y,\n'
               'key with key (Tab/Enter/Escape/arrows/one character), scroll with selector OR x/y and delta_y (-1000..1000).\n'
               'Actions are actual CDP input events, never supplied JavaScript. Default: 0/250/700ms at all 3 profiles, no actions.\n'
               'Optional trace_samples_ms: 2..128 ordered times within the screenshot timeline, with explicit selectors.\n'
               'An independent clock samples DOM bounds, transform and opacity while screenshots run; actual times are recorded.\n'
               'Geometry traces do not establish pixel continuity, hidden application state or a quality score.\n'
               'Optional audio_probe: {"mode":"tone|silence|unavailable","file_input_selector":"#file","play_button_selector":"#play"}.\n'
               'One mode per capture: evaluator-owned 17s mono PCM WAV, 16000 Hz/16-bit, fixed 440 Hz tone or silence.\n'
               'Loads an actual file input via CDP and clicks an actual rendered play button. Unavailable injects a fixed\n'
               'pre-navigation main-world createAnalyser fault; it tests that condition only, not all audio failures.\n'
               'Audio observations use isolated-world media playback and conditional captureStream FFT. Unavailable FFT\n'
               'is recorded as unverified; a requested tone alone is not measured signal or application FFT correctness.\n'
               'Evidence scope version 2 by default, version 3 with geometry traces.\n'
               'Capture success is not an aesthetic, motion-quality, or causal quality pass.\n'
               'Example spec: {"samples_ms":[0,200,700],"actions":[{"time_ms":100,"type":"click","selector":"button"}]}\n'
               'Exit 0: bounded evidence captured; 1: replay failed; 2: invalid command-line arguments.')
    parser.add_argument('source', type=Path, nargs='?', help='Existing UTF-8 HTML; network resources are blocked and local assets retain their base.')
    parser.add_argument('--source', dest='source_option', type=Path, help='Named alias for the source argument; select only one form.')
    parser.add_argument('--browser', type=Path, required=True, help='Existing Chromium executable mounted read-only in the enclosing sandbox.')
    parser.add_argument('--output', type=Path, required=True, help='NEW directory with an existing parent; no symlinks or parent traversal.')
    parser.add_argument('--spec', type=Path, help='Optional bounded JSON capture specification, at most 16 KiB.')
    parser.add_argument('--timeout', type=float, default=35, help='Total wall-clock seconds, 3..90 (default: 35).')
    args = parser.parse_args()
    if bool(args.source) == bool(args.source_option):
        parser.error('Select one positional source or --source path')
    source = args.source or args.source_option
    try:
        specification = None
        if args.spec:
            path = safe_path(args.spec)
            if not path.is_file() or path.stat().st_size > MAX_SPEC_BYTES:
                raise ValueError('Capture spec exceeds byte limit or is not a regular file')
            specification = json.loads(path.read_text(encoding='utf-8'))
        result = capture(source, args.output, args.browser, specification, timeout=args.timeout)
        print(json.dumps({'passed': result['passed'], 'frames': len(result['frames']), 'interactions': result['interactions'],
                          'source_sha256': result['source_sha256'], 'scope': result['scope'], 'failure': result.get('failure'),
                          'evidence': str(args.output / 'evidence.json')}))
        return 0 if result['passed'] else 1
    except (OSError, ValueError) as exc:
        print(json.dumps({'passed': False, 'failure': str(exc)[:1000]}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
