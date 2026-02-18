import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.db.session import Base, get_db
from main import app

# Use a separate PostgreSQL test database
TEST_DATABASE_URL = "postgresql+asyncpg://amrutam_user:amrutam_pass@localhost:5432/amrutam_test_db"

engine_test = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool
)

AsyncSessionTest = async_sessionmaker(
    engine_test,
    class_=AsyncSession,
    expire_on_commit=False
)


async def override_get_db():
    async with AsyncSessionTest() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def setup_database():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def client(setup_database):
    async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
    ) as ac:
        yield ac

    # Clear all tables after each test
    async with engine_test.begin() as conn:
        # Delete in correct order to respect foreign keys
        await conn.execute(text("TRUNCATE TABLE prescriptions CASCADE"))
        await conn.execute(text("TRUNCATE TABLE payments CASCADE"))
        await conn.execute(text("TRUNCATE TABLE consultations CASCADE"))
        await conn.execute(text("TRUNCATE TABLE availability_slots CASCADE"))
        await conn.execute(text("TRUNCATE TABLE doctors CASCADE"))
        await conn.execute(text("TRUNCATE TABLE user_profiles CASCADE"))
        await conn.execute(text("TRUNCATE TABLE refresh_tokens CASCADE"))
        await conn.execute(text("TRUNCATE TABLE audit_logs CASCADE"))
        await conn.execute(text("TRUNCATE TABLE users CASCADE"))


@pytest.fixture(scope="function")
async def registered_user(client):
    response = await client.post("/api/v1/auth/register", json={
        "email": "testuser@example.com",
        "password": "Test@1234",
        "first_name": "Test",
        "last_name": "User",
        "role": "patient"
    })
    return response.json()


@pytest.fixture(scope="function")
async def auth_headers(client, registered_user):
    response = await client.post("/api/v1/auth/login", json={
        "email": "testuser@example.com",
        "password": "Test@1234"
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}