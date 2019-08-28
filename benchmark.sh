#!/bin/bash
bazel run :benchmark -- \
  --bazel_commits=3e213679130015e18fddbafa887d6095ed1b07ae,40c3ab341049c40ddda6bff8e9f433dab0fdd067,030ca7fb98c56bfc63f5dc9e61e6a89c4b274293,bb54224bd9eb7b1974ae4b1bea329dcb0c6689bc,522099d4907dd4c1baefbfaba656219b57f41892 \
  --project_source=https://github.com/bazelbuild/bazel.git \
  --project_commits=04e2ebfb6476b373dfccf728aa2a465ed814cc12 \
  --platform=own_machine \
  --data_directory=/tmp/.bazel-bench/out \
  --collect_memory \
  --runs=10 \
  --collect_json_profile \
  --aggregate_json_profiles \
  -- build //src:bazel
