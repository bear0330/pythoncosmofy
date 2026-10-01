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

## APEBind

[APEBind](https://github.com/nuwainfo/apebind) treats this CLI as the ABI.
`commands:` in `--help` is the section it discovers, and metavars such as
`NUMBER` are how it sees an integer flag. Inspect the built APE, then generate
from the reviewed schema in `sympy.apebind.yaml`:

```sh
apebind inspect ./sympy.com -o sympy.discovered.apebind.yaml
apebind validate sympy.apebind.yaml
apebind generate sympy.apebind.yaml --ape ./sympy.com --lang node -o bindings/node
apebind generate sympy.apebind.yaml --ape ./sympy.com --lang java -o bindings/java
```

`apebind` here is [apebind.com v0.4.1](https://github.com/nuwainfo/apebind/releases/tag/v0.4.1)
or a checkout of that release. The reviewed schema keeps the inspected grammar
and changes the library surface:

- Operations read JSON. `version` returns the `result` string. The others
  return the whole `{result, latex}` object.
- `--text` stays on the CLI and is left out of the schema, so a generated
  call cannot turn that JSON off.
- The `eval` subcommand is exposed as `evaluate`. A JavaScript module cannot
  export a function named `eval`.
- `--var` is exposed as `symbols`. `var` is a reserved parameter name in Java.
- `subs` requires `--value`.
- The package name is `sympy-ape`.
- Generated processes unset `PYTHONHOME`, `PYTHONPATH`, and `PYTHONSTARTUP`.

Node.js:

```js
import { integrate, diff } from 'sympy-ape';

console.log(await integrate({ expr: 'sin(x)' }));
console.log(await diff({ expr: '-x**2' }));
```

Java:

```java
import apebind.generated.sympy_ape.SympyAPEBinding;

var value = SympyAPEBinding.integrate(
    SympyAPEBinding.IntegrateParameters.builder()
        .expr("sin(x)")
        .build());
```

`bindings/` holds those generated projects, including a copy of `sympy.com`.
That directory is gitignored.

## ctypes

This `python.com` has no `_ctypes` extension. SymPy imports `ctypes` from
`sympy/external/gmpy.py` while the package is loading. That import is only
used to measure the width of a C `long` and set `LONG_MAX`.

`prepare.sh` changes `gmpy.py` so a missing `ctypes` module uses a 64-bit
`LONG_MAX` instead. Without that change, `import sympy` fails with
`No module named '_ctypes'`.
