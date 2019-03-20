load("@third_party//:requirements.bzl", "requirement")
package(default_visibility = ["//visibility:public"])

filegroup(
  name = "utils-srcs",
  srcs = glob(["*.py"])
)

py_library(
  name = "utils",
  srcs = [":utils-srcs"],
  deps = [
      requirement('cachetools'),
      requirement('certifi'),
      requirement('chardet'),
      requirement('enum34'),
      requirement('funcsigs'),
      requirement('futures'),
      requirement('google-api-core'),
      requirement('google-auth'),
      requirement('google-cloud-bigquery'),
      requirement('google-cloud-core'),
      requirement('google-resumable-media'),
      requirement('googleapis-common-protos'),
      requirement('idna'),
      requirement('mock'),
      requirement('numpy'),
      requirement('pbr'),
      requirement('protobuf'),
      requirement('psutil'),
      requirement('pyasn1'),
      requirement('pyasn1-modules'),
      requirement('pytz'),
      requirement('requests'),
      requirement('rsa'),
      requirement('scipy'),
      requirement('six'),
      requirement('urllib3')
  ]
)
