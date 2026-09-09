You're right. I misunderstood what you meant by **one `.md` file**. You wanted the **entire README as one single Markdown code block**, including Tech Stack, Installation, Configuration, Running, etc., without breaking parts into separate blocks.

The previous answer was still one file, but the nested code fences made it annoying to copy as a single `.md`. That's on me.

Here is the clean approach: **use four backticks around the entire README**, so every internal triple-backtick section remains part of the same Markdown file.

````
# AI Predictive Maintenance

An AI-powered predictive maintenance and machine health monitoring system built with Python and Streamlit.

The application simulates industrial machine sensor data, analyzes machine health in real time, detects degradation and abnormal conditions, provides AI-powered maintenance insights using Google Gemini, and generates downloadable PDF reports.

## Features

- Real-time machine health monitoring
- Simulated industrial sensor data
- Multiple machine operating scenarios
- Machine health and condition analysis
- Historical trend analysis
- AI-powered maintenance insights using Google Gemini
- Rule-based fallback analysis when Gemini is unavailable
- PDF maintenance report generation
- Interactive Streamlit dashboard
- Configurable refresh intervals
- Simulation reset and step-by-step execution
- Error handling and logging
- Automated tests

## Tech Stack

- **Python** - Core programming language
- **Streamlit** - Interactive web dashboard
- **Pandas** - Data processing and analysis
- **Plotly** - Interactive data visualization
- **Google Gemini API** - AI-powered maintenance insights
- **ReportLab** - PDF report generation
- **python-dotenv** - Environment variable management
- **Pytest** - Testing

## Monitored Sensors

| Sensor | Unit | Purpose |
|--------|------|---------|
| Temperature | °C | Detect thermal abnormalities |
| Vibration | mm/s RMS | Identify mechanical instability |
| Pressure | bar | Monitor pressure-related abnormalities |
| Motor Current | A | Detect abnormal motor load |

**Default Machine:** Primary Coolant Pump P-101 (`MACHINE-01`)

## Operating Scenarios

The simulator supports multiple machine conditions:

- **NORMAL** - Normal operating conditions
- **GRADUAL_DEGRADATION** - Slowly deteriorating machine condition
- **RAPID_DEGRADATION** - Accelerated deterioration
- **INTERMITTENT_FAULT** - Occasional abnormal sensor behavior

## System Architecture

```text
                    ┌──────────────────────┐
                    │   Sensor Simulator   │
                    │                      │
                    │ Temperature          │
                    │ Vibration            │
                    │ Pressure             │
                    │ Motor Current        │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Sensor Interface    │
                    │  Validation Layer     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Health Analysis     │
                    │      Engine          │
                    └──────────┬───────────┘
                               │
                    ┌──────────┴───────────┐
                    ▼                      ▼
          ┌─────────────────┐    ┌─────────────────┐
          │ Streamlit       │    │ Gemini AI       │
          │ Dashboard       │    │ Analyzer        │
          └─────────────────┘    └─────────────────┘
                    │                      │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │   PDF Report         │
                    │     Generator        │
                    └──────────────────────┘
```

## Project Structure

```text
ai_predictive_maintenance/
│
├── ai/
│   ├── gemini_client.py
│   └── prompt_builder.py
│
├── dashboard/
│   ├── charts.py
│   ├── components.py
│   └── layout.py
│
├── health_engine/
│   ├── business_metrics.py
│   └── health_engine.py
│
├── models/
│   └── data_models.py
│
├── pdf/
│   └── report_generator.py
│
├── reports/
├── sensor_interface/
├── simulator/
├── tests/
├── utils/
│
├── .env.example
├── .gitignore
├── app.py
├── config.py
└── requirements.txt
```

## Installation

### Prerequisites

Make sure you have the following installed:

- Python 3.9 or higher
- Git
- pip

### Clone the Repository

```bash
git clone https://github.com/Meghansh-sinha/ai_predictive_maintenance.git
cd ai_predictive_maintenance
```

### Create a Virtual Environment

```bash
python -m venv venv
```

### Activate the Virtual Environment

**Windows:**

```bash
venv\Scripts\activate
```

**macOS / Linux:**

```bash
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root based on `.env.example`.

```env
GEMINI_API_KEY=your-gemini-api-key-here
```

The Gemini integration is optional. If no API key is configured, the application can use its rule-based fallback analysis.

> **Important:** Never commit your `.env` file or expose your API key publicly.

## Running the Application

Start the Streamlit application:

```bash
streamlit run app.py
```

The application will normally be available at:

```text
http://localhost:8501
```

Open the URL in your browser to access the dashboard.

## How It Works

### 1. Sensor Simulation

The system generates simulated sensor readings for the machine, including:

- Temperature
- Vibration
- Pressure
- Motor Current

The simulator models normal operating behavior, sensor noise, degradation, and intermittent faults.

### 2. Sensor Validation

Generated readings pass through the sensor interface before being analyzed.

This ensures incoming values are valid and within expected operating ranges.

### 3. Health Analysis

The health engine evaluates validated sensor readings and maintains historical information about the machine.

It identifies changes in machine condition and generates health-related metrics.

### 4. Dashboard

The Streamlit dashboard provides:

- Current machine condition
- Live sensor readings
- Historical trends
- Health metrics
- Machine status
- Scenario controls
- AI-generated insights
- PDF report generation

### 5. AI Analysis

The application can use Google Gemini to interpret the latest machine condition and historical summary.

The AI layer includes:

- Gemini API client
- Prompt builder
- Maintenance insight generation
- Fallback analysis when Gemini is unavailable

### 6. PDF Reports

The system can generate PDF reports containing:

- Machine health information
- Sensor data
- Analysis results
- AI-generated maintenance insights

## Simulation Controls

The dashboard allows the operator to:

- Select a machine scenario
- Enable or disable automatic updates
- Adjust the refresh interval
- Run individual simulation steps
- Reset the simulation
- Generate AI analysis
- Generate PDF reports

## Testing

The project includes automated tests.

Run the test suite using:

```bash
pytest
```

For verbose output:

```bash
pytest -v
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | No | Google Gemini API key for AI-powered analysis |

## Security

- Never commit API keys or secrets.
- Keep `.env` out of version control.
- Use `.env.example` for documenting required environment variables.
- Do not expose production credentials in source code.

## Future Improvements

- Integration with real industrial IoT sensors
- MQTT-based sensor ingestion
- Database-backed historical storage
- Machine learning-based failure prediction
- Remaining Useful Life (RUL) estimation
- Automated maintenance alerts
- Email and WhatsApp notifications
- Multi-machine monitoring
- Cloud deployment
- Role-based access control
- Advanced anomaly detection
- Model performance monitoring

## Use Cases

This system can serve as a prototype for:

- Industrial machine monitoring
- Predictive maintenance research
- Smart manufacturing
- IoT and sensor analytics
- Machine health monitoring
- Maintenance decision support
- AI-assisted industrial operations

## Disclaimer

This project uses simulated sensor data and is intended for demonstration, development, and research purposes.

It should not be used as the sole basis for real-world industrial safety or maintenance decisions.

## License

Add the appropriate license for this project before distributing it publicly.
````
