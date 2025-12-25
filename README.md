# SafeOps-LogMiner

A microservices-based DevSecOps platform for detecting security anomalies in CI/CD pipelines using Isolation Forest machine learning.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  LogCollector   │────▶│   RabbitMQ      │────▶│   LogParser     │
│  (Node.js)      │     │   (Broker)      │     │   (Python)      │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Dashboard     │◀────│  TimescaleDB    │◀────│ AnomalyDetector │
│   (React)       │     │  (Metrics)      │     │   (Python/ML)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

# Demo

<video controls width="900">

  <source src="SafeOps_Demo.mp4" type="video/mp4">
</video>

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for local development)
- Python 3.9+ (for local development)
- GitHub Personal Access Token (for fetching workflow logs)

### Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your GitHub token
GITHUB_TOKEN=your_github_pat_token
```

### Start Services

```bash
# Start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f
```

### Service Endpoints

| Service              | URL                                           | Credentials          |
| -------------------- | --------------------------------------------- | -------------------- |
| Dashboard            | `http://localhost`                            | -                    |
| Anomaly Detector API | `http://localhost:3002`                       | -                    |
| Log Collector        | `http://localhost:3001`                       | -                    |
| RabbitMQ Management  | `http://localhost:15672`                      | safeops / safeops123 |
| MongoDB              | `mongodb://localhost:27017`                   | admin / safeops123   |
| TimescaleDB          | `postgresql://localhost:5432/safeops_metrics` | safeops / safeops123 |

## Project Structure

```
SafeOps5/
├── docker-compose.yml          # Infrastructure orchestration
├── .env                        # Environment variables
├── init-scripts/
│   ├── mongo/                  # MongoDB initialization
│   └── postgres/               # TimescaleDB initialization
├── services/
│   ├── log-collector/          # Webhook ingestion (Node.js/Express)
│   ├── log-parser/             # Drain parsing & feature extraction (Python)
│   └── anomaly-detector/       # Isolation Forest ML inference (Python/Flask)
├── dashboard/                  # React frontend (Vite + TypeScript)
├── data-factory/               # Synthetic data generator
└── scripts/                    # Testing and demo utilities
```

## Features

- **Real-time Log Ingestion** - Webhooks from GitHub Actions and GitLab CI
- **Drain Algorithm Parsing** - Structured log template extraction
- **Isolation Forest Detection** - Unsupervised anomaly detection with 12 security features
- **Visual Dashboard** - Real-time build health monitoring with charts
- **Attack Detection** - Cryptomining, data exfiltration, reverse shell patterns

## API Endpoints

### Log Collector (port 3001)

| Endpoint          | Method | Description             |
| ----------------- | ------ | ----------------------- |
| `/webhook`        | POST   | Main webhook endpoint   |
| `/webhook/github` | POST   | GitHub-specific webhook |
| `/health`         | GET    | Health check            |
| `/stats`          | GET    | Service statistics      |

### Anomaly Detector (port 3002)

| Endpoint      | Method | Description             |
| ------------- | ------ | ----------------------- |
| `/predict`    | POST   | Single prediction       |
| `/results`    | GET    | Query detection results |
| `/stats`      | GET    | Aggregated statistics   |
| `/model/info` | GET    | Model configuration     |
| `/health`     | GET    | Health check            |

## GitHub Webhook Setup

1. Go to your repository Settings > Webhooks > Add webhook
2. Set Payload URL to your public endpoint (use ngrok for local testing)
3. Set Content type to `application/json`
4. Select event: **Workflow runs**
5. Save webhook

For local testing with ngrok:

```bash
ngrok http 3001
# Use the generated URL as your webhook endpoint
```

## Development

See individual service READMEs for development instructions.

## License

MIT - EMSI
