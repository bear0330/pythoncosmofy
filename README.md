# pythoncosmofy

`pythoncosmofy` packages a Python program as a self-contained Cosmopolitan
Python APE. It comes from
[cosmofy 0.1.0](https://github.com/metaist/cosmofy/releases/tag/0.1.0).
The self-updater from that release is not included.

The base runtime is the latest [`python.com`](https://github.com/bear0330/python-ape/releases/latest/download/python.com)
published by [python-ape](https://github.com/bear0330/python-ape/releases).
After bootstrap, `dist/pythoncosmofy.com` bundles apps by itself.

## Bootstrap

With no path, bootstrap downloads that latest `python.com`. A local file is
used when you pass one. A host `python3` copies the runtime and embeds this
package. The modules are compiled by that `python.com`, so the host Python
version does not have to match the APE:

```sh
./scripts/bootstrap.sh
./scripts/bootstrap.sh /path/to/python.com
```

## Bundle an app

```sh
./dist/pythoncosmofy.com examples/hello -o dist/hello.com
./dist/hello.com 'two words'
# Hello from embedded Python: two words
```

`pythoncosmofy.com` clones its embedded runtime, compiles the program into
that copy, and writes `/zip/.args`. Pass `--python-url` to start from a
downloaded `python.com` instead of the clone. The default URL is the latest
python-ape release:

```sh
./dist/pythoncosmofy.com \
  --python-url https://github.com/bear0330/python-ape/releases/latest/download/python.com \
  examples/hello -o dist/hello.com
```

For the hello example the startup configuration is:

```text
-m
hello
...
```

`...` forwards caller arguments to the program.

A project folder may also contain `Lib/` or `lib/`. `Lib/` is stored at
`Lib/` inside the APE. Packages under a Linux prefix
`lib/.../site-packages` are stored at `Lib/site-packages`, which is where
this runtime imports them. Other `lib/` files stay at `lib/`.
[`examples/sympy`](examples/sympy/README.md) prepares SymPy that way. The
resulting `sympy.com` and its Node.js and Java bindings live in the sibling
[sympy-ape](https://github.com/bear0330/sympy-ape) project.

## License

MIT. Copyright 2024 Metaist LLC. See [`LICENSE.md`](LICENSE.md).
