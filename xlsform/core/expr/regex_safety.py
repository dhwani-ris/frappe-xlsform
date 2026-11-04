"""Safe ``regex()``: which patterns are accepted, and a matcher that can't be made slow.

Python's ``re`` backtracks, so a pattern such as ``^([a-z0-9]+\\s?)*$`` takes exponential
time on a crafted answer, and even ``x.*y.*z`` takes polynomial time. No new dependency
(RE2) is allowed, so:

1. At upload, a pattern must be fixed text of at most ``MAX_PATTERN_LENGTH`` characters,
   valid, without back-references, look-arounds, conditionals, atomic or possessive parts
   or flags, without a repeat inside a repeat (``(x+)*``), and without a repeated choice
   whose alternatives can start with the same character (``(ab|ac)*``). Others get
   ``E-REGEX-UNSAFE``.
2. On the server, accepted patterns run on :class:`Matcher`, a Thompson NFA built from the
   tree of Python's own regex parser. It visits each character once per state, so a match
   costs at most ``len(text) * states``. Text longer than ``MAX_INPUT_LENGTH`` and any
   pattern outside the safe set never match (the constraint fails; nothing is slow).
"""

import operator
import re
from functools import lru_cache, partial
from re import _parser as sre

from xlsform.core.i18n import N_

MAX_PATTERN_LENGTH = 200
MAX_INPUT_LENGTH = 1000
MAX_STATES = 4000

REASON_LENGTH = N_("it is longer than {limit} characters")
REASON_INVALID = N_("it isn't a valid pattern")
REASON_FEATURE = N_("back-references, look-arounds, flags and conditionals can't be used")
REASON_NESTED = N_("a repeated part contains another repeat, as in (a+)*")
REASON_ALTERNATION = N_("a repeated part has alternatives that can start with the same character")
REASON_DYNAMIC = N_("the pattern must be fixed text in quotes")

REPEATS = {"MAX_REPEAT", "MIN_REPEAT"}
ATOMS = {"LITERAL", "NOT_LITERAL", "ANY", "IN"}
ASSERTIONS = {
	"AT_BEGINNING",
	"AT_BEGINNING_STRING",
	"AT_END",
	"AT_END_STRING",
	"AT_BOUNDARY",
	"AT_NON_BOUNDARY",
}
UNICODE_ONLY = int(re.UNICODE)


class _Unsafe(Exception):
	def __init__(self, reason: str):
		super().__init__(reason)
		self.reason = reason


def unsafe_reason(pattern: str) -> str | None:
	"""``None`` for a safe pattern, else an ``N_``-marked reason (``{limit}`` to fill in)."""
	return _compile(pattern)[1]


def safe_search(pattern: str, text: str) -> bool:
	"""Whether ``pattern`` matches somewhere in ``text``; False for unsafe patterns or long text."""
	matcher, reason = _compile(pattern)
	if reason is not None or len(text) > MAX_INPUT_LENGTH:
		return False
	return matcher.search(text)


@lru_cache(maxsize=512)
def _compile(pattern: str) -> tuple["Matcher | None", str | None]:
	if len(pattern) > MAX_PATTERN_LENGTH:
		return None, REASON_LENGTH
	try:
		re.compile(pattern)
		tree = sre.parse(pattern)
	except (re.error, RecursionError, OverflowError):
		return None, REASON_INVALID
	try:
		if tree.state.flags & ~UNICODE_ONLY:
			raise _Unsafe(REASON_FEATURE)
		items = list(tree)
		_check(items, inside_repeat=False)
		return Matcher(items), None
	except _Unsafe as exc:
		return None, exc.reason
	except RecursionError:
		return None, REASON_INVALID


def _check(items: list, inside_repeat: bool) -> None:
	for op, av in items:
		name = str(op)
		if name in REPEATS:
			_low, high, body = av
			body = list(body)
			repeats = high > 1
			if repeats and inside_repeat:
				raise _Unsafe(REASON_NESTED)
			if repeats:
				_check_alternation(body)
			_check(body, inside_repeat or repeats)
		elif name == "SUBPATTERN":
			if av[1] or av[2]:
				raise _Unsafe(REASON_FEATURE)
			_check(list(av[3]), inside_repeat)
		elif name == "BRANCH":
			for alternative in av[1]:
				_check(list(alternative), inside_repeat)
		elif name == "AT":
			if str(av) not in ASSERTIONS:
				raise _Unsafe(REASON_FEATURE)
		elif name not in ATOMS:
			raise _Unsafe(REASON_FEATURE)


def _check_alternation(items: list) -> None:
	for op, av in items:
		name = str(op)
		if name == "SUBPATTERN":
			_check_alternation(list(av[3]))
		elif name == "BRANCH":
			seen: set[str] = set()
			for alternative in av[1]:
				first = _first_chars(list(alternative))
				if first is None or seen & first:
					raise _Unsafe(REASON_ALTERNATION)
				seen |= first


PROBE = [chr(c) for c in range(32, 127)] + ["\t", "\n", " ", "é", "अ", "१", "一"]


def _first_chars(items: list) -> set[str] | None:
	"""Probe characters a sequence can start with; ``None`` when it can match empty text."""
	out: set[str] = set()
	for op, av in items:
		name = str(op)
		if name == "AT":
			continue
		if name in REPEATS:
			inner = _first_chars(list(av[2]))
			out |= inner or set()
			if av[0] == 0 or inner is None:
				continue
			return out
		if name == "SUBPATTERN":
			inner = _first_chars(list(av[3]))
			if inner is None:
				continue
			return out | inner
		if name == "BRANCH":
			alternatives = [_first_chars(list(a)) for a in av[1]]
			out |= set().union(*(a for a in alternatives if a))
			if any(a is None for a in alternatives):
				continue
			return out
		test = _predicate(name, av)
		return out | {c for c in PROBE if test(c)}
	return None


def _is_word(ch: str) -> bool:
	return ch.isalnum() or ch == "_"


CATEGORIES = {
	"CATEGORY_DIGIT": str.isdecimal,
	"CATEGORY_NOT_DIGIT": lambda c: not c.isdecimal(),
	"CATEGORY_SPACE": str.isspace,
	"CATEGORY_NOT_SPACE": lambda c: not c.isspace(),
	"CATEGORY_WORD": _is_word,
	"CATEGORY_NOT_WORD": lambda c: not _is_word(c),
}


def _predicate(name: str, av):
	if name == "LITERAL":
		return partial(operator.eq, chr(av))
	if name == "NOT_LITERAL":
		return partial(operator.ne, chr(av))
	if name == "ANY":
		return lambda c: c != "\n"
	return _class_predicate(list(av))


def _class_predicate(items: list):
	negate = False
	tests = []
	for op, av in items:
		name = str(op)
		if name == "NEGATE":
			negate = True
		elif name == "LITERAL":
			tests.append(partial(operator.eq, chr(av)))
		elif name == "RANGE":
			tests.append(lambda c, lo=av[0], hi=av[1]: lo <= ord(c) <= hi)
		elif name == "CATEGORY" and str(av) in CATEGORIES:
			tests.append(CATEGORIES[str(av)])
		else:
			raise _Unsafe(REASON_FEATURE)

	def test(c: str) -> bool:
		return any(t(c) for t in tests) != negate

	return test


class Matcher:
	"""A Thompson NFA for the safe subset; ``search`` runs in O(len(text) x states)."""

	def __init__(self, items: list):
		self.states: list[tuple] = [("match",)]
		self.start = self._sequence(items, 0)

	def _add(self, state: tuple) -> int:
		if len(self.states) >= MAX_STATES:
			raise _Unsafe(REASON_LENGTH)
		self.states.append(state)
		return len(self.states) - 1

	def _sequence(self, items: list, nxt: int) -> int:
		for item in reversed(items):
			nxt = self._item(item, nxt)
		return nxt

	def _item(self, item, nxt: int) -> int:
		op, av = item
		name = str(op)
		if name in ATOMS:
			return self._add(("char", _predicate(name, av), nxt))
		if name == "AT":
			return self._add(("assert", str(av), nxt))
		if name == "SUBPATTERN":
			return self._sequence(list(av[3]), nxt)
		if name == "BRANCH":
			return self._add(("alt", tuple(self._sequence(list(a), nxt) for a in av[1])))
		low, high, body = av
		body = list(body)
		if high == sre.MAXREPEAT:
			loop = self._add(("alt", ()))
			self.states[loop] = ("alt", (self._sequence(body, loop), nxt))
			current = loop
		else:
			current = nxt
			for _ in range(high - low):
				current = self._add(("alt", (self._sequence(body, current), nxt)))
		for _ in range(low):
			current = self._sequence(body, current)
		return current

	def search(self, text: str) -> bool:
		active, matched = self._closure([self.start], text, 0)
		for i, ch in enumerate(text):
			if matched:
				return True
			moved = [self.states[s][2] for s in active if self.states[s][1](ch)]
			moved.append(self.start)
			active, matched = self._closure(moved, text, i + 1)
		return matched

	def _closure(self, seeds: list[int], text: str, i: int) -> tuple[list[int], bool]:
		seen: set[int] = set()
		chars: list[int] = []
		stack = list(reversed(seeds))
		while stack:
			s = stack.pop()
			if s in seen:
				continue
			seen.add(s)
			state = self.states[s]
			kind = state[0]
			if kind == "match":
				return chars, True
			if kind == "char":
				chars.append(s)
			elif kind == "alt":
				stack.extend(state[1])
			elif _holds(state[1], text, i):
				stack.append(state[2])
		return chars, False


def _holds(assertion: str, text: str, i: int) -> bool:
	n = len(text)
	if assertion in ("AT_BEGINNING", "AT_BEGINNING_STRING"):
		return i == 0
	if assertion == "AT_END":
		return i == n or (i == n - 1 and text[i] == "\n")
	if assertion == "AT_END_STRING":
		return i == n
	before = i > 0 and _is_word(text[i - 1])
	after = i < n and _is_word(text[i])
	return (before != after) == (assertion == "AT_BOUNDARY")
