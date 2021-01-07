# Bazel Performance Benchmarking

[![Build Status](https://badge.buildkite.com/1499c911d1faf665b9f6ba28d0a61e64c26a8586321b9d63a8.svg)](https://buildkite.com/bazel/bazel-bench)

**Status**: WIP

![logo](bb-icon.png)

# Setup

This script works with python3.

Pre-requisites: `python`, `pip`, `git`, `bazel`, [`venv`](https://docs.python.org/3/library/venv.html) (strongly
recommended).

```
# Clone bazel-bench.
$ git clone https://github.com/bazelbuild/bazel-bench.git
$ cd bazel-bench

# (Optional, Recommended) Create and activate the virtual environment.
$ python3 -m venv .venv/
$ source .venv/bin/activate

# Install the dependencies. pip or pip3, depends on your setup.
$ pip3 install -r third_party/requirements.txt
```

To do a test run, run the following command (if you're on Windows, populate
`--data_directory` with an appropriate Windows-style path):

```shell
$ bazel run :benchmark \
-- \
--bazel_commits=b8468a6b68a405e1a5767894426d3ea9a1a2f22f,ad503849e78b98d762f03168de5a336904280150 \
--project_source=https://github.com/bazelbuild/rules_cc.git \
--data_directory=/tmp/bazel-bench-data \
--verbose \
-- build //:all
```

The Bazel commits might be too old and no longer buildable by your local Bazel. Replace them with the more recent commits from [bazelbuild/bazel](https://github.com/bazelbuild/bazel). The above command would print a result table on the terminal and outputs a csv
file to the specified `--data_directory`.

## Syntax

Bazel-bench has the following syntax:

```shell
$ bazel run :benchmark -- <bazel-bench-flags> -- <args to pass to bazel binary>

```

For example, to benchmark the performance of 2 bazel commits A and B on the same
command `bazel build --nobuild //:all` of `rules_cc` project, you'd do:

```shell
$ bazel run :benchmark \
-- \
--bazel_commits=A,B \
--project_source=https://github.com/bazelbuild/rules_cc.git \
-- build --nobuild //:all
```

Note the double-dash `--` before the command arguments. You can pass any
arguments that you would normally run on Bazel to the script. The performance of
commands other than `build` can also be benchmarked e.g. `query`, ...

### Config-file Interface

The flag-based approach does not support cases where the benchmarked Bazel
commands differ. The most common use case for this: As a rule developer, I want
to verify the effect of my flag on Bazel performance. For that, we'd need the
config-file interface. The example config file would look like this:

```yaml
# config.yaml
global_options:
  project_commit: 595a730
  runs: 5
  collect_profile: false
  project_source: /path/to/project/repo
units:
 - bazel_binary: /usr/bin/bazel
   command: --startup_option1 build --nomy_flag //:all
 - bazel_binary: /usr/bin/bazel
   command: --startup_option2 build --my_flag //:all
```

To launch the benchmark:

```shell
$ bazel run :benchmark -- --benchmark_config=/absolute/path/to/config.yaml
```

The above config file would benchmark 2 "units". A unit is defined as a set of 
conditions that describes a scenario to be benchmarked. This setup allows
maximum flexibility, as the conditions are independent between units. It's even 
possible to benchmark a `bazel_commit` against a pre-built `bazel_binary`.

`global_options` is the list of options applied to every units. These global options are overridden by local options.

For the list of currently supported flags/attributes and their default values,
refer to [utils/benchmark_config.py](utils/benchmark_config.py).

#### Known Limitations:

- `project_source` should be a global option, as we don't support benchmarking
multiple projects in 1 benchmark. Though, `project_commit` can differ between units.
- Incremental benchmarks isn't available.
- Commands have to be in canonical form (next section).


### Bazel Arguments Interpretation

Bazel arguments are parsed manually. It
is _important_ that the supplied arguments in the command line strictly follows
the canonical form:

```
<command> <canonical options> <expressions>
```

Example of non-canonical command line arguments that could result in wrong
interpretation:

```
GOOD: (correct order, options in canonical form)
  build --nobuild --compilation_mode=opt //:all

BAD: (non-canonical options)
  build --nobuild -c opt //:all

BAD: (wrong order)
  build --nobuild //:all --compilation_mode=opt
```

## Available flags

To show all the available flags:

```
$ bazel run :benchmark -- --helpshort
```

Some useful flags are:

```
  --bazel_binaries: The pre-built bazel binaries to benchmark.
    (a comma separated list)
  --bazel_commits: The commits at which bazel is built.
    (default: 'latest')
    (a comma separated list)
  --bazel_source: Either a path to the local Bazel repo or a https url to a GitHub repository.
    (default: 'https://github.com/bazelbuild/bazel.git')
  --bazelrc: The path to a .bazelrc file.
  --csv_file_name: The name of the output csv, without the .csv extension
  --data_directory: The directory in which the csv files should be stored.
  --[no]prefetch_ext_deps: Whether to do an initial run to pre-fetch external dependencies.
    (default: 'true')
  --project_commits: The commits from the git project to be benchmarked.
    (default: 'latest')
    (a comma separated list)
  --project_source: Either a path to the local git project to be built or a https url to a GitHub repository.
  --runs: The number of benchmark runs.
    (default: '5')
    (an integer)
  --[no]verbose: Whether to include git/Bazel stdout logs.
    (default: 'false')
  --[no]collect_json_profile: Whether to collect JSON profile for each run.
    Requires --data_directory to be set.
    (default: 'false')
```

## Collecting JSON Profile

[Bazel's JSON Profile](https://docs.bazel.build/versions/master/skylark/performance.html#json-profile)
is a useful tool to investigate the performance of Bazel. You can configure
`bazel-bench` to export these JSON profiles on runs using the
`--collect_json_profile` flag.

### JSON Profile Aggregation

For each pair of `project_commit` and `bazel_commit`, we produce a couple JSON
profiles, based on the number of runs. To have a better overview of the
performance of each phase and events, we can aggregate these profiles and
produce the median duration of each event across them.

To run the tool:

```
bazel run utils:json_profiles_merger \
-- \
--bazel_source=<some commit or path> \
--project_source=<some url or path> \
--project_commit=<some_commit> \
--output_path=/tmp/outfile.csv \
-- /tmp/my_json_profiles_*.profile
```

You can pass the pattern that selects the input profiles into the positional
argument of the script, like in the above example
(`/tmp/my_json_profiles_*.profile`).

## Output Directory Layout

By default, bazel-bench will store the measurement results and other required
files (project clones, built binaries, ...) under the `~/.bazel-bench`
directory.

The layout is:

```
~/.bazel-bench/                         <= The root of bazel-bench's output dir.
  bazel/                                <= Where bazel's repository is cloned.
  bazel-bin/                            <= Where the built bazel binaries are stored.
    fba9a2c87ee9589d72889caf082f1029/   <= The bazel commit hash.
      bazel                             <= The actual bazel binary.
  project-clones/                       <= Where the projects' repositories are cloned.
    7ffd56a6e4cb724ea575aba15733d113/   <= Each project is stored under a project hash,
                                           computed from its source.
  out/                                  <= This is the default output root. But
                                           the output root can also be set via --data_directory.
```

To clear the caches, simply `rm -rf` where necessary.

## Uploading to BigQuery & Storage

As an important part of our bazel-bench daily pipeline, we upload the csv output
files to BigQuery and Storage, using separate targets.

To upload the output to BigQuery & Storage you'll need the GCP credentials and
the table details. Please contact leba@google.com.

BigQuery:

```
bazel run utils:bigquery_upload \
-- \
--upload_to_bigquery=<project_id>:<dataset_id>:<table_id>:<location> \
-- \
<file1> <file2> ...
```

Storage:

```
bazel run utils:storage_upload \
-- \
--upload_to_storage=<project_id>:<bucket_id>:<subdirectory> \
-- \
<file1> <file2> ...
```

## Performance Report

We generate a performance report with BazelCI. The generator script can be found
under the `/report` directory.

Example Usage: `$ python3 report/generate_report.py --date=2019-01-01
--project=dummy --storage_bucket=dummy_bucket`

For more detailed usage information, run: `$ python3 report/generate_report.py
--help`

## Tests

The tests for each module are found in the same directory. To run the test,
simply:

```
$ bazel test ...
```
