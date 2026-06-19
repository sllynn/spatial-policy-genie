# Databricks notebook source
# DBTITLE 1,Deploy the Insured properties Genie space
# MAGIC %md
# MAGIC # Deploy Genie space
# MAGIC
# MAGIC Renders `genie_space.template.json` with the bundle variables and
# MAGIC **create-or-updates** the Genie space via the REST API
# MAGIC (`/api/2.0/genie/spaces`). Genie spaces are not a native Asset Bundle
# MAGIC resource, so this notebook is run as a job task after the data is built.
# MAGIC
# MAGIC Idempotent: the space is matched by **title** under `parent_path`. A match
# MAGIC is patched; otherwise a new space is created.

# COMMAND ----------

# DBTITLE 1,Parameters
dbutils.widgets.text("catalog", "geo_sme_emea_catalog")
dbutils.widgets.text("schema", "esure")
dbutils.widgets.text("source_schema", "benchmarking")
dbutils.widgets.text("warehouse_id", "994009ac5de169d0")
dbutils.widgets.text("parent_path", "")
dbutils.widgets.text("template_path", "genie_space.template.json")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
SOURCE_SCHEMA = dbutils.widgets.get("source_schema")
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id")
PARENT_PATH = dbutils.widgets.get("parent_path")
TEMPLATE_PATH = dbutils.widgets.get("template_path")

# COMMAND ----------

# DBTITLE 1,Render the template
import json
import os


def resolve_template(path):
    """Find the template regardless of the working directory.

    Depending on how the notebook is launched, the cwd may be the project root
    or the notebook's own folder. Try the path as given, then relative to this
    file's directory, then by basename in the cwd.
    """
    candidates = [path]
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(here, os.path.basename(path)))
    except NameError:
        pass
    candidates.append(os.path.basename(path))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(
        f"Could not find template '{path}'. Tried: {[c for c in candidates if c]}"
    )


with open(resolve_template(TEMPLATE_PATH), "r", encoding="utf-8") as handle:
    rendered = handle.read()

for token, value in {
    "{{CATALOG}}": CATALOG,
    "{{SCHEMA}}": SCHEMA,
    "{{SOURCE_SCHEMA}}": SOURCE_SCHEMA,
    "{{WAREHOUSE_ID}}": WAREHOUSE_ID,
    "{{PARENT_PATH}}": PARENT_PATH,
}.items():
    rendered = rendered.replace(token, value)

doc = json.loads(rendered)

# Build the API request body. serialized_space must be a JSON-encoded *string*;
# the rest are outer metadata. Drop any read-only fields just in case.
doc.pop("etag", None)
doc.pop("space_id", None)
serialized_space = json.dumps(doc["serialized_space"])

request_body = {
    "title": doc["title"],
    "description": doc.get("description", ""),
    "parent_path": doc["parent_path"],
    "warehouse_id": doc["warehouse_id"],
    "serialized_space": serialized_space,
}

print(f"Title:        {request_body['title']}")
print(f"Parent path:  {request_body['parent_path']}")
print(f"Warehouse:    {request_body['warehouse_id']}")

# COMMAND ----------

# DBTITLE 1,Create or update via REST
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# The Genie API requires parent_path to be an existing workspace folder, but the
# bundle only deploys files under ${workspace.file_path}, never this folder. Create
# it up front (mkdirs is idempotent and creates intermediate folders).
if PARENT_PATH:
    w.workspace.mkdirs(PARENT_PATH)


def find_existing_space(title, parent_path):
    """Return the space_id of an existing space with this title/parent, else None."""
    page_token = None
    while True:
        query = {"page_size": 100}
        if page_token:
            query["page_token"] = page_token
        resp = w.api_client.do("GET", "/api/2.0/genie/spaces", query=query) or {}
        for space in resp.get("spaces", []):
            if space.get("title") == title and space.get("parent_path", parent_path) == parent_path:
                return space.get("space_id")
        page_token = resp.get("next_page_token")
        if not page_token:
            return None


existing_id = find_existing_space(request_body["title"], request_body["parent_path"])

if existing_id:
    print(f"Updating existing space {existing_id} ...")
    result = w.api_client.do(
        "PATCH", f"/api/2.0/genie/spaces/{existing_id}", body=request_body
    )
else:
    print("Creating new space ...")
    result = w.api_client.do("POST", "/api/2.0/genie/spaces", body=request_body)

space_id = (result or {}).get("space_id", existing_id)
workspace_url = w.config.host.rstrip("/")
print(f"Done. space_id = {space_id}")
print(f"Open: {workspace_url}/genie/rooms/{space_id}")

# COMMAND ----------

# DBTITLE 1,Surface the result to the job run
dbutils.notebook.exit(json.dumps({"space_id": space_id}))
