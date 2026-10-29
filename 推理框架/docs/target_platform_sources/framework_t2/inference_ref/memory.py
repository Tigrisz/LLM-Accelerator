"""Deterministic conservative static lifetimes; plan before arena allocation."""

from dataclasses import asdict, dataclass
from math import prod

from .contracts import require
from .model_package import ModelPackage, align_up
from .platform import checked_range,checked_span

DEFAULT_BUDGET = 64 * 1024 * 1024


def validate_plan_addressing(plan,*,address_bits=64):
    require(isinstance(plan,MemoryPlan),'INVALID_ARGUMENT','MemoryPlan required')
    capacities={'weights':plan.weight_bytes,'activations':plan.activation_bytes,'workspace':plan.workspace_bytes}
    checked_span(0,plan.total_bytes,bits=address_bits)
    for value in capacities.values(): checked_span(0,value,bits=address_bits)
    for p in plan.placements:
        require(p.arena in capacities,'INVALID_ARGUMENT','Unknown plan arena')
        checked_range(p.offset,p.reserved_bytes,capacities[p.arena])
        checked_range(p.offset,p.byte_length,capacities[p.arena])
        checked_span(p.offset,p.reserved_bytes,bits=address_bits)


@dataclass(frozen=True)
class Placement:
    tensor_id: str
    arena: str
    offset: int
    byte_length: int
    reserved_bytes: int
    first_use: int
    last_use: int
    reusable: bool


@dataclass(frozen=True)
class MemoryPlan:
    alignment: int
    placements: tuple[Placement, ...]
    weight_bytes: int
    activation_bytes: int
    workspace_bytes: int
    alignment_overhead_bytes: int
    total_bytes: int
    unpooled_bytes: int

    def placement(self, tensor_id: str) -> Placement:
        p = next((p for p in self.placements if p.tensor_id == tensor_id), None)
        require(p is not None, "INVALID_ARGUMENT", "Tensor absent from plan")
        return p

    def to_dict(self) -> dict:
        return asdict(self)


def plan_memory(package: ModelPackage, *, memory_budget=DEFAULT_BUDGET, alignment=64) -> MemoryPlan:
    require(isinstance(package, ModelPackage), "INVALID_ARGUMENT", "Expected validated package")
    require(type(memory_budget) is int and 0 <= memory_budget <= 2**63-1,
            "INVALID_ARGUMENT", "Invalid arena budget")
    require(type(alignment) is int and 4 <= alignment <= 4096 and alignment & (alignment-1) == 0,
            "INVALID_ARGUMENT", "Alignment must be power of two in 4..4096")
    n = len(package.nodes)
    first = {t.id: -1 for t in package.tensors if t.role in {"input", "constant"}}
    last = {t.id: -1 for t in package.tensors}
    for i, node in enumerate(package.nodes):
        first[node.output] = i
        for _, name in node.inputs:
            last[name] = i
    for name in package.outputs:
        last[name] = n
    placements, weights = [], 0
    for t in package.tensors:
        if t.role == "constant":
            size = align_up(t.spec.byte_length, alignment)
            placements.append(Placement(t.id, "weights", weights, t.spec.byte_length, size, -1, n, False))
            weights += size
    activations = [t for t in package.tensors if t.role != "constant"]
    activations.sort(key=lambda t: first[t.id])
    active, free, highwater = [], [], 0
    for t in activations:
        start, end = first[t.id], last[t.id]
        for previous in active[:]:
            if previous.last_use < start:
                active.remove(previous)
                if previous.reusable:
                    free.append((previous.offset, previous.reserved_bytes))
        size = align_up(t.spec.byte_length, alignment)
        reusable = t.spec.shape == t.spec.storage_shape
        choice = next((slot for slot in sorted(free) if slot[1] >= size), None) if reusable else None
        if choice:
            free.remove(choice)
            offset, reserved = choice
        else:
            offset, reserved = highwater, size
            highwater += size
        placement = Placement(t.id, "activations", offset, t.spec.byte_length, reserved, start, end, reusable)
        placements.append(placement)
        active.append(placement)
    scratch = align_up(max(prod(package.tensor(node.output).spec.shape)*4 for node in package.nodes), alignment)
    overhead = sum(alignment-1 for size in (weights, highwater, scratch) if size)
    total = weights + highwater + scratch + overhead
    require(total <= memory_budget, "RESOURCE_LIMIT", f"Arena budget {memory_budget}, need {total}")
    unpooled = weights + sum(align_up(t.spec.byte_length, alignment) for t in activations) + scratch + overhead
    return MemoryPlan(alignment, tuple(placements), weights, highwater, scratch, overhead, total, unpooled)
