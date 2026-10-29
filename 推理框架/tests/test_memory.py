import importlib
from pathlib import Path
import unittest

from inference_ref.contracts import ContractError
from tests.package_support import chain_definition
from tests.support import Workspace

try:
    pkg = importlib.import_module("inference_ref.model_package")
    memory = importlib.import_module("inference_ref.memory")
except ModuleNotFoundError:
    pkg = memory = None


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(memory, "A5 arena planner implementation is missing")
        self.work = Workspace()
        self.addCleanup(self.work.cleanup)

    def package(self, padded=False, outputs=None):
        definition = chain_definition(padded=padded)
        if outputs:
            definition["outputs"] = outputs
            for t in definition["tensors"]:
                if t["id"] in outputs: t["role"] = "output"
        path = Path(self.work.name) / ("padded" if padded else "compact")
        pkg.write_package(path, **definition)
        return pkg.read_package(path)

    def assert_live_disjoint(self, plan):
        placements = list(plan.placements)
        for a in placements:
            self.assertEqual(a.offset % plan.alignment, 0)
            for b in placements:
                if a.tensor_id >= b.tensor_id or a.arena != b.arena: continue
                live_overlap = max(a.first_use, b.first_use) <= min(a.last_use, b.last_use)
                memory_overlap = max(a.offset, b.offset) < min(a.offset+a.byte_length, b.offset+b.byte_length)
                self.assertFalse(live_overlap and memory_overlap, (a, b))

    def test_compact_chain_reuses_storage_and_is_deterministic(self):
        model = self.package()
        plan = memory.plan_memory(model)
        self.assertGreater(plan.unpooled_bytes, plan.total_bytes)
        self.assertEqual(plan.to_dict(), memory.plan_memory(model).to_dict())
        self.assert_live_disjoint(plan)
        self.assertEqual(plan.workspace_bytes, 64)
        with self.assertRaises((AttributeError, TypeError)):
            plan.activation_bytes = 1

    def test_exact_budget_and_one_byte_less(self):
        model = self.package()
        plan = memory.plan_memory(model)
        self.assertEqual(memory.plan_memory(model, memory_budget=plan.total_bytes).total_bytes, plan.total_bytes)
        with self.assertRaises(ContractError) as caught:
            memory.plan_memory(model, memory_budget=plan.total_bytes-1)
        self.assertEqual(caught.exception.code, "RESOURCE_LIMIT")

    def test_padding_uses_dedicated_slots(self):
        model = self.package(padded=True)
        plan = memory.plan_memory(model)
        self.assert_live_disjoint(plan)
        activations = [p for p in plan.placements if p.arena == "activations"]
        self.assertEqual(len({p.offset for p in activations}), len(activations))

    def test_early_output_is_pinned_to_chain_end(self):
        model = self.package(outputs=["h1", "y"])
        plan = memory.plan_memory(model)
        h1 = plan.placement("h1")
        self.assertEqual(h1.last_use, len(model.nodes))
        self.assert_live_disjoint(plan)

    def test_bad_budget_and_alignment_are_rejected(self):
        model = self.package()
        for args in ({"memory_budget": True}, {"memory_budget": -1},
                     {"alignment": 3}, {"alignment": True}, {"alignment": 8192}):
            with self.subTest(args=args), self.assertRaises(ContractError):
                memory.plan_memory(model, **args)
