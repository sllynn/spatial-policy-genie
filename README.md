# Policy Genie — Insured Properties Geospatial Demo

A self-contained Databricks demo showing how to combine **interactive geospatial
visualisation in notebooks** with a **natural-language Genie space** for
exploring insured-property risk. Built for esure.

The narrative: insured properties (modelled here using Italian McDonald's
locations from the [Overture Maps](https://overturemaps.org/) Places dataset as a
stand-in) are materialised into a Delta table, visualised on interactive maps, and
then made queryable in plain English through Genie — including spatial risk
questions such as *"which of my insured properties are within 10km of a river that
has burst its banks?"*

---

## Contents

| File | Description |
|------|-------------|
| `databricks.yml` | Asset bundle definition. Declares the `catalog`, `schema`, `source_schema`, `warehouse_id`, and `parent_path` variables and the deployment targets. |
| `resources/policy_genie.job.yml` | The bundle job — task 1 builds the data, task 2 deploys the Genie space. |
| `Insured properties data.py` | The Databricks notebook (source format). Queries Overture Maps, materialises the `insured_properties` Delta table, and renders interactive maps with GeoPandas `explore()` (Folium) and GPU-accelerated [Lonboard](https://developmentseed.org/lonboard/). Reads `catalog`/`schema`/`source_schema` from notebook widgets. |
| `requirements.txt` | Python dependencies installed inside the notebook via `uv`. |
| `genie/genie_space.template.json` | Tokenised Genie space definition (`{{CATALOG}}`, `{{SCHEMA}}`, …) rendered at deploy time. |
| `genie/deploy_genie_space.py` | Deploy notebook — renders the template and create-or-updates the Genie space via REST. |
| `genie-space-insured-properties-explorer.json` | The original raw export, kept for reference. |
| `assets/logo.png` | Logo asset referenced by the notebook's intro cell. |

---

## Prerequisites

- A Databricks workspace with **serverless or a cluster supporting geospatial
  SQL functions** (`st_transform`, `st_distance`, `st_intersects`, `st_dwithin`,
  `st_union_agg`, etc.).
- Access to the [Overture Maps](https://overturemaps.org/) Places data (the
  original demo reads from `geo_sme_emea_catalog.benchmarking.places`).
- A SQL warehouse for the Genie space.

### Python dependencies

```
lonboard==0.16.0
geopandas==1.1.3
mapclassify==2.10.0
folium==0.20.0
```

These are installed at runtime by the notebook itself (`uv pip install -r ./requirements.txt`),
so no separate setup step is required.

---

## Setup

The whole demo is a [Databricks Asset Bundle](https://docs.databricks.com/dev-tools/bundles/index.html).
Deploying it builds the data **and** the Genie space in one go, re-pointed at
whatever catalog/schema you choose.

### 1. Configure the target

Everything that varies between workspaces is a bundle variable
(`databricks.yml`), with the original demo values as defaults:

| Variable | Default | Purpose |
|----------|---------|---------|
| `catalog` | `geo_sme_emea_catalog` | Catalog for output + Overture source tables |
| `schema` | `esure` | Schema the demo writes `insured_properties` into |
| `source_schema` | `benchmarking` | Schema holding the Overture `places`/`buildings`/`water` tables |
| `warehouse_id` | `994009ac5de169d0` | SQL warehouse for the Genie space |
| `parent_path` | _(your user folder)_ | Workspace folder the Genie space is created under |

Override any of them at deploy time with `--var`, or edit the defaults in
`databricks.yml`.

### 2. Deploy

```bash
# Validate the config and variable substitution
databricks bundle validate -t dev

# Sync files + create the job (override variables as needed)
databricks bundle deploy -t dev \
  --var="catalog=main,schema=policy_demo,warehouse_id=abc123def456"
```

### 3. Run

```bash
databricks bundle run policy_genie_job -t dev
```

This runs two tasks:
1. **`build_data`** — installs deps with `uv`, creates the schema, materialises
   the `insured_properties` Delta table (geometries projected to EPSG:7794 for
   accurate distance calculations), and renders the Folium + Lonboard maps.
2. **`deploy_genie`** — renders `genie/genie_space.template.json` with your
   variables and **create-or-updates** the Genie space via REST. The space is
   matched by title, so re-running updates in place rather than duplicating.

> The notebook can still be run on its own (the catalog/schema/source_schema
> widgets default to the original demo values), and the raw Genie export
> (`genie-space-insured-properties-explorer.json`) is kept for reference.

---

## The Genie space

The **Insured properties explorer** lets business users ask spatial-risk
questions in plain English. It is curated with:

- **Instructions** steering Genie to compute true distances with `st_distance` /
  `st_dwithin` on *projected* coordinates rather than relying on regional
  associations, and to be careful with partial string matching.
- **Example SQL** for common lookups.
- **Benchmark questions** that demonstrate the headline use cases, for example:
  - *"The Tyber river (Tevere in Italian) has burst its banks in multiple
    locations. Which of my insured properties are within 10km of the river?"*
  - *"For restaurants within 2km of the Tevere river, which have a building
    height of less than 10m?"*

These showcase flood-proximity risk and building-attribute joins — directly
relevant to insurance underwriting and claims scenarios.

---

## Notes

- The McDonald's locations are a **proxy for insured properties** — purely to
  give the demo realistic, recognisable geospatial points without using real
  policyholder data.
- `display_lonboard()` in the notebook is a small helper that works around the
  ipywidgets binary-buffer size limit by rendering Lonboard via `to_html()` and
  patching iframe heights for Databricks' `displayHTML`.
