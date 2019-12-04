load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

git_repository(
    name = "rules_python",
    remote = "https://github.com/bazelbuild/rules_python.git",
    # TODO(leba): This is temporary to use pip3. Replace with a released version later.
    commit = "94677401bc56ed5d756f50b441a6a5c7f735a6d4",
)

load("@rules_python//python:repositories.bzl", "py_repositories")
py_repositories()

# Only needed if using the packaging rules.
load("@rules_python//python:pip.bzl", "pip_repositories")
pip_repositories()

# This rule translates the specified requirements.txt into
# @my_deps//:requirements.bzl, which itself exposes a pip_install method.
load("@rules_python//python:pip.bzl", "pip3_import")
pip3_import(
    name = "third_party",
    requirements = "//third_party:requirements.txt",
)

# Load the pip_install symbol for my_deps, and create the dependencies'
# repositories.
load("@third_party//:requirements.bzl", "pip_install")

pip_install()
