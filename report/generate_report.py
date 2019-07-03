#!/usr/bin/env python3
#
# Copyright 2019 The Bazel Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Generates a daily HTML report for the projects.
The steps:
  1. Get the necessary data from Storage for projects/date.
  2. Manipulate the data to a format suitable for graphs.
  3. Generate a HTML report containing the graphs.
  4. Upload the generated HTMLs to GCP Storage.
"""
import argparse
import collections
import csv
import datetime
import json
import io
import os
import statistics
import subprocess
import sys
import tempfile
import urllib.request


TMP = tempfile.gettempdir()
REPORTS_DIRECTORY = os.path.join(TMP, ".bazel_bench", "reports")
EVENTS_ORDER = [
  "Launch Blaze",
  "Initialize command",
  "Load packages",
  "Analyze dependencies",
  "Analyze licenses",
  "Prepare for build",
  "Build artifacts",
  "Complete build",
]

def _upload_to_storage(src_file_path, storage_bucket, destination_dir):
  """Uploads the file from src_file_path to the specified location on Storage.
  """
  args = ["gsutil", "cp", src_file_path, "gs://{}/{}".format(storage_bucket, destination_dir)]
  subprocess.run(args)


def _load_csv_from_remote_file(http_url):
  with urllib.request.urlopen(http_url) as resp:
    reader = csv.DictReader(io.TextIOWrapper(resp))
    return [row for row in reader]


def _load_json_from_remote_file(http_url):
  with urllib.request.urlopen(http_url) as resp:
    data = resp.read()
    encoding = resp.info().get_content_charset("utf-8")
    return json.loads(data.decode(encoding))


def _get_storage_url(storage_bucket, dated_subdir):
  # In this case, the storage_bucket is a Domain-named bucket.
  # https://cloud.google.com/storage/docs/domain-name-verification
  return "https://{}/{}".format(storage_bucket, dated_subdir)


def _get_dated_subdir_for_project(project, date):
  return "{}/{}".format(project, date.strftime("%Y/%m/%d"))


def _get_bazel_github_a_component(commit):
  return '<a href="{}">{}</a>'.format(
      "https://github.com/bazelbuild/bazel/commit/" + commit, commit)

def _get_file_list_from_gs(bucket_name, gs_subdir):
  args = ["gsutil", "ls", "gs://{}/{}".format(bucket_name, gs_subdir)]
  command_output = subprocess.check_output(args)
  # The last element is just an empty string.
  decoded = command_output.decode("utf-8").split("\n")[:-1]

  return [line.strip("'").replace("gs://", "https://") for line in decoded]


def _get_file_list_component(bucket_name, dated_subdir, platform):
  gs_subdir = "{}/{}".format(dated_subdir, platform)
  links = _get_file_list_from_gs(bucket_name, gs_subdir)
  li_components = [
      '<li><a href="{}">{}</a></li>'.format(link, os.path.basename(link))
      for link in links]
  return """
<b>{}</b>
<ul>{}</ul>
""".format(platform, "\n".join(li_components))


def _get_proportion_breakdown(aggr_json_profile):
  bazel_commit_to_phases = {}
  for entry in aggr_json_profile:
    bazel_commit = entry["bazel_source"]
    if bazel_commit not in bazel_commit_to_phases:
      bazel_commit_to_phases[bazel_commit] = []
    bazel_commit_to_phases[bazel_commit].append({
        "name": entry["name"],
        "dur": entry["dur"]
    })

  bazel_commit_to_phase_proportion = {}
  for bazel_commit in bazel_commit_to_phases.keys():
    total_time = sum(
        [float(entry["dur"]) for entry in bazel_commit_to_phases[bazel_commit]])
    bazel_commit_to_phase_proportion[bazel_commit] = {
        entry["name"]: float(entry["dur"]) / total_time
        for entry in bazel_commit_to_phases[bazel_commit]}

  return bazel_commit_to_phase_proportion


def _fit_data_to_phase_proportion(reading, proportion_breakdown):
  result = []
  for phase in EVENTS_ORDER:
    if phase not in proportion_breakdown:
      result.append(0)
    else:
      result.append(reading * proportion_breakdown[phase])
  return result


def _short_form(commit):
  return commit[:7]


def _prepare_data_for_graph(performance_data, aggr_json_profile):
  """Massage the data to fit a format suitable for graph generation.
  """
  bazel_commit_to_phase_proportion = _get_proportion_breakdown(
      aggr_json_profile)
  ordered_commit_to_readings = collections.OrderedDict()
  for entry in performance_data:
    # Exclude measurements from failed runs in the graphs.
    # TODO(leba): Print the summary table, which includes info on which runs
    # failed.
    if entry['exit_status'] != '0':
      continue

    bazel_commit = entry["bazel_commit"]
    if bazel_commit not in ordered_commit_to_readings:
      ordered_commit_to_readings[bazel_commit] = {
          "bazel_commit": bazel_commit,
          "wall_readings": [],
          "memory_readings": [],
      }
    ordered_commit_to_readings[bazel_commit]["wall_readings"].append(float(entry["wall"]))
    ordered_commit_to_readings[bazel_commit]["memory_readings"].append(float(entry["memory"]))

  wall_data = [["Bazel Commit"] + EVENTS_ORDER]
  memory_data = [["Bazel Commit", "Memory (MB)"]]

  for obj in ordered_commit_to_readings.values():
    commit = _short_form(obj["bazel_commit"])
    wall_data.append(
        [commit]
        + _fit_data_to_phase_proportion(
            statistics.median(
                obj["wall_readings"]),
            bazel_commit_to_phase_proportion[bazel_commit]))
    memory_data.append([commit, statistics.median(obj["memory_readings"])])

  return wall_data, memory_data


def _row_component(content):
  return """
<div class="row">{content}</div>
""".format(content=content)


def _col_component(col_class, content):
  return """
<div class="{col_class}">{content}</div>
""".format(col_class=col_class, content=content)


def _commits_component(performance_data):
  # Bazel commits, in chronological order.
  sorted_bazel_commits = []
  for entry in performance_data:
    if entry["bazel_commit"] not in sorted_bazel_commits:
      sorted_bazel_commits.append(entry["bazel_commit"])

  li_components = "\n".join(
      ['<li>{}</li>'.format(_get_bazel_github_a_component(commit), commit)
       for commit in sorted_bazel_commits])
  return """
<b>Commits:</b>
<ul>
  {}
</ul>
""".format(li_components)


# TODO(leba): Add stddev/error bars to the bars in the chart.
def _single_graph(metric, metric_label, data, platform):
  """Returns the HTML <div> component of a single graph.
  """
  title = "[{}] Bar Chart of {} vs Bazel commits".format(platform, metric_label)
  vAxis = "Bazel Commits (chronological order)"
  hAxis = metric_label
  chart_id = "{}-{}".format(platform, metric)

  return """
<script type="text/javascript">
  google.charts.setOnLoadCallback(drawChart);
  function drawChart() {{
    var data = google.visualization.arrayToDataTable({data})

    var options = {{
    title: "{title}",
    titleTextStyle: {{ color: "gray" }},
    hAxis: {{
      title: "{hAxis}",
      titleTextStyle: {{ color: "darkgray" }},
      textStyle: {{ color: "darkgray" }},
      minValue: 0,
    }},
    vAxis: {{
      title: "{vAxis}",
      titleTextStyle: {{ color: "darkgray" }},
      textStyle: {{ color: "darkgray" }},
    }},
    bars: "horizontal",
    axes: {{
      y: {{
      0: {{ side: "right"}}
      }}
    }},
    chartArea: {{ width: "70%"}},
    isStacked: true,
    trendlines: {{
      0: {{
        type: 'linear',
        color: 'green',
        lineWidth: 3,
        opacity: 0.3,
        showR2: true,
        visibleInLegend: true
      }}
    }},
    }};
    var chart = new google.visualization.BarChart(document.getElementById("{chart_id}"));
    chart.draw(data, options);
  }}
  </script>
<div id="{chart_id}" style="min-height: 500px"></div>
""".format(
    title=title, data=data, hAxis=hAxis, vAxis=vAxis, chart_id=chart_id
  )


def _full_report(project, project_source, date, command, graph_components, raw_files_components):
  """Returns the full HTML of a complete report, from the graph components.
  """
  return """
<html>
  <head>
  <script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
  <script type="text/javascript">
    google.charts.load("current", {{ packages:["corechart"] }});
  </script>
  <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css" integrity="sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T" crossorigin="anonymous">
  <style>
    h1 {{ font-size: 1.7rem; }}
    h2 {{ font-size: 1.3rem; color: gray; }}
    h2.underlined {{ border-bottom: 2px dotted lightgray; }}
    body {{ font-family: monospace; padding: 1% 3% 1% 3%; font-size:1.1rem; }}
  </style>
  </head>
  <body>
  <div class="container-fluid">
    <div class="row">
    <div class="col-sm-12">
      <h1>[<a href="{project_source}">{project}</a>] Report for {date}</h1>
      </hr>
    </div>
    <div class="col-sm-12">
      <b>Command: </b><span style="font-family: monospace">{command}</span>
    </div>
    </div>
    {graphs}
    <h2>Raw Files:</h2>
    <div class="row">
    {files}
    </div>
  </div>
  </body>
</html>
""".format(
    project=project,
    project_source=project_source,
    date=date,
    command=command,
    graphs=graph_components,
    files=raw_files_components
  )


def _generate_report_for_date(project, date, storage_bucket):
  """Generates a html report for the specified date & project.

  Args:
    project: the project to generate report for. Check out bazel_bench.py.
    date: the date to generate report for.
    storage_bucket: the Storage bucket to upload the report to.
  """
  dated_subdir = _get_dated_subdir_for_project(project, date)
  root_storage_url = _get_storage_url(storage_bucket, dated_subdir)
  metadata_file_url = "{}/METADATA".format(root_storage_url)
  metadata = _load_json_from_remote_file(metadata_file_url)

  graph_components = []
  raw_files_components = []
  added_commits_component = False
  for platform_measurement in metadata["platforms"]:
    # Get the data
    performance_data = _load_csv_from_remote_file(
        "{}/{}".format(root_storage_url, platform_measurement["perf_data"])
    )
    if not added_commits_component:
      graph_components.append(
          _row_component(
              _col_component(
                  "col-sm-10",
                  _commits_component(performance_data))))
      added_commits_component = True

    aggr_json_profile = _load_csv_from_remote_file(
        "{}/{}".format(
            root_storage_url, platform_measurement["aggr_json_profiles"])
    )

    wall_data, memory_data = _prepare_data_for_graph(
      performance_data, aggr_json_profile)
    platform = platform_measurement["platform"]
    # Generate a graph for that platform.
    row_content = []
    row_content.append(
        _col_component("col-sm-6", _single_graph(
            metric="wall",
            metric_label="Wall Time (s)",
            data=wall_data,
            platform=platform,
        ))
    )

    row_content.append(
        _col_component("col-sm-6", _single_graph(
            metric="memory",
            metric_label="Memory (MB)",
            data=memory_data,
            platform=platform,
        ))
    )

    graph_components.append(
        _row_component(
            _col_component(
                "col-sm-5",
                '<h2 class="underlined">{}</h2></hr>'.format(platform))))
    raw_files_components.append(
        _col_component(
            "col-sm-10",
            _get_file_list_component(
                storage_bucket,
                dated_subdir,
                platform)))
    graph_components.append(_row_component("\n".join(row_content)))


  content = _full_report(
      project,
      metadata["project_source"],
      date,
      command=metadata["command"],
      graph_components="\n".join(graph_components),
      raw_files_components="\n".join(raw_files_components))

  if not os.path.exists(REPORTS_DIRECTORY):
    os.makedirs(REPORTS_DIRECTORY)

  report_tmp_file = "{}/report_{}_{}.html".format(
      REPORTS_DIRECTORY, project, date.strftime("%Y%m%d")
  )
  with open(report_tmp_file, "w") as fo:
    fo.write(content)

  if storage_bucket:
    _upload_to_storage(
        report_tmp_file, storage_bucket, dated_subdir + "/report.html")
  else:
    print(content)


def main(args=None):
  if args is None:
    args = sys.argv[1:]

  parser = argparse.ArgumentParser(description="Bazel Bench Daily Report")
  parser.add_argument("--date", type=str, help="Date in YYYY-mm-dd format.")
  parser.add_argument(
      "--project",
      action="append",
      help=(
          "Projects to generate report for. Use the storage_subdir defined "
          "in the main bazel-bench script in bazelbuild/continuous-integration."
      ),
  )
  parser.add_argument(
      "--storage_bucket",
      help="The GCP Storage bucket to upload the reports to.")
  parsed_args = parser.parse_args(args)

  date = (
      datetime.datetime.strptime(parsed_args.date, "%Y-%m-%d").date()
      if parsed_args.date
      else datetime.date.today()
  )

  for project in parsed_args.project:
    _generate_report_for_date(project, date, parsed_args.storage_bucket)


if __name__ == "__main__":
  sys.exit(main())

