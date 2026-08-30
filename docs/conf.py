"""Sphinx configuration for strict local documentation builds."""

project = "ASC OS"
copyright = "2026, AI4SciComp"  # noqa: A001
author = "AI4SciComp contributors"
release = "0.1.0"
extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.doctest"]
source_suffix = {".md": "markdown"}
exclude_patterns = ["_build"]
html_theme = "furo"
nitpicky = True
linkcheck_ignore = [r"https://github.com/AI4SciComp/asc-os/issues/.*"]
