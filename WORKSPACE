load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

http_archive(
    name = "rules_python",
    sha256 = "a3a6e99f497be089f81ec082882e40246bfd435f52f4e82f37e89449b04573f6",
    strip_prefix = "rules_python-0.10.2",
    url = "https://github.com/bazelbuild/rules_python/archive/refs/tags/0.10.2.tar.gz",
)

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
