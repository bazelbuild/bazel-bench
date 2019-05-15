load("@third_party//:requirements.bzl", "requirement")

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
    deps = [
        ":benchmark",
        "//testutils",
        requirement("mock"),
    ],
)
