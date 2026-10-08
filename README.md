# Bazel Performance Benchmarking

[![Build Status](https://badge.buildkite.com/1499c911d1faf665b9f6ba28d0a61e64c26a8586321b9d63a8.svg)](https://buildkite.com/bazel/bazel-bench)

![logo](bb-icon.png)

# Setup

Pre-requisites: `git` and `bazel` (or [`bazelisk`](https://github.com/bazelbuild/bazelisk); `.bazelversion` pins Bazel 9.x with Bzlmod).

```
# Clone bazel-bench.
$ git clone https://github.com/bazelbuild/bazel-bench.git
$ cd bazel-bench
```

To do a test run, run the following command:

```shell
$ bazel run :benchmark \
-- \
--bazel_commits=b8468a6b68a405e1a5767894426d3ea9a1a2f22f,ad503849e78b98d762f03168de5a336904280150 \
--project_source=https://github.com/bazelbuild/rules_cc.git \
--verbose \
-- build //:all
```

The Bazel commits above might be too old and no longer buildable by your local Bazel. Replace them with more recent commits from [bazelbuild/bazel](https://github.com/bazelbuild/bazel), or pass pre-built binaries with `--bazel_binaries=/path/to/bazel_a,/path/to/bazel_b`.

The command prints a formatted summary table on the terminal (comparing every unit against the first unit as the baseline, including mean, `±stddev`, `Δ mean`, and speedup ratio with statistical significance) and automatically exports **CSV** (`<uid>.csv`), **plain-text summary** (`<uid>.txt`), **Markdown** (`<uid>.md`), and **structured JSON** (`<uid>.json`) reports to `--data_directory`. If `--data_directory` is not specified, `bazel-bench` creates a temporary directory `/tmp/benchmark.<random>` and updates a `/tmp/benchmark.latest` symlink pointing to the most recent run's output directory.

## Syntax

Bazel-bench has the following syntax:

```shell
$ bazel run :benchmark -- <bazel-bench-flags> -- <args to pass to bazel binary>
```

For example, to benchmark the performance of 2 bazel commits `A` and `B` on the same
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

- **Pre-built Bazel binaries (`--bazel_binaries`)**: When `--bazel_binaries` is passed (without `--bazel_commits` or `--bisect`), `bazel-bench` validates that the binaries exist and are executable and skips cloning the Bazel repository.
- **In-place local project benchmarking**: When `--project_source` points to a local directory and `--project_commits` is omitted (or `project_commit` is omitted in `config.yaml`), `bazel-bench` runs directly in the local project checkout without cloning it.

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
  warmup_runs: 1
  collect_profile: false
  collect_bep: true
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

`global_options` is the list of options applied to every unit. These global options are overridden by local unit options. Supported options include `runs`, `warmup_runs`, `max_outlier_reruns`, `interleave`, `clean`, `shutdown`, `collect_memory`, `collect_process_memory`, `collect_bep`, `collect_peak_post_gc_memory`, `collect_profile`, `patch_file`, `env_configure`, and `bazel_source`.

For the list of currently supported flags/attributes and their default values,
refer to [utils/benchmark_config.py](utils/benchmark_config.py).

#### Known Limitations:

- `project_source` should be a global option, as we don't support benchmarking
multiple projects in 1 benchmark. Though, `project_commit` can differ between units (or be omitted to benchmark a local `project_source` in place).
- Commands have to be in canonical form (next section).


### Bazel Arguments Interpretation

Bazel arguments are parsed manually. It
is _important_ that the supplied arguments in the command line strictly follows
the canonical form:

```
<startup_options> <command> <canonical options> [--] <expressions>
```

Example of non-canonical command line arguments that could result in wrong
interpretation:

```
GOOD: (correct order, options in canonical form)
  build --nobuild --compilation_mode=opt //:all

GOOD: (using -- to separate options from target patterns)
  build --nobuild -- //foo/... -//foo/excluded/...

BAD: (non-canonical options)
  build --nobuild -c opt //:all

BAD: (wrong order)
  build --nobuild //:all --compilation_mode=opt
```

## Execution & Profiling Features

### Warmup Runs, Outlier Reruns, and Interleaving

- **Warmup runs (`--warmup_runs`, default: `1`)**: Performs discarded warmup runs before measurement runs begin.
- **Outlier reruns (`--max_outlier_reruns`, default: `0`)**: Automatically detects wall-time outliers using Modified Z-score (Median Absolute Deviation / MAD) and reruns the worst outlier up to `N` times.
- **Round-robin unit interleaving (`--[no]interleave`, default: `false`)**: After preparing and warming up each unit, interleaves measurement runs across units in round-robin order (`Unit #0 run 1 -> Unit #1 run 1 -> ...`) to mitigate thermal throttling and background system drift.
- **Clean and shutdown control (`--[no]clean`, `--[no]shutdown`, default: `true`)**: Controls whether `bazel clean` and `bazel shutdown` are invoked between runs.

### Memory & Build Event Protocol (BEP) Metrics

- **Retained heap memory (`--[no]collect_memory`, default: `true`)**: Collects retained JVM heap size (`memory`) after each command via `bazel info used-heap-size-after-gc`. Pass `--nocollect_memory` to skip post-build heap inspection.
- **Peak process RSS (`--[no]collect_process_memory`, default: `false`)**: Samples the Bazel server's anonymous RSS (`RssAnon` from `/proc/<pid>/status`) in a background thread during execution to report `peakProcessRss`.
- **BEP metrics (`--[no]collect_bep`, default: `false`)**: Parses the Build Event Protocol JSON file (`--build_event_json_file`) after each run to extract:
  - Build graph & analysis: `packagesLoaded`, `targetsConfigured`, `actionsCreated`, `actionsExecuted`, `outputArtifactCount`
  - Phase timings: `analysisPhaseTime`, `executionPhaseTime`
  - Action cache & runner statistics: `actionCacheHits`, `actionCacheMisses`, `remoteCacheHits`, `diskCacheHits`, `runner-<name>`
  - JVM heap & GC metrics: `usedHeapSizePostBuild`, `edenSpaceGarbage`, `oldGenGarbage`, `peakPostGcHeapSize`
- **Peak post-GC heap memory (`--[no]collect_peak_post_gc_memory`, default: `false`)**: Enables `--collect_bep` and automatically adds `--memory_profile=/dev/null` (unless `--memory_profile` is already specified) so Bazel records `peakPostGcHeapSize` in the BEP output.

### Incremental Benchmarks & Synthetic Patches

To benchmark incremental builds, disable `clean` and `shutdown` between runs (`--noclean --noshutdown`) and optionally supply a git patch file via `--patch_file=/path/to/change.patch` (or `patch_file` in `config.yaml`).

Before each run, `bazel-bench` replaces every occurrence of `__RANDOM_TOKEN__` in the patch file with a fresh 32-character hex token, applies the patch to the project repository, runs the build, and reverse-applies the patch afterward. Note that `--patch_file` requires the project to be cloned (either via a remote `--project_source` URL or by specifying `--project_commits` / `project_commit`), so that a local working tree is never modified in place.

### Automated Git Bisection

`bazel-bench` can automatically bisect a Bazel commit range (`[good, bad]`) to find the first commit that caused a statistically significant regression on a target metric (e.g. `wall`, `cpu`, `memory`):

```shell
$ bazel run :benchmark \
-- \
--bazel_commits=<good_commit>,<bad_commit> \
--project_source=/path/to/project \
--bisect=wall \
-- build //:all
```

At the end of bisection, `bazel-bench` prints the culprit commit and evaluation history and exports `<uid>_bisect.md` to the data directory.

## Available flags

To show all the available flags:

```
$ bazel run :benchmark -- --helpshort
```

Available flags:

```
  --[no]aggregate_json_profiles: Whether to aggregate the collected JSON
    profiles. Requires --collect_profile to be set.
    (default: 'false')
  --bazel_bin_dir: The directory to store the bazel binaries from each commit.
  --bazel_binaries: The pre-built bazel binaries to benchmark.
    (a comma separated list)
  --bazel_commits: The commits at which bazel is built.
    (a comma separated list)
  --bazel_source: Either a path to the local Bazel repo or a https url to a
    GitHub repository.
    (default: 'https://github.com/bazelbuild/bazel.git')
  --bazelrc: The path to a .bazelrc file.
  --benchmark_config: Whether to use the config-file interface to define
    benchmark units.
  --bisect: Run automated git bisection for regressions on the specified metric
    (e.g. wall, cpu, memory). Requires --bazel_commits with exactly two commits
    [good, bad].
  --[no]clean: Whether to invoke clean between runs/builds.
    (default: 'true')
  --[no]collect_bep: Whether to collect build metrics from the Build Event
    Protocol (BEP).
    (default: 'false')
  --[no]collect_memory: Whether to collect retained heap size via GC after
    command execution.
    (default: 'true')
  --[no]collect_peak_post_gc_memory: Whether to collect peak post-GC heap memory
    via BEP and memory profiler. Turns on --collect_bep.
    (default: 'false')
  --[no]collect_process_memory: Whether to sample peak anonymous process RSS
    memory.
    (default: 'false')
  --[no]collect_profile: Whether to collect JSON profile for each run. Requires
    --data_directory to be set.
    (default: 'false')
  --csv_file_name: The name of the output csv, without the .csv extension.
  --data_directory: The directory in which the csv files should be stored.
  --env_configure: The shell commands to configure the project's environment.
  --[no]interleave: Whether to interleave benchmark runs across units in a
    round-robin order.
    (default: 'false')
  --max_outlier_reruns: Maximum number of automatic reruns when a wall-time
    outlier is detected.
    (default: '0')
    (an integer)
  --patch_file: Path to a patch file containing changes to apply for incremental
    builds.
  --platform: The platform on which bazel-bench is run. This is just to
    categorize data and has no impact on the actual script execution.
  --[no]prefetch_ext_deps: Whether to do an initial run to pre-fetch external
    dependencies.
    (default: 'true')
  --project_commits: The commits from the git project to be benchmarked.
    (a comma separated list)
  --project_label: The label of the project. Only relevant in the daily
    performance report.
  --project_source: Either a path to the local git project to be built or a
    https url to a GitHub repository.
  --runs: The number of benchmark runs.
    (default: '5')
    (an integer)
  --[no]shutdown: Whether to invoke shutdown between runs/builds.
    (default: 'true')
  --[no]verbose: Whether to include git/Bazel stdout logs.
    (default: 'false')
  --warmup_runs: The number of warmup runs to perform before measurements
    (discarded).
    (default: '1')
    (an integer)
```

## Collecting JSON Profile

[Bazel's JSON Profile](https://bazel.build/advanced/performance/json-trace-profile)
is a useful tool to investigate the performance of Bazel. You can configure
`bazel-bench` to export these JSON profiles on runs using the
`--collect_profile` flag.

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

By default, `bazel-bench` stores cloned repositories and built Bazel binaries under `~/.bazel-bench`:

```
~/.bazel-bench/                         <= The root of bazel-bench's cache dir.
  bazel-clones/                         <= Where Bazel repositories are cloned (by source hash).
  bazel-bin/                            <= Where built Bazel binaries are stored (can be overridden via --bazel_bin_dir).
    fba9a2c87ee9589d72889caf082f1029/   <= The Bazel commit hash (optionally under a <platform>/ subdir).
      bazel                             <= The actual Bazel binary.
  project-clones/                       <= Where benchmarked project repositories are cloned.
    7ffd56a6e4cb724ea575aba15733d113/   <= Each project is stored under an MD5 hash of its source.
```

Measurement outputs (`.csv`, `.txt`, `.md`, `.json`, and optional `.profile.gz` / `.bep.json` files) are written to `--data_directory`. When `--data_directory` is not specified, `bazel-bench` creates a temporary `/tmp/benchmark.<random>` directory and updates `/tmp/benchmark.latest` as a symlink to that directory.

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
