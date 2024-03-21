load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

http_archive(
    name = "rules_python",
    sha256 = "e85ae30de33625a63eca7fc40a94fea845e641888e52f32b6beea91e8b1b2793",
    strip_prefix = "rules_python-0.27.1",
    url = "https://github.com/bazelbuild/rules_python/releases/download/0.27.1/rules_python-0.27.1.tar.gz",
)

load("@rules_python//python:repositories.bzl", "py_repositories")

py_repositories()

load("@rules_python//python:pip.bzl", "pip_parse")
load("@rules_python//python:repositories.bzl", "python_register_toolchains")


# Use a hermetic Python interpreter so that builds are reproducible
# irrespective of the Python version available on the host machine.
python_register_toolchains(
    name = "python3_10",
    python_version = "3.10",
)

load("@python3_10//:defs.bzl", "interpreter")

# Translate requirements.txt into a @third_party external repository.
pip_parse(
    name = "third_party",
    python_interpreter_target = interpreter,
    requirements_lock = "//third_party:requirements.txt",
)

load("@third_party//:requirements.bzl", "install_deps")
#
install_deps()
