"""Use OpenAI to generate a cover letter for a job."""

from openai import OpenAI
from openai import RateLimitError

from ..config import AppConfig
from .prompts import COVER_LETTER_SYSTEM, COVER_LETTER_USER

_MAX_RESUME_CHARS = 8_000
_MAX_JD_CHARS = 12_000


def generate_cover_letter(
    config: AppConfig,
    resume_text: str,
    job_description: str,
    company: str,
    role: str,
    name: str,
) -> str:
    """Return a tailored cover letter using OpenAI."""
    client = OpenAI(api_key=config.env.openai_api_key)

    resume_text = resume_text[:_MAX_RESUME_CHARS]
    job_description = job_description[:_MAX_JD_CHARS]

    messages = [
        {"role": "system", "content": COVER_LETTER_SYSTEM},
        {
            "role": "user",
            "content": COVER_LETTER_USER.format(
                name=name,
                resume_text=resume_text,
                company=company,
                role=role,
                job_description=job_description,
            ),
        },
    ]

    for model in [config.ai.tailor_model, config.ai.model]:
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=config.ai.max_tokens_cover_letter,
                messages=messages,
            )
            return response.choices[0].message.content.strip()
        except RateLimitError:
            if model == config.ai.model:
                raise
            print(f"  [warn] Rate limit on {model}, retrying with {config.ai.model}...")
