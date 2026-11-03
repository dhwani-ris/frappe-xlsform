"""Did you mean" suggestions (edit distance <= 2, REQUIREMENTS.md section 6.1)."""

import re


def distance(a: str, b: str) -> int:
	"""Optimal string alignment distance (Levenshtein plus adjacent transpositions)."""
	if a == b:
		return 0
	rows = len(a) + 1
	cols = len(b) + 1
	d = [[0] * cols for _ in range(rows)]
	for i in range(rows):
		d[i][0] = i
	for j in range(cols):
		d[0][j] = j
	for i in range(1, rows):
		for j in range(1, cols):
			cost = 0 if a[i - 1] == b[j - 1] else 1
			d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
			if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
				d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
	return d[-1][-1]


def closest(word: str, candidates, max_distance: int = 2) -> str | None:
	best = None
	best_d = max_distance + 1
	lowered = word.lower()
	for cand in sorted(set(candidates)):
		dist = distance(lowered, cand.lower())
		if dist < best_d:
			best, best_d = cand, dist
	return best


def slug(text: str) -> str:
	"""Turn any text into a valid XLSForm name: household size -> household_size."""
	s = re.sub(r"[^A-Za-z0-9_]+", "_", text.strip()).strip("_").lower()
	s = re.sub(r"_+", "_", s)
	if not s:
		return "question"
	if s[0].isdigit():
		s = "q_" + s
	return s
