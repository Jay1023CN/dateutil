from __future__ import unicode_literals

import copy
import itertools
import pickle
from datetime import datetime, timedelta

import pytest

from dateutil import tz
from dateutil.rrule import DAILY, MO, MONTHLY, rrule, rruleset


class TaggedRule(rrule):
    __slots__ = ("tag",)


@pytest.fixture(params=["deepcopy"] + list(range(pickle.HIGHEST_PROTOCOL + 1)))
def roundtrip(request):
    if request.param == "deepcopy":
        return copy.deepcopy
    return lambda value: pickle.loads(pickle.dumps(value, request.param))


def make_rule(kind, cache):
    start = datetime(2024, 1, 1)
    dates = [start + timedelta(days=i) for i in range(25)]
    rule = rrule(DAILY, dtstart=start, count=25, cache=cache)
    if kind == "rule":
        return rule, dates

    result = rruleset(cache=cache)
    result.rrule(rule)
    result.exrule(rrule(DAILY, dtstart=start, interval=3, count=9, cache=cache))
    result.exdate(dates[1])
    extra = start + timedelta(days=35)
    result.rdate(extra)
    expected = [value for i, value in enumerate(dates) if i % 3 and i != 1]
    return result, expected + [extra]


@pytest.mark.parametrize("kind", ["rule", "set"])
@pytest.mark.parametrize("state", ["disabled", "empty", "partial", "complete"])
def test_rrule_roundtrip(roundtrip, kind, state):
    original, expected = make_rule(kind, state != "disabled")
    iterator = None
    if state == "partial":
        iterator = iter(original)
        assert next(iterator) == expected[0]
    elif state == "complete":
        assert list(original) == expected

    restored = roundtrip(original)
    assert list(restored) == expected
    assert restored.count() == len(expected)
    assert restored.before(expected[-1]) == expected[-2]
    assert restored.after(expected[0]) == expected[1]
    assert restored[2:5] == expected[2:5]
    assert expected[1] in restored
    if iterator is not None:
        assert list(iterator) == expected[1:]
    assert list(original) == expected


@pytest.mark.parametrize("state", ["empty", "partial", "complete"])
def test_restored_rruleset_can_invalidate_cache(roundtrip, state):
    original, expected = make_rule("set", True)
    if state == "partial":
        next(iter(original))
    elif state == "complete":
        list(original)

    restored = roundtrip(original)
    restored.exdate(expected[0])
    extra = datetime(2024, 3, 1)
    restored.rdate(extra)
    assert list(restored) == expected[1:] + [extra]
    assert list(original) == expected


@pytest.mark.parametrize("kind", ["rule", "set"])
def test_unbounded_cached_rule_roundtrip(roundtrip, kind):
    original = rrule(DAILY, dtstart=datetime(2024, 1, 1), cache=True)
    if kind == "set":
        result = rruleset(cache=True)
        result.rrule(original)
        original = result
    expected = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(15)]
    assert list(itertools.islice(original, 12)) == expected[:12]
    restored = roundtrip(original)
    assert list(itertools.islice(restored, 15)) == expected


def test_cached_rule_preserves_options_and_timezone():
    original = rrule(
        MONTHLY,
        dtstart=datetime(2024, 1, 1, tzinfo=tz.UTC),
        count=4,
        byweekday=MO(1),
        byhour=9,
        cache=True,
    )
    expected = [
        datetime(2024, month, day, 9, tzinfo=tz.UTC)
        for month, day in [(1, 1), (2, 5), (3, 4), (4, 1)]
    ]
    next(iter(original))
    # Weekday objects already require protocol 2 or later; their legacy
    # protocol support is independent of the recurrence cache.
    for protocol in range(2, pickle.HIGHEST_PROTOCOL + 1):
        restored = pickle.loads(pickle.dumps(original, protocol))
        assert list(restored) == expected
        assert str(restored) == str(original)
    assert list(copy.deepcopy(original)) == expected


@pytest.mark.parametrize("cache", [False, True])
def test_rrule_subclass_state_roundtrip(roundtrip, cache):
    original = TaggedRule(
        DAILY, dtstart=datetime(2024, 1, 1), count=2, cache=cache
    )
    original.tag = ["slot value"]
    original.extra = {"attribute": "value"}
    restored = roundtrip(original)
    assert type(restored) is TaggedRule
    assert restored.tag == original.tag
    assert restored.extra == original.extra
    restored.tag.append("new value")
    assert original.tag == ["slot value"]
    assert list(restored) == list(original)


@pytest.mark.parametrize("kind", ["rule", "set"])
def test_completed_empty_cache_roundtrip(roundtrip, kind):
    if kind == "rule":
        original = rrule(
            DAILY, dtstart=datetime(2024, 1, 1), count=0, cache=True
        )
    else:
        original = rruleset(cache=True)
    assert list(original) == []
    restored = roundtrip(original)
    assert list(restored) == []
    assert restored.count() == 0
