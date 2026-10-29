import hashlib
import importlib
import json
from pathlib import Path
import unittest
from unittest import mock

import numpy as np

from inference_ref.contracts import ContractError
from tests.package_support import chain_definition
from tests.support import Workspace

try:
    pkg = importlib.import_module("inference_ref.model_package")
except ModuleNotFoundError:
    pkg = None


class ModelPackageTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(pkg, "A5 model package implementation is missing")
        self.work = Workspace()
        self.addCleanup(self.work.cleanup)
        self.path = Path(self.work.name) / "model"

    def write(self, **changes):
        definition = chain_definition(padded=True)
        definition.update(changes)
        pkg.write_package(self.path, **definition)
        return pkg.read_package(self.path)

    def mutate(self, change):
        path = self.path / "manifest.json"
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def rejected(self, code=None):
        with self.assertRaises(ContractError) as caught:
            pkg.read_package(self.path)
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_roundtrip_constants_are_readonly_and_metadata_immutable(self):
        model = self.write()
        self.assertEqual(len(model.nodes), 4)
        self.assertEqual(model.inputs, ("x",))
        w = model.constant_array("w")
        self.assertEqual(w.shape, (2, 5))
        np.testing.assert_array_equal(w[:, :3], chain_definition()["constants"]["w"])
        np.testing.assert_array_equal(w[:, 3:], 0)
        self.assertFalse(w.flags.writeable)
        self.assertEqual(hashlib.sha256(model.weights).hexdigest(), model.weights_sha256)
        with self.assertRaises((AttributeError, TypeError)):
            model.tensors[0].role = "constant"
        with self.assertRaises(ContractError):
            pkg.write_package(self.path, **chain_definition())

    def test_deterministic_package_bytes(self):
        self.write()
        second = Path(self.work.name) / "second"
        pkg.write_package(second, **chain_definition(padded=True))
        for name in ("manifest.json", "weights.bin"):
            self.assertEqual((self.path / name).read_bytes(), (second / name).read_bytes())

    def test_duplicate_json_keys_unknown_fields_and_bad_versions(self):
        self.write()
        original = (self.path / "manifest.json").read_text()
        (self.path / "manifest.json").write_text(original.replace('"version": 1', '"version": 1, "version": 1'))
        self.rejected("INVALID_MODEL")
        (self.path / "manifest.json").write_text(original)
        self.mutate(lambda m: m.update(executable="payload.py"))
        self.rejected("INVALID_MODEL")
        (self.path / "manifest.json").write_text(original)
        self.mutate(lambda m: m.update(version=True))
        self.rejected("UNSUPPORTED")

    def test_graph_forward_reference_duplicate_writer_and_role_rejected(self):
        for kind in ("forward", "writer", "constant_output", "duplicate_id", "unknown_ref", "binding", "shape"):
            with self.subTest(kind=kind):
                definition = chain_definition()
                if kind == "forward": definition["nodes"][0]["inputs"]["input"] = "h2"
                if kind == "writer": definition["nodes"][1]["output"] = "h1"
                if kind == "constant_output": definition["nodes"][0]["output"] = "w"
                if kind == "duplicate_id": definition["tensors"][1]["id"] = "x"
                if kind == "unknown_ref": definition["nodes"][0]["inputs"]["input"] = "missing"
                if kind == "binding": definition["nodes"][0]["inputs"]["extra"] = "x"
                if kind == "shape": definition["tensors"][-1]["shape"] = [1]
                with self.assertRaises(ContractError):
                    pkg.write_package(Path(self.work.name) / kind, **definition)

    def test_unsupported_operator_dtype_layout_and_quantization(self):
        for kind in ("operator", "dtype", "layout", "quantization"):
            definition = chain_definition()
            if kind == "operator": definition["nodes"][0]["op"] = "attention"
            if kind == "dtype": definition["tensors"][0]["dtype"] = "int4"
            if kind == "layout": definition["tensors"][0]["layout"] = "blocked"
            if kind == "quantization": definition["tensors"][0]["quantization"] = "W4A8"
            with self.subTest(kind=kind), self.assertRaises(ContractError):
                pkg.write_package(Path(self.work.name) / kind, **definition)

    def test_whole_and_per_constant_checksums(self):
        self.write()
        blob = self.path / "weights.bin"
        values = bytearray(blob.read_bytes())
        values[0] ^= 1
        blob.write_bytes(values)
        self.rejected("CHECKSUM_MISMATCH")
        self.mutate(lambda m: m["weights"].update(sha256=hashlib.sha256(values).hexdigest()))
        self.rejected("CHECKSUM_MISMATCH")

    def test_truncation_offset_overlap_alignment_and_paths(self):
        self.write()
        original = (self.path / "manifest.json").read_bytes()
        edits = [lambda m: m["weights"].update(file="../weights.bin"),
                 lambda m: m["weights"].update(byte_length=1),
                 lambda m: m["tensors"][2]["blob"].update(offset=0),
                 lambda m: m["tensors"][1]["blob"].update(offset=1),
                 lambda m: m["tensors"][1]["blob"].update(length=2**64),
                 lambda m: m["tensors"][0].update(shape=[True])]
        for edit in edits:
            (self.path / "manifest.json").write_bytes(original)
            self.mutate(edit)
            self.rejected()
        (self.path / "manifest.json").write_bytes(original)
        (self.path / "weights.bin").write_bytes(b"short")
        self.rejected("INVALID_MODEL")

    def test_padding_and_nonfinite_rejected_even_with_valid_checksums(self):
        for nonfinite in (False, True):
            path = Path(self.work.name) / str(nonfinite)
            pkg.write_package(path, **chain_definition("float32", padded=True))
            manifest = json.loads((path / "manifest.json").read_text())
            data = bytearray((path / "weights.bin").read_bytes())
            values = np.frombuffer(data, dtype="<f4", count=10)
            values[0 if nonfinite else 3] = np.nan if nonfinite else 7
            manifest["weights"]["sha256"] = hashlib.sha256(data).hexdigest()
            manifest["tensors"][1]["blob"]["sha256"] = hashlib.sha256(data[:40]).hexdigest()
            (path / "weights.bin").write_bytes(data)
            (path / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ContractError) as caught:
                pkg.read_package(path)
            self.assertEqual(caught.exception.code, "NONFINITE" if nonfinite else "INVALID_MODEL")

    def test_metadata_and_weight_resource_limits(self):
        self.path.mkdir()
        (self.path / "manifest.json").write_bytes(b" " * (1024*1024+1))
        self.rejected("RESOURCE_LIMIT")
        (self.path / "manifest.json").unlink()
        self.path.rmdir()
        self.write()
        self.mutate(lambda m: m["weights"].update(byte_length=16*1024*1024+1))
        self.rejected("RESOURCE_LIMIT")

    def test_nonregular_files_are_rejected_before_read(self):
        self.write()
        with mock.patch.object(Path, "is_file", return_value=False):
            self.rejected("IO_ERROR")

    def test_invalid_root_paths_have_typed_errors(self):
        for path in (Path("x\0y"), None):
            with self.subTest(path=repr(path)):
                with self.assertRaises(Exception) as caught:
                    pkg.read_package(path)
                self.assertIsInstance(caught.exception, ContractError)
                self.assertEqual(caught.exception.code, "INVALID_ARGUMENT")
        with self.assertRaises(Exception) as caught:
            pkg.write_package(Path("x\0y"), **chain_definition())
        self.assertIsInstance(caught.exception, ContractError)
        self.assertEqual(caught.exception.code, "INVALID_ARGUMENT")
