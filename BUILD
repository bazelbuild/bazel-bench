load("@third_party//:requirements.bzl", "requirement")
load("@bazel_tools//tools/python:toolchain.bzl", "py_runtime_pair")

# TODO(https://github.com/bazelbuild/bazel-bench/issues/36): Make these work for python3.
py_binary(
    name = "benchmark",
    srcs = ["benchmark.py"],
    python_version = "PY2",
    deps = [
        "//utils",
        "//utils:bigquery_upload",
        "//utils:storage_upload",
        requirement("absl-py"),
        requirement("GitPython"),
        requirement("gitdb2"),
    ],
)

py_test(
    name = "benchmark_test",
    srcs = ["benchmark_test.py"],
    python_version = "PY2",
    deps = [
        ":benchmark",
        "//testutils",
        requirement("mock"),
    ],
)
