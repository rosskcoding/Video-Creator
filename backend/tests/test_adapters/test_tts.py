"""
Tests for TTSAdapter
"""
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.tts import TTSAdapter


class TestTTSAdapter:
    """Tests for TTSAdapter class"""
    
    @pytest.fixture
    def adapter(self):
        """Create adapter with test API key"""
        return TTSAdapter(
            api_key="test-key",
            voice_id="test-voice-id",
            model="eleven_flash_v2_5"
        )
    
    def test_compute_audio_hash(self):
        """Test audio hash computation"""
        hash1 = TTSAdapter.compute_audio_hash(
            text="Hello world",
            voice_id="voice123",
            lang="en",
            model="eleven_flash_v2_5"
        )
        
        hash2 = TTSAdapter.compute_audio_hash(
            text="Hello world",
            voice_id="voice123",
            lang="en",
            model="eleven_flash_v2_5"
        )
        
        # Same inputs should give same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length
    
    def test_compute_audio_hash_different_inputs(self):
        """Test that different inputs produce different hashes"""
        hash1 = TTSAdapter.compute_audio_hash(
            text="Hello world",
            voice_id="voice123",
            lang="en"
        )
        
        hash2 = TTSAdapter.compute_audio_hash(
            text="Different text",
            voice_id="voice123",
            lang="en"
        )
        
        hash3 = TTSAdapter.compute_audio_hash(
            text="Hello world",
            voice_id="voice456",  # Different voice
            lang="en"
        )
        
        hash4 = TTSAdapter.compute_audio_hash(
            text="Hello world",
            voice_id="voice123",
            lang="ru"  # Different language
        )
        
        assert hash1 != hash2
        assert hash1 != hash3
        assert hash1 != hash4
    
    def test_check_cache_no_file(self, adapter, tmp_path):
        """Test cache check when file doesn't exist"""
        result = adapter.check_cache(
            audio_hash="nonexistent_hash",
            audio_dir=tmp_path
        )
        
        assert result is None
    
    def test_check_cache_file_exists(self, adapter, tmp_path):
        """Test cache check when file exists"""
        # Create a cached file
        audio_hash = "test_hash_12345"
        cached_file = tmp_path / f"slide_001_{audio_hash}.mp3"
        cached_file.write_bytes(b"audio data")
        
        result = adapter.check_cache(
            audio_hash=audio_hash,
            audio_dir=tmp_path
        )
        
        assert result == cached_file
    
    @pytest.mark.asyncio
    async def test_generate_speech(self, adapter, tmp_path):
        """Test speech generation"""
        output_path = tmp_path / "output.mp3"
        
        # Mock ElevenLabs client
        mock_response = [b"audio", b"data", b"chunks"]
        adapter.client.text_to_speech.convert = MagicMock(return_value=mock_response)
        
        # Mock ffprobe for duration
        with patch.object(
            adapter,
            '_get_audio_duration',
            new_callable=AsyncMock,
            return_value=5.5
        ):
            duration = await adapter.generate_speech(
                text="Hello world",
                output_path=output_path,
            )
            
            assert duration == 5.5
            assert output_path.exists()
            
            # Verify file contains the audio data
            content = output_path.read_bytes()
            assert content == b"audiodatachunks"
    
    @pytest.mark.asyncio
    async def test_generate_speech_creates_directory(self, adapter, tmp_path):
        """Test that generate_speech creates output directory if needed"""
        output_path = tmp_path / "nested" / "dir" / "output.mp3"
        
        mock_response = [b"test"]
        adapter.client.text_to_speech.convert = MagicMock(return_value=mock_response)
        
        with patch.object(
            adapter,
            '_get_audio_duration',
            new_callable=AsyncMock,
            return_value=1.0
        ):
            await adapter.generate_speech(
                text="Test",
                output_path=output_path,
            )
            
            assert output_path.parent.exists()
    
    @pytest.mark.asyncio
    async def test_generate_speech_with_custom_params(self, adapter, tmp_path):
        """Test speech generation with custom voice and model"""
        output_path = tmp_path / "output.mp3"
        
        mock_response = [b"audio"]
        mock_convert = MagicMock(return_value=mock_response)
        adapter.client.text_to_speech.convert = mock_convert
        
        with patch.object(
            adapter,
            '_get_audio_duration',
            new_callable=AsyncMock,
            return_value=1.0
        ):
            await adapter.generate_speech(
                text="Hello",
                output_path=output_path,
                voice_id="custom_voice",
                model="custom_model",
            )
            
            # Verify correct params passed to client
            mock_convert.assert_called_once()
            call_kwargs = mock_convert.call_args.kwargs
            
            assert call_kwargs["text"] == "Hello"
            assert call_kwargs["voice_id"] == "custom_voice"
            assert call_kwargs["model_id"] == "custom_model"


class TestTTSAdapterAudioDuration:
    """Tests for audio duration calculation"""
    
    @pytest.fixture
    def adapter(self):
        return TTSAdapter(api_key="test-key")
    
    @pytest.mark.asyncio
    async def test_get_audio_duration(self, adapter, tmp_path):
        """Test audio duration extraction via ffprobe"""
        audio_path = tmp_path / "test.mp3"
        audio_path.write_bytes(b"fake audio")
        
        # Mock asyncio.create_subprocess_exec
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(
                b'{"format": {"duration": "10.5"}}',
                b''
            )
        )
        mock_process.returncode = 0
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            duration = await adapter._get_audio_duration(audio_path)
            
            assert duration == 10.5


class TestTTSAdapterCaching:
    """Tests for TTS caching functionality"""
    
    @pytest.fixture
    def adapter(self):
        return TTSAdapter(api_key="test-key")
    
    def test_cache_key_includes_all_params(self):
        """Test that cache key includes all relevant parameters"""
        # Different params version should produce different hash
        hash1 = TTSAdapter.compute_audio_hash(
            text="Hello",
            voice_id="voice",
            lang="en",
            model="model",
            params_version="v1"
        )
        
        hash2 = TTSAdapter.compute_audio_hash(
            text="Hello",
            voice_id="voice",
            lang="en",
            model="model",
            params_version="v2"
        )
        
        assert hash1 != hash2
    
    def test_check_cache_multiple_extensions(self, adapter, tmp_path):
        """Test cache check finds files with different extensions"""
        audio_hash = "abc123hash"
        
        # Create cached wav file
        cached_wav = tmp_path / f"slide_{audio_hash}.wav"
        cached_wav.write_bytes(b"wav data")
        
        result = adapter.check_cache(audio_hash, tmp_path)
        assert result == cached_wav
        
        # Clean and create mp3 instead
        cached_wav.unlink()
        cached_mp3 = tmp_path / f"audio_{audio_hash}.mp3"
        cached_mp3.write_bytes(b"mp3 data")
        
        result = adapter.check_cache(audio_hash, tmp_path)
        assert result == cached_mp3

