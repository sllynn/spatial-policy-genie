# Databricks notebook source
# DBTITLE 1,Introduction
# MAGIC %md
# MAGIC # Insured Properties
# MAGIC ## Geospatial visualisation in the notebook
# MAGIC
# MAGIC <img src="./assets/logo.png" width="200"/>
# MAGIC
# MAGIC This notebook demonstrates how to:
# MAGIC 1. **Query** the Overture Maps Places dataset to extract Italian McDonald's locations as a proxy for insured properties
# MAGIC 2. **Materialise** the results into a Delta table with projected geometries
# MAGIC 3. **Visualise** the locations interactively using both GeoPandas' built-in `explore()` and the GPU-accelerated [Lonboard](https://developmentseed.org/lonboard/) library
# MAGIC

# COMMAND ----------

# MAGIC %pip install uv

# COMMAND ----------

# MAGIC %sh uv pip install -r ./requirements.txt

# COMMAND ----------

# MAGIC %restart_python

# COMMAND ----------

# DBTITLE 1,Configuration & Data Preparation
# MAGIC %md
# MAGIC ## Configuration & Data Preparation
# MAGIC
# MAGIC We parameterise the **catalog** and **schema** so the notebook can be re-pointed to a different environment with a single change. The source data comes from the [Overture Maps](https://overturemaps.org/) **Places** dataset, which provides rich POI information including addresses, categories, and precise geometries.

# COMMAND ----------

# DBTITLE 1,Define parameters & create schema
# These are surfaced as notebook widgets so the bundle (or a manual run) can
# re-point the demo at any catalog/schema. The defaults match the original demo
# environment, so the notebook still runs standalone with no parameters set.
dbutils.widgets.text("catalog", "geo_sme_emea_catalog")
dbutils.widgets.text("schema", "esure")
dbutils.widgets.text("source_schema", "benchmarking")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
SOURCE_SCHEMA = dbutils.widgets.get("source_schema")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

# COMMAND ----------

# DBTITLE 1,Create insured_properties table
spark.sql(f"""
CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.insured_properties AS
SELECT 
    id,
    addresses[0].freeform   AS building_street,
    addresses[0].locality   AS locality,
    addresses[0].region     AS region,
    addresses[0].postcode   AS postcode,
    addresses[0].country    AS country,
    names.primary           AS primary_name,
    operating_status,
    basic_category,
    version,
    geometry                AS geometry_4326,
    st_transform(geometry, 7794) AS geometry_7794
FROM {CATALOG}.{SOURCE_SCHEMA}.places
WHERE lcase(names.primary) LIKE '%mcdonald%'
    AND categories.primary = 'fast_food_restaurant'
    AND addresses[0].country = 'IT'
""")


# COMMAND ----------

# DBTITLE 1,Preview the table
display(spark.table(f"{CATALOG}.{SCHEMA}.insured_properties"))


# COMMAND ----------

# DBTITLE 1,Visualisation approach
# MAGIC %md
# MAGIC ## Building a GeoDataFrame for Visualisation
# MAGIC
# MAGIC To plot the insured property locations on an interactive map we convert the Spark DataFrame to a [GeoPandas](https://geopandas.org/) `GeoDataFrame`. This involves:
# MAGIC 1. Extracting the geometry column as **WKB** (Well-Known Binary)
# MAGIC 2. Parsing it into Shapely geometry objects
# MAGIC 3. Assigning the **WGS 84** (EPSG:4326) coordinate reference system

# COMMAND ----------

from lonboard import Map, PolygonLayer, ScatterplotLayer
import geopandas as gpd

import pyspark.sql.functions as F
import pyspark.databricks.sql.functions as DBF

# COMMAND ----------

# DBTITLE 1,Convert to GeoDataFrame
key_cols = [
    "id",
    "primary_name",
    "operating_status",
    "basic_category",
    "version",
]

# serialise geometries to something geopandas will understand
properties_sdf = (
    spark.table(f"{CATALOG}.{SCHEMA}.insured_properties")
    .select(*key_cols, DBF.st_aswkb("geometry_4326").alias("geometry_4326"))
)

# collect to local pandas DF
properties_pdf = properties_sdf.toPandas()

# create a geoseries object
properties_pdf["geometry"] = gpd.GeoSeries.from_wkb(properties_pdf["geometry_4326"], crs=4326)

# create a geodataframe object
properties_gdf = gpd.GeoDataFrame(properties_pdf.drop("geometry_4326", axis=1), geometry="geometry")

# COMMAND ----------

# DBTITLE 1,Quick explore
# MAGIC %md
# MAGIC ### Quick Exploration with `explore()`
# MAGIC
# MAGIC GeoPandas provides a built-in `explore()` method that renders an interactive [Folium](https://python-visualization.github.io/folium/) map — perfect for a quick sanity-check of the point locations before building a more customised visualisation.

# COMMAND ----------

# DBTITLE 1,Interactive folium map
properties_gdf.explore(
    marker_kwds={"radius": 5},
    style_kwds={"weight": 1},
    tooltip=["primary_name", "basic_category"],
)

# COMMAND ----------

# DBTITLE 1,Lonboard section
# MAGIC %md
# MAGIC ### Custom Visualisation with Lonboard
# MAGIC
# MAGIC [Lonboard](https://developmentseed.org/lonboard/) provides GPU-accelerated, large-scale geospatial rendering directly in the notebook. Below we build a `ScatterplotLayer` with custom styling and wrap it in a helper that renders the map inside Databricks' `displayHTML`.

# COMMAND ----------

# DBTITLE 1,Lonboard widget test
import re

def display_lonboard(m, height=600):
    """Display a lonboard Map in Databricks via displayHTML.
    
    Works around the ipywidgets binary buffer size limit by using
    lonboard's to_html() and patching viewport heights for the iframe.
    """
    html_str = m.to_html()
    # Patch 100%/100vh heights → fixed pixels (displayHTML iframe needs measurable content)
    html_str = re.sub(r'height:\s*100[^;]*;', f'height: {height}px;', html_str)
    html_str = re.sub(r'height:\s*100[^"]*"', f'height: {height}px"', html_str)
    if '<body' in html_str and 'height' not in html_str.split('<body')[1].split('>')[0]:
        html_str = html_str.replace('<body', f'<body style="height:{height}px;margin:0;"', 1)
    displayHTML(html_str)

# Build the map using lonboard's full Python API
layer = ScatterplotLayer.from_geopandas(
    properties_gdf,
    get_fill_color=[0, 255, 0, 200],
    get_line_color=[0, 0, 0],
    get_radius=500,
    radius_min_pixels=5,
    radius_max_pixels=15,
    stroked=True,
    filled=True,
    pickable=True,
)
m = Map(
    layers=[layer],
)
display_lonboard(m)