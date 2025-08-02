#!/usr/bin/env python3
# -*- coding: utf-8 -*-

################################################################################

# Make sure we are in a development environment set up correctly

import os
import sys

if not os.environ.get("DEVELOPMENT"):
    print("Don't use this script in production. Set DEVELOPMENT=yes to make a development environment.")
    sys.exit(1)

API_KEY = os.environ.get("DEVELOPMENT_API_KEY")
if not API_KEY:
    print("Set you API key on DEVELOPMENT_API_KEY before running this script.")
    sys.exit(1)

MESSAGE = sys.argv[1] if len(sys.argv) > 1 else "Just say TEST"

REQUEST_TIMEOUT_IN_SECONDS = 30

################################################################################

# Let's get this bread

import json
import requests

try:
    print("Sending request to proxy...")

    response = requests.post(
        "http://127.0.0.1:5000/",
        json={
            'messages': [{ 'content': MESSAGE, 'role': 'user' }],
            'max_tokens': 10_000,
            'model': 'gemini-2.5-pro',
            'temperature': 0,
            'stream': False,
        },
        headers={
            'Authorization': 'Bearer ' + API_KEY,
            'User-Agent': 'test_proxy/1.0',
            'Content-Type': 'application/json',
        },
        timeout=REQUEST_TIMEOUT_IN_SECONDS
    )

    print("Received response from proxy.", response.status_code, response.reason)
except requests.exceptions.Timeout:
    print("Request timeout after", REQUEST_TIMEOUT_IN_SECONDS, "seconds.")
    sys.exit(1)

if not response.ok:
    print("Proxy wasn't feeling so good...")
    sys.exit(1)

response_json = response.json()
if not response_json:
    print("Proxy returned no json!")
    sys.exit(1)

print(json.dumps(response_json, indent=4))

################################################################################
