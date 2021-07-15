load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

git_repository(
    name = "rules_python",
    commit = "748aa53d7701e71101dfd15d800e100f6ff8e5d1",
    remote = "https://github.com/bazelbuild/rules_python.git",
)

# Only needed for PIP support:
load("@rules_python//python:pip.bzl", "pip_repositories", "pip3_import")

pip_repositories()

# This rule translates the specified requirements.txt into
# @my_deps//:requirements.bzl, which itself exposes a pip_install method.
pip3_import(
    name = "third_party",
    requirements = "//third_party:requirements.txt",
    timeout = 1000,
)

# Load the pip_install symbol for my_deps, and create the dependencies'
# repositories.
load("@third_party//:requirements.bzl", "pip_install")

pip_install()
