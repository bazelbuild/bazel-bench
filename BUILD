load("@third_party//:requirements.bzl", "requirement")

py_binary(
    name = "benchmark",
    srcs = ["benchmark.py"],
    deps = [
        "//utils:utils",
        requirement('absl-py'),
        requirement('GitPython'),
    ],
    legacy_create_init = 0
)

py_test(
    name = "benchmark_test",
    srcs = ["benchmark_test.py"],
    deps = [
        "//testutils:testutils",
    ]
)
