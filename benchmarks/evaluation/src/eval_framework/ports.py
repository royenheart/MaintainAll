"""Ports: the only places the framework crosses an I/O boundary.

Adapters implement these; core contracts and workflow never import them.
"""
from __future__ import annotations

from typing import Protocol


class CaseSource(Protocol):
    def suite(self): ...
    def list_cases(self): ...


class TrialRunner(Protocol):
    def run(self, manifest, case): ...


class Grader(Protocol):
    def grade(self, trial): ...


class Reviewer(Protocol):
    def review(self, record): ...


class RecordStore(Protocol):
    def seal(self, record): ...
    def list(self): ...


class ReportBuilder(Protocol):
    def build(self, records, suites, published, output): ...


class TraceSink(Protocol):
    def emit(self, manifest): ...
