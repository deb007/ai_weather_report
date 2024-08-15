from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel, EmailStr
from typing import List
import requests
import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To
from datetime import datetime
import pytz

# Load environment variables
load_dotenv()

# API configurations
OWM_API_KEY = os.getenv("OWM_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

app = FastAPI()


class WeatherPreferences(BaseModel):
    temperature: bool = True
    humidity: bool = False
    wind_speed: bool = False
    cloudiness: bool = False


class Location(BaseModel):
    city: str
    country: str


class WeatherRequest(BaseModel):
    locations: List[Location]
    preferences: WeatherPreferences
    receiver_emails: List[EmailStr]
    timezone: str = "Asia/Kolkata"  # Default to IST


def get_weather_data(city, country):
    base_url = "http://api.openweathermap.org/data/2.5/"

    # Current Weather API
    current_response = requests.get(
        f"{base_url}weather?q={city},{country}&appid={OWM_API_KEY}&units=metric"
    )
    current_data = current_response.json()

    # 5 Day / 3 Hour Forecast API
    forecast_response = requests.get(
        f"{base_url}forecast?q={city},{country}&appid={OWM_API_KEY}&units=metric"
    )
    forecast_data = forecast_response.json()

    # Air Pollution API
    lat, lon = current_data["coord"]["lat"], current_data["coord"]["lon"]
    pollution_response = requests.get(
        f"{base_url}air_pollution?lat={lat}&lon={lon}&appid={OWM_API_KEY}"
    )
    pollution_data = pollution_response.json()

    return current_data, forecast_data, pollution_data


def celsius_to_fahrenheit(celsius):
    return (celsius * 9 / 5) + 32


def get_expected_max_min(forecast_data):
    today = datetime.now().date()
    today_forecasts = [
        f
        for f in forecast_data["list"]
        if datetime.fromtimestamp(f["dt"]).date() == today
    ]

    if not today_forecasts:
        return None, None

    max_temp = max(f["main"]["temp_max"] for f in today_forecasts)
    min_temp = min(f["main"]["temp_min"] for f in today_forecasts)
    return max_temp, min_temp


def get_weather_description(weather_id):
    if weather_id < 300:
        return "Thunderstorm"
    elif weather_id < 500:
        return "Drizzle"
    elif weather_id < 600:
        return "Rain"
    elif weather_id < 700:
        return "Snow"
    elif weather_id < 800:
        return "Atmosphere"
    elif weather_id == 800:
        return "Clear"
    else:
        return "Clouds"


def summarize_weather(
    location, current_data, forecast_data, pollution_data, preferences, timezone
):
    tz = pytz.timezone(timezone)
    current_time = (
        datetime.fromtimestamp(current_data["dt"])
        .replace(tzinfo=pytz.UTC)
        .astimezone(tz)
    )
    expected_max, expected_min = get_expected_max_min(forecast_data)

    summary = f"Weather report for {location.city}, {location.country}:\n\n"
    summary += (
        f"Report generated at: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
    )

    # Current weather
    weather_id = current_data["weather"][0]["id"]
    weather_description = get_weather_description(weather_id)
    summary += f"Current weather: {weather_description}\n"

    if preferences.temperature:
        temp = current_data["main"]["temp"]
        feels_like = current_data["main"]["feels_like"]
        summary += (
            f"Current temperature: {temp:.1f}°C ({celsius_to_fahrenheit(temp):.1f}°F)\n"
        )
        summary += f"Feels like: {feels_like:.1f}°C ({celsius_to_fahrenheit(feels_like):.1f}°F)\n"
        if expected_max is not None and expected_min is not None:
            summary += f"Today's expected temperature range: {expected_min:.1f}°C to {expected_max:.1f}°C "
            summary += f"({celsius_to_fahrenheit(expected_min):.1f}°F to {celsius_to_fahrenheit(expected_max):.1f}°F)\n"
    if preferences.humidity:
        summary += f"Humidity: {current_data['main']['humidity']}%\n"
    if preferences.wind_speed:
        wind_speed = current_data["wind"]["speed"]
        wind_deg = current_data["wind"].get("deg", "N/A")
        summary += f"Wind speed: {wind_speed} m/s\n"
        summary += f"Wind direction: {wind_deg}°\n"
    if preferences.cloudiness:
        summary += f"Cloudiness: {current_data['clouds']['all']}%\n"

    # Pressure
    pressure = current_data["main"]["pressure"]
    summary += f"Atmospheric Pressure: {pressure} hPa\n"

    # Visibility
    visibility = current_data.get("visibility", "N/A")
    if visibility != "N/A":
        visibility_km = visibility / 1000
        summary += f"Visibility: {visibility_km:.1f} km\n"

    # Sunrise and sunset
    sunrise = (
        datetime.fromtimestamp(current_data["sys"]["sunrise"])
        .replace(tzinfo=pytz.UTC)
        .astimezone(tz)
    )
    sunset = (
        datetime.fromtimestamp(current_data["sys"]["sunset"])
        .replace(tzinfo=pytz.UTC)
        .astimezone(tz)
    )
    summary += f"Sunrise: {sunrise.strftime('%H:%M %Z')}\n"
    summary += f"Sunset: {sunset.strftime('%H:%M %Z')}\n"

    # Day length
    day_length = sunset - sunrise
    summary += f"Day length: {day_length}\n"

    # Pollution data
    aqi = pollution_data["list"][0]["main"]["aqi"]
    aqi_labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
    summary += f"Air Quality Index: {aqi_labels[aqi]}\n\n"

    # 5-day forecast
    summary += "5-day forecast:\n"
    for forecast in forecast_data["list"][::8]:  # Every 24 hours
        date = (
            datetime.fromtimestamp(forecast["dt"])
            .replace(tzinfo=pytz.UTC)
            .astimezone(tz)
        )
        temp = forecast["main"]["temp"]
        description = forecast["weather"][0]["description"]
        pop = forecast.get("pop", 0) * 100  # Probability of precipitation
        summary += f"{date.strftime('%Y-%m-%d')}: {temp:.1f}°C ({celsius_to_fahrenheit(temp):.1f}°F), {description.capitalize()}, {pop:.0f}% chance of precipitation\n"

    return summary


def generate_ai_summary(weather_summary):
    import json
    import random

    with open("readers.json", "r") as file:
        data = json.load(file)

    # Get the list of weather readers
    weather_readers = data["weather_readers"]
    selected_reader = random.choice(weather_readers)
    name = selected_reader["name"]
    affiliation = selected_reader["affiliation"]
    country = selected_reader["country"]
    usp = selected_reader["usp"]

    # Azure OpenAI configuration
    client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-01",
    )
    prompt = (
        f"Summarize this weather report in a friendly, conversational tone as if by {name},"
        f" a renowned weather presenter from {affiliation} in {country}. "
        f"{name} is known for {usp}."
        f"Use emoticons as much as possible: {weather_summary} "
    )

    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant who is an expert in summarizing weather reports.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )
    res = (
        f"AI-generated summary:\nPersonality used today: {name} from {affiliation} in {country}\n"
        f"{usp}.\n\n"
        f"{response.choices[0].message.content}"
    )

    return res


def send_email(receiver_emails, subject, body):
    print("Email body:")
    print(body)
    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=[To(email) for email in receiver_emails],
        subject=subject,
        plain_text_content=body,
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email: {e}")


def process_weather_request(weather_request: WeatherRequest):
    full_report = ""
    for location in weather_request.locations:
        current_data, forecast_data, pollution_data = get_weather_data(
            location.city, location.country
        )
        weather_summary = summarize_weather(
            location,
            current_data,
            forecast_data,
            pollution_data,
            weather_request.preferences,
            weather_request.timezone,
        )
        ai_summary = generate_ai_summary(weather_summary)
        full_report += (
            f"{ai_summary}\n\n{'='*50}\n\nAPI Information:\n{weather_summary}\n\n"
        )

    subject = f"Weather Report - {datetime.now(pytz.timezone(weather_request.timezone)).strftime('%Y-%m-%d')}"
    send_email(weather_request.receiver_emails, subject, full_report)


@app.post("/weather_report")
async def create_weather_report(
    weather_request: WeatherRequest, background_tasks: BackgroundTasks
):
    background_tasks.add_task(process_weather_request, weather_request)
    return {
        "message": "Weather report generation started. You will receive an email soon."
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
