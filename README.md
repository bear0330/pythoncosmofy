# pythoncosmofy

`pythoncosmofy` packages a Python program as a self-contained Cosmopolitan
Python APE. It comes from
[cosmofy 0.1.0](https://github.com/metaist/cosmofy/releases/tag/0.1.0).
The self-updater from that release is not included.

The base runtime is the latest [`python.com`](https://github.com/bear0330/python-ape/releases) from python-ape.
After bootstrap, `dist/pythoncosmofy.com` bundles apps by itself.

## Bootstrap

Download `python.com` from the
[python-ape releases](https://github.com/bear0330/python-ape/releases).
A host `python3` is only used to copy that runtime and embed this package:

```sh
./scripts/bootstrap.sh /path/to/python.com
```

## Bundle an app

```sh
./dist/pythoncosmofy.com examples/hello -o dist/hello.com
./dist/hello.com 'two words'
# Hello from embedded Python: two words
```

`pythoncosmofy.com` clones its embedded python-ape runtime, compiles the
program into that copy, and writes `/zip/.args`. For this example the startup
configuration is:

```text
-m
hello
...
```

`...` forwards caller arguments to the program.

## License

MIT. Copyright 2024 Metaist LLC. See [`LICENSE.md`](LICENSE.md).
