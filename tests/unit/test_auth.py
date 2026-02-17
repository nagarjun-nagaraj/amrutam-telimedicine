import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestRegistration:

    async def test_register_success(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "newuser@example.com",
            "password": "Test@1234",
            "first_name": "New",
            "last_name": "User",
            "role": "patient"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "patient"
        assert data["is_active"] is True
        assert "id" in data
        assert "hashed_password" not in data

    async def test_register_duplicate_email(self, client: AsyncClient):
        payload = {
            "email": "duplicate@example.com",
            "password": "Test@1234",
            "first_name": "Test",
            "last_name": "User",
            "role": "patient"
        }
        await client.post("/api/v1/auth/register", json=payload)
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409
        assert "already registered" in response.json()["detail"]

    async def test_register_weak_password(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "weak@example.com",
            "password": "password",
            "first_name": "Weak",
            "last_name": "Pass",
            "role": "patient"
        })
        assert response.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "Test@1234",
            "first_name": "Bad",
            "last_name": "Email",
            "role": "patient"
        })
        assert response.status_code == 422


class TestLogin:

    async def test_login_success(self, client: AsyncClient, registered_user):
        response = await client.post("/api/v1/auth/login", json={
            "email": "testuser@example.com",
            "password": "Test@1234"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["role"] == "patient"

    async def test_login_wrong_password(self, client: AsyncClient, registered_user):
        response = await client.post("/api/v1/auth/login", json={
            "email": "testuser@example.com",
            "password": "WrongPass@123"
        })
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "Test@1234"
        })
        assert response.status_code == 401

    async def test_get_me(self, client: AsyncClient, auth_headers):
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "testuser@example.com"

    async def test_get_me_no_token(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in [401, 403]

    async def test_refresh_token(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "email": "refreshuser@example.com",
            "password": "Test@1234",
            "first_name": "Refresh",
            "last_name": "User",
            "role": "patient"
        })
        login_response = await client.post("/api/v1/auth/login", json={
            "email": "refreshuser@example.com",
            "password": "Test@1234"
        })
        refresh_token = login_response.json()["refresh_token"]
        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert response.status_code == 200
        assert "access_token" in response.json()


class TestSecurity:

    async def test_password_not_in_response(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "secure@example.com",
            "password": "Test@1234",
            "first_name": "Secure",
            "last_name": "User",
            "role": "patient"
        })
        assert "password" not in response.json()
        assert "hashed_password" not in response.json()

    async def test_invalid_token_rejected(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalidtoken123"}
        )
        assert response.status_code in [401, 403]

    async def test_health_check(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"