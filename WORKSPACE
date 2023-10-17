load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

http_archive(
    name = "rules_python",
    sha256 = "9d04041ac92a0985e344235f5d946f71ac543f1b1565f2cdbc9a2aaee8adf55b",
    strip_prefix = "rules_python-0.26.0",
    url = "https://github.com/bazelbuild/rules_python/archive/refs/tags/0.26.0.tar.gz",
)

load("@rules_python//python:repositories.bzl", "py_repositories")

py_repositories()

load("@rules_python//python:pip.bzl", "pip_install")
load("@rules_python//python:repositories.bzl", "python_register_toolchains")

# Use a hermetic Python interpreter so that builds are reproducible
# irrespective of the Python version available on the host machine.
python_register_toolchains(
    name = "python3_10",
    python_version = "3.10",
)

load("@python3_10//:defs.bzl", "interpreter")

# Translate requirements.txt into a @third_party external repository.
pip_install(
   name = "third_party",
   python_interpreter_target = interpreter,
   requirements = "//third_party:requirements.txt",
)

load("@third_party//:requirements.bzl", "install_deps")

install_deps()
