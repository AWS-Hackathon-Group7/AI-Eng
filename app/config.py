from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into the process environment so boto3 picks up AWS credentials
# (AWS_ACCESS_KEY_ID / SECRET / SESSION_TOKEN). pydantic-settings only reads
# the fields defined below; boto3 reads straight from os.environ.
load_dotenv()


class Settings(BaseSettings):
    """App configuration, loaded from environment variables / .env."""

    aws_region: str = "us-east-1"
    # S3 bucket Textract reads from. Async PDF detection requires the
    # document to live in S3 — bytes-in-request only works for the sync API.
    textract_bucket: str
    # Key prefix for uploaded documents inside the bucket.
    s3_prefix: str = "textract-uploads/"

    # Async job polling.
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 120.0

    # Bedrock (Claude) for document classification in §3.5. A fast/cheap model
    # is appropriate for classify + field extraction. Newer models on Bedrock
    # are invoked via an inference profile id (the "us." prefix).
    bedrock_region: str = "us-west-2"
    # Fast/cheap model for §3.5 document classification.
    bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    # Stronger model for §3.1 conversational pre-vetting.
    bedrock_chat_model_id: str = "us.anthropic.claude-sonnet-4-6"

    # Bedrock Knowledge Base that grounds pre-vetting (§4). Holds the
    # per-service required-documents checklists.
    knowledge_base_id: str = "UC64X5D8BU"
    kb_num_results: int = 4

    # Amazon Location Service for §3.2 smart "leave now" alert. DepartNow=True
    # gives live-traffic ETA. arrival_buffer = how early we aim to get the
    # customer there before their estimated call time.
    location_calculator_name: str = "queuesmart-routes"
    arrival_buffer_seconds: int = 300

    # extra="ignore": the .env also holds AWS_* credentials for boto3, which
    # aren't fields here — don't reject them.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
