from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from rv32_rtl import select_rtl


class RTLSelectionTests(unittest.TestCase):
    def test_overlay_is_explicit_and_leaves_archived_rtl_unchanged(self):
        path=ROOT/'docs/target_platform_sources/main/fpga/generated/qinglong_all.sv';before=path.read_bytes()
        original,a=select_rtl(ROOT,'upstream');portable,b=select_rtl(ROOT,'portable-metadata')
        self.assertEqual(original,before);self.assertEqual(path.read_bytes(),before)
        self.assertFalse(a['local_overlay']);self.assertTrue(b['local_overlay'])
        self.assertNotEqual(a['selected_sha256'],b['selected_sha256'])
        self.assertEqual(portable.count(b'fetch_meta[fi] <= response_meta;'),1)
        self.assertEqual(portable.count(b'fetch_meta[fi] <= response_meta_second;'),1)
        self.assertIsNone(b['formal_equivalence']);self.assertFalse(b['hardware_verified'])
        with self.assertRaises(ValueError):select_rtl(ROOT,'other')
