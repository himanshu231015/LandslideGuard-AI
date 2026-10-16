
import json
import ssl
import certifi

from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# ---------------------------------------------------------
# Configuration and helpers
# ---------------------------------------------------------

def utc_now():
    """Return the current timezone-aware timestamp."""
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url, timeout=12):
    """
    Fetch JSON over HTTPS with certificate verification enabled.
    Uses certifi's trusted CA bundle.
    """
    request = Request(
        url,
        headers={
            "User-Agent": "LandslideGuard-AI/1.0",
            "Accept": "application/json",
        },
    )

    ssl_context = ssl.create_default_context(
        cafile=certifi.where()
    )

    with urlopen(
        request,
        timeout=timeout,
        context=ssl_context,
    ) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def extract_records(payload):
    """Extract records without assuming every feed uses the same schema."""
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("data", "results", "records", "alerts"):
        value = payload.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            return [value]

    return []


def record_matches_location(record):
    """Check for relevant location text without inferring safety."""
    searchable = json.dumps(
        record,
        ensure_ascii=False,
    ).lower()

    return any(
        term in searchable
        for term in (
            "kedarnath",
            "rudraprayag",
            "uttarakhand",
        )
    )


# ---------------------------------------------------------
# Main real-time data bundle
# ---------------------------------------------------------

def get_realtime_bundle(
    place="Kedarnath, Uttarakhand, India"
):
    retrieved_at = utc_now()

    result = {
        "requested_place": place,
        "retrieved_at_utc": retrieved_at,
        "coordinates": None,
        "weather": None,
        "weather_error": None,

        "alerts": {
            "status": "unknown",
            "sources": [],
            "alerts": [],
            "note": (
                "Missing or unavailable alert data does not mean "
                "the location is safe."
            ),
        },

        "roads": {
            "road_status": "unknown",
            "message": (
                "No verified machine-readable live road-status feed "
                "is configured. Check official sources before travelling."
            ),
            "retrieved_at_utc": retrieved_at,

            "official_sources": [
                {
                    "name": "Uttarakhand PWD",
                    "url": "https://pwd.uk.gov.in/documents/page/91/",
                },
                {
                    "name": "Uttarakhand State Disaster Management Authority",
                    "url": "https://usdma.uk.gov.in/",
                },
            ],

            "emergency_contacts": [
                {
                    "name": "State Emergency Operations Centre",
                    "phone": "1070",
                },
                {
                    "name": "Emergency Response Support System",
                    "phone": "112",
                },
            ],
        },

        "map": None,
    }

    # -----------------------------------------------------
    # 1. Resolve location with Open-Meteo geocoding
    # -----------------------------------------------------

    try:
        geocode_query = urlencode({
            "name": place,
            "count": 1,
            "language": "en",
            "format": "json",
        })

        geocode_url = (
            "https://geocoding-api.open-meteo.com/v1/search?"
            + geocode_query
        )

        geocode_data = fetch_json(geocode_url)
        locations = geocode_data.get("results") or []

        if not locations:
            result["weather_error"] = (
                "Location could not be resolved by Open-Meteo."
            )
            result["alerts"]["status"] = "not_checked_location_unresolved"
            result["alerts"]["note"] = (
                "Location resolution failed; alert feeds were not checked. "
                "This does not mean the location is safe."
            )
            return result

        location = locations[0]
        latitude = float(location["latitude"])
        longitude = float(location["longitude"])

        result["coordinates"] = {
            "latitude": latitude,
            "longitude": longitude,
            "resolved_name": location.get("name"),
            "admin1": location.get("admin1"),
            "country": location.get("country"),
        }

        result["map"] = {
            "provider": "OpenStreetMap",
            "map_url": (
                "https://www.openstreetmap.org/"
                f"?mlat={latitude}&mlon={longitude}"
                f"#map=14/{latitude}/{longitude}"
            ),
            "coordinates": {
                "latitude": latitude,
                "longitude": longitude,
            },
        }

    except Exception as exc:
        result["weather_error"] = (
            f"Geocoding request failed: "
            f"{type(exc).__name__}: {exc}"
        )
        result["alerts"]["status"] = "not_checked_location_unresolved"
        result["alerts"]["note"] = (
            "Location resolution failed; alert feeds were not checked. "
            "This does not mean the location is safe."
        )
        return result

    # -----------------------------------------------------
    # 2. Retrieve weather from Open-Meteo
    # -----------------------------------------------------

    try:
        weather_query = urlencode({
            "latitude": latitude,
            "longitude": longitude,

            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "apparent_temperature,"
                "precipitation,"
                "rain,"
                "showers,"
                "snowfall,"
                "weather_code,"
                "wind_speed_10m,"
                "wind_direction_10m,"
                "wind_gusts_10m"
            ),

            "hourly": (
                "precipitation_probability,"
                "precipitation"
            ),

            "forecast_days": 2,
            "timezone": "auto",
        })

        weather_url = (
            "https://api.open-meteo.com/v1/forecast?"
            + weather_query
        )

        weather_data = fetch_json(weather_url)

        result["weather"] = {
            "provider": "Open-Meteo",
            "source_url": weather_url,
            "retrieved_at_utc": utc_now(),
            "data_type": (
                "Forecast model output; not guaranteed station observations"
            ),
            "timezone": weather_data.get("timezone"),
            "current": weather_data.get("current"),
            "current_units": weather_data.get("current_units"),
            "hourly": weather_data.get("hourly"),
            "hourly_units": weather_data.get("hourly_units"),
        }

    except Exception as exc:
        result["weather_error"] = (
            f"Weather request failed: "
            f"{type(exc).__name__}: {exc}"
        )

    # -----------------------------------------------------
    # 3. Attempt official IMD warning feeds
    # -----------------------------------------------------

    imd_sources = [
        (
            "IMD District Warning",
            "https://api.imd.gov.in/api/v1/districtwarning",
        ),
        (
            "IMD District Nowcast",
            "https://api.imd.gov.in/api/v1/districtnowcast",
        ),
    ]

    successful_feeds = 0

    for source_name, source_url in imd_sources:
        source_result = {
            "name": source_name,
            "source_url": source_url,
            "status": "error",
            "retrieved_at_utc": utc_now(),
        }

        try:
            payload = fetch_json(source_url)
            source_result["status"] = "ok"
            successful_feeds += 1

            records = extract_records(payload)

            for record in records:
                if not isinstance(record, dict):
                    continue

                if not record_matches_location(record):
                    continue

                result["alerts"]["alerts"].append({
                    "area": (
                        record.get("district")
                        or record.get("area")
                        or record.get("name")
                        or "Area not identified in record"
                    ),

                    "message": (
                        record.get("message")
                        or record.get("warning")
                        or record.get("description")
                        or "See the original official record."
                    ),

                    "issued_at": (
                        record.get("issued_at")
                        or record.get("issue_time")
                        or record.get("date")
                    ),

                    "source": source_name,
                    "source_url": source_url,

                    # Preserve the source record for inspection.
                    "official_record": record,
                })

        except Exception as exc:
            source_result["error"] = (
                f"{type(exc).__name__}: {exc}"
            )

        result["alerts"]["sources"].append(source_result)

    # -----------------------------------------------------
    # 4. Summarize feed availability
    # -----------------------------------------------------

    if successful_feeds == len(imd_sources):
        result["alerts"]["status"] = (
            "records_found"
            if result["alerts"]["alerts"]
            else "no_matching_records_returned"
        )

    elif successful_feeds > 0:
        result["alerts"]["status"] = "partial"

    else:
        result["alerts"]["status"] = "unavailable"

    result["alerts"]["note"] = (
        "Feed results are not a safety clearance. Confirm current warnings "
        "with official authorities; source availability and record schemas "
        "may vary. An empty result does not mean there is no danger."
    )

    # -----------------------------------------------------
    # 5. Final timestamps and response
    # -----------------------------------------------------

    result["retrieved_at_utc"] = utc_now()
    result["roads"]["retrieved_at_utc"] = (
        result["retrieved_at_utc"]
    )

    return result
