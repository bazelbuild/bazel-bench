load("@rules_python//python:defs.bzl", "py_library")

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "testutils-srcs",
    srcs = glob(["*.py"]),
)

py_library(
    name = "testutils",
    srcs = [":testutils-srcs"],
)
