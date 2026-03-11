try:
    from _version import __version__
except ImportError:
    # Fallback if _version.py is not available (e.g., in installed PEX without version file)
    __version__ = "0.0.0"
