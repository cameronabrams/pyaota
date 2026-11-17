from unittest import TestCase

from pyaota.generator.packing import fits_in_order, packed_order, parse_measures

LOG = '''pyaota-measure: room 397.5pt gap 31.0pt
(some other line)
pyaota-measure: question 1 137.41pt
pyaota-measure: question 2 89.41pt
pyaota-measure: question 3 161.41pt
'''


class TestMeasures(TestCase):

    def test_parse(self):
        self.assertEqual(parse_measures(LOG), (397.5, 31.0, [137.41, 89.41, 161.41]))

    def test_missing_measures(self):
        self.assertIsNone(parse_measures('no measures here'))
        self.assertIsNone(parse_measures(LOG.replace('question 2', 'question 7')))

    def test_last_pass_wins(self):
        self.assertEqual(parse_measures(LOG + 'pyaota-measure: question 1 10.0pt\n')[2][0], 10.0)


class TestPacking(TestCase):
    # heights of a version whose third question is too tall for the room left
    # under the first two, so that the last has nowhere to go
    H, GAP, ROOM = [137, 89, 161, 89, 65, 89], 31, 397

    def test_a_fitting_order_is_kept(self):
        heights = [100, 100, 100, 100]
        self.assertTrue(fits_in_order(heights, 10, 210))
        self.assertEqual(packed_order(heights, 10, 210), [0, 1, 2, 3])

    def test_overflowing_order_is_packed(self):
        self.assertFalse(fits_in_order(self.H, self.GAP, self.ROOM))
        order = packed_order(self.H, self.GAP, self.ROOM)
        self.assertEqual(sorted(order), list(range(6)))
        self.assertTrue(fits_in_order([self.H[i] for i in order], self.GAP, self.ROOM))

    def test_columns_keep_the_drawn_order(self):
        order = packed_order(self.H, self.GAP, self.ROOM)
        for k in range(1, 6):
            first, second = order[:k], order[k:]
            if first == sorted(first) and second == sorted(second):
                break
        else:
            self.fail(f'{order} is not two runs in drawn order')

    def test_too_tall_for_any_split(self):
        self.assertIsNone(packed_order([300, 300, 300], 10, 400))
