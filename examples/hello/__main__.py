"""Hello from embedded Python."""

import sys


def main() -> None:
    text = " ".join(sys.argv[1:])
    if text:
        print(f"Hello from embedded Python: {text}")
    else:
        print("Hello from embedded Python")


if __name__ == "__main__":
    main()
