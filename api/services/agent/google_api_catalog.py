from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ActionClass = Literal["read", "draft", "execute"]
RiskLevel = Literal["low", "medium", "high"]
AuthMode = Literal["oauth", "api_key", "none"]


@dataclass(frozen=True)
class GoogleApiToolSpec:
    tool_id: str
    api_name: str
    domain: str
    action_class: ActionClass
    minimum_role: str
    execution_policy: Literal["auto_execute", "confirm_before_execute"]
    risk_level: RiskLevel
    description: str
    base_url: str
    default_path: str
    default_method: str
    allowed_methods: tuple[str, ...]
    auth_mode: AuthMode
    api_key_envs: tuple[str, ...] = ()


_MAPS_KEY = ("GOOGLE_MAPS_API_KEY",)

_SPEC_ROWS: tuple[tuple[object, ...], ...] = (
    ("google.api.address_validation", "Address Validation API", "marketing_research", "read", "analyst", "auto_execute", "low", "Validate and normalize postal addresses.", "https://addressvalidation.googleapis.com", "v1:validateAddress", "POST", ("POST",), "api_key", _MAPS_KEY),
    ("google.api.aerial_view", "Aerial View API", "marketing_research", "read", "analyst", "auto_execute", "low", "Retrieve aerial-view video metadata for places.", "https://aerialview.googleapis.com", "v1/videos:lookupVideo", "GET", ("GET",), "api_key", _MAPS_KEY),
    ("google.api.air_quality", "Air Quality API", "marketing_research", "read", "analyst", "auto_execute", "low", "Retrieve air-quality conditions for a location.", "https://airquality.googleapis.com", "v1/currentConditions:lookup", "POST", ("POST",), "api_key", _MAPS_KEY),
    ("google.api.analytics_hub", "Analytics Hub API", "analytics", "read", "member", "auto_execute", "medium", "Discover and inspect shared analytics data exchanges.", "https://analyticshub.googleapis.com", "v1/projects", "GET", ("GET",), "oauth", ()),
    ("google.api.bigquery", "BigQuery API", "data_analysis", "read", "member", "auto_execute", "medium", "Query and inspect warehouse datasets.", "https://bigquery.googleapis.com", "bigquery/v2/projects", "GET", ("GET", "POST"), "oauth", ()),
    ("google.api.bigquery_connection", "BigQuery Connection API", "data_analysis", "execute", "admin", "confirm_before_execute", "high", "Manage BigQuery external data connections.", "https://bigqueryconnection.googleapis.com", "v1/projects", "GET", ("GET", "POST", "PATCH"), "oauth", ()),
    ("google.api.bigquery_data_policy", "BigQuery Data Policy API", "data_analysis", "execute", "admin", "confirm_before_execute", "high", "Manage data masking and fine-grained policies.", "https://bigquerydatapolicy.googleapis.com", "v1/projects", "GET", ("GET", "POST", "PATCH"), "oauth", ()),
    ("google.api.bigquery_data_transfer", "BigQuery Data Transfer API", "data_analysis", "execute", "admin", "confirm_before_execute", "high", "Schedule and manage data transfer configurations.", "https://bigquerydatatransfer.googleapis.com", "v1/projects", "GET", ("GET", "POST", "PATCH"), "oauth", ()),
    ("google.api.bigquery_migration", "BigQuery Migration API", "data_analysis", "execute", "admin", "confirm_before_execute", "high", "Inspect and execute migration workflows.", "https://bigquerymigration.googleapis.com", "v2/projects", "GET", ("GET", "POST"), "oauth", ()),
    ("google.api.bigquery_reservation", "BigQuery Reservation API", "data_analysis", "execute", "admin", "confirm_before_execute", "high", "Manage reservation slots and commitments.", "https://bigqueryreservation.googleapis.com", "v1/projects", "GET", ("GET", "POST", "PATCH"), "oauth", ()),
    ("google.api.bigquery_storage", "BigQuery Storage API", "data_analysis", "read", "member", "auto_execute", "medium", "Read query and table data via Storage API.", "https://bigquerystorage.googleapis.com", "v1/projects", "GET", ("GET", "POST"), "oauth", ()),
    ("google.api.cloud_dataplex", "Cloud Dataplex API", "data_analysis", "read", "member", "auto_execute", "medium", "Inspect dataplex lakes, zones, and assets.", "https://dataplex.googleapis.com", "v1/projects", "GET", ("GET",), "oauth", ()),
    ("google.api.cloud_datastore", "Cloud Datastore API", "data_analysis", "execute", "admin", "confirm_before_execute", "high", "Query and mutate Datastore entities.", "https://datastore.googleapis.com", "v1/projects", "POST", ("GET", "POST"), "oauth", ()),
    ("google.api.cloud_logging", "Cloud Logging API", "analytics", "read", "analyst", "auto_execute", "medium", "Read log entries for operational diagnostics.", "https://logging.googleapis.com", "v2/entries:list", "POST", ("POST",), "oauth", ()),
    ("google.api.cloud_monitoring", "Cloud Monitoring API", "analytics", "read", "analyst", "auto_execute", "medium", "Inspect metrics and alerting resources.", "https://monitoring.googleapis.com", "v3/projects", "GET", ("GET",), "oauth", ()),
    ("google.api.cloud_sql", "Cloud SQL Admin API", "data_analysis", "execute", "admin", "confirm_before_execute", "high", "Manage Cloud SQL instances and operations.", "https://sqladmin.googleapis.com", "sql/v1beta4/projects", "GET", ("GET", "POST", "PATCH"), "oauth", ()),
    ("google.api.cloud_storage", "Cloud Storage API", "document_ops", "execute", "member", "auto_execute", "medium", "Read and write Cloud Storage objects.", "https://storage.googleapis.com", "storage/v1/b", "GET", ("GET", "POST", "PATCH", "PUT"), "oauth", ()),
    ("google.api.cloud_storage_json", "Google Cloud Storage JSON API", "document_ops", "execute", "member", "auto_execute", "medium", "Use JSON endpoints for bucket/object operations.", "https://storage.googleapis.com", "storage/v1/b", "GET", ("GET", "POST", "PATCH", "PUT"), "oauth", ()),
    ("google.api.cloud_trace", "Cloud Trace API", "analytics", "read", "analyst", "auto_execute", "medium", "Inspect distributed trace latency and spans.", "https://cloudtrace.googleapis.com", "v2/projects", "GET", ("GET", "POST"), "oauth", ()),
    ("google.api.dataform", "Dataform API", "data_analysis", "execute", "admin", "confirm_before_execute", "high", "Manage SQL workflows and data transformation runs.", "https://dataform.googleapis.com", "v1/projects", "GET", ("GET", "POST"), "oauth", ()),
    ("google.api.directions", "Directions API", "marketing_research", "read", "analyst", "auto_execute", "low", "Compute driving/walking/transit directions.", "https://maps.googleapis.com", "maps/api/directions/json", "GET", ("GET",), "api_key", _MAPS_KEY),
    ("google.api.distance_matrix", "Distance Matrix API", "marketing_research", "read", "analyst", "auto_execute", "low", "Compute travel distance/time matrices.", "https://maps.googleapis.com", "maps/api/distancematrix/json", "GET", ("GET",), "api_key", _MAPS_KEY),
    ("google.api.drive_labels", "Drive Labels API", "document_ops", "execute", "member", "auto_execute", "medium", "Inspect and update Google Drive label metadata.", "https://drivelabels.googleapis.com", "v2/labels", "GET", ("GET", "POST", "PATCH"), "oauth", ()),
    ("google.api.geocoding", "Geocoding API", "marketing_research", "read", "analyst", "auto_execute", "low", "Convert addresses to coordinates and vice versa.", "https://maps.googleapis.com", "maps/api/geocode/json", "GET", ("GET",), "api_key", _MAPS_KEY),
    ("google.api.geolocation", "Geolocation API", "marketing_research", "read", "analyst", "auto_execute", "low", "Estimate location from network and cell data.", "https://www.googleapis.com", "geolocation/v1/geolocate", "POST", ("POST",), "api_key", _MAPS_KEY),
    ("google.api.gmail", "Gmail API", "email_ops", "execute", "admin", "confirm_before_execute", "high", "Access Gmail resources and messaging operations.", "https://gmail.googleapis.com", "gmail/v1/users/me/messages", "GET", ("GET", "POST"), "oauth", ()),
    ("google.api.google_analytics", "Google Analytics API", "analytics", "read", "analyst", "auto_execute", "medium", "Access Analytics management resources.", "https://analyticsadmin.googleapis.com", "v1beta/accountSummaries", "GET", ("GET",), "oauth", ()),
    ("google.api.google_analytics_data", "Google Analytics Data API", "analytics", "read", "analyst", "auto_execute", "medium", "Run GA4 property reports and metrics queries.", "https://analyticsdata.googleapis.com", "v1beta/properties", "POST", ("GET", "POST"), "oauth", ()),
    ("google.api.google_calendar", "Google Calendar API", "scheduling", "execute", "admin", "confirm_before_execute", "high", "Read and write calendars and events.", "https://www.googleapis.com", "calendar/v3/calendars/primary/events", "GET", ("GET", "POST", "PATCH"), "oauth", ()),
    ("google.api.google_docs", "Google Docs API", "document_ops", "execute", "member", "auto_execute", "medium", "Read and edit Google Docs documents.", "https://docs.googleapis.com", "v1/documents", "GET", ("GET", "POST"), "oauth", ()),
    ("google.api.google_drive", "Google Drive API", "document_ops", "execute", "member", "auto_execute", "medium", "Search, read, and manage Drive files.", "https://www.googleapis.com", "drive/v3/files", "GET", ("GET", "POST", "PATCH"), "oauth", ()),
    ("google.api.google_sheets", "Google Sheets API", "document_ops", "execute", "member", "auto_execute", "medium", "Read and update spreadsheet values and metadata.", "https://sheets.googleapis.com", "v4/spreadsheets", "GET", ("GET", "POST", "PUT"), "oauth", ()),
    ("google.api.google_slides", "Google Slides API", "document_ops", "execute", "member", "auto_execute", "medium", "Generate and update Slides presentations.", "https://slides.googleapis.com", "v1/presentations", "GET", ("GET", "POST"), "oauth", ()),
    ("google.api.google_tasks", "Google Tasks API", "scheduling", "execute", "member", "auto_execute", "medium", "Read and manage task lists and tasks.", "https://tasks.googleapis.com", "tasks/v1/users/@me/lists", "GET", ("GET", "POST", "PATCH"), "oauth", ()),
    ("google.api.map_tiles", "Map Tiles API", "marketing_research", "read", "analyst", "auto_execute", "low", "Fetch map tile metadata and session resources.", "https://tile.googleapis.com", "v1/createSession", "POST", ("POST",), "api_key", _MAPS_KEY),
    ("google.api.maps_elevation", "Maps Elevation API", "marketing_research", "read", "analyst", "auto_execute", "low", "Retrieve elevation for coordinates.", "https://maps.googleapis.com", "maps/api/elevation/json", "GET", ("GET",), "api_key", _MAPS_KEY),
    ("google.api.maps_embed", "Maps Embed API", "marketing_research", "read", "analyst", "auto_execute", "low", "Build embeddable map URLs for results.", "https://www.google.com", "maps/embed/v1/place", "GET", ("GET",), "api_key", _MAPS_KEY),
    ("google.api.maps_platform_datasets", "Maps Platform Datasets API", "marketing_research", "execute", "member", "auto_execute", "medium", "Manage Maps platform datasets and features.", "https://mapsplatformdatasets.googleapis.com", "v1/projects", "GET", ("GET", "POST"), "oauth", ()),
    ("google.api.maps_static", "Maps Static API", "marketing_research", "read", "analyst", "auto_execute", "low", "Generate static map image requests.", "https://maps.googleapis.com", "maps/api/staticmap", "GET", ("GET",), "api_key", _MAPS_KEY),
    ("google.api.pagespeed_insights", "PageSpeed Insights API", "analytics", "read", "analyst", "auto_execute", "low", "Analyze webpage performance and optimization opportunities.", "https://www.googleapis.com", "pagespeedonline/v5/runPagespeed", "GET", ("GET",), "none", ()),
)


GOOGLE_API_TOOL_SPECS: tuple[GoogleApiToolSpec, ...] = tuple(
    GoogleApiToolSpec(
        tool_id=str(row[0]),
        api_name=str(row[1]),
        domain=str(row[2]),
        action_class=str(row[3]),  # type: ignore[arg-type]
        minimum_role=str(row[4]),
        execution_policy=str(row[5]),  # type: ignore[arg-type]
        risk_level=str(row[6]),  # type: ignore[arg-type]
        description=str(row[7]),
        base_url=str(row[8]),
        default_path=str(row[9]),
        default_method=str(row[10]),
        allowed_methods=tuple(row[11]),  # type: ignore[arg-type]
        auth_mode=str(row[12]),  # type: ignore[arg-type]
        api_key_envs=tuple(row[13]),  # type: ignore[arg-type]
    )
    for row in _SPEC_ROWS
)

GOOGLE_API_TOOL_IDS: set[str] = {spec.tool_id for spec in GOOGLE_API_TOOL_SPECS}

