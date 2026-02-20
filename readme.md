# Amrutam Telemedicine Backend

Production-grade telemedicine backend built with FastAPI, PostgreSQL, and Redis.

[![CI](https://github.com/nagarjun-nagaraj/amrutam-telimedicine/actions/workflows/ci.yml/badge.svg)](https://github.com/nagarjun-nagaraj/amrutam-telimedicine/actions)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)

## Features

- 🔐 JWT authentication + MFA (TOTP)
- 👥 Role-based access control (Patient/Doctor/Admin)
- 📅 Doctor availability & booking system
- 💊 Prescription management
- 💳 Payment processing (idempotent)
- 📊 Admin analytics dashboard
- 🔍 Audit logging for compliance
- 📈 Prometheus metrics + Grafana dashboards

---

## Quick Start (Docker) - Recommended

### Prerequisites
- Docker Desktop installed and running

### Setup
```bash
# 1. Clone repository
git clone https://github.com/nagarjun-nagaraj/amrutam-telimedicine.git
cd amrutam-telemedicine

# 2. Start all services
docker compose up -d

# 3. Run database migrations
docker compose exec api alembic upgrade head

# 4. Verify
curl http://localhost:8000/health
```

### Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| API Docs | http://localhost:8000/docs | - |
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3000 | admin / admin123 |

### Stop Services
```bash
docker compose down
```

---

## Local Development Setup

### Prerequisites
- Python 3.13
- PostgreSQL 16
- Redis 7

### Installation
```bash
# 1. Clone repository
git clone https://github.com/nagarjun-nagaraj/amrutam-telimedicine.git
cd amrutam-telemedicine

# 2. Create virtual environment
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install greenlet

# 4. Create PostgreSQL database
psql postgres -c "CREATE USER amrutam_user WITH PASSWORD 'amrutam_pass';"
psql postgres -c "CREATE DATABASE amrutam_db OWNER amrutam_user;"
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE amrutam_db TO amrutam_user;"

# 5. Create test database (for running tests)
psql postgres -c "CREATE DATABASE amrutam_test_db OWNER amrutam_user;"

# 6. Copy environment file
cp .env.example .env
# Edit .env if needed

# 7. Run database migrations
alembic upgrade head

# 8. Start server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs to see API documentation.

---

## Running Tests
```bash
# Activate virtual environment
source venv/bin/activate

# Run tests with coverage
pytest tests/unit/test_auth.py -v --cov=app

# Expected output: 13 passed, 65% coverage
```

---

## Project Structure
```
amrutam-telemedicine/
├── app/
│   ├── api/v1/endpoints/    # API routes
│   ├── core/                # Config, security
│   ├── models/              # Database models
│   ├── schemas/             # Request/response schemas
│   ├── services/            # Business logic
│   └── middleware/          # Logging, security headers
├── tests/                   # Test suite
├── docs/                    # Architecture docs
├── alembic/                 # Database migrations
├── docker-compose.yml       # Multi-service setup
└── main.py                  # Application entry point
```

---

## Environment Variables

Key variables (see `.env.example` for full list):
```env
DATABASE_URL=postgresql+asyncpg://amrutam_user:amrutam_pass@localhost:5432/amrutam_db
SECRET_KEY=your-secret-key-min-32-characters
REDIS_URL=redis://localhost:6379/0
```

---

## API Usage Example
```bash
# Register user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "patient@example.com",
    "password": "Test@1234",
    "first_name": "John",
    "last_name": "Doe",
    "role": "patient"
  }'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "patient@example.com",
    "password": "Test@1234"
  }'

# Use token from login response for authenticated requests
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.115 |
| Language | Python 3.13 |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Auth | JWT + TOTP (MFA) |
| Testing | pytest |
| CI/CD | GitHub Actions |
| Monitoring | Prometheus + Grafana |

---

## Troubleshooting

**Port already in use:**
```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9
```

**Database connection error:**
```bash
# Verify PostgreSQL is running
psql postgres -c "SELECT 1"

# Check credentials in .env match database
```

**Docker issues:**
```bash
# Reset everything
docker compose down -v
docker compose up --build -d
docker compose exec api alembic upgrade head
```