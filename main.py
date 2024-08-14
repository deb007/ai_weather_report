from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import List
import requests
import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from datetime import datetime, timedelta

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
    receiver_email: str


def get_weather_data(city, country):
    base_url = "http://api.openweathermap.org/data/2.5/"

    # Current weather
    current_response = requests.get(
        f"{base_url}weather?q={city},{country}&appid={OWM_API_KEY}&units=metric"
    )
    current_data = current_response.json()

    # 5-day forecast
    forecast_response = requests.get(
        f"{base_url}forecast?q={city},{country}&appid={OWM_API_KEY}&units=metric"
    )
    forecast_data = forecast_response.json()

    # Pollution data
    lat, lon = current_data["coord"]["lat"], current_data["coord"]["lon"]
    pollution_response = requests.get(
        f"{base_url}air_pollution?lat={lat}&lon={lon}&appid={OWM_API_KEY}"
    )
    pollution_data = pollution_response.json()

    return current_data, forecast_data, pollution_data


def celsius_to_fahrenheit(celsius):
    return (celsius * 9 / 5) + 32


def summarize_weather(
    location, current_data, forecast_data, pollution_data, preferences
):
    summary = f"Weather report for {location.city}, {location.country}:\n\n"

    # Current weather
    if preferences.temperature:
        temp = current_data["main"]["temp"]
        summary += (
            f"Current temperature: {temp:.1f}°C ({celsius_to_fahrenheit(temp):.1f}°F)\n"
        )
    if preferences.humidity:
        summary += f"Humidity: {current_data['main']['humidity']}%\n"
    if preferences.wind_speed:
        summary += f"Wind speed: {current_data['wind']['speed']} m/s\n"
    if preferences.cloudiness:
        summary += f"Cloudiness: {current_data['clouds']['all']}%\n"

    # Sunrise and sunset
    sunrise = datetime.fromtimestamp(current_data["sys"]["sunrise"])
    sunset = datetime.fromtimestamp(current_data["sys"]["sunset"])
    summary += f"Sunrise: {sunrise.strftime('%H:%M')}\n"
    summary += f"Sunset: {sunset.strftime('%H:%M')}\n"

    # Pollution data
    aqi = pollution_data["list"][0]["main"]["aqi"]
    aqi_labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
    summary += f"Air Quality Index: {aqi_labels[aqi]}\n\n"

    # 5-day forecast
    summary += "5-day forecast:\n"
    for forecast in forecast_data["list"][::8]:  # Every 24 hours
        date = datetime.fromtimestamp(forecast["dt"])
        temp = forecast["main"]["temp"]
        description = forecast["weather"][0]["description"]
        summary += f"{date.strftime('%Y-%m-%d')}: {temp:.1f}°C ({celsius_to_fahrenheit(temp):.1f}°F), {description}\n"

    return summary


def generate_ai_summary(weather_summary):
    # Azure OpenAI configuration
    client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-01",
    )

    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        messages=[
            {
                "role": "system",
                "content": "YYou are a helpful assistant who is an expert in summarizing weather reports.",
            },
            {
                "role": "user",
                "content": f"Summarize this weather report in a friendly, conversational tone. Use emoticons as much as possible: {weather_summary}",
            },
        ],
    )

    return response.choices[0].message.content


def send_email(receiver_email, subject, body):
    print("Email body:")
    print(body)
    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=receiver_email,
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
        )
        ai_summary = generate_ai_summary(weather_summary)
        full_report += (
            f"{weather_summary}\n\nAI-generated summary:\n{ai_summary}\n\n{'='*50}\n\n"
        )

    subject = f"Weather Report - {datetime.now().strftime('%Y-%m-%d')}"
    send_email(weather_request.receiver_email, subject, full_report)


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
