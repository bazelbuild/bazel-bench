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
from google.cloud import bigquery


TMP = tempfile.gettempdir()
REPORTS_DIRECTORY = os.path.join(TMP, ".bazel_bench", "reports")
PLATFORMS = ["macos", "ubuntu1804"]
PROJECT_SOURCE_TO_NAME = {
  "https://github.com/bazelbuild/bazel.git": "bazel",
  "https://github.com/tensorflow/tensorflow.git": "tensorflow"
}


def _upload_to_storage(src_file_path, storage_bucket, destination_dir):
  """Uploads the file from src_file_path to the specified location on Storage.
  """
  args = ["gsutil", "cp", src_file_path, "gs://{}/{}".format(storage_bucket, destination_dir)]
  subprocess.run(args)


def _get_storage_url(storage_bucket, dated_subdir):
  # In this case, the storage_bucket is a Domain-named bucket.
  # https://cloud.google.com/storage/docs/domain-name-verification
  return "https://{}/{}".format(storage_bucket, dated_subdir)


def _short_hash(commit):
  return commit[:7]


def _row_component(content):
  return """
<div class="row">{content}</div>
""".format(content=content)


def _col_component(col_class, content):
  return """
<div class="{col_class}">{content}</div>
""".format(col_class=col_class, content=content)
 

def _historical_graph(metric, metric_label, data, platform):
  """Returns the HTML <div> component of a single graph.
  """
  title = "[{}] Historical values of {}".format(platform, metric_label)
  hAxis = "Date (commmit)"
  vAxis = metric_label
  chart_id = "{}-{}-time".format(platform, metric)

  return """
<script type="text/javascript">
  google.charts.setOnLoadCallback(drawChart);
  function drawChart() {{
    var rawDataFromScript = {data}
    for (var i = 0; i < rawDataFromScript.length; i++) {{
      for (var j = 0; j < rawDataFromScript[i].length; j++) {{
        if (rawDataFromScript[i][j] === "null") {{
          rawDataFromScript[i][j] = null
        }}
      }}
    }}
    var data = google.visualization.arrayToDataTable(rawDataFromScript)

    var options = {{
      title: "{title}",
      titleTextStyle: {{ color: "gray" }},
      hAxis: {{
        title: "{hAxis}",
        titleTextStyle: {{ color: "darkgray" }},
        textStyle: {{ color: "darkgray" }},
      }},
      vAxis: {{
        title: "{vAxis}",
        titleTextStyle: {{ color: "darkgray" }},
        textStyle: {{ color: "darkgray" }},
      }},
      axes: {{
        y: {{
          wall: {{ label: "{metric_label}"}},
        }}
      }},
      intervals: {{ 'style':'area' }},
      legend: {{ position: "right" }},
    }};
    var chart = new google.visualization.LineChart(document.getElementById("{chart_id}"));
    chart.draw(data, options);
  }}
  </script>
<div id="{chart_id}" style="min-height: 400px"></div>
""".format(
    title=title, data=data, hAxis=hAxis, vAxis=vAxis, chart_id=chart_id,
    metric_label=metric_label)


def _full_report(date, graph_components, project_reports_components):
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
    <script src="https://code.jquery.com/jquery-3.3.1.slim.min.js" integrity="sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo" crossorigin="anonymous"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.14.7/umd/popper.min.js" integrity="sha384-UO2eT0CpHqdSJQ6hJty5KVphtPhzWj9WO1clHTMGa3JDZwrnQq4sF86dIHNDz0W1" crossorigin="anonymous"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/js/bootstrap.min.js" integrity="sha384-JjSmVgyd0p3pXB1rRibZUAYoIIy6OrQ6VrjIEaFf/nJGzIxFDsf4x0xIM+B07jRM" crossorigin="anonymous"></script>
    <!-- For the datepicker. -->
    <script src="https://unpkg.com/gijgo@1.9.13/js/gijgo.min.js" type="text/javascript"></script>
    <link href="https://unpkg.com/gijgo@1.9.13/css/gijgo.min.css" rel="stylesheet" type="text/css" />

    <style>
      h1 {{ font-size: 1.7rem; color: darkslategrey; }}
      h2 {{ font-size: 1.3rem; color: gray; }}
      h2.underlined {{ border-bottom: 2px dotted lightgray; }}
      body {{ font-family: monospace; padding: 1% 3% 1% 3%; font-size:1.1rem; }}
    </style>
    <link rel="icon" type="image/png" href="https://raw.githubusercontent.com/bazelbuild/bazel-bench/master/bb-icon.png">
    <title>[{date}] Master Report</title>
  </head>
  <body>
    <div class="container-fluid">
      <div class="row">
        <div class="col-sm-12">
          <h1>Report for {date}</h1>
        </div>
      </div>
      <div class="row">
        <div class="col-sm-12">
          {reports}
        </div>
      </div>

      <div class="row">
        <div class="col-sm-3 input-group">
          <span><input id="datePicker" width="150px"/></span>
          <span><button id="viewReportButton" type="button" class="btn btn-sm btn-link">View Past Report</button><i>(Date & time are in UTC.)</i></span>
        </div>
        <script>
          // latestReportDate is always yesterday.
          var latestReportDate = new Date();
          latestReportDate.setDate(latestReportDate.getDate() - 1)

          var $datePicker = $('#datePicker').datepicker({{
              uiLibrary: 'bootstrap4',
              size: 'small',
              format: 'yyyy/mm/dd',
              value: '{date}',
              disableDates: function (date) {{
                return date < latestReportDate;
              }}
          }});
          
          $('#viewReportButton').on('click', function () {{
            var dateSubdir = $datePicker.value();
            var url = `https://perf.bazel.build/all/${{dateSubdir}}/report.html`;
            window.open(url, '_blank');
          }});
        </script>
      </div>
      <br>

      {graphs}
    </div>
  </body>
</html>
""".format(
    date=date.strftime("%Y/%m/%d"),
    graphs=graph_components,
    reports=project_reports_components
  )


def _query_bq(bq_project, bq_table, date_cutoff, platform):
  bq_client = bigquery.Client(project=bq_project)
  query = """
SELECT
  MIN(wall) as min_wall,
  APPROX_QUANTILES(wall, 101)[OFFSET(50)] AS median_wall,
  MAX(wall) as max_wall,
  MIN(memory) as min_memory,
  APPROX_QUANTILES(memory, 101)[OFFSET(50)] AS median_memory,
  MAX(memory) as max_memory,
  bazel_commit,
  DATE(MIN(started_at)) as report_date,
  project_label
FROM (
  SELECT wall, memory, started_at, bazel_commit, project_label FROM `{bq_project}.{bq_table}`
  WHERE bazel_commit IN (
    SELECT bazel_commit
    FROM (
      SELECT bazel_commit, started_at,
            RANK() OVER (PARTITION BY project_commit
                             ORDER BY started_at DESC
                        ) AS `Rank`
        FROM `{bq_project}.{bq_table}`
        WHERE DATE(started_at) <= "{date_cutoff}"
        AND platform = "{platform}"
        AND exit_status = 0       
    )
    WHERE Rank=1
    ORDER BY started_at DESC
    LIMIT 10
  )
  AND platform = "{platform}"
  AND exit_status = 0       
)
GROUP BY bazel_commit, project_label
ORDER BY report_date, project_label ASC;
""".format(bq_project=bq_project, bq_table=bq_table, date_cutoff=date_cutoff, platform=platform)

  return bq_client.query(query)


# TODO(leba): Normalize data between projects.
def _prepare_time_series_data(raw_data):
  """Massage the data to fit a format suitable for graph generation.
  """
  headers = ["Date"]
  project_to_pos = {}
  date_to_wall = {}
  date_to_mem = {}

  # First pass to gather the projects and form the headers.
  for row in raw_data:
    if row.project_label not in project_to_pos:
      project_to_pos[row.project_label] = len(project_to_pos)
      headers.extend([row.project_label, {"role": "interval"}, {"role": "interval"}])

  for row in raw_data:
    if row.report_date not in date_to_wall:
      # Commits on day X are benchmarked on day X + 1.
      date_str = "{} ({})".format(
        (row.report_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
        _short_hash(row.bazel_commit))
      
      date_to_wall[row.report_date] = ["null"] * len(headers)
      date_to_mem[row.report_date] = ["null"] * len(headers)

      date_to_wall[row.report_date][0] = date_str
      date_to_mem[row.report_date][0] = date_str

    base_pos = project_to_pos[row.project_label] * 3
    date_to_wall[row.report_date][base_pos + 1] = row.median_wall
    date_to_wall[row.report_date][base_pos + 2] = row.min_wall
    date_to_wall[row.report_date][base_pos + 3] = row.max_wall
    date_to_mem[row.report_date][base_pos + 1] = row.median_memory
    date_to_mem[row.report_date][base_pos + 2] = row.min_memory
    date_to_mem[row.report_date][base_pos + 3] = row.max_memory

  return [headers] + list(date_to_wall.values()), [headers] + list(date_to_mem.values()), project_to_pos.keys()


def _project_reports_components(date, projects):
  links = " - ".join(
    ['<a href="https://perf.bazel.build/{project_label}/{date_subdir}/report.html">{project_label}</a>'.format(
      date_subdir=date.strftime("%Y/%m/%d"), project_label=label) for label in projects])
  return "<p><b>Individual Project Reports:</b> {}</p>".format(links)


def _generate_report_for_date(date, storage_bucket, report_name, upload_report, bq_project, bq_table):
  """Generates a html report for the specified date & project.

  Args:
    date: the date to generate report for.
    storage_bucket: the Storage bucket to fetch data from/upload the report to.
    report_name: the name of the report on GS.
    upload_report: whether to upload the report to GCS.
    bq_project: the BigQuery project.
    bq_table: the BigQuery table.
  """
  bq_date_cutoff = (date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

  graph_components = []
  projects = set()

  for platform in PLATFORMS:

    historical_wall_data, historical_mem_data, platform_projects = _prepare_time_series_data(
      _query_bq(bq_project, bq_table, bq_date_cutoff, platform))

    projects = projects.union(set(platform_projects))
    # Generate a graph for that platform.
    row_content = []

    row_content.append(
        _col_component("col-sm-6", _historical_graph(
            metric="wall",
            metric_label="Wall Time (s)",
            data=historical_wall_data,
            platform=platform,
        ))
    )

    row_content.append(
        _col_component("col-sm-6", _historical_graph(
            metric="memory",
            metric_label="Memory (MB)",
            data=historical_mem_data,
            platform=platform,
        ))
    )

    graph_components.append(_row_component("\n".join(row_content)))
    
  content = _full_report(
    date,
    graph_components="\n".join(graph_components),
    project_reports_components=_project_reports_components(date, projects))

  if not os.path.exists(REPORTS_DIRECTORY):
    os.makedirs(REPORTS_DIRECTORY)

  report_tmp_file = "{}/report_master_{}.html".format(
      REPORTS_DIRECTORY, date.strftime("%Y%m%d")
  )
  with open(report_tmp_file, "w") as fo:
    fo.write(content)

  if upload_report:
    _upload_to_storage(
        report_tmp_file, storage_bucket, "all/{}/{}.html".format(date.strftime("%Y/%m/%d"), report_name))
  else:
    print(content)


def main(args=None):
  if args is None:
    args = sys.argv[1:]

  parser = argparse.ArgumentParser(description="Bazel Bench Daily Master Report")
  parser.add_argument("--date", type=str, help="Date in YYYY-mm-dd format.")
  parser.add_argument(
      "--storage_bucket",
      help="The GCP Storage bucket to fetch benchmark data from/upload the reports to.")
  parser.add_argument(
      "--upload_report", type=bool, default=False,
      help="Whether to upload the report.")
  parser.add_argument(
      "--bigquery_table",
      help="The BigQuery table to fetch data from. In the format: project:table_identifier.")
  parser.add_argument(
      "--report_name", type=str,
      help="The name of the generated report.", default="report")
  parsed_args = parser.parse_args(args)

  date = (
      datetime.datetime.strptime(parsed_args.date, "%Y-%m-%d").date()
      if parsed_args.date
      else datetime.date.today()
  )

  bq_project, bq_table = parsed_args.bigquery_table.split(':')
  _generate_report_for_date(
      date, parsed_args.storage_bucket, parsed_args.report_name,
      parsed_args.upload_report, bq_project, bq_table)


if __name__ == "__main__":
  sys.exit(main())
