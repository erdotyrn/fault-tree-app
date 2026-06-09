"""
Data models for Fault Tree and Event Tree analysis.

Defines all domain objects:
  - BasicEvent: a leaf-level failure event with reliability parameters
  - Gate: a logical AND/OR node combining child events or sub-gates
  - FaultTree: the complete fault tree structure
  - EventTreeBranch / EventTree: event tree with sequential branch points
  - Project: top-level container with JSON save/load

Probability conventions used throughout:
  R = reliability = P(component works)
  F = failure probability = 1 - R = P(component fails)
  For time-dependent mode: R = e^(-λt)  where λ = failure rate, t = mission time
"""

import json
import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GateType(Enum):
    """Logical gate types for fault tree nodes."""
    AND = "AND"
    OR = "OR"
    VOTE = "VOTE"


@dataclass
class BasicEvent:
    """
    A basic (leaf) event in reliability analysis.

    Two input modes:
      1. Direct: user supplies R directly
      2. Time-dependent: user supplies λ and t, program computes R = e^(-λt)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    reliability: Optional[float] = None
    failure_rate: Optional[float] = None   # λ (per hour, per year, etc.)
    time: Optional[float] = None           # t (matching time unit)
    use_time_dependent: bool = False

    def get_reliability(self) -> float:
        """
        Return the reliability R of this event.

        Time-dependent mode: R = e^(-λt)
          This is the exponential reliability model, which assumes a constant
          failure rate (memoryless / exponential distribution). It is the most
          widely used model in nuclear and process safety analysis.

        Direct mode: returns the user-supplied R value.
        Default: R = 1.0 (perfectly reliable) if nothing is set.
        """
        if self.use_time_dependent and self.failure_rate is not None and self.time is not None:
            return math.exp(-self.failure_rate * self.time)
        if self.reliability is not None:
            return self.reliability
        return 1.0

    def get_failure_probability(self) -> float:
        """F = 1 - R. The probability that this component fails."""
        return 1.0 - self.get_reliability()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "reliability": self.reliability,
            "failure_rate": self.failure_rate,
            "time": self.time,
            "use_time_dependent": self.use_time_dependent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BasicEvent":
        return cls(**data)


@dataclass
class Gate:
    """
    Logical gate connecting child nodes in a fault tree.

    AND gate: the output event occurs only when ALL children occur.
    OR gate:  the output event occurs when ANY child occurs.

    Children are referenced by their ID strings and can be
    either BasicEvent IDs or other Gate IDs.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    gate_type: GateType = GateType.AND
    children: list[str] = field(default_factory=list)
    vote_k: int = 2

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "gate_type": self.gate_type.value,
            "children": list(self.children),
        }
        if self.gate_type == GateType.VOTE:
            d["vote_k"] = self.vote_k
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Gate":
        return cls(
            id=data["id"],
            name=data["name"],
            gate_type=GateType(data["gate_type"]),
            children=list(data.get("children", [])),
            vote_k=data.get("vote_k", 2),
        )


@dataclass
class FaultTree:
    """
    Complete fault tree structure.

    Contains a collection of basic events and gates. One gate is
    designated as the 'top event' — the undesired system-level failure
    whose probability we want to compute.
    """
    name: str = "Fault Tree"
    basic_events: dict[str, BasicEvent] = field(default_factory=dict)
    gates: dict[str, Gate] = field(default_factory=dict)
    top_event_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "basic_events": {k: v.to_dict() for k, v in self.basic_events.items()},
            "gates": {k: v.to_dict() for k, v in self.gates.items()},
            "top_event_id": self.top_event_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FaultTree":
        ft = cls()
        ft.name = data.get("name", "Fault Tree")
        ft.basic_events = {
            k: BasicEvent.from_dict(v) for k, v in data.get("basic_events", {}).items()
        }
        ft.gates = {
            k: Gate.from_dict(v) for k, v in data.get("gates", {}).items()
        }
        ft.top_event_id = data.get("top_event_id")
        return ft


@dataclass
class EventTreeBranch:
    """
    A single branch point (safety system / barrier) in an event tree.

    Each branch point splits the timeline into success and failure paths.
    The success probability can come from a linked BasicEvent or be
    entered directly.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    basic_event_id: Optional[str] = None
    success_probability: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "basic_event_id": self.basic_event_id,
            "success_probability": self.success_probability,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EventTreeBranch":
        return cls(**data)


@dataclass
class EventTree:
    """
    Event tree starting from an initiating event.

    An event tree models accident sequences: starting from an initiating
    event (e.g. pipe break), each safety system either succeeds or fails,
    creating a binary tree of possible outcomes. With N branch points,
    there are 2^N distinct outcome sequences.
    """
    name: str = "Event Tree"
    initiating_event_name: str = "Initiating Event"
    initiating_event_frequency: float = 1.0
    branches: list[EventTreeBranch] = field(default_factory=list)
    outcome_labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "initiating_event_name": self.initiating_event_name,
            "initiating_event_frequency": self.initiating_event_frequency,
            "branches": [b.to_dict() for b in self.branches],
            "outcome_labels": self.outcome_labels,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EventTree":
        et = cls()
        et.name = data.get("name", "Event Tree")
        et.initiating_event_name = data.get("initiating_event_name", "Initiating Event")
        et.initiating_event_frequency = data.get("initiating_event_frequency", 1.0)
        et.branches = [EventTreeBranch.from_dict(b) for b in data.get("branches", [])]
        et.outcome_labels = data.get("outcome_labels", [])
        return et


@dataclass
class SPNode:
    """
    Recursive node for series-parallel system modelling.

    node_type:
      "component" — leaf node with a fixed reliability value
      "series"    — children connected in series  (R = R₁×R₂×…)
      "parallel"  — children connected in parallel (R = 1-∏(1-Rᵢ))
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    node_type: str = "component"
    reliability: float = 0.95
    children: list["SPNode"] = field(default_factory=list)

    def calc_reliability(self) -> float:
        if self.node_type == "component":
            return self.reliability
        child_rs = [c.calc_reliability() for c in self.children]
        if not child_rs:
            return 1.0
        if self.node_type == "series":
            r = 1.0
            for cr in child_rs:
                r *= cr
            return r
        product = 1.0
        for cr in child_rs:
            product *= (1.0 - cr)
        return 1.0 - product

    def to_dict(self) -> dict:
        d = {"id": self.id, "name": self.name, "node_type": self.node_type}
        if self.node_type == "component":
            d["reliability"] = self.reliability
        else:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SPNode":
        node = cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            node_type=data.get("node_type", "component"),
            reliability=data.get("reliability", 0.95),
        )
        if "children" in data:
            node.children = [cls.from_dict(c) for c in data["children"]]
        return node


@dataclass
class SPConfig:
    root: SPNode = field(
        default_factory=lambda: SPNode(name="Sistem", node_type="series"))

    def to_dict(self) -> dict:
        return {"root": self.root.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "SPConfig":
        cfg = cls()
        if "root" in data:
            cfg.root = SPNode.from_dict(data["root"])
        elif "is_series" in data:
            cfg.root = SPNode(
                name="Sistem",
                node_type="series" if data["is_series"] else "parallel",
            )
            for cd in data.get("components", []):
                cfg.root.children.append(SPNode(
                    name=cd.get("name", ""),
                    node_type="component",
                    reliability=cd.get("reliability", 0.95),
                ))
        return cfg


@dataclass
class Project:
    fault_tree: FaultTree = field(default_factory=FaultTree)
    event_tree: EventTree = field(default_factory=EventTree)
    sp_config: SPConfig = field(default_factory=SPConfig)

    def save(self, filepath: str) -> None:
        data = {
            "version": "1.0",
            "fault_tree": self.fault_tree.to_dict(),
            "event_tree": self.event_tree.to_dict(),
            "sp_config": self.sp_config.to_dict(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> "Project":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        proj = cls()
        proj.fault_tree = FaultTree.from_dict(data.get("fault_tree", {}))
        proj.event_tree = EventTree.from_dict(data.get("event_tree", {}))
        if "sp_config" in data:
            proj.sp_config = SPConfig.from_dict(data["sp_config"])
        return proj
