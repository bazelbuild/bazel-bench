# Bazel Performance Benchmarking

**Status**: WIP

# Setup

Pre-requisites: `pip`, `git`, `bazel`

To do a test run:

1.  The use of `virtualenv` is strongly recommended. Do this before you carry on
    with step 2.
2.  Install the dependencies: `$ pip install -r requirements.txt`
3.  Run the following command (with `--project_path` flag filled with the
    appropriate value):
    ```
    $ python benchmark.py \
    --bazel_commits=b8468a6b68a405e1a5767894426d3ea9a1a2f22f,ad503849e78b98d762f03168de5a336904280150 \
    --project_source=https://github.com/bazelbuild/rules_cc.git \
    --data_directory=/tmp/out.csv \
    -- build //:all
    ```

## Syntax

Bazel-bench has the following syntax:

```
$ python benchmark.py <bazel-bench-flags> -- <args to pass to bazel binary>

```

For example, to benchmark the performance of 2 bazel commits A and B on the same command `bazel build --nobuild //:all` of `rules_cc` project, you'd do:

```
$ python benchmark.py \
--bazel_commits=A,B \
--project_source=https://github.com/bazelbuild/rules_cc.git \
-- build --nobuild //:all
```

You can pass any arguments that you would normally run on Bazel to the script. The performance of commands other than `build` can also be benchmarked e.g. `query`, ...

### Bazel Arguments Interpretation

Bazel arguments are interpreted with [Build Event Protocol](https://docs.bazel.build/versions/master/build-event-protocol.html). This happens during the first pre-run of each Bazel binary to pre-fetch the external dependencies.

In case of `--noprefetch_external_deps`, Bazel arguments are parsed manually. It is _crucial_ that the supplied arguments in the command line strictly follows the canonical form:

```
<command> <canonical options> <expressions>
```

Example of non-canonical command line arguments that could result in wrong interpretation:

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
$ python benchmark.py --helpshort

       USAGE: benchmark.py [flags]
flags:

benchmark.py:
  --bazel_commits: The commits at which bazel is built.
    (default: 'latest')
    (a comma separated list)
  --bazel_source: Either a path to the local Bazel repo or a https url to a GitHub repository.
    (default: 'https://github.com/bazelbuild/bazel.git')
  --bazelrc: The path to a .blazerc file.
  --[no]collect_memory: Whether to collect used heap sizes.
    (default: 'false')
  --data_directory: The directory in which the csv files should be stored (including the trailing "/") turns on memory collection.
  --[no]prefetch_ext_deps: Whether to do an initial run to pre-fetch external dependencies.
    (default: 'true')
  --project_commits: The commits from the git project to be benchmarked.
    (default: 'latest')
    (a comma separated list)
  --project_source: Either a path to the local git project to be built or a https url to a GitHub repository.
  --runs: The number of benchmark runs.
    (default: '3')
    (an integer)
  --upload_data_to: The details of the BigQuery table to upload results to: <dataset_id>:<table_id>:<location>
  --[no]verbose: Whether to include git/Bazel stdout logs.
    (default: 'false')


```

## Uploading to BigQuery

To upload the output to BigQuery, you'll need the GCP credentials and the table details. Please contact leba@google.com.

## Tests

The tests for each module are found in the same directory.
