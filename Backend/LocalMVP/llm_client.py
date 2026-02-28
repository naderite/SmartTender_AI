import json
from typing import Any

from openai import OpenAI

try:
    from google import genai
except Exception:  # pragma: no cover
    genai = None


class LLMHelper:
    def __init__(
        self,
        openrouter_api_key: str,
        openrouter_model: str,
        gemini_api_key: str,
        gemini_model: str,
    ):
        self.openrouter_model = openrouter_model
        self.gemini_model = gemini_model

        self.openrouter_client = (
            OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_api_key)
            if openrouter_api_key
            else None
        )
        self.gemini_client = (
            genai.Client(api_key=gemini_api_key) if gemini_api_key and genai is not None else None
        )

    def _parse_json(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)

    def _generate_openrouter(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        if not self.openrouter_client:
            return None
        response = self.openrouter_client.chat.completions.create(
            model=self.openrouter_model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        return self._parse_json(content)

    def _generate_gemini(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        if not self.gemini_client:
            return None
        prompt = f"{system_prompt}\n\nUser input:\n{user_prompt}"
        response = self.gemini_client.models.generate_content(
            model=self.gemini_model,
            contents=prompt,
        )
        return self._parse_json(response.text or "")

    def _generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        for generator in (self._generate_gemini, self._generate_openrouter):
            try:
                payload = generator(system_prompt, user_prompt)
                if payload:
                    return payload
            except Exception:
                continue
        return None

    def enrich_tender(self, raw_text: str) -> dict[str, Any] | None:
        system_prompt = """
You extract structured tender requirements.
Return valid JSON only.

Schema:
{
  "title": "string",
  "required_skills": ["string"],
  "preferred_skills": ["string"],
  "languages": ["string"],
  "experience_level": 0,
  "education_level": "string",
  "summary": "string"
}
"""
        user_prompt = f"Extract the tender requirements from this text:\n\n{raw_text[:12000]}"
        return self._generate_json(system_prompt, user_prompt)

    def enrich_cv(self, raw_text: str) -> dict[str, Any] | None:
        system_prompt = """
You extract structured CV information.
Return valid JSON only.

Schema:
{
  "full_name": "string",
  "email": "string",
  "phone": "string",
  "professional_summary": "string",
  "technical_skills": ["string"],
  "soft_skills": ["string"],
  "languages": ["string"],
  "education_level": "string",
  "experience_years": 0
}
"""
        user_prompt = f"Extract the candidate profile from this CV text:\n\n{raw_text[:12000]}"
        return self._generate_json(system_prompt, user_prompt)

    def explain_match(
        self,
        tender_json: dict[str, Any],
        cv_json: dict[str, Any],
        lexical_score: float,
        semantic_score: float,
        final_score: float,
    ) -> list[str] | None:
        system_prompt = """
You produce concise recruiter-style matching notes.
Return valid JSON only.

Schema:
{
  "justification": ["short sentence", "short sentence", "short sentence"]
}
"""
        user_prompt = json.dumps(
            {
                "tender": tender_json,
                "cv": cv_json,
                "lexical_score": lexical_score,
                "semantic_score": semantic_score,
                "final_score": final_score,
            },
            ensure_ascii=False,
        )
        payload = self._generate_json(system_prompt, user_prompt)
        if payload and isinstance(payload.get("justification"), list):
            return [str(item) for item in payload["justification"][:4]]
        return None
