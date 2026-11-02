"""Adapter: sealed session replays.

The replay artifact records the source session hash, cutoff, prompt hash, fixed
tool budget and every final answer. This adapter only projects those files into
the shared record shape; it never mutates the replay.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..contracts import Attempt, Record, RunManifest, sha256
from ..metrics import summarize


def records(root: Path) -> list[Record]:
    root = Path(root).resolve()
    out: list[Record] = []
    for manifest_path in sorted(root.glob('*/manifest.json')):
        replay = json.loads(manifest_path.read_text())
        source = replay['source']
        workflow_sha256 = sha256(manifest_path.read_bytes())
        for entry in replay.get('arms', []):
            payload = json.loads((manifest_path.parent / entry['file']).read_text())
            score, maximum = payload.get('score'), payload.get('max')
            if not isinstance(score, int) or not isinstance(maximum, int) or maximum <= 0:
                continue
            arm = entry['arm']
            run_id = f"replay-{manifest_path.parent.name}-{arm}-{entry['trial']}"
            manifest = RunManifest(
                run_id=run_id,
                suite='dsh-replays',
                case='session-d26-gpu',
                arm=arm,
                workflow_sha256=workflow_sha256,
                prompt_sha256=source['prompt_sha256'],
                skill_sha256=sha256('dsh-runtime-guide') if arm == 'with' else None,
                agent_runtime='dsh',
                model=source['model'],
                provider=source['provider'],
                source='session-replay',
                subject='skill',
                split='control',
                scale='small',
                category='replay',
                runner='sdk-resume',
                adapter='session-d26-gpu',
                environment={
                    'cutoff_seq': source['cutoff_seq'],
                    'cutoff_turn': source['cutoff_turn'],
                    'cwd': source['cwd_label'],
                    'forced_proxy': source['forced_proxy'],
                    'skills_mode': source['skills_mode'],
                },
                budgets={'tool_calls': source['tool_budget']},
                evaluation={
                    'trial': entry['trial'],
                    'record': entry['file'],
                    'tool_calls': payload.get('tool_calls', 0),
                },
            )
            attempt = Attempt(
                attempt_id=f"a{entry['trial']}",
                trial_id=f"{arm}-{entry['trial']}",
                outcome='scored',
                reward=float(score),
                max_reward=float(maximum),
                checks=payload.get('checks', {}),
                usage={'toolCalls': int(payload.get('tool_calls', 0))},
                artifacts={'answer': f"{manifest_path.parent.name}/{entry['file']}"},
            )
            out.append(Record(
                record_id=run_id,
                manifest=manifest,
                state='sealed',
                attempts=(attempt,),
                metrics=summarize((attempt,)),
                evidence={
                    'replay_manifest_sha256': workflow_sha256,
                    'source_session_sha256': source['session_sha256'],
                    'source_session_id_sha256': source['session_id_sha256'],
                },
            ).with_hash())
    return out
