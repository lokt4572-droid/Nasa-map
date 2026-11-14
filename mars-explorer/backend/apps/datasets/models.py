from django.db import models


class Dataset(models.Model):
    """A scientific raster registered with the application (never modified by it)."""

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available (registered, not yet validated)"
        DOWNLOADING = "DOWNLOADING", "Downloading"
        PROCESSING = "PROCESSING", "Processing"
        VALID = "VALID", "Valid"
        INVALID = "INVALID", "Invalid"
        MISSING = "MISSING", "File missing"

    class DataType(models.TextChoices):
        DEM = "DEM", "Digital elevation model"
        ORTHOIMAGE = "ORTHOIMAGE", "Orthoimage / mosaic"
        SLOPE = "SLOPE", "Slope raster"
        HILLSHADE = "HILLSHADE", "Hillshade"
        ROUGHNESS = "ROUGHNESS", "Roughness"
        OTHER = "OTHER", "Other"

    class Planet(models.TextChoices):
        MARS = "MARS", "Mars"
        EARTH = "EARTH", "Earth"
        MOON = "MOON", "Moon"
        MERCURY = "MERCURY", "Mercury"
        VENUS = "VENUS", "Venus"

    name = models.SlugField(max_length=120, unique=True)
    planet = models.CharField(max_length=10, choices=Planet.choices, default=Planet.MARS, db_index=True)
    license = models.CharField(max_length=300, blank=True)
    download_url = models.URLField(max_length=500, blank=True)
    source = models.CharField(max_length=200, blank=True, help_text="Archive / provider, e.g. NASA PDS Geosciences Node")
    instrument = models.CharField(max_length=120, blank=True, help_text="e.g. MGS MOLA, MRO HiRISE")
    product_id = models.CharField(max_length=200, blank=True)
    data_type = models.CharField(max_length=20, choices=DataType.choices, default=DataType.DEM)
    file_path = models.CharField(max_length=1024)
    driver = models.CharField(max_length=40, blank=True, help_text="GDAL driver that opened the file")
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    # Only what metadata states: nullable instead of an invented value.
    resolution_meters = models.FloatField(null=True, blank=True)
    pixel_size_x = models.FloatField(null=True, blank=True, help_text="In CRS axis units")
    pixel_size_y = models.FloatField(null=True, blank=True, help_text="In CRS axis units")
    crs = models.TextField(blank=True, help_text="CRS as WKT read from the file")
    crs_name = models.CharField(max_length=200, blank=True)
    longitude_convention = models.CharField(max_length=40, default="UNKNOWN")
    latitude_convention = models.CharField(max_length=40, default="UNKNOWN")
    vertical_datum = models.CharField(max_length=200, default="UNSPECIFIED")
    units = models.CharField(max_length=40, blank=True)
    nodata_value = models.FloatField(null=True, blank=True)
    coverage_bbox = models.JSONField(null=True, blank=True, help_text="Native bounds: {crs_units, left, bottom, right, top}")
    observation_date = models.DateField(null=True, blank=True)
    download_date = models.DateField(null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    checksum = models.CharField(max_length=80, blank=True, help_text="sha256:<hex>")
    is_validated = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    validation_messages = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True, help_text="Full GDAL inspection result")
    # v0.4: where the values are read from, the real footprint and the provider's quality data.
    access = models.CharField(max_length=12, default="LOCAL", help_text="LOCAL file or REMOTE_COG (HTTP range reads)")
    footprint = models.JSONField(null=True, blank=True, help_text="GeoJSON footprint in planetocentric lon/lat, from the provider")
    quality = models.JSONField(default=dict, blank=True, help_text="Provider quality metadata (valid %, QA links)")
    quality_status = models.CharField(max_length=30, default="NOT_DOCUMENTED")
    source_url = models.URLField(max_length=500, blank=True, help_text="Catalogue record of the product")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"
