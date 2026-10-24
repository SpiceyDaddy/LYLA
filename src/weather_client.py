from datetime import datetime, timezone
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


GEOCODING_API = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
GEOCODING_DOCS = "https://open-meteo.com/en/docs/geocoding-api"
FORECAST_DOCS = "https://open-meteo.com/en/docs"
REQUEST_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 512_000

CURRENT_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
)
DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
)

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherServiceError(RuntimeError):
    """Raised when the upstream geocoding or forecast service is unavailable."""


class AmbiguousWeatherLocation(ValueError):
    def __init__(self, candidates: list[str]):
        super().__init__("More than one place matched. Add a state or country.")
        self.candidates = candidates


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, _request, _response, _code, _message, _headers, _url):
        return None


class OpenMeteoClient:
    """Fetch attributed current conditions and a seven-day forecast."""

    def get_forecast(self, location: str) -> dict:
        if not isinstance(location, str):
            raise ValueError("Enter a place name.")
        location = location.strip()
        if not 2 <= len(location) <= 120:
            raise ValueError("Place names must be from 2 to 120 characters.")
        if any(ord(character) < 32 for character in location):
            raise ValueError("Place names cannot contain control characters.")

        geocoding_params = {
            "name": location,
            "count": 5,
            "language": "en",
            "format": "json",
        }
        geocoding_url = f"{GEOCODING_API}?{urlencode(geocoding_params)}"
        geocoding = self._get_json(geocoding_url, "geocoding-api.open-meteo.com")
        results = geocoding.get("results")
        if results is None or results == []:
            raise ValueError("No matching place was found. Try a city and region.")
        if not isinstance(results, list):
            raise WeatherServiceError("The location service returned an invalid result.")

        valid_results = [
            result
            for result in results
            if isinstance(result, dict)
            and isinstance(result.get("name"), str)
            and isinstance(result.get("latitude"), (int, float))
            and isinstance(result.get("longitude"), (int, float))
        ]
        if not valid_results:
            raise WeatherServiceError(
                "The location service returned results without coordinates."
            )
        if len(valid_results) != 1:
            raise AmbiguousWeatherLocation(
                [self._location_label(result) for result in valid_results]
            )
        place = valid_results[0]

        forecast_params = {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": ",".join(CURRENT_FIELDS),
            "daily": ",".join(DAILY_FIELDS),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "auto",
            "forecast_days": 7,
        }
        forecast_url = f"{FORECAST_API}?{urlencode(forecast_params)}"
        forecast = self._get_json(forecast_url, "api.open-meteo.com")
        return self._format_result(place, forecast)

    @staticmethod
    def _location_label(place: dict) -> str:
        parts = [
            place.get("name"),
            place.get("admin1"),
            place.get("country"),
        ]
        return ", ".join(
            part for part in parts if isinstance(part, str) and part.strip()
        )

    @staticmethod
    def _get_json(url: str, expected_host: str) -> dict:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "LYLA-AI-local-weather/1.0",
            },
        )
        try:
            opener = build_opener(_NoRedirectHandler())
            with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                response_url = urlsplit(response.geturl())
                if (
                    response_url.scheme != "https"
                    or response_url.hostname != expected_host
                ):
                    raise WeatherServiceError(
                        "The weather provider redirected to an unexpected host."
                    )
                raw_data = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise WeatherServiceError(
                "Could not reach Open-Meteo. Check the internet connection and try again."
            ) from exc
        if len(raw_data) > MAX_RESPONSE_BYTES:
            raise WeatherServiceError("The weather provider response was too large.")
        try:
            data = json.loads(raw_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WeatherServiceError(
                "The weather provider returned invalid JSON."
            ) from exc
        if not isinstance(data, dict):
            raise WeatherServiceError("The weather provider returned an invalid response.")
        return data

    @classmethod
    def _format_result(cls, place: dict, forecast: dict) -> dict:
        current = forecast.get("current")
        daily = forecast.get("daily")
        if not isinstance(current, dict) or not isinstance(daily, dict):
            raise WeatherServiceError("The forecast response is missing weather data.")
        days = daily.get("time")
        if not isinstance(days, list):
            raise WeatherServiceError("The forecast response has no daily dates.")

        daily_result = []
        for index, day in enumerate(days):
            code = cls._value_at(daily, "weather_code", index)
            daily_result.append(
                {
                    "date": day,
                    "condition": cls.weather_description(code),
                    "temperature_max": cls._value_at(
                        daily, "temperature_2m_max", index
                    ),
                    "temperature_min": cls._value_at(
                        daily, "temperature_2m_min", index
                    ),
                    "precipitation_probability_max": cls._value_at(
                        daily, "precipitation_probability_max", index
                    ),
                    "precipitation_sum": cls._value_at(
                        daily, "precipitation_sum", index
                    ),
                }
            )

        current_code = current.get("weather_code")
        return {
            "location": cls._location_label(place),
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "timezone": forecast.get("timezone"),
            "current": {
                "time": current.get("time"),
                "condition": cls.weather_description(current_code),
                "temperature": current.get("temperature_2m"),
                "feels_like": current.get("apparent_temperature"),
                "relative_humidity": current.get("relative_humidity_2m"),
                "precipitation": current.get("precipitation"),
                "wind_speed": current.get("wind_speed_10m"),
            },
            "daily": daily_result,
            "units": {
                "temperature": "°F",
                "wind_speed": "mph",
                "precipitation": "in",
                "relative_humidity": "%",
                "precipitation_probability": "%",
            },
            "sources": [
                {"name": "Open-Meteo geocoding", "url": GEOCODING_DOCS},
                {"name": "Open-Meteo forecast", "url": FORECAST_DOCS},
            ],
            "caveat": (
                "Forecast output is model guidance, not a guarantee or an "
                "official weather warning."
            ),
        }

    @staticmethod
    def _value_at(data: dict, key: str, index: int):
        values = data.get(key)
        return values[index] if isinstance(values, list) and index < len(values) else None

    @staticmethod
    def weather_description(code) -> str:
        if isinstance(code, int):
            return WEATHER_CODES.get(code, f"Weather code {code}")
        return "Condition unavailable"
