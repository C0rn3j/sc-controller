"""Register the dynamically generated GdkX11 GI module for analysis."""


def pre_safe_import_module(api):
	api.add_runtime_module(api.module_name)
