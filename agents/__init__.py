"""Courier Memory ajanları. `Services` API ve betikler için tek giriş noktasıdır."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .assignment import AssignmentAgent
from .briefing import BriefingAgent
from .feed import AgentFeed
from .memory import MemoryAgent
from .harvest import HarvestAgent, HarvestStore
from .llm import LLM
from .memorybook import MemoryBook
from .orchestrator import SessionStore, Orchestrator
from .region_agent import RegionAgent
from .review import ReviewStore
from .rundata import RunData


@dataclass
class Services:
    run: RunData
    llm: LLM
    book: MemoryBook
    assignment: AssignmentAgent
    memory: MemoryAgent
    briefing: BriefingAgent
    orchestrator: Orchestrator
    sessions: SessionStore
    harvest: HarvestStore
    feed: AgentFeed
    review: ReviewStore
    region: RegionAgent

    @classmethod
    def create(cls, run_dir: str | Path | None = None, mode: str | None = None, memory_file: str | Path | None = None) -> "Services":
        run = RunData(run_dir)
        llm = LLM(mode=mode)
        # Ajan başına model (CM_MODEL_ASSIGNMENT / _MEMORY / _BRIEFING / _ORCHESTRATOR / _HARVEST / _REVIEW / _REGION); yoksa CM_MODEL_ID.
        per = {ag: LLM(mode=mode, model=os.environ.get(f"CM_MODEL_{ag.upper()}") or None)
               for ag in ("assignment", "memory", "briefing", "orchestrator", "harvest", "review", "region")}
        book = MemoryBook(run, memory_file)
        orch = Orchestrator(run, book, per["orchestrator"])
        sessions = SessionStore(orch)
        memory = MemoryAgent(run, book, per["memory"])
        feed = AgentFeed(Path(memory_file).with_name("agent_feed.json") if memory_file else None)
        review = ReviewStore(run, book, per["review"], feed)
        return cls(run=run, llm=llm, book=book, assignment=AssignmentAgent(run, per["assignment"]), memory=memory,
                   briefing=BriefingAgent(run, book, per["briefing"], plans=sessions.plans), orchestrator=orch, sessions=sessions,
                   harvest=HarvestStore(HarvestAgent(run, book, per["harvest"], plans=sessions.plans), memory),
                   feed=feed, review=review, region=RegionAgent(run, book, per["region"], feed, review.question_queue))
