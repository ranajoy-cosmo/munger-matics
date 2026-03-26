"""Smoke tests — verify the package is importable and fundamentally intact."""


def test_package_imports() -> None:
    import munger_matics

    assert munger_matics is not None
