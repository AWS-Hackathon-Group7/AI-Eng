#!/usr/bin/env python3
"""Deploy the FastAPI app as a single Lambda behind a public Function URL.

This is the frontend-testing surface: the whole app/main.py (all endpoints +
Swagger /docs + /openapi.json) served at a public HTTPS URL, via Mangum. It
reuses the same execution role as the contract Lambdas. Idempotent.

Usage:  python scripts/deploy_api.py
Prints the Function URL on success.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import boto3

# Reuse the shared config + role-policy logic from the contract deployer.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy as base  # noqa: E402

FUNCTION_NAME = "queuesmart-api"
HANDLER = "app.asgi.handler"
TIMEOUT = 180
MEMORY = 1024
ROOT = base.ROOT


def build_zip() -> bytes:
    build = ROOT / ".build" / "api"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--quiet",
            "-r", str(ROOT / "requirements-api.txt"),
            "--target", str(build),
            "--platform", "manylinux2014_x86_64",
            "--implementation", "cp", "--python-version", "3.12",
            "--only-binary=:all:",
        ],
        check=True,
    )
    shutil.copytree(ROOT / "app", build / "app", ignore=shutil.ignore_patterns("__pycache__"))
    zip_path = ROOT / ".build" / "queuesmart-api.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in build.rglob("*"):
            if "__pycache__" in path.parts or path.is_dir():
                continue
            zf.write(path, path.relative_to(build))
    return zip_path.read_bytes()


def deploy(code: bytes) -> None:
    lam = boto3.client("lambda", region_name=base.REGION)
    try:
        lam.create_function(
            FunctionName=FUNCTION_NAME, Runtime="python3.12", Role=base.ROLE_ARN,
            Handler=HANDLER, Code={"ZipFile": code}, Timeout=TIMEOUT, MemorySize=MEMORY,
            Environment={"Variables": base.ENV_VARS}, Architectures=["x86_64"],
        )
        print(f"  created {FUNCTION_NAME}")
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=FUNCTION_NAME, ZipFile=code)
        lam.get_waiter("function_updated").wait(FunctionName=FUNCTION_NAME)
        lam.update_function_configuration(
            FunctionName=FUNCTION_NAME, Handler=HANDLER, Timeout=TIMEOUT,
            MemorySize=MEMORY, Environment={"Variables": base.ENV_VARS},
        )
        print(f"  updated {FUNCTION_NAME}")


def ensure_public_url() -> str:
    lam = boto3.client("lambda", region_name=base.REGION)
    cors = {"AllowOrigins": ["*"], "AllowMethods": ["*"], "AllowHeaders": ["*"]}
    try:
        cfg = lam.create_function_url_config(
            FunctionName=FUNCTION_NAME, AuthType="NONE", Cors=cors
        )
    except lam.exceptions.ResourceConflictException:
        cfg = lam.update_function_url_config(
            FunctionName=FUNCTION_NAME, AuthType="NONE", Cors=cors
        )
    # Public invoke needs an explicit resource-based permission.
    try:
        lam.add_permission(
            FunctionName=FUNCTION_NAME, StatementId="FunctionURLPublic",
            Action="lambda:InvokeFunctionUrl", Principal="*",
            FunctionUrlAuthType="NONE",
        )
    except lam.exceptions.ResourceConflictException:
        pass
    return cfg["FunctionUrl"]


def main() -> None:
    print("building API zip...")
    code = build_zip()
    print(f"  zip: {len(code) // 1024} KB")
    print("ensuring role permissions...")
    base.ensure_role_policy()
    print("deploying API function...")
    deploy(code)
    url = ensure_public_url()
    print("done.")
    print(f"\n  API:   {url}")
    print(f"  Docs:  {url}docs")


if __name__ == "__main__":
    main()
