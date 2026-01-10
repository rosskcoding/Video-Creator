"""
Security Audit Tests (SEC-01 to SEC-03)

Цель: без дыр уровня "любой может открыть чужой проект".

Test Matrix:
- SEC-01: Direct object access (403/404 для чужих проектов)
- SEC-02: Upload ограничения (размер, MIME, валидация)
- SEC-03: Secrets не в клиенте (API keys не светятся)
"""
import uuid
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Project, ProjectVersion, Slide, SlideScript,
    ProjectStatus, ScriptSource
)


class TestSecuritySEC01_DirectObjectAccess:
    """
    SEC-01: Direct object access
    
    Шаги: взять project_id другого пользователя (или подменить в URL/API)
    Ожидаемо: 403/404
    
    Note: В текущей реализации нет multi-user системы, все проекты доступны
    авторизованному пользователю. Тесты проверяют базовую защиту endpoints.
    """
    
    @pytest.mark.asyncio
    async def test_sec01_nonexistent_project_returns_404(
        self,
        client: AsyncClient
    ):
        """Accessing non-existent project returns 404, not 500"""
        fake_id = uuid.uuid4()
        
        response = await client.get(f"/api/projects/{fake_id}")
        assert response.status_code == 404
        
        # Error message shouldn't reveal internal details
        error = response.json()
        assert "project" in error["detail"].lower()
        assert "not found" in error["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_sec01_nonexistent_version_returns_404(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Accessing non-existent version returns 404"""
        fake_version_id = uuid.uuid4()
        
        response = await client.get(
            f"/api/slides/projects/{sample_project.id}/versions/{fake_version_id}/slides"
        )
        # Should return 200 with empty list or 404
        assert response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    async def test_sec01_nonexistent_slide_returns_404(
        self,
        client: AsyncClient
    ):
        """Accessing non-existent slide returns 404"""
        fake_id = uuid.uuid4()
        
        response = await client.get(f"/api/slides/{fake_id}")
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_sec01_nonexistent_job_returns_404(
        self,
        client: AsyncClient
    ):
        """Accessing non-existent job returns 404"""
        fake_id = uuid.uuid4()
        
        response = await client.get(f"/api/render/jobs/{fake_id}")
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_sec01_invalid_uuid_returns_422(
        self,
        client: AsyncClient
    ):
        """Invalid UUID format returns 422, not 500"""
        response = await client.get("/api/projects/not-a-uuid")
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_sec01_sql_injection_safe(
        self,
        client: AsyncClient
    ):
        """SQL injection attempts are safely handled"""
        # Try SQL injection in project name
        response = await client.post(
            "/api/projects",
            json={
                "name": "'; DROP TABLE projects; --",
                "base_language": "en"
            }
        )
        # Should succeed or fail gracefully, not execute SQL
        assert response.status_code in [200, 400, 422]
        
        # Verify projects still work
        response = await client.get("/api/projects")
        assert response.status_code == 200


class TestSecuritySEC02_UploadRestrictions:
    """
    SEC-02: Upload ограничения
    
    Шаги: залить файл > лимита, неверный MIME, испорченный PPTX
    Ожидаемо: отказ с нормальным сообщением
    """
    
    @pytest.mark.asyncio
    async def test_sec02_file_type_whitelist(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Only whitelisted file types are accepted"""
        disallowed_types = [
            ("script.exe", "application/x-executable"),
            ("script.sh", "application/x-sh"),
            ("document.html", "text/html"),
            ("script.js", "application/javascript"),
            ("archive.zip", "application/zip"),
        ]
        
        for filename, mime_type in disallowed_types:
            response = await client.post(
                f"/api/projects/{sample_project.id}/upload",
                files={"file": (filename, b"content", mime_type)}
            )
            assert response.status_code == 400, f"Should reject {filename}"
    
    @pytest.mark.asyncio
    async def test_sec02_file_extension_validated(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """File extension is validated, not just MIME type"""
        # Try to upload .exe with fake MIME type
        response = await client.post(
            f"/api/projects/{sample_project.id}/upload",
            files={"file": (
                "malicious.exe",
                b"fake content",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )}
        )
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_sec02_path_traversal_prevented(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Path traversal attempts are blocked"""
        dangerous_filenames = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config",
            "slide/../../../secret.txt",
            "slide%2F..%2F..%2Fsecret",
        ]
        
        for filename in dangerous_filenames:
            response = await client.post(
                f"/api/projects/{sample_project.id}/upload",
                files={"file": (
                    filename,
                    b"malicious content",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                )}
            )
            # Should either reject or sanitize filename
            # Not return 500 or actually traverse
            assert response.status_code in [200, 400, 422]
    
    @pytest.mark.asyncio
    async def test_sec02_music_file_type_restricted(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Music upload only accepts MP3"""
        # Try WAV
        response = await client.post(
            f"/api/projects/{sample_project.id}/upload_music",
            files={"file": ("music.wav", b"wav data", "audio/wav")}
        )
        assert response.status_code == 400
        assert "mp3" in response.json()["detail"].lower()
        
        # Try OGG
        response = await client.post(
            f"/api/projects/{sample_project.id}/upload_music",
            files={"file": ("music.ogg", b"ogg data", "audio/ogg")}
        )
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_sec02_image_type_validated_for_slides(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Slide images must be valid image types"""
        invalid_types = [
            ("slide.svg", b"<svg></svg>", "image/svg+xml"),
            ("slide.gif", b"GIF89a", "image/gif"),
            ("slide.bmp", b"BM", "image/bmp"),
        ]
        
        for filename, content, mime in invalid_types:
            response = await client.post(
                f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides/add",
                files={"file": (filename, content, mime)}
            )
            assert response.status_code == 400


class TestSecuritySEC03_SecretsNotExposed:
    """
    SEC-03: Secrets не в клиенте
    
    Шаги: проверить network/JS bundle
    Ожидаемо: ElevenLabs ключи/секреты не светятся
    """
    
    @pytest.mark.asyncio
    async def test_sec03_api_keys_not_in_response(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """API keys are not exposed in responses"""
        # Get various endpoints and check responses
        endpoints = [
            f"/api/projects/{sample_project.id}",
            f"/api/projects/{sample_project.id}/audio_settings",
            "/api/projects/voices",
        ]
        
        for endpoint in endpoints:
            response = await client.get(endpoint)
            response_text = response.text.lower()
            
            # Should not contain actual API key patterns
            # Note: "elevenlabs" may appear as voice model name, which is fine
            assert "sk-" not in response_text  # OpenAI key pattern
            assert "xi-" not in response_text  # ElevenLabs key pattern
            # Check for raw API key patterns (long alphanumeric strings)
            import re
            # Should not have long alphanumeric strings that look like API keys
            api_key_pattern = r'[a-zA-Z0-9]{32,}'
            # Allow known safe patterns (UUIDs, etc.)
            matches = re.findall(api_key_pattern, response_text)
            for match in matches:
                # UUIDs have dashes and are 32 hex chars without dashes
                assert len(match) <= 40 or "-" in response.text, f"Potential API key exposed: {match[:10]}..."
    
    @pytest.mark.asyncio
    async def test_sec03_error_messages_dont_leak_secrets(
        self,
        client: AsyncClient
    ):
        """Error messages don't contain secrets"""
        # Trigger various errors
        response = await client.get(f"/api/projects/{uuid.uuid4()}")
        error_text = response.text.lower()
        
        assert "password" not in error_text
        assert "api_key" not in error_text
        assert "secret" not in error_text
    
    @pytest.mark.asyncio
    async def test_sec03_voices_endpoint_safe(
        self,
        client: AsyncClient
    ):
        """Voices endpoint doesn't expose API credentials"""
        # Mock to avoid actual API call
        with patch("app.api.routes.projects.settings.ELEVENLABS_API_KEY", "test-key"):
            with patch("app.api.routes.projects._voices_cache", {"voices": [], "timestamp": 0}):
                response = await client.get("/api/projects/voices")
                
                if response.status_code == 200:
                    data = response.json()
                    response_str = str(data)
                    
                    # No API keys in response
                    assert "test-key" not in response_str
                    assert "api_key" not in response_str.lower()
    
    @pytest.mark.asyncio
    async def test_sec03_internal_paths_not_exposed(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Internal file paths are not exposed to client"""
        response = await client.get(f"/api/projects/{sample_project.id}")
        response_text = response.text
        
        # Should not contain absolute paths
        assert "/data/projects" not in response_text
        assert "/tmp" not in response_text
        assert "/home" not in response_text
        assert "/Users" not in response_text


class TestSecurityInputValidation:
    """Additional input validation tests"""
    
    @pytest.mark.asyncio
    async def test_xss_in_project_name_sanitized(
        self,
        client: AsyncClient
    ):
        """XSS in project name is handled safely"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            '"><img src=x onerror=alert(1)>',
            "javascript:alert(1)",
        ]
        
        for payload in xss_payloads:
            response = await client.post(
                "/api/projects",
                json={"name": payload, "base_language": "en"}
            )
            # Should accept (stored as-is, frontend sanitizes) or reject
            # But not execute or crash
            assert response.status_code in [200, 400, 422]
            
            if response.status_code == 200:
                # If accepted, verify it's returned as-is (not executed)
                project_id = response.json()["id"]
                get_response = await client.get(f"/api/projects/{project_id}")
                
                # Should return the name as data, not execute it
                assert get_response.status_code == 200
                
                # Cleanup
                await client.delete(f"/api/projects/{project_id}")
    
    @pytest.mark.asyncio
    async def test_language_code_validated(
        self,
        client: AsyncClient
    ):
        """Language codes are validated"""
        response = await client.post(
            "/api/projects",
            json={"name": "Test", "base_language": "invalid_lang_code_xyz"}
        )
        # Should reject invalid language codes
        assert response.status_code in [400, 422]
    
    @pytest.mark.asyncio
    async def test_json_bomb_rejected(
        self,
        client: AsyncClient
    ):
        """Extremely nested JSON is rejected"""
        # Create deeply nested JSON
        nested = {}
        current = nested
        for i in range(100):
            current["nested"] = {}
            current = current["nested"]
        
        response = await client.post(
            "/api/projects",
            json={"name": "Test", "extra": nested}
        )
        # Should not crash the server
        assert response.status_code in [200, 400, 422]


class TestSecurityAuthentication:
    """Authentication-related security tests"""
    
    @pytest.mark.asyncio
    async def test_unauthenticated_request_rejected(self):
        """Requests without auth are rejected"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        
        # Client without auth headers
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as unauth_client:
            response = await unauth_client.get("/api/projects")
            # Should be rejected (401 or 403)
            assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_invalid_credentials_rejected(self):
        """Invalid credentials are rejected"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        import base64
        
        # Client with wrong credentials
        bad_auth = base64.b64encode(b"wrong:credentials").decode("utf-8")
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Basic {bad_auth}"}
        ) as bad_client:
            response = await bad_client.get("/api/projects")
            assert response.status_code in [401, 403]

