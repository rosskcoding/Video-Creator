"""
Tests for main application
"""
import pytest
from httpx import AsyncClient


class TestHealthCheck:
    """Tests for health check endpoint"""
    
    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check returns healthy status"""
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert "app" in data


class TestAppConfiguration:
    """Tests for application configuration"""
    
    @pytest.mark.asyncio
    async def test_cors_headers(self, client: AsyncClient):
        """Test CORS headers are present"""
        response = await client.options(
            "/api/projects",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            }
        )
        
        # CORS should allow the origin
        assert "access-control-allow-origin" in response.headers or response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_api_routes_mounted(self, client: AsyncClient):
        """Test that API routes are properly mounted"""
        # Test projects endpoint
        response = await client.get("/api/projects")
        assert response.status_code == 200
        
        # Test 404 for non-existent route
        response = await client.get("/api/nonexistent")
        assert response.status_code in [404, 405]

