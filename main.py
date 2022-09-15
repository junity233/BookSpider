#!/usr/bin/python3

from cli.cli import cli_main
from core.manager import Manager


def main(*args) -> int:
    mgr = Manager()
    cli_main(mgr)


if __name__ == "__main__":
    exit(main())
