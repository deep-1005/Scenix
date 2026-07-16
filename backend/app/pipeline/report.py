# backend/app/pipeline/report.py
import os
from jinja2 import Template
from weasyprint import HTML

REPORT_TEMPLATE = """
<html><body>
<h1>Scene Report — Job {{ job_id }}</h1>
<h2>Room dimensions ({{ unit }})</h2>
<p>{{ room_dimensions }}</p>
<h2>Evidence Items</h2>
<table border="1" cellpadding="6">
<tr><th>ID</th><th>Label</th><th>Classification</th><th>Dimensions</th></tr>
{% for item in evidence %}
<tr>
  <td>{{ item.id }}</td>
  <td>{{ item.label }}</td>
  <td>{{ item.classification }} ({{ "%.2f"|format(item.classification_confidence or 0) }})</td>
  <td>{{ item.dimensions }}</td>
</tr>
{% endfor %}
</table>
</body></html>
"""


def run_report(job_id: str, scene_out: str) -> str:
    import json
    with open(os.path.join(scene_out, "measurements.json")) as f:
        measurements = json.load(f)

    html = Template(REPORT_TEMPLATE).render(
        job_id=job_id,
        unit=measurements["unit"],
        room_dimensions=measurements["room_dimensions"],
        evidence=measurements["evidence"],
    )

    out_path = os.path.join(scene_out, "report.pdf")
    HTML(string=html).write_pdf(out_path)
    return out_path