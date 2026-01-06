"""
OpenAI Translation Adapter
Handles multilingual translation with glossary support
"""
import hashlib
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

import httpx
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class TranslationError(Exception):
    """Translation-specific error"""
    pass


class TranslationParseError(TranslationError):
    """Failed to parse batch translation output"""
    pass


class TranslateAdapter:
    """Adapter for OpenAI-based translation with glossary"""
    
    # Maximum retries for batch translation before falling back to single
    MAX_BATCH_RETRIES = 2
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_sec: Optional[int] = None,
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.TRANSLATION_MODEL
        self.timeout_sec = timeout_sec or settings.TRANSLATE_HTTP_TIMEOUT_SEC
        
        # Configure client with timeout
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            timeout=httpx.Timeout(self.timeout_sec, connect=10.0),
        )
    
    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        do_not_translate: Optional[List[str]] = None,
        preferred_translations: Optional[List[Dict[str, str]]] = None,
        style: str = "formal",
        extra_rules: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Translate text with glossary support.
        
        Args:
            text: Source text to translate
            source_lang: Source language code (e.g., 'en')
            target_lang: Target language code (e.g., 'ru')
            do_not_translate: Terms to keep in original language
            preferred_translations: [{term, lang, translation}, ...]
            style: Translation style ('formal', 'neutral', 'friendly')
            extra_rules: Additional translation instructions
            
        Returns:
            Tuple of (translated_text, metadata)
        """
        do_not_translate = do_not_translate or []
        preferred_translations = preferred_translations or []
        
        # Filter preferred translations for target language
        lang_translations = [
            pt for pt in preferred_translations 
            if pt.get("lang") == target_lang
        ]
        
        # Build prompt
        system_prompt = self._build_system_prompt(
            source_lang,
            target_lang,
            do_not_translate,
            lang_translations,
            style,
            extra_rules
        )
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.3,  # Lower temperature for consistent translations
        )
        
        translated_text = response.choices[0].message.content.strip()
        
        # Build metadata
        metadata = {
            "model": self.model,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "style": style,
            "timestamp": datetime.utcnow().isoformat(),
            "glossary_terms_count": len(do_not_translate) + len(lang_translations),
            "source_checksum": self._checksum(text),
        }
        
        return translated_text, metadata
    
    async def translate_batch(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        do_not_translate: Optional[List[str]] = None,
        preferred_translations: Optional[List[Dict[str, str]]] = None,
        style: str = "formal",
        extra_rules: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Translate multiple texts with validation and fallback.
        
        For efficiency, tries batch translation first. If parsing fails,
        falls back to individual translations for reliability.
        """
        if not texts:
            return []
        
        # For single text, use regular translate
        if len(texts) == 1:
            result = await self.translate(
                texts[0], source_lang, target_lang,
                do_not_translate, preferred_translations, style, extra_rules
            )
            return [result]
        
        do_not_translate = do_not_translate or []
        preferred_translations = preferred_translations or []
        
        lang_translations = [
            pt for pt in preferred_translations 
            if pt.get("lang") == target_lang
        ]
        
        # Try batch translation with retries
        last_error = None
        for attempt in range(self.MAX_BATCH_RETRIES):
            try:
                translations = await self._batch_translate_attempt(
                    texts, source_lang, target_lang,
                    do_not_translate, lang_translations,
                    style, extra_rules,
                    strict=(attempt > 0)  # Use stricter prompt on retry
                )
                
                # Validate we got all translations
                self._validate_batch_result(translations, len(texts))
                
                # Build results with metadata
                return self._build_batch_results(
                    texts, translations, source_lang, target_lang,
                    style, do_not_translate, lang_translations
                )
                
            except TranslationParseError as e:
                last_error = e
                logger.warning(
                    f"Batch translation parse failed (attempt {attempt + 1}/{self.MAX_BATCH_RETRIES}): {e}"
                )
                continue
        
        # Fallback to individual translations
        logger.warning(
            f"Batch translation failed after {self.MAX_BATCH_RETRIES} attempts, "
            f"falling back to individual translations. Last error: {last_error}"
        )
        return await self._fallback_translate(
            texts, source_lang, target_lang,
            do_not_translate, preferred_translations,
            style, extra_rules
        )
    
    async def _batch_translate_attempt(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        do_not_translate: List[str],
        lang_translations: List[Dict[str, str]],
        style: str,
        extra_rules: Optional[str],
        strict: bool = False,
    ) -> List[str]:
        """Single attempt at batch translation"""
        system_prompt = self._build_batch_system_prompt(
            source_lang, target_lang, do_not_translate,
            lang_translations, style, extra_rules, strict
        )
        
        # Format input as numbered list
        numbered_input = "\n\n".join(
            f"[{i+1}]\n{text}" for i, text in enumerate(texts)
        )
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": numbered_input}
            ],
            temperature=0.2 if strict else 0.3,  # Lower on retry
        )
        
        output = response.choices[0].message.content.strip()
        return self._parse_numbered_output(output, len(texts))
    
    def _validate_batch_result(self, translations: List[str], expected_count: int) -> None:
        """Validate batch translation result"""
        if len(translations) != expected_count:
            raise TranslationParseError(
                f"Expected {expected_count} translations, got {len(translations)}"
            )
        
        # Check for empty translations (warning only for now)
        empty_count = sum(1 for t in translations if not t.strip())
        if empty_count > 0:
            logger.warning(f"Batch translation returned {empty_count} empty results")
            # If ALL are empty, that's an error
            if empty_count == expected_count:
                raise TranslationParseError("All translations are empty")
    
    async def _fallback_translate(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        do_not_translate: Optional[List[str]],
        preferred_translations: Optional[List[Dict[str, str]]],
        style: str,
        extra_rules: Optional[str],
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Fallback: translate texts one by one"""
        results = []
        for text in texts:
            result = await self.translate(
                text, source_lang, target_lang,
                do_not_translate, preferred_translations, style, extra_rules
            )
            results.append(result)
        return results
    
    def _build_batch_results(
        self,
        texts: List[str],
        translations: List[str],
        source_lang: str,
        target_lang: str,
        style: str,
        do_not_translate: List[str],
        lang_translations: List[Dict[str, str]],
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Build result tuples with metadata"""
        base_metadata = {
            "model": self.model,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "style": style,
            "timestamp": datetime.utcnow().isoformat(),
            "glossary_terms_count": len(do_not_translate) + len(lang_translations),
            "batch_size": len(texts),
        }
        
        results = []
        for i, (original, translated) in enumerate(zip(texts, translations)):
            metadata = {
                **base_metadata,
                "batch_index": i,
                "source_checksum": self._checksum(original),
            }
            results.append((translated, metadata))
        
        return results
    
    def _build_system_prompt(
        self,
        source_lang: str,
        target_lang: str,
        do_not_translate: List[str],
        preferred_translations: List[Dict[str, str]],
        style: str,
        extra_rules: Optional[str],
    ) -> str:
        """Build system prompt for translation"""
        
        style_guide = {
            "formal": "Use formal, professional language appropriate for business presentations.",
            "neutral": "Use neutral, clear language.",
            "friendly": "Use friendly, conversational language while maintaining professionalism.",
        }
        
        prompt_parts = [
            f"You are a professional translator from {source_lang} to {target_lang}.",
            f"Style: {style_guide.get(style, style_guide['formal'])}",
            "",
            "IMPORTANT RULES:",
            "1. Preserve ALL numbers, percentages, and numerical values exactly as they appear",
            "2. Preserve ALL ticker symbols, stock codes, and financial abbreviations",
            "3. Preserve ALL acronyms and technical abbreviations (IFRS, ESG, KPI, etc.)",
            "4. Do NOT add, remove, or modify any information - translate only what is given",
            "5. Maintain the same paragraph structure and line breaks",
            "6. Adapt punctuation and formatting to target language conventions where appropriate",
        ]
        
        if do_not_translate:
            prompt_parts.extend([
                "",
                "DO NOT TRANSLATE these terms (keep in original language):",
                ", ".join(do_not_translate)
            ])
        
        if preferred_translations:
            prompt_parts.extend([
                "",
                "USE THESE PREFERRED TRANSLATIONS:"
            ])
            for pt in preferred_translations:
                prompt_parts.append(f"- \"{pt['term']}\" → \"{pt['translation']}\"")
        
        if extra_rules:
            prompt_parts.extend([
                "",
                "ADDITIONAL RULES:",
                extra_rules
            ])
        
        prompt_parts.extend([
            "",
            "Translate the following text. Output ONLY the translation, nothing else."
        ])
        
        return "\n".join(prompt_parts)
    
    def _build_batch_system_prompt(
        self,
        source_lang: str,
        target_lang: str,
        do_not_translate: List[str],
        preferred_translations: List[Dict[str, str]],
        style: str,
        extra_rules: Optional[str],
        strict: bool = False,
    ) -> str:
        """Build system prompt for batch translation"""
        
        base_prompt = self._build_system_prompt(
            source_lang, target_lang, do_not_translate,
            preferred_translations, style, extra_rules
        )
        
        if strict:
            # Stricter prompt for retry attempts
            batch_instructions = """

INPUT FORMAT:
You will receive multiple texts, each prefixed with [N] where N is the number.

OUTPUT FORMAT (STRICT):
You MUST translate each text and output in the EXACT same numbered format:
[1]
<translation 1>

[2]
<translation 2>

[3]
<translation 3>

CRITICAL REQUIREMENTS:
- Output EXACTLY the same number of translations as inputs
- Each translation MUST be preceded by [N] marker on its own line
- Do NOT add any explanations, notes, or extra text
- Do NOT skip any translations
- Do NOT combine multiple translations
- If a text is empty, still output the [N] marker with empty translation"""
        else:
            batch_instructions = """

INPUT FORMAT:
You will receive multiple texts, each prefixed with [N] where N is the number.

OUTPUT FORMAT:
Translate each text and output in the same numbered format:
[1]
<translation 1>

[2]
<translation 2>

etc.

IMPORTANT: Maintain the exact same numbering. Output exactly the same number of translations as inputs."""

        return base_prompt + batch_instructions
    
    def _parse_numbered_output(self, output: str, expected_count: int) -> List[str]:
        """
        Parse numbered translation output with validation.
        
        Returns list of translations, raises TranslationParseError if parsing fails.
        """
        # Split by [N] markers
        pattern = r'\[(\d+)\]\s*'
        parts = re.split(pattern, output)
        
        # parts will be: ['', '1', 'translation1', '2', 'translation2', ...]
        # or if there's text before first marker: ['some text', '1', 'translation1', ...]
        translations = {}
        
        for i in range(1, len(parts) - 1, 2):
            try:
                idx = int(parts[i])
                text = parts[i + 1].strip()
                translations[idx] = text
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse translation at position {i}: {e}")
                continue
        
        # Validate we found any translations
        if not translations:
            raise TranslationParseError(
                f"No numbered translations found in output. "
                f"Output starts with: {output[:200]}..."
            )
        
        # Check for missing numbers
        found_numbers = set(translations.keys())
        expected_numbers = set(range(1, expected_count + 1))
        missing = expected_numbers - found_numbers
        
        if missing:
            raise TranslationParseError(
                f"Missing translation numbers: {sorted(missing)}. "
                f"Expected 1-{expected_count}, got {sorted(found_numbers)}"
            )
        
        # Build result list in order
        result = []
        for i in range(1, expected_count + 1):
            result.append(translations.get(i, ""))
        
        return result
    
    def _checksum(self, text: str) -> str:
        """Compute checksum of text for tracking"""
        return hashlib.md5(text.encode()).hexdigest()[:12]


# Singleton instance
translate_adapter = TranslateAdapter()
