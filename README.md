# SafeOps-LogMiner

A microservices-based DevSecOps platform for detecting security anomalies in CI/CD pipelines using Isolation Forest machine learning.

## 🏗️ Architecture

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

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for local development)
- Python 3.9+ (for local development)

### Start Infrastructure

```bash
# Start all services (MongoDB, TimescaleDB, RabbitMQ)
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f
```

### Service Endpoints

| Service | URL | Credentials |
|---------|-----|-------------|
| MongoDB | `mongodb://localhost:27017` | admin / safeops123 |
| TimescaleDB | `postgresql://localhost:5432/safeops_metrics` | safeops / safeops123 |
| RabbitMQ Management | `http://localhost:15672` | safeops / safeops123 |

## 📁 Project Structure

```
SafeOps5/
├── docker-compose.yml          # Infrastructure orchestration
├── .env                        # Environment variables
├── init-scripts/
│   ├── mongo/                  # MongoDB initialization
│   └── postgres/               # TimescaleDB initialization
├── services/
│   ├── log-collector/          # Webhook ingestion (Node.js)
│   ├── log-parser/             # Drain parsing (Python)
│   ├── anomaly-detector/       # ML inference (Python)
│   └── dashboard/              # React frontend
└── data-factory/               # Synthetic data generator
```

## 📊 Features

- **Real-time Log Ingestion** - Webhooks from GitHub Actions / GitLab CI
- **Drain Algorithm Parsing** - Structured log templates extraction
- **Isolation Forest Detection** - Unsupervised anomaly detection
- **Visual Dashboard** - Real-time build health monitoring

## 🔧 Development

See individual service READMEs for development instructions.

## 📄 License

Academic Project - EMSI
