# sympy

SymPy example for pythoncosmofy. The SymPy and mpmath trees are not part of
this repository. `prepare.sh` downloads the SymPy 1.14.0 wheel (and mpmath,
which it requires), extracts them into `Lib/site-packages`, applies the
ctypes change below, and compiles that tree with `python.com`.

## Prepare

```sh
./prepare.sh /path/to/python.com
```

After that, this folder looks like:

```text
sympy/
  main.py
  Lib/site-packages/sympy/
  Lib/site-packages/mpmath/
```

## Bundle

From `examples/`:

```sh
../dist/pythoncosmofy.com sympy -o sympy.com
./sympy.com integrate 'sin(x)'
# {"result": "-cos(x)", "latex": "- \\cos{\\left(x \\right)}"}
./sympy.com integrate --text 'sin(x)'
# -cos(x)
```

`main.py` is an ordinary script. pythoncosmofy compiles it to
`Lib/site-packages/main.pyc` and starts the APE with `-m main`. `Lib/` is
copied into the APE at `Lib/`. A Linux prefix such as
`lib/python3.12/site-packages` is accepted too: those packages are stored at
`Lib/site-packages`, which is the path this runtime imports. Other files
under `lib/` stay at `lib/`.

## Commands

`sympy.com` is an argparse program. The subcommands are `version`, `eval`,
`simplify`, `expand`, `factor`, `apart`, `diff`, `integrate`, `solve`,
`limit`, `series`, `subs`, and `numeric`. Each one prints a single JSON
object, `{"result", "latex"}`, on stdout. `--text` prints only the result
string. A failing expression exits 1 and writes the error to stderr.

```sh
./sympy.com diff --order 2 'x**3'
./sympy.com solve 'x**2-1'
./sympy.com subs --value 3 --var x 'x**2+y'
./sympy.com numeric --digits 5 'pi'
./sympy.com limit --point oo '1/x'
./sympy.com diff '-x**2'
```

`--var` is a comma-separated symbol list. The first name is the symbol that
`diff`, `integrate`, `solve`, `limit`, `series`, and `subs` act on. `x`, `y`,
`z`, `t`, `n`, and `k` are always defined. An expression may start with `-`.

The portable CLI and its Node.js and Java bindings live in the sibling
[sympy-ape](https://github.com/bear0330/sympy-ape) project. This folder only prepares and bundles
`sympy.com`.

## ctypes

This `python.com` has no `_ctypes` extension. SymPy imports `ctypes` from
`sympy/external/gmpy.py` while the package is loading. That import is only
used to measure the width of a C `long` and set `LONG_MAX`.

`prepare.sh` changes `gmpy.py` so a missing `ctypes` module uses a 64-bit
`LONG_MAX` instead. Without that change, `import sympy` fails with
`No module named '_ctypes'`.
