from xlsform.runtime.settings import is_designer


def has_app_permission() -> bool:
	"""Show the XLSForm tile to designers and System Managers."""
	return is_designer()
