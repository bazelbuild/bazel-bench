# Bazel Performance Benchmarking

[![Build Status](https://badge.buildkite.com/1499c911d1faf665b9f6ba28d0a61e64c26a8586321b9d63a8.svg)](https://buildkite.com/bazel/bazel-bench)

**Status**: WIP

# Setup

This script works for `Python 2.7` and `3.x`.

Pre-requisites: `python`, `git`, `bazel`

To do a test run, run the following command (if you're on Windows, populate
`--data_directory` with an appropriate Windows-style path):

```
$ bazel
run :benchmark \
-- \
--bazel_commits=b8468a6b68a405e1a5767894426d3ea9a1a2f22f,ad503849e78b98d762f03168de5a336904280150\
--project_source=https://github.com/bazelbuild/rules_cc.git \
--data_directory=/tmp/bazel-bench-data \
-- build //:all
```

The above command would print a result table on the terminal and outputs a csv
file to the specified `--data_directory`.

## Syntax

Bazel-bench has the following syntax:

```
$ bazel run :benchmark -- <bazel-bench-flags> -- <args to pass to bazel binary>

```

For example, to benchmark the performance of 2 bazel commits A and B on the same
command `bazel build --nobuild //:all` of `rules_cc` project, you'd do:

```
$ bazel run :benchmark \
-- \
--bazel_commits=A,B \
--project_source=https://github.com/bazelbuild/rules_cc.git \
-- build --nobuild //:all
```

Note the double-dash `--` before the command arguments. You can pass any
arguments that you would normally run on Bazel to the script. The performance of
commands other than `build` can also be benchmarked e.g. `query`, ...

### Bazel Arguments Interpretation

Bazel arguments are interpreted with
[Build Event Protocol](https://docs.bazel.build/versions/master/build-event-protocol.html).
This happens during the first pre-run of each Bazel binary to pre-fetch the
external dependencies.

In case of `--noprefetch_external_deps`, Bazel arguments are parsed manually. It
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
  --bazel_commits: The commits at which bazel is built.
    (default: 'latest')
    (a comma separated list)
  --bazel_source: Either a path to the local Bazel repo or a https url to a GitHub repository.
    (default: 'https://github.com/bazelbuild/bazel.git')
  --bazelrc: The path to a .bazelrc file.
  --[no]collect_memory: Whether to collect used heap sizes.
    (default: 'false')
  --csv_file_name: The name of the output csv, without the .csv extension
  --data_directory: The directory in which the csv files should be stored. Turns on memory collection.
  --[no]prefetch_ext_deps: Whether to do an initial run to pre-fetch external dependencies.
    (default: 'true')
  --project_commits: The commits from the git project to be benchmarked.
    (default: 'latest')
    (a comma separated list)
  --project_source: Either a path to the local git project to be built or a https url to a GitHub repository.
  --runs: The number of benchmark runs.
    (default: '3')
    (an integer)
  --[no]verbose: Whether to include git/Bazel stdout logs.
    (default: 'false')
  --[no]collect_json_profile: Whether to collect JSON profile for each run.
    Requires --data_directory to be set.
    (default: 'false')
```

## Collecting JSON Profile

[Bazel's JSON Profile](https://docs.bazel.build/versions/master/skylark/performance.html#json-profile) is a useful tool to investigate the performance of Bazel. You can configure `bazel-bench` to export these JSON profiles on runs using the `--collect_json_profile` flag.

### JSON Profile Aggregation

For each pair of `project_commit` and `bazel_commit`, we produce a couple JSON
profiles, based on the number of runs. To have a better overview of the
performance of each phase and events, we can aggregate these profiles and
produce the median duration of each event across them.

To run the tool:

```
bazel run utils:json_profile_merger \
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

We generate a performance report with BazelCI. The generator script can be 
found under the `/report` directory.

Example Usage:
```
$ python3 report/generate_report.py --date=2019-01-01 --project=dummy
--storage_bucket=dummy_bucket
```

For more detailed usage information, run:
```
$ python3 report/generate_report.py --help
```

## Tests

The tests for each module are found in the same directory. To run the test,
simply:

```
$ bazel test ...
```
