"""Use OpenAI to tailor a resume to a job description."""

from openai import OpenAI
from openai import RateLimitError

from ..config import AppConfig
from .prompts import RESUME_TAILOR_SYSTEM, RESUME_TAILOR_USER

# Character limits to keep input tokens well under 30k TPM
_MAX_RESUME_CHARS = 8_000
_MAX_JD_CHARS = 12_000


def tailor_resume(
    config: AppConfig,
    resume_text: str,
    job_description: str,
    company: str,
    role: str,
) -> str:
    """Return tailored resume text using OpenAI."""
    client = OpenAI(api_key=config.env.openai_api_key)

    resume_text = resume_text[:_MAX_RESUME_CHARS]
    job_description = job_description[:_MAX_JD_CHARS]

    messages = [
        {"role": "system", "content": RESUME_TAILOR_SYSTEM},
        {
            "role": "user",
            "content": RESUME_TAILOR_USER.format(
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
                max_tokens=config.ai.max_tokens_resume,
                messages=messages,
            )
            return response.choices[0].message.content.strip()
        except RateLimitError:
            if model == config.ai.model:
                raise
            print(f"  [warn] Rate limit on {model}, retrying with {config.ai.model}...")
            continue
