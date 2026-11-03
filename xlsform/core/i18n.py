"""Translation shim for the framework-free core.

The core never imports frappe, so it can be unit-tested without a site. User-facing
strings are marked with ``N_("...")`` (a no-op that Frappe's extractor recognises) and
translated at render time with :func:`translate`. Inside Frappe, ``xlsform.boot``
installs ``frappe._`` as the translator.
"""

from collections.abc import Callable

_translator: Callable[[str], str] = lambda text: text


def N_(text: str) -> str:
	return text


def set_translator(fn: Callable[[str], str]) -> None:
	global _translator
	_translator = fn


def translate(text: str) -> str:
	return _translator(text)


def tr(template: str, **params) -> str:
	"""Translate a ``N_``-marked template, then fill in ``{placeholders}``."""
	return translate(template).format(**params)
