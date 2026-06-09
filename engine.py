"""
Calculation engine for Fault Tree Analysis (FTA) and Event Tree Analysis (ETA).

Fault Tree calculation:
  Traverses the tree from the top event downward, computing the failure
  probability of each gate from its children using Boolean algebra
  (assuming statistically independent basic events):

    AND gate:  P(gate) = P(child_1) × P(child_2) × ... × P(child_n)
      → The gate event (failure) occurs only when ALL children fail.
      → Used when redundant systems must all fail simultaneously.

    OR gate:   P(gate) = 1 - (1 - P(child_1)) × (1 - P(child_2)) × ...
      → The gate event occurs when ANY child fails.
      → Used when a single failure is enough to cause the output event.

Event Tree calculation:
  Enumerates all 2^N outcome sequences for N branch points.
  Each sequence is a path of success/failure decisions. The probability
  of each path is the product of individual branch probabilities along
  that path. The frequency of each outcome = initiating event frequency × path probability.
"""

from itertools import combinations
from math import comb as math_comb

from models import FaultTree, EventTree, Gate, GateType, BasicEvent


class MinimalCutSetEngine:
    """
    MOCUS (Method of Obtaining Cut Sets) algoritması ile
    Minimal Kesim Kümeleri hesaplar.
    """

    def __init__(self, fault_tree: FaultTree):
        self.ft = fault_tree

    def calculate(self) -> list[frozenset[str]]:
        if not self.ft.top_event_id:
            return []
        raw = self._expand(self.ft.top_event_id)
        return self._minimize(raw)

    def _expand(self, node_id: str) -> list[frozenset[str]]:
        if node_id in self.ft.basic_events:
            return [frozenset([node_id])]

        gate = self.ft.gates.get(node_id)
        if gate is None:
            return []

        child_sets_list = [self._expand(cid) for cid in gate.children]
        child_sets_list = [cs for cs in child_sets_list if cs]

        if not child_sets_list:
            return []

        if gate.gate_type == GateType.AND:
            result = child_sets_list[0]
            for next_sets in child_sets_list[1:]:
                result = [a | b for a in result for b in next_sets]
            return result
        elif gate.gate_type == GateType.VOTE:
            # k/n: combine every k-subset of children with AND logic
            k = gate.vote_k
            n = len(child_sets_list)
            k = max(1, min(k, n))
            result = []
            for combo in combinations(range(n), k):
                group = child_sets_list[combo[0]]
                for idx in combo[1:]:
                    group = [a | b for a in group for b in child_sets_list[idx]]
                result.extend(group)
            return result
        else:
            result = []
            for cs in child_sets_list:
                result.extend(cs)
            return result

    def _minimize(self, cut_sets: list[frozenset[str]]) -> list[frozenset[str]]:
        unique = list(set(cut_sets))
        unique.sort(key=len)
        minimal = []
        for cs in unique:
            if not any(m < cs for m in minimal):
                minimal.append(cs)
        return minimal

    def top_probability_from_mcs(self, mcs_list: list[frozenset[str]]) -> float:
        """Rare event approximation: P(top) ≈ Σ P(MCS_i)"""
        total = 0.0
        for mcs in mcs_list:
            p = 1.0
            for eid in mcs:
                ev = self.ft.basic_events.get(eid)
                if ev:
                    p *= ev.get_failure_probability()
            total += p
        return min(total, 1.0)

    def mcs_probabilities(self, mcs_list: list[frozenset[str]]) -> list[tuple[frozenset[str], float]]:
        result = []
        for mcs in mcs_list:
            p = 1.0
            for eid in mcs:
                ev = self.ft.basic_events.get(eid)
                if ev:
                    p *= ev.get_failure_probability()
            result.append((mcs, p))
        result.sort(key=lambda x: x[1], reverse=True)
        return result


class FaultTreeEngine:
    """
    Computes failure probabilities for all nodes in a fault tree.

    Uses recursive depth-first traversal with memoization to handle
    shared sub-trees efficiently. Detects circular references to
    prevent infinite recursion.
    """

    def __init__(self, fault_tree: FaultTree):
        self.ft = fault_tree
        self._cache: dict[str, float] = {}
        self._visiting: set[str] = set()  # cycle detection

    def calculate(self) -> dict:
        """
        Calculate failure probabilities for the entire tree.

        Returns a dict keyed by node ID, each containing:
          - name: display name
          - type: 'basic_event' or 'gate_AND'/'gate_OR'
          - reliability: R = 1 - F
          - failure_probability: F
        Plus a special '_top_event' key with the top-level results.
        """
        self._cache.clear()
        self._visiting.clear()
        results = {}

        # Step 1: Compute each basic event's failure probability.
        # These are the leaf nodes of the tree.
        for eid, event in self.ft.basic_events.items():
            fp = event.get_failure_probability()
            self._cache[eid] = fp
            results[eid] = {
                "name": event.name,
                "type": "basic_event",
                "reliability": event.get_reliability(),
                "failure_probability": fp,
            }

        # Step 2: Compute each gate's failure probability.
        # Gates are internal nodes; their probability depends on children.
        # The recursive _calc_gate method handles dependency ordering.
        for gid in self.ft.gates:
            fp = self._calc_gate(gid)
            gate = self.ft.gates[gid]
            results[gid] = {
                "name": gate.name,
                "type": f"gate_{gate.gate_type.value}",
                "reliability": 1.0 - fp,
                "failure_probability": fp,
            }

        # Step 3: Extract top event result.
        top_fp = None
        if self.ft.top_event_id and self.ft.top_event_id in self._cache:
            top_fp = self._cache[self.ft.top_event_id]

        results["_top_event"] = {
            "id": self.ft.top_event_id,
            "failure_probability": top_fp,
            "reliability": (1.0 - top_fp) if top_fp is not None else None,
        }

        return results

    def _calc_gate(self, gate_id: str) -> float:
        """
        Recursively calculate the failure probability of a gate node.

        For each child of this gate:
          - If it's a basic event, use its failure probability directly
          - If it's another gate, recurse into it first

        Then combine child probabilities according to the gate type:

        AND gate (all children must fail for the gate to fail):
          P(gate) = P(c1) × P(c2) × ... × P(cn)

          Example: two redundant pumps (AND gate)
            P(pump_A) = 0.01, P(pump_B) = 0.02
            P(both fail) = 0.01 × 0.02 = 0.0002

        OR gate (any child failing causes the gate to fail):
          P(gate) = 1 - ∏(1 - P(ci))
                  = 1 - (1-P(c1)) × (1-P(c2)) × ... × (1-P(cn))

          Example: two failure modes (OR gate)
            P(overheat) = 0.01, P(leak) = 0.02
            P(either) = 1 - (0.99 × 0.98) = 1 - 0.9702 = 0.0298
        """
        if gate_id in self._cache:
            return self._cache[gate_id]

        # Circular reference protection
        if gate_id in self._visiting:
            return 0.0
        self._visiting.add(gate_id)

        gate = self.ft.gates.get(gate_id)
        if gate is None:
            self._visiting.discard(gate_id)
            return 0.0

        # Collect failure probabilities of all children
        child_fps = []
        for child_id in gate.children:
            if child_id in self.ft.basic_events:
                fp = self.ft.basic_events[child_id].get_failure_probability()
                self._cache[child_id] = fp
            elif child_id in self.ft.gates:
                fp = self._calc_gate(child_id)
            else:
                continue
            child_fps.append(fp)

        # Apply gate logic
        if not child_fps:
            result = 0.0
        elif gate.gate_type == GateType.AND:
            result = 1.0
            for fp in child_fps:
                result *= fp
        elif gate.gate_type == GateType.VOTE:
            # k-out-of-n: system fails when k or more children fail
            k = gate.vote_k
            n = len(child_fps)
            k = max(1, min(k, n))
            result = self._calc_vote(child_fps, k)
        else:
            product_of_reliabilities = 1.0
            for fp in child_fps:
                product_of_reliabilities *= (1.0 - fp)
            result = 1.0 - product_of_reliabilities

        self._cache[gate_id] = result
        self._visiting.discard(gate_id)
        return result

    @staticmethod
    def _calc_vote(child_fps: list[float], k: int) -> float:
        """P(k or more failures out of n) via inclusion-exclusion on combinations."""
        n = len(child_fps)
        total = 0.0
        for combo in combinations(range(n), k):
            p = 1.0
            for i in range(n):
                if i in combo:
                    p *= child_fps[i]
                else:
                    p *= (1.0 - child_fps[i])
            total += p
        if k < n:
            total += FaultTreeEngine._calc_vote(child_fps, k + 1)
        return min(total, 1.0)


class ImportanceMeasures:
    """
    Temel olay önem ölçülerini hesaplar.

    Birnbaum:  I_B(i) = P(top | q_i=1) - P(top | q_i=0)
    FV:        I_FV(i) = (P(top) - P(top | q_i=0)) / P(top)
    RAW:       I_RAW(i) = P(top | q_i=1) / P(top)
    RRW:       I_RRW(i) = P(top) / P(top | q_i=0)
    """

    def __init__(self, fault_tree: FaultTree):
        self.ft = fault_tree

    def _calc_top_with_override(self, event_id: str, forced_fp: float) -> float:
        original_ev = self.ft.basic_events[event_id]
        original_r = original_ev.reliability
        original_fr = original_ev.failure_rate
        original_t = original_ev.time
        original_td = original_ev.use_time_dependent

        original_ev.reliability = 1.0 - forced_fp
        original_ev.use_time_dependent = False
        original_ev.failure_rate = None
        original_ev.time = None

        engine = FaultTreeEngine(self.ft)
        results = engine.calculate()
        top = results.get("_top_event", {})
        p_top = top.get("failure_probability", 0.0) or 0.0

        original_ev.reliability = original_r
        original_ev.failure_rate = original_fr
        original_ev.time = original_t
        original_ev.use_time_dependent = original_td

        return p_top

    def calculate(self) -> dict[str, dict[str, float]]:
        if not self.ft.top_event_id or not self.ft.basic_events:
            return {}

        engine = FaultTreeEngine(self.ft)
        base_results = engine.calculate()
        p_top = base_results["_top_event"].get("failure_probability")
        if p_top is None or p_top == 0.0:
            return {}

        importance = {}
        for eid in self.ft.basic_events:
            p_top_1 = self._calc_top_with_override(eid, 1.0)
            p_top_0 = self._calc_top_with_override(eid, 0.0)

            birnbaum = p_top_1 - p_top_0
            fv = (p_top - p_top_0) / p_top if p_top > 0 else 0.0
            raw = p_top_1 / p_top if p_top > 0 else 0.0
            rrw = p_top / p_top_0 if p_top_0 > 0 else float('inf')

            importance[eid] = {
                "birnbaum": birnbaum,
                "fussell_vesely": fv,
                "raw": raw,
                "rrw": rrw,
            }

        return importance


class EventTreeEngine:
    """
    Computes all outcome sequence probabilities for an event tree.

    An event tree with N branch points (safety systems / barriers)
    produces 2^N distinct outcomes. Each outcome represents a unique
    combination of system successes and failures following the
    initiating event.
    """

    def __init__(self, event_tree: EventTree,
                 basic_events: dict[str, BasicEvent] | None = None):
        self.et = event_tree
        self.basic_events = basic_events or {}

    def calculate(self) -> list[dict]:
        """
        Enumerate and calculate all outcome sequences.

        For each branch point, determine the success probability:
          - From linked basic event: P(success) = R(event) = e^(-λt) or direct R
          - From direct input: user-specified P(success)
          - Default: 0.5 if nothing specified

        Then enumerate all 2^N paths through the tree. For path i:
          - Convert i to binary: each bit selects success (0) or failure (1)
          - Path probability = product of individual branch probabilities
          - Path frequency = initiating event frequency × path probability

        Returns list of dicts, each containing:
          - sequence: [(branch_name, "Success"/"Failure"), ...]
          - probability: float
          - frequency: float
        """
        # Step 1: Resolve success probability for each branch point
        branch_probs = []
        for branch in self.et.branches:
            if branch.basic_event_id and branch.basic_event_id in self.basic_events:
                # Linked to a basic event: success = reliability of that event
                p_success = self.basic_events[branch.basic_event_id].get_reliability()
            elif branch.success_probability is not None:
                p_success = branch.success_probability
            else:
                p_success = 0.5
            branch_probs.append((branch.name, p_success))

        # Step 2: Enumerate all 2^N outcome sequences
        n = len(branch_probs)
        if n == 0:
            return []

        outcomes = []
        for i in range(2 ** n):
            sequence = []
            prob = 1.0
            for j in range(n):
                name, p_success = branch_probs[j]
                # Bit j of i: 0 means success, 1 means failure
                # We read bits from MSB to LSB so branch order is preserved
                bit = (i >> (n - 1 - j)) & 1
                if bit == 1:
                    sequence.append((name, "Failure"))
                    prob *= (1.0 - p_success)
                else:
                    sequence.append((name, "Success"))
                    prob *= p_success

            outcomes.append({
                "sequence": sequence,
                "probability": prob,
                "frequency": self.et.initiating_event_frequency * prob,
            })

        return outcomes
