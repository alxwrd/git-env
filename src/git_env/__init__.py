import importlib.metadata

try:
    __version__ = importlib.metadata.version("git-env")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0+dev"


def main() -> None:
    import __main__

    __main__.__version__ = __version__

    from .cli import main as cli_main

    cli_main()
