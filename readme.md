# Weather Report FastAPI App

## Description

This Weather Report FastAPI App is a powerful and flexible tool for generating personalized weather reports. It fetches data from OpenWeatherMap API, including current weather, 5-day forecasts, and air quality information for multiple locations. The app then generates a comprehensive report, enhanced with an AI-generated summary using Azure OpenAI, and sends it via email using SendGrid.

## Features

- FastAPI backend for efficient API requests
- Support for multiple locations in a single request
- Personalized weather preferences
- 5-day weather forecast
- Current weather conditions
- Air quality information
- Sunrise and sunset times
- AI-generated weather summaries using Azure OpenAI
- Email delivery of reports using SendGrid
- Background task processing to handle long-running operations

## Prerequisites

Before you begin, ensure you have met the following requirements:

- Python 3.7+
- OpenWeatherMap API key
- SendGrid API key
- Azure OpenAI API key and endpoint

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/weather-report-fastapi-app.git
   cd weather-report-fastapi-app
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory by renaming `sample.env` and filling in the values:
   ```
   OWM_API_KEY=your_openweathermap_api_key
   SENDGRID_API_KEY=your_sendgrid_api_key
   SENDER_EMAIL=your_sender_email@example.com
   AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
   AZURE_OPENAI_API_KEY=your_azure_openai_api_key
   AZURE_OPENAI_DEPLOYMENT=your_azure_openai_deployment
   ```

   Replace the placeholder values with your actual API keys and configuration.

## Usage

1. Start the FastAPI server:
   ```
   python main.py
   ```

2. The API will be available at `http://localhost:8000`.

3. To request a weather report, send a POST request to `http://localhost:8000/weather_report` with a JSON payload like this:

   ```json
   {
     "locations": [
       {"city": "London", "country": "UK"},
       {"city": "New York", "country": "US"}
     ],
     "preferences": {
       "temperature": true,
       "humidity": true,
       "wind_speed": false,
       "cloudiness": true
     },
     "receiver_emails": ["user@example.com"],
     "timezone": "Asia/Kolkata"
   }
   ```

4. The app will process your request in the background and send an email with the weather report to the specified email address.

## API Endpoints

### POST /weather_report

Generate a weather report for specified locations and preferences.

#### Request Body

- `locations`: List of locations, each with `city` and `country`
- `preferences`: Weather data preferences (temperature, humidity, wind_speed, cloudiness)
- `receiver_email`: Email address to receive the weather report

#### Response

- `message`: Confirmation that the weather report generation has started

## Configuration

You can modify the following aspects of the app:

- Email content: Modify the `summarize_weather` function to change the report format
- API endpoints: Add new endpoints in the FastAPI app to extend functionality

## Contributing

Contributions to the Weather Report FastAPI App are welcome. Please follow these steps:

1. Fork the repository
2. Create a new branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Commit your changes (`git commit -m 'Add some amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
