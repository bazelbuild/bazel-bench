load("@third_party//:requirements.bzl", "requirement")
load("@bazel_tools//tools/python:toolchain.bzl", "py_runtime_pair")

package(default_visibility = ["//visibility:public"])

py_binary(
  name = "generate_report",
  srcs = ["generate_report.py"],
  deps = [
      # This is a workaround for https://github.com/bazelbuild/rules_python/issues/14,
      # google-cloud-bigquery must be listed first.
      requirement("google-cloud-bigquery"),
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