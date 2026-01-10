"""
Tests for TranslateAdapter
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.translate import TranslateAdapter, TranslationParseError


class TestTranslateAdapter:
    """Tests for TranslateAdapter class"""
    
    @pytest.fixture
    def adapter(self):
        """Create adapter with test API key"""
        return TranslateAdapter(api_key="test-key", model="gpt-4o")
    
    @pytest.fixture
    def mock_openai_response(self):
        """Create mock OpenAI response"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Translated text"
        return mock_response
    
    @pytest.mark.asyncio
    async def test_translate_single_text(self, adapter, mock_openai_response):
        """Test single text translation"""
        with patch.object(
            adapter.client.chat.completions,
            'create',
            new_callable=AsyncMock,
            return_value=mock_openai_response
        ) as mock_create:
            translated, metadata = await adapter.translate(
                text="Hello world",
                source_lang="en",
                target_lang="ru"
            )
            
            assert translated == "Translated text"
            assert metadata["source_lang"] == "en"
            assert metadata["target_lang"] == "ru"
            assert metadata["model"] == "gpt-4o"
            assert "timestamp" in metadata
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_translate_with_glossary(self, adapter, mock_openai_response):
        """Test translation with do_not_translate and preferred_translations"""
        with patch.object(
            adapter.client.chat.completions,
            'create',
            new_callable=AsyncMock,
            return_value=mock_openai_response
        ) as mock_create:
            translated, metadata = await adapter.translate(
                text="The KPI shows 10% growth in ESG metrics",
                source_lang="en",
                target_lang="ru",
                do_not_translate=["KPI", "ESG"],
                preferred_translations=[
                    {"term": "growth", "lang": "ru", "translation": "рост"}
                ],
                style="formal"
            )
            
            # Verify glossary terms count in metadata
            assert metadata["glossary_terms_count"] == 3  # 2 do_not_translate + 1 preferred
            
            # Verify prompt includes glossary
            call_args = mock_create.call_args
            system_prompt = call_args.kwargs["messages"][0]["content"]
            assert "KPI" in system_prompt
            assert "ESG" in system_prompt

    @pytest.mark.asyncio
    async def test_translate_preserves_marker_tokens(self, adapter):
        """If input contains ⟦M:uuid⟧, prompt must instruct to preserve and metadata must reflect preservation."""
        token = "⟦M:6f2c9f7a-1234-5678-9abc-def012345678⟧"
        text = f"Hello {token} world"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = f"Привет {token} мир"

        with patch.object(
            adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_create:
            translated, metadata = await adapter.translate(
                text=text,
                source_lang="en",
                target_lang="ru",
            )

            assert token in translated
            assert metadata["has_marker_tokens"] is True
            assert metadata["markers_preserved"] is True
            assert metadata["marker_count"] == 1

            call_args = mock_create.call_args
            system_prompt = call_args.kwargs["messages"][0]["content"]
            assert "PRESERVE MARKER TOKENS" in system_prompt

    @pytest.mark.asyncio
    async def test_translate_detects_missing_marker_tokens(self, adapter):
        """If translation drops tokens, metadata marks markers_preserved=False."""
        token = "⟦M:6f2c9f7a-1234-5678-9abc-def012345678⟧"
        text = f"Hello {token} world"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Привет мир"  # token lost

        with patch.object(
            adapter.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            translated, metadata = await adapter.translate(
                text=text,
                source_lang="en",
                target_lang="ru",
            )

            assert token not in translated
            assert metadata["has_marker_tokens"] is True
            assert metadata["markers_preserved"] is False
    
    @pytest.mark.asyncio
    async def test_translate_batch_single_text(self, adapter, mock_openai_response):
        """Test batch translation with single text (should use regular translate)"""
        with patch.object(
            adapter.client.chat.completions,
            'create',
            new_callable=AsyncMock,
            return_value=mock_openai_response
        ):
            results = await adapter.translate_batch(
                texts=["Hello"],
                source_lang="en",
                target_lang="ru"
            )
            
            assert len(results) == 1
            assert results[0][0] == "Translated text"
    
    @pytest.mark.asyncio
    async def test_translate_batch_multiple_texts(self, adapter):
        """Test batch translation with multiple texts"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "[1]\nПривет\n\n[2]\nМир"
        
        with patch.object(
            adapter.client.chat.completions,
            'create',
            new_callable=AsyncMock,
            return_value=mock_response
        ):
            results = await adapter.translate_batch(
                texts=["Hello", "World"],
                source_lang="en",
                target_lang="ru"
            )
            
            assert len(results) == 2
            assert results[0][0] == "Привет"
            assert results[1][0] == "Мир"
    
    @pytest.mark.asyncio
    async def test_translate_batch_empty_list(self, adapter):
        """Test batch translation with empty list"""
        results = await adapter.translate_batch(
            texts=[],
            source_lang="en",
            target_lang="ru"
        )
        
        assert results == []
    
    def test_build_system_prompt(self, adapter):
        """Test system prompt building"""
        prompt = adapter._build_system_prompt(
            source_lang="en",
            target_lang="ru",
            do_not_translate=["IFRS", "ESG"],
            preferred_translations=[
                {"term": "revenue", "translation": "выручка"}
            ],
            style="formal",
            extra_rules="Use formal business language"
        )
        
        assert "en" in prompt
        assert "ru" in prompt
        assert "IFRS" in prompt
        assert "ESG" in prompt
        assert "revenue" in prompt
        assert "выручка" in prompt
        assert "Use formal business language" in prompt
    
    def test_parse_numbered_output(self, adapter):
        """Test parsing of numbered output"""
        output = "[1]\nFirst translation\n\n[2]\nSecond translation\n\n[3]\nThird"
        
        result = adapter._parse_numbered_output(output, 3)
        
        assert len(result) == 3
        assert result[0] == "First translation"
        assert result[1] == "Second translation"
        assert result[2] == "Third"
    
    def test_parse_numbered_output_missing_numbers(self, adapter):
        """Test parsing when some numbers are missing"""
        output = "[1]\nFirst\n\n[3]\nThird"
        with pytest.raises(TranslationParseError):
            adapter._parse_numbered_output(output, 3)
    
    def test_checksum(self, adapter):
        """Test checksum computation"""
        checksum1 = adapter._checksum("Hello world")
        checksum2 = adapter._checksum("Hello world")
        checksum3 = adapter._checksum("Different text")
        
        assert checksum1 == checksum2
        assert checksum1 != checksum3
        assert len(checksum1) == 12


class TestTranslateAdapterStyles:
    """Tests for translation styles"""
    
    @pytest.fixture
    def adapter(self):
        return TranslateAdapter(api_key="test-key")
    
    def test_formal_style_in_prompt(self, adapter):
        """Test that formal style is included in prompt"""
        prompt = adapter._build_system_prompt(
            source_lang="en",
            target_lang="ru",
            do_not_translate=[],
            preferred_translations=[],
            style="formal",
            extra_rules=None
        )
        
        assert "formal" in prompt.lower() or "professional" in prompt.lower()
    
    def test_friendly_style_in_prompt(self, adapter):
        """Test that friendly style is included in prompt"""
        prompt = adapter._build_system_prompt(
            source_lang="en",
            target_lang="ru",
            do_not_translate=[],
            preferred_translations=[],
            style="friendly",
            extra_rules=None
        )
        
        assert "friendly" in prompt.lower() or "conversational" in prompt.lower()
    
    def test_neutral_style_in_prompt(self, adapter):
        """Test that neutral style is included in prompt"""
        prompt = adapter._build_system_prompt(
            source_lang="en",
            target_lang="ru",
            do_not_translate=[],
            preferred_translations=[],
            style="neutral",
            extra_rules=None
        )
        
        assert "neutral" in prompt.lower()

