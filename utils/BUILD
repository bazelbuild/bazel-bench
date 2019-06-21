load("@third_party//:requirements.bzl", "requirement")
load("@bazel_tools//tools/python:toolchain.bzl", "py_runtime_pair")

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "utils-srcs",
    srcs = glob(
        ["*.py"],
        exclude = [
            "*_test.py",
            "json_profile_merger.py",
            "bigquery_upload.py",
            "storage_upload.py",
        ],
    ),
)

py_library(
    name = "utils",
    srcs = [":utils-srcs"],
    deps = [
        requirement("absl-py"),
        requirement("certifi"),
        requirement("chardet"),
        requirement("enum34"),
        requirement("funcsigs"),
        requirement("idna"),
        requirement("numpy"),
        requirement("pbr"),
        requirement("psutil"),
        requirement("pyasn1"),
        requirement("pyasn1-modules"),
        requirement("rsa"),
        requirement("scipy"),
        requirement("six"),
        requirement("urllib3"),
    ],
)

py_library(
    name = "google-common",
    srcs_version = "PY2",
    deps = [
        requirement("cachetools"),
        requirement("google-api-core"),
        requirement("google-auth"),
        requirement("google-cloud-core"),
        requirement("google-resumable-media"),
        requirement("googleapis-common-protos"),
        requirement("protobuf"),
        requirement("pytz"),
        requirement("requests"),
    ],
)

py_binary(
    name = "bigquery_upload",
    srcs = ["bigquery_upload.py"],
    python_version = "PY2",
    deps = [
        # This is a workaround for https://github.com/bazelbuild/rules_python/issues/14,
        # google-cloud-bigquery must be listed first.
        requirement("google-cloud-bigquery"),
        requirement("absl-py"),
        requirement("futures"),
        ":google-common",
    ],
)

py_binary(
    name = "storage_upload",
    srcs = ["storage_upload.py"],
    python_version = "PY2",
    deps = [
        # This is a workaround for https://github.com/bazelbuild/rules_python/issues/14,
        # google-cloud-storage must be listed first.
        requirement("google-cloud-storage"),
        requirement("absl-py"),
        ":google-common",
    ],
)

py_binary(
    name = "json_profiles_merger",
    srcs = ["json_profiles_merger.py"],
    python_version = "PY2",
    deps = [
        ":utils",
        requirement("absl-py"),
    ],
)

py_test(
    name = "bazel_args_parser_test",
    size = "small",
    srcs = ["bazel_args_parser_test.py"],
    python_version = "PY2",
    deps = [
        ":utils",
        requirement("mock"),
    ],
)

py_test(
    name = "bazel_test",
    size = "small",
    srcs = ["bazel_test.py"],
    python_version = "PY2",
    deps = [
        ":utils",
        requirement("mock"),
    ],
)

py_test(
    name = "values_test",
    size = "small",
    srcs = ["values_test.py"],
    python_version = "PY2",
    deps = [
        ":utils",
        requirement("mock"),
    ],
)

py_test(
    name = "json_profiles_merger_lib_test",
    size = "small",
    srcs = ["json_profiles_merger_lib_test.py"],
    python_version = "PY2",
    deps = [
        ":utils",
        requirement("mock"),
    ],
)
