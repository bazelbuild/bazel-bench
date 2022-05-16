load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

http_archive(
    name = "rules_python",
    sha256 = "15f84594af9da06750ceb878abbf129241421e3abbd6e36893041188db67f2fb",
    strip_prefix = "rules_python-0.7.0",
    url = "https://github.com/bazelbuild/rules_python/archive/refs/tags/0.7.0.tar.gz",
)

load("@rules_python//python:pip.bzl", "pip_install")

# Translate requirements.txt into a @third_party external repository.
pip_install(
   name = "third_party",
   requirements = "//third_party:requirements.txt",
)
