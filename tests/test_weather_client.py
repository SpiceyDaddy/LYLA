import json
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import patch

from src.weather_client import (
    AmbiguousWeatherLocation,
    OpenMeteoClient,
    WeatherServiceError,
)


class FakeResponse:
    def __init__(self, payload, url):
        self.payload = json.dumps(payload).encode("utf-8")
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def geturl(self):
        return self.url

    def read(self, _limit):
        return self.payload


class OpenMeteoClientTests(unittest.TestCase):
    def test_returns_attributed_current_conditions_and_daily_forecast(self):
        geocoding = {
            "results": [
                {
                    "name": "Jackson",
                    "admin1": "Tennessee",
                    "country": "United States",
                    "latitude": 35.6145,
                    "longitude": -88.8139,
                }
            ]
        }
        forecast = {
            "timezone": "America/Chicago",
            "current": {
                "time": "2026-10-24T12:00",
                "temperature_2m": 71.0,
                "apparent_temperature": 70.0,
                "relative_humidity_2m": 50,
                "precipitation": 0.0,
                "weather_code": 2,
                "wind_speed_10m": 4.2,
            },
            "daily": {
                "time": ["2026-10-24"],
                "weather_code": [3],
                "temperature_2m_max": [75.0],
                "temperature_2m_min": [52.0],
                "precipitation_probability_max": [20],
                "precipitation_sum": [0.1],
            },
        }
        responses = [
            FakeResponse(
                geocoding,
                "https://geocoding-api.open-meteo.com/v1/search",
            ),
            FakeResponse(
                forecast,
                "https://api.open-meteo.com/v1/forecast",
            ),
        ]
        with patch("src.weather_client.build_opener") as build_opener:
            build_opener.return_value.open.side_effect = responses
            result = OpenMeteoClient().get_forecast("Jackson, Tennessee")

        self.assertEqual(result["location"], "Jackson, Tennessee, United States")
        self.assertEqual(result["current"]["temperature"], 71.0)
        self.assertEqual(result["current"]["condition"], "Partly cloudy")
        self.assertEqual(result["daily"][0]["condition"], "Overcast")
        self.assertEqual(result["units"]["temperature"], "°F")
        self.assertIn("not a guarantee", result["caveat"])
        self.assertEqual(result["sources"][1]["name"], "Open-Meteo forecast")

        requests = build_opener.return_value.open.call_args_list
        geocoding_request = requests[0].args[0]
        geocoding_query = parse_qs(urlsplit(geocoding_request.full_url).query)
        self.assertEqual(geocoding_query["name"], ["Jackson, Tennessee"])
        forecast_request = requests[1].args[0]
        forecast_query = parse_qs(urlsplit(forecast_request.full_url).query)
        self.assertEqual(forecast_query["temperature_unit"], ["fahrenheit"])
        self.assertEqual(forecast_query["forecast_days"], ["7"])

    def test_ambiguous_location_requires_a_more_specific_place(self):
        response = FakeResponse(
            {
                "results": [
                    {
                        "name": "Jackson",
                        "admin1": "Tennessee",
                        "country": "United States",
                        "latitude": 35.6,
                        "longitude": -88.8,
                    },
                    {
                        "name": "Jackson",
                        "admin1": "Mississippi",
                        "country": "United States",
                        "latitude": 32.3,
                        "longitude": -90.2,
                    },
                ]
            },
            "https://geocoding-api.open-meteo.com/v1/search",
        )
        with patch("src.weather_client.build_opener") as build_opener:
            build_opener.return_value.open.return_value = response
            with self.assertRaises(AmbiguousWeatherLocation) as error:
                OpenMeteoClient().get_forecast("Jackson")
        self.assertEqual(len(error.exception.candidates), 2)
        self.assertIn("Tennessee", error.exception.candidates[0])

    def test_missing_place_is_reported_without_forecast_request(self):
        response = FakeResponse(
            {"results": []},
            "https://geocoding-api.open-meteo.com/v1/search",
        )
        with patch("src.weather_client.build_opener") as build_opener:
            build_opener.return_value.open.return_value = response
            with self.assertRaisesRegex(ValueError, "No matching place"):
                OpenMeteoClient().get_forecast("No Such City")
        build_opener.return_value.open.assert_called_once()

    def test_invalid_place_does_not_make_a_network_request(self):
        with patch("src.weather_client.build_opener") as build_opener:
            with self.assertRaisesRegex(ValueError, "2 to 120 characters"):
                OpenMeteoClient().get_forecast("x")
        build_opener.assert_not_called()

    def test_upstream_connection_error_is_reported(self):
        with patch(
            "src.weather_client.build_opener"
        ) as build_opener:
            build_opener.return_value.open.side_effect = URLError("offline")
            with self.assertRaises(WeatherServiceError):
                OpenMeteoClient._get_json(
                    "https://api.open-meteo.com/v1/forecast",
                    "api.open-meteo.com",
                )

    def test_rejects_unexpected_redirect_host(self):
        response = FakeResponse(
            {},
            "https://example.com/redirect",
        )
        with patch("src.weather_client.build_opener") as build_opener:
            build_opener.return_value.open.return_value = response
            with self.assertRaisesRegex(WeatherServiceError, "unexpected host"):
                OpenMeteoClient._get_json(
                    "https://api.open-meteo.com/v1/forecast",
                    "api.open-meteo.com",
                )


if __name__ == "__main__":
    unittest.main()
