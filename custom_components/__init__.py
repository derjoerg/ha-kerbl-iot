"""Namespace marker only.

This file exists purely so static tooling (mypy, pytest) resolves
``custom_components.kerbl_iot`` as a qualified package instead of treating
``kerbl_iot`` as a top-level module -- which would collide with the actual
``kerbl_iot`` PyPI package this integration depends on. Home Assistant
itself does not care either way: it discovers integrations by scanning the
``custom_components`` directory on disk, not by importing it as a package.
"""
