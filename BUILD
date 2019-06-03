load("@third_party//:requirements.bzl", "requirement")
load("@bazel_tools//tools/python:toolchain.bzl", "py_runtime_pair")

py_binary(
    name = "benchmark",
    srcs = ["benchmark.py"],
    deps = [
        "//utils",
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
