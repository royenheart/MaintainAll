"""Pure contracts for one evaluation framework.

No filesystem, network, model or clock access. The framework's portable evidence is
`RunManifest`, `Attempt`, `Record`, `CaseSpec` and `SuiteSpec`; adapters translate legacy
stacks into these and never write a second source of truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

SCHEMA = 1


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha256(value: Any) -> str:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode('utf-8')
    else:
        raw = canonical(value).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class RunManifest:
    """The bridge between a live/bench trial and the evidence layer (issue #8)."""
    run_id: str
    suite: str
    case: str
    arm: str
    workflow_sha256: str
    prompt_sha256: str
    skill_sha256: str | None
    agent_runtime: str
    model: str
    provider: str
    source: str
    subject: str = 'skill'
    split: str = 'development'
    scale: str = 'small'
    category: str = ''
    runner: str = 'legacy-adapter'
    adapter: str = ''
    environment: dict[str, Any] = field(default_factory=dict)
    budgets: dict[str, Any] = field(default_factory=dict)
    calibration: dict[str, Any] = field(default_factory=dict)
    trial_plan: dict[str, Any] = field(default_factory=dict)
    git_commit: str | None = None
    target: str | None = None
    trace_id: str | None = None
    evaluation: dict[str, Any] | None = None
    started_at: str = field(default_factory=now)
    finished_at: str | None = None

    def validate(self) -> None:
        for key in ('run_id', 'suite', 'case', 'arm', 'workflow_sha256', 'prompt_sha256', 'agent_runtime', 'model', 'provider', 'source'):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'RunManifest.{key} must be a non-empty string')
        for key in ('workflow_sha256', 'prompt_sha256', 'skill_sha256'):
            value = getattr(self, key)
            if value is not None and (not isinstance(value, str) or len(value) != 64):
                raise ValueError(f'RunManifest.{key} must be a SHA-256 hex digest')

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class Attempt:
    attempt_id: str
    trial_id: str
    outcome: str
    reward: float | None = None
    max_reward: float | None = None
    checks: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    OUTCOMES = frozenset({'scored', 'timeout', 'exception', 'infrastructure', 'incomplete', 'failed'})

    def validate(self) -> None:
        for key in ('attempt_id', 'trial_id', 'outcome'):
            if not isinstance(getattr(self, key), str) or not getattr(self, key):
                raise ValueError(f'Attempt.{key} must be a non-empty string')
        if self.outcome not in self.OUTCOMES:
            raise ValueError(f'unknown attempt outcome: {self.outcome}')
        if self.reward is not None and (not isinstance(self.reward, (int, float)) or self.reward < 0):
            raise ValueError('Attempt.reward must be non-negative')
        if self.max_reward is not None and (not isinstance(self.max_reward, (int, float)) or self.max_reward <= 0):
            raise ValueError('Attempt.max_reward must be positive')
        if self.reward is not None and self.max_reward is not None and self.reward > self.max_reward:
            raise ValueError('Attempt.reward cannot exceed max_reward')

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    suite: str
    split: str
    scale: str
    prompt_sha256: str
    fixture_sha256: str
    grader_sha256: str
    truth_sha256: str | None = None
    category: str = ''
    mutation_policy: str = 'report-only'
    requirements_sha256: str | None = None
    description: str = ''

    def validate(self) -> None:
        if self.split not in ('control', 'development', 'holdout'):
            raise ValueError(f'invalid case split: {self.split}')
        for key in ('case_id', 'suite', 'prompt_sha256', 'fixture_sha256', 'grader_sha256'):
            if not getattr(self, key):
                raise ValueError(f'CaseSpec.{key} is required')

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class SuiteSpec:
    suite_id: str
    version: int
    source: str
    cases: tuple[CaseSpec, ...] = ()
    scoring: dict[str, Any] = field(default_factory=dict)
    calibration_policy: dict[str, Any] = field(default_factory=dict)
    comparison_policy: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.suite_id or not self.source:
            raise ValueError('SuiteSpec.suite_id and source are required')
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError('duplicate case id in suite')
        for case in self.cases:
            case.validate()

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {'suite_id': self.suite_id, 'version': self.version, 'source': self.source,
                'cases': [case.as_dict() for case in self.cases]}


@dataclass(frozen=True)
class Record:
    record_id: str
    manifest: RunManifest
    state: str
    attempts: tuple[Attempt, ...]
    metrics: dict[str, Any]
    evidence: dict[str, str] = field(default_factory=dict)
    schema: int = SCHEMA
    sealed_at: str = field(default_factory=now)
    record_hash: str = ''

    STATES = frozenset({'planned', 'calibrated', 'running', 'evaluated', 'graded', 'reviewed', 'sealed', 'failed'})

    def body(self) -> dict[str, Any]:
        return {
            'schema': self.schema, 'record_id': self.record_id,
            'manifest': self.manifest.as_dict(), 'state': self.state,
            'attempts': [attempt.as_dict() for attempt in self.attempts],
            'metrics': self.metrics, 'evidence': self.evidence,
            'sealed_at': self.sealed_at,
        }

    def with_hash(self) -> 'Record':
        self.manifest.validate()
        if self.state not in self.STATES:
            raise ValueError(f'invalid record state: {self.state}')
        for attempt in self.attempts:
            attempt.validate()
        body = self.body()
        return Record(**{**self.__dict__, 'record_hash': sha256(body)})

    def validate(self) -> None:
        self.manifest.validate()
        if self.state not in self.STATES:
            raise ValueError(f'invalid record state: {self.state}')
        for attempt in self.attempts:
            attempt.validate()
        if self.record_hash and self.record_hash != sha256(self.body()):
            raise ValueError('record hash does not match its body')

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {**self.body(), 'record_hash': self.record_hash}
