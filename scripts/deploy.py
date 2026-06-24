#!/usr/bin/env python3
"""Build and deploy the QueueSmart AI Lambdas with boto3 (no SAM required).

Why not SAM: the workshop `WSParticipantRole` cannot create IAM roles (SAM's
default), and the bundled SAM CLI doesn't run on macOS 12. This script instead
reuses an existing Lambda execution role and creates/updates the five functions
directly. It is idempotent — safe to re-run to push code changes.

Steps:
  1. Build a Linux x86_64 deployment zip (compiled pydantic-core must match the
     Lambda runtime; boto3 is provided by the runtime).
  2. Ensure the execution role has the extra scoped permissions smart-alert and
     doc-analysis need (geo:CalculateRoute, textract, s3:GetObject).
  3. create-or-update each function.

Config is read from the environment (falls back to the workshop defaults).
Credentials come from the usual boto3 chain (e.g. the local .env).

Usage:  python scripts/deploy.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_REGION", "us-west-2")
ACCOUNT = os.environ.get("AWS_ACCOUNT_ID", "432183140028")
EXEC_ROLE = os.environ.get("LAMBDA_EXEC_ROLE", "ec2-ubuntu-kiro-workshop-lambda-role")
TEXTRACT_BUCKET = os.environ.get("TEXTRACT_BUCKET", f"{ACCOUNT}-{REGION}-textract-uploads")
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "UC64X5D8BU")
LOCATION_CALCULATOR = os.environ.get("LOCATION_CALCULATOR_NAME", "queuesmart-routes")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
BEDROCK_CHAT_MODEL_ID = os.environ.get("BEDROCK_CHAT_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/{EXEC_ROLE}"
EXTRA_POLICY_NAME = "QueueSmartTextractLocationS3"

# (function name, handler, timeout seconds)
FUNCTIONS = [
    ("ai-prevetting", "app.handlers.prevetting", 60),
    ("ai-smart-alert", "app.handlers.smart_alert", 30),
    ("ai-routing", "app.handlers.routing", 30),
    ("ai-manager-advice", "app.handlers.manager_advice", 30),
    ("ai-doc-analysis", "app.handlers.doc_analysis", 180),
]

ENV_VARS = {
    "TEXTRACT_BUCKET": TEXTRACT_BUCKET,
    "KNOWLEDGE_BASE_ID": KNOWLEDGE_BASE_ID,
    "LOCATION_CALCULATOR_NAME": LOCATION_CALCULATOR,
    "BEDROCK_REGION": REGION,
    "BEDROCK_MODEL_ID": BEDROCK_MODEL_ID,
    "BEDROCK_CHAT_MODEL_ID": BEDROCK_CHAT_MODEL_ID,
}

ROOT = Path(__file__).resolve().parent.parent


def build_zip() -> bytes:
    build = ROOT / ".build" / "lambda"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)

    # Linux wheels for the Lambda runtime (pydantic-core is compiled).
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--quiet",
            "pydantic", "pydantic-settings",
            "--target", str(build),
            "--platform", "manylinux2014_x86_64",
            "--implementation", "cp", "--python-version", "3.12",
            "--only-binary=:all:",
        ],
        check=True,
    )
    shutil.copytree(ROOT / "app", build / "app", ignore=shutil.ignore_patterns("__pycache__"))

    zip_path = ROOT / ".build" / "queuesmart.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in build.rglob("*"):
            if "__pycache__" in path.parts or path.is_dir():
                continue
            zf.write(path, path.relative_to(build))
    return zip_path.read_bytes()


def ensure_role_policy() -> None:
    iam = boto3.client("iam", region_name=REGION)
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "Location", "Effect": "Allow", "Action": "geo:CalculateRoute",
             "Resource": f"arn:aws:geo:{REGION}:{ACCOUNT}:route-calculator/{LOCATION_CALCULATOR}"},
            {"Sid": "Textract", "Effect": "Allow",
             "Action": ["textract:StartDocumentTextDetection", "textract:GetDocumentTextDetection"],
             "Resource": "*"},
            {"Sid": "S3Read", "Effect": "Allow", "Action": "s3:GetObject",
             "Resource": f"arn:aws:s3:::{TEXTRACT_BUCKET}/*"},
        ],
    }
    iam.put_role_policy(
        RoleName=EXEC_ROLE, PolicyName=EXTRA_POLICY_NAME, PolicyDocument=json.dumps(policy)
    )
    print(f"  ensured inline policy {EXTRA_POLICY_NAME} on {EXEC_ROLE}")


def deploy_functions(code: bytes) -> None:
    lam = boto3.client("lambda", region_name=REGION)
    for name, handler, timeout in FUNCTIONS:
        try:
            lam.create_function(
                FunctionName=name, Runtime="python3.12", Role=ROLE_ARN, Handler=handler,
                Code={"ZipFile": code}, Timeout=timeout, MemorySize=512,
                Environment={"Variables": ENV_VARS}, Architectures=["x86_64"],
            )
            print(f"  created {name}")
        except lam.exceptions.ResourceConflictException:
            lam.update_function_code(FunctionName=name, ZipFile=code)
            waiter = lam.get_waiter("function_updated")
            waiter.wait(FunctionName=name)
            lam.update_function_configuration(
                FunctionName=name, Handler=handler, Timeout=timeout,
                Environment={"Variables": ENV_VARS},
            )
            print(f"  updated {name}")


def main() -> None:
    print("building deployment zip...")
    code = build_zip()
    print(f"  zip: {len(code) // 1024} KB")
    print("ensuring role permissions...")
    ensure_role_policy()
    print("deploying functions...")
    deploy_functions(code)
    print("done.")


if __name__ == "__main__":
    main()
