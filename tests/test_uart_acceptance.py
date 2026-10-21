import struct
import unittest
import numpy as np
from scripts.audit_uart_delivery import dequantize, unified_capture
from scripts.compare_results import compare


class UartAcceptanceTests(unittest.TestCase):
    def test_nonuniform_group_scales(self):
        # Summing integer groups before scaling would give zero instead of -2.
        p = np.array([[2, -2]], dtype=np.int32)
        s = np.array([[1., 3.]])
        np.testing.assert_array_equal(dequantize(p, s, np.array(.5)), [-2.])

    def test_bad_scales(self):
        p = np.array([[1, 2]], dtype=np.int32)
        for s, a in [(np.ones((2, 1)), np.array(1.)),
                     (np.array([[1., np.nan]]), np.array(1.)),
                     (np.array([[1., -1.]]), np.array(1.)),
                     (np.array([[1., 0.]]), np.array(1.)),
                     (np.ones((1, 2)), np.array([1.])),
                     (np.ones((1, 2)), np.array(np.inf))]:
            with self.subTest(scales=s, activation=a), self.assertRaises(ValueError):
                dequantize(p, s, a)

    def test_raw_order_and_sign_preserved(self):
        frame = b'\xa5\x5a\x01' + struct.pack('<I', 2)
        frame += struct.pack('<HHi', 0, 1, -7) + struct.pack('<HHi', 0, 0, 4) + b'\x5a\xa5'
        capture = unified_capture(frame, 'simulation', 'test')
        self.assertEqual(capture['results'][0]['partial_sum'], -7)
        result = compare([[4, -7]], capture)
        self.assertEqual(result['error_counts'], {'order': 2})
        self.assertEqual(capture['source'], 'simulation')
        with self.assertRaises(ValueError):
            unified_capture(frame[:-1], 'board', 'truncated')

    def test_integer_type_and_range(self):
        for p in (np.array([[1.]]), np.array([[2**31]], dtype=np.int64)):
            with self.assertRaises(ValueError):
                dequantize(p, np.ones((1, 1)), np.array(1.))


if __name__ == '__main__':
    unittest.main()
