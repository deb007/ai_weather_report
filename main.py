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
        f"Always generate in English language ONLY."
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

def generate_html_ui(weather_summary):
    """Generate HTML UI for weather report based on the weather summary."""
    current_weather = weather_summary['current_weather']
    forecast = weather_summary['forecast']
    
    # Helper function to create forecast card
    def create_forecast_card(day_data):
        return f'''
            <div class="forecast-day">
                <div class="day">{day_data['day']}</div>
                <div class="weather-icon">
                    <img src="path_to_icons/{day_data['icon']}.svg" alt="{day_data['description']}">
                </div>
                <div class="temp">{day_data['temp']}°C</div>
                <div class="description">{day_data['description']}</div>
            </div>
        '''

    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Weather Report - {weather_summary['location']}</title>
        <style>
            :root {{
                --primary-color: #1a73e8;
                --text-color: #202124;
                --secondary-text: #5f6368;
                --background: #ffffff;
                --card-shadow: 0 1px 3px rgba(0,0,0,0.12);
            }}
            
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f0f5ff;
                color: var(--text-color);
            }}
            
            .weather-card {{
                background: var(--background);
                border-radius: 12px;
                padding: 24px;
                max-width: 800px;
                margin: 0 auto;
                box-shadow: var(--card-shadow);
            }}
            
            .location {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }}
            
            .current-weather {{
                display: grid;
                grid-template-columns: auto 1fr;
                gap: 20px;
                margin-bottom: 30px;
            }}
            
            .temperature {{
                font-size: 48px;
                font-weight: 400;
            }}
            
            .weather-details {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 16px;
                margin: 20px 0;
            }}
            
            .detail-item {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .forecast {{
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 16px;
                margin-top: 30px;
                text-align: center;
            }}
            
            .forecast-day {{
                padding: 12px;
                border-radius: 8px;
                background: #f8f9fa;
            }}
            
            .air-quality {{
                color: {current_weather['air_quality_color']};
                font-weight: 500;
            }}
        </style>
    </head>
    <body>
        <div class="weather-card">
            <div class="location">
                <div>
                    <h2>{weather_summary['location']}</h2>
                </div>
                <div>{current_weather['timestamp']}</div>
            </div>
            
            <div class="current-weather">
                <div class="temperature">
                    {current_weather['temperature']}°C
                    <div style="font-size: 16px;">{current_weather['description']}</div>
                </div>
                
                <div class="weather-details">
                    <div class="detail-item">
                        <span>Feels Like</span>
                        <span>{current_weather['feels_like']}°C</span>
                    </div>
                    <div class="detail-item">
                        <span>Humidity</span>
                        <span>{current_weather['humidity']}%</span>
                    </div>
                    <div class="detail-item">
                        <span>Wind</span>
                        <span>{current_weather['wind_speed']} m/s</span>
                    </div>
                    <div class="detail-item">
                        <span>Air Quality</span>
                        <span class="air-quality">{current_weather['air_quality']}</span>
                    </div>
                    <div class="detail-item">
                        <span>Sunrise</span>
                        <span>{current_weather['sunrise']}</span>
                    </div>
                    <div class="detail-item">
                        <span>Sunset</span>
                        <span>{current_weather['sunset']}</span>
                    </div>
                </div>
            </div>
            
            <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 24px 0;">
            <div class="ai-summary" style="padding: 16px; background: #f8f9fa; border-radius: 8px; margin-bottom: 24px; line-height: 1.5;">
                {weather_summary['ai_summary']}
            </div>
            
            <div class="forecast">
                {''.join(create_forecast_card(day) for day in forecast)}
            </div>
        </div>
    </body>
    </html>
    '''
    
    return html

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
        weather_summary_dict = {
            'location': f"{location.city}, {location.country}",
            'current_weather': {
                'temperature': current_data["main"]["temp"],
                'feels_like': current_data["main"]["feels_like"],
                'humidity': current_data["main"]["humidity"],
                'wind_speed': current_data["wind"]["speed"],
                'air_quality': pollution_data["list"][0]["main"]["aqi"],
                'air_quality_color': 'green' if pollution_data["list"][0]["main"]["aqi"] < 3 else 'red',
                'description': current_data["weather"][0]["description"],
                'timestamp': datetime.fromtimestamp(current_data["dt"]).strftime('%Y-%m-%d %H:%M:%S'),
                'sunrise': datetime.fromtimestamp(current_data["sys"]["sunrise"]).strftime('%H:%M'),
                'sunset': datetime.fromtimestamp(current_data["sys"]["sunset"]).strftime('%H:%M'),
            },
            'forecast': [
                {
                    'day': datetime.fromtimestamp(forecast["dt"]).strftime('%Y-%m-%d'),
                    'temp': forecast["main"]["temp"],
                    'icon': forecast["weather"][0]["icon"],
                    'description': forecast["weather"][0]["description"],
                } for forecast in forecast_data["list"][::8]
            ],
            'ai_summary': generate_ai_summary(weather_summary),
        }
        full_report += generate_html_ui(weather_summary_dict)

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
