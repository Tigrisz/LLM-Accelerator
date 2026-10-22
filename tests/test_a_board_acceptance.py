import struct
import unittest
from scripts.accept_multigroup_float import raw_records


class ArchivedFrameTests(unittest.TestCase):
    def frame(self):
        return b'\xa5\x5a\x01' + struct.pack('<I', 2) + struct.pack('<HHiHHi', 2, 1, -2147483648, 0, 3, 2147483647) + b'\x5a\xa5'

    def test_signed_extremes_and_actual_tag_order(self):
        records = raw_records(self.frame(), 2)
        self.assertEqual(records, [dict(row_id=2, group_id=1, partial_sum=-2147483648),
                                   dict(row_id=0, group_id=3, partial_sum=2147483647)])

    def test_incomplete_extra_or_wrong_header_count_footer_rejected(self):
        frame = self.frame()
        for bad in (frame[:-1], frame+b'\x00', b'\x00'+frame[1:],
                    frame[:3]+struct.pack('<I',3)+frame[7:], frame[:-1]+b'\x00'):
            with self.subTest(frame=bad), self.assertRaises(ValueError):
                raw_records(bad,2)


if __name__=='__main__':
    unittest.main()
