import os

import requests
from dotenv import load_dotenv

from tools.base import BaseTool


class WeatherTool(BaseTool):
    name = "weathertool"
    description = '''
    Fetches current weather data for a given location using the Visual Crossing Weather API.
    Reads the API key from the .env file as WEATHER_API_KEY.
    Returns temperature, humidity, wind speed, and weather conditions for the specified location.
    '''
    input_schema = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City name, coordinates (lat,lon), or postal code for which to fetch weather."
            }
        },
        "required": ["location"]
    }

    def execute(self, **kwargs) -> str:
        load_dotenv()
        api_key = os.getenv("WEATHER_API_KEY")
        if not api_key:
            return "Error: WEATHER_API_KEY not found in .env file."

        location = kwargs.get("location")
        if not location:
            return "Error: 'location' parameter is required."

        url = (
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
            f"{requests.utils.quote(location)}"
            f"?unitGroup=metric&key={api_key}&include=current"
        )

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            return f"Error fetching weather data: {e}"

        current = data.get("currentConditions")
        if not current:
            return "Error: Could not retrieve current weather conditions for the specified location."

        temperature = current.get("temp")
        humidity = current.get("humidity")
        wind_speed = current.get("windspeed")
        conditions = current.get("conditions")

        result = (
            f"Weather for '{location}':\n"
            f"- Temperature: {temperature}°C\n"
            f"- Humidity: {humidity}%\n"
            f"- Wind Speed: {wind_speed} km/h\n"
            f"- Conditions: {conditions}"
        )
        return result