# Binance DataTool

[![PyPI](https://img.shields.io/pypi/v/binance-datatool?logo=pypi&logoColor=white)](https://pypi.org/project/binance-datatool/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-green)](https://github.com/lostleaf/binance-datatool/blob/main/LICENSE)

Binance DataTool is an unofficial CLI for downloading historical Spot, USDⓈ-M Futures, and
COIN-M Futures data from [Binance's public archive](https://data.binance.vision/) and
verifying it locally with SHA256. With the [binance-datatool skill][skill], your AI agent
can discover datasets, preview downloads, and read results as JSON.

## Install

Install the CLI with [pipx](https://pipx.pypa.io/) and Python 3.11 or later.
For downloads, install aria2 with `brew install aria2` on macOS or `sudo apt install aria2`
on Ubuntu/Debian.

```bash
pipx install binance-datatool
export BINANCE_DATATOOL_ARCHIVE_HOME="$HOME/binance_archive"
```

The archive home is where downloads and their checksums are stored. Add the `export` line to
your shell profile to reuse the same directory in future sessions. If your shell cannot find
`binance-datatool` after installation, run `pipx ensurepath` and open a new terminal.

## Download and verify BTCUSDT candles

### With an AI agent

Install the skill from your project directory with `npx` (included with npm).

```bash
npx skills add lostleaf/binance-datatool --skill binance-datatool
```

Paste this prompt into Codex CLI. In Claude Code, start it with `/binance-datatool`.

> `$binance-datatool` Download all available monthly archives of BTCUSDT spot daily candles to
> `~/binance_archive`. Verify the files and tell me how many passed.

### From the command line

```bash
binance-datatool download spot --freq monthly --type klines --interval 1d BTCUSDT
binance-datatool verify spot --freq monthly --type klines --interval 1d BTCUSDT
```

Each ZIP covers one month of daily candles. Look under
`~/binance_archive/data/spot/monthly/klines/BTCUSDT/1d/`. Rerun `download` to fetch missing
or updated files. After a fresh download, `verify` should report verified ZIPs and `0 failed`.
Later runs count ZIPs with a current verification as `skipped`.

## Preview a batch download

Pipe a symbol list into `download --dry-run` to see which files a batch would fetch.

```bash
binance-datatool list-symbols spot --freq monthly --quote USDT --exclude-stables \
  | binance-datatool download spot --freq monthly --type klines --interval 1d --dry-run
```

## Documentation

- To choose a dataset, check [availability by market type and archive frequency][datasets],
  then use `list-files` to see which archives Binance publishes for a symbol.
- Run `binance-datatool --help` to list commands. For options and JSON output, see the [CLI reference][cli].
- To work on Binance DataTool, see the [contributor guide][contributing].

## Feedback

To report a bug or suggest a feature, open an issue on the [GitHub Issues page][issues].
For a bug, include your DataTool version, the command you ran, what you expected, and what
happened. For a feature, describe your use case and the behavior you want.

Follow the issue for updates and the outcome. When a fix is published on PyPI, the issue will
note which version includes it.

[skill]: https://github.com/lostleaf/binance-datatool/blob/main/skills/binance-datatool/SKILL.md
[datasets]: https://github.com/lostleaf/binance-datatool/blob/main/skills/binance-datatool/references/archive-availability.md#datasets-by-market-type
[cli]: https://github.com/lostleaf/binance-datatool/blob/main/docs/reference/cli/archive.md
[contributing]: https://github.com/lostleaf/binance-datatool/blob/main/docs/README.md
[issues]: https://github.com/lostleaf/binance-datatool/issues
