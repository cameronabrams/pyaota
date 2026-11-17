# Author: Cameron F. Abrams, <cfa22@drexel.edu>
"""
Packing a single-page quiz's questions into two columns.

multicols fills the columns in question order, so a tall question that does not
fit at the bottom of the first column starts the second, and the questions after
it can run out of room although the first column has space.  When a build
overflows, its log holds the height of every question and the room for the
columns (see ``\\putquestionbox`` and the single-page branch of the document);
from those, ``packed_order`` picks which questions go in which column.
"""
import re
from itertools import combinations
from pathlib import Path

_MEASURE = re.compile(r'^pyaota-measure: (question (\d+) ([\d.]+)pt|room ([-\d.]+)pt gap ([\d.]+)pt)$',
                      re.MULTILINE)


def parse_measures(log_text: str):
    """
    Return ``(room, gap, heights)`` in points from a LaTeX log, or None if the
    log does not have them.  ``heights[i]`` is question ``i+1``'s box; ``gap`` is
    the space below each box.  A log of two passes gives the last pass's values.
    """
    room = gap = None
    heights = {}
    for m in _MEASURE.finditer(log_text):
        if m.group(2):
            heights[int(m.group(2))] = float(m.group(3))
        else:
            room, gap = float(m.group(4)), float(m.group(5))
    if room is None or not heights or sorted(heights) != list(range(1, len(heights) + 1)):
        return None
    return room, gap, [heights[i] for i in sorted(heights)]


def column_height(heights, gap) -> float:
    """The height of questions stacked in one column; the last one's gap falls at the break."""
    return sum(heights) + gap * max(len(heights) - 1, 0)


def fits_in_order(heights, gap, room) -> bool:
    """Whether some split of the questions, in this order, fits both columns."""
    return any(column_height(heights[:k], gap) <= room and column_height(heights[k:], gap) <= room
               for k in range(len(heights) + 1))


def packed_order(heights, gap, room):
    """
    Return an order of the question indices (0-based) whose two columns both fit
    in ``room``: the given order if it fits, otherwise the first column's
    questions followed by the second's, each in their given order, choosing the
    most even columns.  Return None if no split fits.
    """
    n = len(heights)
    if fits_in_order(heights, gap, room):
        return list(range(n))
    best = None
    for k in range(1, n):
        for first in combinations(range(n), k):
            second = [i for i in range(n) if i not in first]
            tallest = max(column_height([heights[i] for i in first], gap),
                          column_height([heights[i] for i in second], gap))
            if tallest <= room and (best is None or tallest < best[0]):
                best = (tallest, list(first) + second)
    return best[1] if best else None


def packed_order_from_log(log_path: Path):
    """``packed_order`` from the measures in a build's log, or None without them."""
    if not Path(log_path).exists():
        return None
    measures = parse_measures(Path(log_path).read_text(encoding='utf-8', errors='replace'))
    if measures is None:
        return None
    room, gap, heights = measures
    return packed_order(heights, gap, room)
