import copy
import hashlib
import importlib
import json
from pathlib import Path
import unittest

import numpy as np

from inference_ref.contracts import ContractError
from tests.support import Workspace

try:
    fixtures = importlib.import_module("inference_ref.fixtures")
except ModuleNotFoundError:
    fixtures = None


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(fixtures, "A2 fixture implementation is missing")
        self.temp = Workspace()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "case"

    def write_case(self):
        fixtures.write_fixture(
            self.path, "hand_case", "linear",
            {"weight": np.array([[1, 2, -3], [4, 0, 1]], np.int32),
             "input": np.array([2, 3, -1], np.int32)},
            np.array([11, 7], np.int32),
            storage_shapes={"weight": (2, 5), "input": (5,)},
            provenance={"kind": "manual", "source": "hand calculation", "seed": None},
        )
        return json.loads((self.path / "manifest.json").read_text(encoding="utf-8"))

    def rewrite(self, meta, data=None, repair=False):
        if data is not None:
            (self.path / "data.bin").write_bytes(data)
        if repair:
            data = (self.path / "data.bin").read_bytes()
            meta["payload"]["sha256"] = hashlib.sha256(data).hexdigest()
            for item in meta["tensors"]:
                chunk = data[item["offset"]:item["offset"] + item["byte_length"]]
                item["sha256"] = hashlib.sha256(chunk).hexdigest()
        (self.path / "manifest.json").write_text(
            json.dumps(meta, allow_nan=False), encoding="utf-8"
        )

    def test_roundtrip_padded_shapes_and_little_endian(self):
        self.write_case()
        case = fixtures.read_fixture(self.path)
        np.testing.assert_array_equal(case.inputs["weight"], [[1, 2, -3], [4, 0, 1]])
        np.testing.assert_array_equal(case.expected, [11, 7])
        self.assertEqual(case.metadata["case_id"], "hand_case")
        self.assertFalse(case.inputs["weight"].flags.writeable)
        raw = (self.path / "data.bin").read_bytes()
        self.assertIn(b"\xfd\xff\xff\xff", raw)  # -3, little endian INT32

    def test_existing_output_is_not_overwritten(self):
        self.write_case()
        before = (self.path / "manifest.json").read_bytes()
        with self.assertRaises(ContractError) as error:
            self.write_case()
        self.assertEqual(error.exception.code, "ALREADY_EXISTS")
        self.assertEqual(before, (self.path / "manifest.json").read_bytes())

    def test_payload_tamper_and_truncation_are_rejected(self):
        self.write_case()
        original = (self.path / "data.bin").read_bytes()
        for data in (bytes([original[0] ^ 1]) + original[1:], original[:-1]):
            (self.path / "data.bin").write_bytes(data)
            with self.assertRaises(ContractError):
                fixtures.read_fixture(self.path)

    def test_tensor_hash_is_checked_independently(self):
        meta = self.write_case()
        meta["tensors"][0]["sha256"] = "0" * 64
        self.rewrite(meta)
        with self.assertRaises(ContractError) as error:
            fixtures.read_fixture(self.path)
        self.assertEqual(error.exception.code, "CHECKSUM_MISMATCH")

    def test_padding_is_checked_even_after_hashes_are_repaired(self):
        meta = self.write_case()
        record = next(t for t in meta["tensors"] if t["name"] == "input")
        data = bytearray((self.path / "data.bin").read_bytes())
        data[record["offset"] + 3 * 4] = 1
        self.rewrite(meta, bytes(data), repair=True)
        with self.assertRaises(ContractError) as error:
            fixtures.read_fixture(self.path)
        self.assertEqual(error.exception.code, "INVALID_FIXTURE")

    def test_malformed_metadata_is_rejected(self):
        original = self.write_case()
        mutations = []
        bad = copy.deepcopy(original); bad["version"] = 2; mutations.append(bad)
        bad = copy.deepcopy(original); bad["version"] = True; mutations.append(bad)
        bad = copy.deepcopy(original); bad["unexpected"] = 1; mutations.append(bad)
        bad = copy.deepcopy(original); del bad["provenance"]; mutations.append(bad)
        bad = copy.deepcopy(original); bad["payload"]["file"] = "../outside.bin"; mutations.append(bad)
        bad = copy.deepcopy(original); bad["provenance"]["seed"] = True; mutations.append(bad)
        bad = copy.deepcopy(original); bad["operation"]["inputs"] = ["weight", "weight"]; mutations.append(bad)
        bad = copy.deepcopy(original); bad["operation"]["attributes"] = {"transpose": True}; mutations.append(bad)
        bad = copy.deepcopy(original); bad["tensors"][0]["dtype"] = "int4"; mutations.append(bad)
        bad = copy.deepcopy(original); bad["tensors"][0]["role"] = "garbage"; mutations.append(bad)
        bad = copy.deepcopy(original); bad["tensors"][0]["offset"] = True; mutations.append(bad)
        bad = copy.deepcopy(original); bad["tensors"][0]["offset"] = 1; mutations.append(bad)
        bad = copy.deepcopy(original); bad["tensors"][0]["byte_length"] += 4; mutations.append(bad)
        bad = copy.deepcopy(original); bad["tensors"][0]["shape"] = [2**63]; mutations.append(bad)
        bad = copy.deepcopy(original); bad["tensors"][1]["name"] = bad["tensors"][0]["name"]; mutations.append(bad)
        bad = copy.deepcopy(original); bad["tensors"][1]["offset"] = 0; mutations.append(bad)
        bad = copy.deepcopy(original); bad["comparison"]["mode"] = "abs_plus_rel"; mutations.append(bad)
        bad = copy.deepcopy(original); bad["comparison"]["atol"] = 10**400; mutations.append(bad)
        for index, meta in enumerate(mutations):
            with self.subTest(index=index):
                self.rewrite(meta)
                with self.assertRaises(ContractError):
                    fixtures.read_fixture(self.path)

    def test_duplicate_json_keys_and_nonfinite_json_are_rejected(self):
        self.write_case()
        for text in ('{"version":1,"version":1}', '{"version":NaN}'):
            (self.path / "manifest.json").write_text(text, encoding="utf-8")
            with self.assertRaises(ContractError):
                fixtures.read_fixture(self.path)

    def test_operation_output_shape_must_match(self):
        meta = self.write_case()
        output = next(t for t in meta["tensors"] if t["name"] == "expected")
        output["shape"] = [1, 2]; output["storage_shape"] = [1, 2]
        self.rewrite(meta)
        with self.assertRaises(ContractError):
            fixtures.read_fixture(self.path)

    def test_missing_file_and_invalid_json_have_typed_errors(self):
        with self.assertRaises(ContractError) as error:
            fixtures.read_fixture(self.path)
        self.assertEqual(error.exception.code, "IO_ERROR")
        self.write_case()
        (self.path / "manifest.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(ContractError) as error:
            fixtures.read_fixture(self.path)
        self.assertEqual(error.exception.code, "INVALID_FIXTURE")

    def test_invalid_writer_input_does_not_create_directory(self):
        with self.assertRaises(ContractError):
            fixtures.write_fixture(
                self.path, "bad_case", "relu", {"input": np.ones(2, np.float32)},
                np.ones(2, np.float32), storage_shapes={"input": (1,)},
                provenance={"kind": "synthetic", "source": "unit test", "seed": 0},
            )
        self.assertFalse(self.path.exists())

    def test_writer_requires_explicit_matching_dtype(self):
        with self.assertRaises(ContractError):
            fixtures.write_fixture(
                self.path, "bad_case", "relu", {"input": np.ones(2, np.float64)},
                np.ones(2, np.float64),
                provenance={"kind": "synthetic", "source": "unit test", "seed": 0},
            )
        self.assertFalse(self.path.exists())
