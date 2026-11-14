from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from services.mars_coordinates import TREK_DECLARED_CRS, LatitudeConvention


class MarsPoint(models.Model):
    """Abstract point with an explicit coordinate convention.

    Longitude is stored east-positive in [-180, 180). The CRS is stored as given by the
    client (normally the CRS declared by the map layer the point was picked on).
    """

    lon_east_deg = models.FloatField(
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)],
        help_text="Longitude, degrees, east-positive, -180..180",
    )
    lat_deg = models.FloatField(
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
        help_text="Latitude, degrees; type given by latitude_convention",
    )
    crs = models.CharField(max_length=200, default=TREK_DECLARED_CRS)
    latitude_convention = models.CharField(
        max_length=40,
        choices=[(c.value, c.value) for c in LatitudeConvention],
        default=LatitudeConvention.AS_DECLARED_BY_SOURCE.value,
    )

    class Meta:
        abstract = True
