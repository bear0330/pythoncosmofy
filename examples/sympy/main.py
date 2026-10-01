"""SymPy command line for humans and for APEBind.

Each command prints one JSON object on stdout: {"result", "latex"}.
--text prints only the result string, for a terminal. The reviewed
APEBind schema leaves --text out so generated calls always receive JSON.
"""

from __future__ import annotations

import argparse
import json
import sys

import sympy

_DEFAULT_NAMES = ("x", "y", "z", "t", "n", "k")
_BOOLEAN_OPTIONS = frozenset({"-h", "--help", "--text"})
_VALUE_OPTIONS = frozenset({"--var", "--order", "--point", "--value", "--digits"})


def _normalize(argv: list[str]) -> list[str]:
    """Move options in front of the expression and accept a leading '-'."""
    if not argv or argv[0].startswith("-"):
        return list(argv)

    command = argv[0]
    options: list[str] = []
    positionals: list[str] = []
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--":
            positionals.extend(argv[index + 1 :])
            break
        if token in _BOOLEAN_OPTIONS:
            options.append(token)
            index += 1
            continue
        if token in _VALUE_OPTIONS:
            if index + 1 >= len(argv):
                return list(argv)
            options.extend((token, argv[index + 1]))
            index += 2
            continue
        if token.startswith("--") and "=" in token:
            flag = token.split("=", 1)[0]
            if flag in _VALUE_OPTIONS or flag in _BOOLEAN_OPTIONS:
                options.append(token)
                index += 1
                continue
        positionals.append(token)
        index += 1

    if not positionals:
        return [command, *options]
    return [command, *options, "--", *positionals]


def _namespace(var_spec: str) -> tuple[dict[str, object], sympy.Symbol]:
    names: list[str] = []
    for part in var_spec.split(","):
        part = part.strip()
        if part and part not in names:
            names.append(part)
    for name in _DEFAULT_NAMES:
        if name not in names:
            names.append(name)
    table = dict(sympy.__dict__)
    symbols = {name: sympy.symbols(name) for name in names}
    table.update(symbols)
    return table, symbols[names[0]]


def _point(text: str, table: dict[str, object]) -> object:
    return sympy.sympify(text, locals=table)


def _compute(args: argparse.Namespace) -> object:
    if args.command == "version":
        return sympy.__version__
    table, symbol = _namespace(args.var)
    expr = eval(args.expr, {"__builtins__": {}}, table)
    if args.command == "eval":
        return expr
    if args.command == "simplify":
        return sympy.simplify(expr)
    if args.command == "expand":
        return sympy.expand(expr)
    if args.command == "factor":
        return sympy.factor(expr)
    if args.command == "apart":
        return sympy.apart(expr)
    if args.command == "diff":
        return sympy.diff(expr, symbol, args.order)
    if args.command == "integrate":
        return sympy.integrate(expr, symbol)
    if args.command == "solve":
        return sympy.solve(expr, symbol)
    if args.command == "limit":
        return sympy.limit(expr, symbol, _point(args.point, table))
    if args.command == "series":
        return sympy.series(expr, symbol, _point(args.point, table), args.order)
    if args.command == "subs":
        return expr.subs(symbol, _point(args.value, table))
    if args.command == "numeric":
        return sympy.N(expr, args.digits)
    raise AssertionError(args.command)


def _emit(result: object, as_text: bool) -> None:
    text = str(result)
    if as_text:
        print(text)
        return
    if isinstance(result, str):
        latex = result
    else:
        latex = sympy.latex(result)
    json.dump({"result": text, "latex": latex}, sys.stdout)
    sys.stdout.write("\n")


def _parser() -> argparse.ArgumentParser:
    text = argparse.ArgumentParser(add_help=False)
    text.add_argument(
        "--text",
        action="store_true",
        help="Print only the result text. The default is a JSON object.",
    )
    symbols = argparse.ArgumentParser(add_help=False)
    symbols.add_argument(
        "--var",
        default="x",
        metavar="NAMES",
        help="Comma-separated symbols. The first one is the active symbol. Default: x.",
    )

    parser = argparse.ArgumentParser(
        prog="sympy.com",
        description="Evaluate, rewrite, and solve SymPy expressions.",
    )
    commands = parser.add_subparsers(dest="command", title="commands", required=True)

    def add(name: str, help_text: str, *, expression: bool = True) -> argparse.ArgumentParser:
        parents = [text, symbols] if expression else [text]
        command = commands.add_parser(
            name,
            help=help_text,
            description=help_text,
            parents=parents,
        )
        if expression:
            command.add_argument(
                "expr",
                metavar="EXPR",
                help="SymPy expression, for example sin(x).",
            )
        return command

    add("version", "Print the SymPy version.", expression=False)
    add("eval", "Evaluate an expression.")
    add("simplify", "Simplify an expression.")
    add("expand", "Expand an expression.")
    add("factor", "Factor an expression.")
    add("apart", "Compute a partial-fraction decomposition.")
    diff = add("diff", "Differentiate an expression.")
    diff.add_argument(
        "--order",
        type=int,
        default=1,
        metavar="NUMBER",
        help="Derivative order. Default: 1.",
    )
    add("integrate", "Integrate an expression.")
    add("solve", "Solve an expression set equal to zero.")
    limit = add("limit", "Take a limit.")
    limit.add_argument(
        "--point",
        default="0",
        metavar="POINT",
        help="Point the variable approaches. Default: 0.",
    )
    series = add("series", "Expand a series.")
    series.add_argument(
        "--point",
        default="0",
        metavar="POINT",
        help="Expansion point. Default: 0.",
    )
    series.add_argument(
        "--order",
        type=int,
        default=6,
        metavar="NUMBER",
        help="Series order. Default: 6.",
    )
    subs = add("subs", "Substitute a value for the active symbol.")
    subs.add_argument(
        "--value",
        required=True,
        metavar="VALUE",
        help="Value that replaces the active symbol, for example 2 or pi/2.",
    )
    numeric = add("numeric", "Evaluate an expression numerically.")
    numeric.add_argument(
        "--digits",
        type=int,
        default=15,
        metavar="NUMBER",
        help="Decimal digits. Default: 15.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(_normalize(list(argv)))
    try:
        _emit(_compute(args), args.text)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
