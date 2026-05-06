"""Command-line interface for the simple project."""

import argparse

from .calculator import add


def main() -> None:
    parser = argparse.ArgumentParser(description="Add two numbers.")
    parser.add_argument("a", type=float, help="First number")
    parser.add_argument("b", type=float, help="Second number")
    args = parser.parse_args()
    print(add(args.a, args.b))


if __name__ == "__main__":
    main()
