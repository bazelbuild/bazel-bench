load("@third_party//:requirements.bzl", "requirement")

py_binary(
    name = "benchmark",
    srcs = ["benchmark.py"],
    deps = [
        "//utils:utils",
      	requirement('absl-py'),
        requirement('gitdb'),
        requirement('GitPython'),
    ],
    legacy_create_init = 0
)
