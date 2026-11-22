"""
A failing assertion of this suite reports a short message, and at once, however large the values it searched or
compared (a page tree dumped as one line of a megabyte, every file of a folder, a whole replay).

pytest explains a failing `x not in text`, and `a == b` of two texts, with difflib over the whole values: on a
dashboard page of 1.1 MB that took more than two hours once and stalled the whole run. So the tests assert on short
lists of offenders -- conftest.found (where a text holds what it must not), changed (what a snapshot of files lost or
gained), differs (where two replays part) -- and conftest.short_explanations() keeps pytest's own explanation short
for a comparison with a large side that a test still makes. Small values keep pytest's own explanation.
"""
import json
import time

import pytest
from _pytest.assertion import util

from conftest import _LARGE, _large, changed, differs, found, short_explanations


def _page(n):
    """A text shaped like a page tree as the browser gets it: one line of JSON."""
    return json.dumps([{'type': 'Div', 'props': {'className': f'c{i % 7}', 'children': f'line {i} of the page'}}
                       for i in range(n)])


def test_found_says_where_and_changed_and_differs_what():
    page = _page(20000)
    assert found(page, 'not there') == [] and found(page.encode(), 'not there') == []
    hits = found(page, 'line 19999 of', 'line 5 of')
    assert len(hits) == 2 and all(len(h) < 300 for h in hits) and hits[0].startswith("'line 19999 of' at ")
    assert len(found(page, 'of the page')) == 3                        # (the first three places, not 20,000)
    assert found(page.encode(), 'line 7 of')[0].startswith("'line 7 of' at ")
    assert found(['a', 'b'], 'b', 'c') == ["'b'"] and found({'k': 1}, 'k') == ["'k'"] and found(set(), 'x') == []
    before = {'a': (1, 10), 'b': (2, 20)}
    assert changed(before, dict(before)) == []
    assert changed(before, {'a': (1, 11), 'c': (3, 30)}) == ['added c', 'removed b', 'changed a']
    assert differs([1, 2, 3], [1, 2, 3]) == [] and differs({'x': 1}, {'x': 1}) == []
    long_a = [{'t': i, 'v': 'x' * 50} for i in range(50000)]
    long_b = [dict(x) for x in long_a]
    long_b[40000]['v'] = 'y'
    said = differs(long_a, long_b)
    assert said[0] == 'the first difference at index 40000:' and sum(len(s) for s in said) < 1500
    assert differs(long_a, long_a[:-1])[0] == 'lengths 50000 and 49999'
    assert 'differs at' in differs({'a': 1, 'b': 2}, {'a': 1, 'b': 3})[0]


def test_a_failing_assertion_on_a_huge_text_is_explained_in_short_and_at_once(pytestconfig):
    """The explanation pytest makes for a failing comparison (what a test's `assert` prints) takes milliseconds and
    a few hundred characters for a megabyte of page; pytest's own takes more than a minute on such a page."""
    assert short_explanations()                                         # (made at the start of the run: conftest)
    page = _page(40000)
    assert len(page) > 1_000_000 and _large(page) and not _large('x' * (_LARGE - 1))
    t0 = time.monotonic()
    said = util.assertrepr_compare(pytestconfig, 'not in', 'line 30000 of', page)
    said += util.assertrepr_compare(pytestconfig, '==', page, page.replace('line 39000 ', 'line 39000! '))
    rows = [{'t': i, 'v': 'x' * 40} for i in range(50000)]
    said += util.assertrepr_compare(pytestconfig, '==', rows, rows[:-1] + [{'t': -1}])
    files = {f'/bot_output/f{i}': (i, i) for i in range(30000)}
    said += util.assertrepr_compare(pytestconfig, '==', files, dict(files, extra=(1, 1)))
    assert time.monotonic() - t0 < 5.0
    text = '\n'.join(said)
    assert len(text) < 4000 and 'line 30000 of' in text and 'the first difference at index 49999' in text
    assert "only right: 'extra'" in text
    # an assert statement of a test (rewritten by pytest, as every test's is): the same, through pytest's own path
    t0 = time.monotonic()
    with pytest.raises(AssertionError) as e:
        assert 'line 30000 of' not in page
    assert time.monotonic() - t0 < 5.0 and len(str(e.value)) < 4000
    # small values keep pytest's own explanation
    own = util.assertrepr_compare(pytestconfig, '==', 'abc', 'abd')
    assert own and not any('a large value' in line for line in own)
