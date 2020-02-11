load("@third_party//:requirements.bzl", "requirement")
load("@bazel_tools//tools/python:toolchain.bzl", "py_runtime_pair")

# TODO(https://github.com/bazelbuild/bazel-bench/issues/36): Make these work for python3.
py_binary(
    name = "benchmark",
    srcs = ["benchmark.py"],
    deps = [
        "//utils:utils",
        requirement("absl-py"),
        requirement("GitPython"),
        requirement("gitdb2"),
    ],
)

py_test(
    name = "benchmark_test",
    srcs = ["benchmark_test.py"],
    deps = [
        ":benchmark",
        "//testutils:testutils",
        requirement("mock"),
    ],
)
