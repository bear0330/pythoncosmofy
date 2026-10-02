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

Pure-Python programs use `python.com` as it is. A C extension needs the
python-ape link SDK. `--sdk` points at that directory. `--c-extension`
points at a directory with `extension.json` and an archive for each
architecture. Those archives are the only extra objects: ssl, sqlite, and
the other Python libraries are already inside `libpython-runtime.a`. The
bundler looks at the extension directory and up to six parents for
`scripts/build-extension.sh` and runs it with the extension directory, the
SDK, and the superconfigure checkout. A `BUILD.mk` extension is built by
superconfigure's `DOWNLOAD_SOURCE` rules: download, sha256 check, extract,
and `patch -p0`. An extension without `BUILD.mk` is compiled from the
sources listed in `extension.json`. A project that does not contain the
shared script still runs its own `build.sh`, which receives the SDK and
the superconfigure checkout. A `python` path in `extension.json` is the
package stored at `Lib/site-packages`.

`cosmocc`, `apelink`, and `ape.elf` come from `--superconfigure`. That
directory contains `cosmopolitan/`. When the flag is omitted, the bundler
uses `superconfigure/` beside the SDK, which is where python-ape's
`install-overlay.sh` clones the tree. `link.json` keeps the cosmos prefix
compiled into the archives so those strings can be rewritten to `/zip`. It
does not store compiler paths.

`extensions/markupsafe` and `extensions/crc32c` are third-party packages.
Their `BUILD.mk` files call `DOWNLOAD_SOURCE`. `native/` is compiled, and
the `python/` directory is the package stored at `Lib/site-packages`.
crc32c 2.7.1 is patched so the package imports the builtin `_crc32c`.
Each extension directory keeps `tests/try.py` as a unittest for that
builtin.

The bundled program is the application directory, the same shape as
[`examples/sympy`](examples/sympy/README.md). Pure-Python libraries such
as Jinja2 sit in that directory under `Lib/site-packages`. Each C
extension is its own `--c-extension` argument, and the flag is repeated
for every extension the program imports. The extension build packs that
extension's `python/` package into `Lib/site-packages`, which is how
Jinja2 finds MarkupSafe. A pure-Python program such as SymPy omits
`--sdk` and `--c-extension`.

```text
myserver/
  main.py
  Lib/site-packages/jinja2/
```

`dist/pythoncosmofy.com` in this checkout was built before the shared
script lookup. Use the source module. Paths passed to cosmofy are relative
to the working directory. `--c-extension` accepts a path outside that
directory.

```sh
cd /path/to/myserver
PYTHONPATH=/path/to/pythoncosmofy/src python3 -m cosmofy \
  --sdk /path/to/python-ape/sdk \
  --superconfigure /path/to/superconfigure \
  --c-extension /path/to/python-ape/extensions/markupsafe \
  --c-extension /path/to/python-ape/extensions/crc32c \
  . -o myserver.com
./myserver.com
```

`main.py` is compiled to `Lib/site-packages/main.pyc` and the APE starts
with `-m main`. Jinja2 is taken from the application's `Lib/` tree.
`markupsafe` and `crc32c` are taken from the extension packages.

`--separate-debug` applies to that same relink. The fat binary omits its
embedded symbol table, so the `.com` is smaller. The unstripped
per-architecture ELFs are written beside the output under cosmocc's names.
`myserver.com` produces `myserver.com.dbg` (x86_64) and
`myserver.aarch64.elf`. Pass the file for the crashing architecture to
`cosmoaddr2line`:

```sh
cosmoaddr2line myserver.com.dbg <address>
cosmoaddr2line myserver.aarch64.elf <address>
```

The flag is used together with `--c-extension`. That relink is what still
has the per-architecture ELFs.

## License

MIT. Copyright 2024 Metaist LLC. See [`LICENSE.md`](LICENSE.md).
