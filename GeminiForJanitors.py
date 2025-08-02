#!/usr/bin/env python3
# -*- coding: utf-8 -*-

################################################################################

# Development requires an environment variable DEVELOPMENT to be set non-empty

import os

if os.environ.get("DEVELOPMENT"):
    PRODUCTION = False
else:
    PRODUCTION = True

    # Production runs on gevent. Prevent issues with ssl monkey-patching.
    from gevent import monkey
    monkey.patch_all()

################################################################################

import json
import logging
import requests
import time
import threading
import traceback
from flask import Flask, Response, request
from flask_cors import CORS
from functools import wraps

################################################################################

SAFETY_SETTINGS_THRESHOLD = 'OFF'

SAFETY_SETTINGS = [
    {
        'category': 'HARM_CATEGORY_HARASSMENT',
        'threshold': SAFETY_SETTINGS_THRESHOLD,
    },
    {
        'category': 'HARM_CATEGORY_HATE_SPEECH',
        'threshold': SAFETY_SETTINGS_THRESHOLD,
    },
    {
        'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT',
        'threshold': SAFETY_SETTINGS_THRESHOLD,
    },
    {
        'category': 'HARM_CATEGORY_DANGEROUS_CONTENT',
        'threshold': SAFETY_SETTINGS_THRESHOLD,
    },
    {
        'category': 'HARM_CATEGORY_CIVIC_INTEGRITY',
        'threshold': SAFETY_SETTINGS_THRESHOLD,
    },
]

TOP_K = 50

TOP_P = 0.95

FREQUENCY_PENALTY = 0.0

PRESENCE_PENALTY = 0.0

DEBUG_PRINT_JSON = False

REQUEST_TIMEOUT_IN_SECONDS = 60

################################################################################

PROXY_AUTHORS = "undefinedundefined (vu5eruz on GitHub)"

PROXY_NAME = "GeminiForJanitors"

PROXY_VERSION = "2025.08.02"

# HTML pro-tip: you can always omit <body> and <head> (screw IE9)
# See https://stackoverflow.com/a/5642982
# <html> is optional too, but lang=en is good manners
INDEX = fr"""<!doctype html>
<html lang=en>
<meta charset=utf-8>
<title>Google AI Studio Proxy for JanitorAI</title>
<h1>{PROXY_NAME} ({PROXY_VERSION}) by {PROXY_AUTHORS}</h1>
<p>Up and running.</p>
</html>
"""

SEPARATOR = '=' * 80

SGR_BOLD_ON  = "\x1B[1m"
SGR_BOLD_OFF = "\x1B[22m"

SGR_FORE_DEFAULT = "\x1B[39m"
SGR_FORE_RED     = "\x1B[31m"
SGR_FORE_GREEN   = "\x1B[32m"
SGR_FORE_YELLOW  = "\x1B[33m"
SGR_FORE_BLUE    = "\x1B[34m"

################################################################################

# JanitorAI proxy test request is a single user message with "Just say TEST"
# max_tokens is set to 10 and temperature to 0, but these checks are sufficient
def is_jai_proxy_test(messages):
    return len(messages) == 1 \
        and messages[0].get('role', '') == 'user' \
        and messages[0].get('content', '') == "Just say TEST"

def debug_print_json(obj):
    if DEBUG_PRINT_JSON and obj:
        print(f"{SGR_FORE_YELLOW}{json.dumps(obj, indent=4)}{SGR_FORE_DEFAULT}")

def print_settings():
    print()
    print(end=SGR_BOLD_ON + SGR_FORE_GREEN)
    print(f"{PROXY_NAME} ({PROXY_VERSION}) settings:")
    print(f" * {PRODUCTION = }")
    print(f" * {SAFETY_SETTINGS_THRESHOLD = }")
    print(f" * {TOP_K = }")
    print(f" * {TOP_P = }")
    print(f" * {FREQUENCY_PENALTY = }")
    print(f" * {PRESENCE_PENALTY = }")
    print(f" * {DEBUG_PRINT_JSON = }")
    print(f" * {REQUEST_TIMEOUT_IN_SECONDS = }")
    print(end=SGR_BOLD_OFF + SGR_FORE_DEFAULT)
    print()

def print_timed_message(message, prev_ref_time=None):
    current_ref_time = time.monotonic()

    delta_time_msg = ""
    if isinstance(prev_ref_time, float):
        delta_time_msg = f" ({current_ref_time - prev_ref_time:.0f} seconds)"

    print(f"{SGR_FORE_BLUE}[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}{delta_time_msg}{SGR_FORE_DEFAULT}")

    return current_ref_time

# This is all JanitorAI seems to need to present a custom error message.
def error_message(message):
    return { 'error': message }

def chat_response(message):
    return {
        'choices': [{
            'index': 0,
            'message': {
                'role': 'assistant',
                'content': message,
            },
            'finish_reason': 'stop'
        }]
    }

def handle_proxy():
    request_json = request.get_json(silent=True)
    if not request_json:
        return error_message("Bad Request. Missing or invalid JSON from JanitorAI."), 400
    debug_print_json(request_json)


    # JanitorAI provides the user's API key through HTTP Bearer authentication.
    # Google AI cannot be used without an API key.

    request_auth = request.headers.get('authorization')
    if not request_auth or not request_auth.startswith('Bearer '):
        return error_message("Unauthorized. API key required."), 401

    jai_api_key = request_auth[len('Bearer '):]


    # Streaming isn't and won't be implemented as it could increase rejections
    if request_json.get('stream', False):
        return error_message("Text streaming is not supported. Disable text streaming to use this proxy."), 501


    # JanitorAI messages are a list of { 'content': '...', 'role': '...' }
    # Messages are in chronological order, from oldest to newest.
    # Roles can be 'system', 'user', or 'assistant'.
    # There is system message at the beginning with the bot specification.
    # Proxy test has no system message and only has a single user message.

    jai_messages = request_json.get('messages', [])


    # JanitorAI allows the user to configure max_tokens, model and temperature.
    # There is currently no means to configure other model parameters.
    # The code can manage if they come to exist and gracefully default if not.

    jai_max_tokens  = request_json.get('max_tokens', 0)
    jai_model       = request_json.get('model', 'gemini-2.5-pro')
    jai_temperature = request_json.get('temperature', 0)
    jai_top_k       = request_json.get('top_k', TOP_K)
    jai_top_p       = request_json.get('top_p', TOP_P)
    jai_frequency_p = request_json.get('frequency_penalty', FREQUENCY_PENALTY)
    jai_presence_p  = request_json.get('presence_penalty', PRESENCE_PENALTY)


    # JanitorAI message format needs to be converted to Google AI

    gem_system_prompt       = ''
    gem_chat_prompt_content = []
    gem_chat_prompt_length  = 0

    for msg in jai_messages:
        msg_content = msg.get('content', '<|empty|>')
        msg_role    = msg.get('role', 'user')

        if msg_role == 'assistant':
            msg_role = 'model' # Google AI convention

        if msg_role == 'system':
            gem_system_prompt = msg_content
        else:
            gem_chat_prompt_length += len(msg_content)
            gem_chat_prompt_content.append({
                'parts': [{
                    'text': msg_content
                }],
                'role': msg_role,
            })


    # Google AI generation configuration

    gem_config = {
        'temperature': jai_temperature,
        'thinkingConfig': {
            'includeThoughts': True,
        },
    }

    if jai_top_k > 0:
        gem_config['topK'] = jai_top_k

    if jai_top_p > 0.0:
        gem_config['topP'] = jai_top_p

    if jai_frequency_p > 0.0:
        gem_config['frequencyPenalty'] = jai_frequency_p

    if jai_presence_p > 0.0:
        gem_config['presencePenalty'] = jai_presence_p

    # JanitorAI proxy test request has a very low max_tokens value.
    # It is not enough to accommodate thinking tokens, leading to rejections.
    # Otherwise, honor a max_tokens limit. Users will get an error on rejection.

    if jai_max_tokens > 0 and not is_jai_proxy_test(jai_messages):
        gem_config['maxOutputTokens'] = jai_max_tokens


    # Let's get this bread

    try:
        print("Sending request to Google AI...")

        response = requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/{jai_model}:generateContent',
            json={
                'contents': gem_chat_prompt_content,
                'systemInstruction': {
                    'parts': [{'text': gem_system_prompt}]
                },
                'safetySettings': SAFETY_SETTINGS,
                'generationConfig': gem_config,
            },
            headers={
                'User-Agent': f'{PROXY_NAME}/{PROXY_VERSION}',
                'Content-Type': 'application/json',
                'X-goog-api-key': jai_api_key,
            },
            timeout=REQUEST_TIMEOUT_IN_SECONDS
        )

        print("Received response from Google AI.", response.status_code, response.reason)
    except requests.exceptions.Timeout:
        print("Request timeout after", REQUEST_TIMEOUT_IN_SECONDS, "seconds.")
        return error_message(f"Gateway Timeout. The request to Google AI timed out."), 504


    response_json = response.json()
    if not response_json:
        return error_message("Bad Gateway. Missing or invalid JSON from Google AI."), 502
    debug_print_json(response_json)

    if not response.ok:
        message = "Google AI error: " + response_json.get('error', {}).get('message', "unknown")
        return error_message(message), response.status_code


    # Be as lenient as possible while processing Google AI responses

    gem_candidates = response_json.get('candidates')
    gem_canditate  = gem_candidates[0] if gem_candidates else None
    gem_metadata   = response_json.get('usageMetadata', {})
    gem_feedback   = response_json.get('promptFeedback', {})

    if not isinstance(gem_canditate, dict):
        message = "Response blocked. Reason: " + gem_feedback.get('blockReason', 'UNKNOWN')
        return error_message(message), 502

    gem_chat_response = ''
    gem_chat_thinking = ''

    for part in gem_canditate.get('content', {}).get('parts', [{}]):
        part_text = part.get('text')
        part_thought = part.get('thought', False)

        if not part_thought:
            gem_chat_response += part_text
        else:
            gem_chat_thinking += part_text

    gem_chat_response = gem_chat_response.strip()
    gem_chat_thinking = gem_chat_thinking.strip()


    gem_chat_prompt_tokens   = gem_metadata.get('promptTokenCount', 0)
    gem_chat_response_tokens = gem_metadata.get('candidatesTokenCount', 0)
    gem_chat_thinking_tokens = gem_metadata.get('thoughtsTokenCount', 0)
    gem_finish_reason        = gem_canditate.get('finishReason', 'STOP')


    print(f"Chat/Prompt length {gem_chat_prompt_length} tokens {gem_chat_prompt_tokens}.")
    print(f"Response length {len(gem_chat_response)} tokens {gem_chat_response_tokens}.")
    print(f"Thinking length {len(gem_chat_thinking)} tokens {gem_chat_thinking_tokens}:")

    if gem_chat_thinking:
        print(f"{SGR_BOLD_ON}{gem_chat_thinking}{SGR_BOLD_OFF}")

    if gem_finish_reason == 'MAX_TOKENS':
        return error_message("Max tokens exceeded. Increase or remove token limit."), 502


    # All done and good

    return chat_response(gem_chat_response), 200

################################################################################

app = Flask(__name__)
CORS(app) # JanitorAI requires CORS on proxies

@app.route('/', methods=['GET'])
def index():
    return Response(
        response=INDEX,
        status=200,
        mimetype='text/html')

@app.route('/', methods=['POST'])
@app.route('/chat/completions', methods=['POST'])
def proxy():
    print(f"{SGR_BOLD_ON}{SEPARATOR}{SGR_BOLD_OFF}")

    ref_time = print_timed_message("Processing request...")

    try:
        response, status = handle_proxy()
    except Exception as e:
        response, status = (error_message("Internal Proxy Error"), 500)

        print(end=SGR_FORE_RED)
        traceback.print_exception(e)
        print(end=SGR_FORE_DEFAULT)

    if 200 <= status <= 299:
        print_timed_message("Processing succeeded", ref_time)
    else:
        print_timed_message(f"Processing failed.", ref_time)
        print(f"{SGR_FORE_RED}{status} {response['error']}{SGR_FORE_DEFAULT}")

    print(f"{SGR_BOLD_ON}{SEPARATOR}{SGR_BOLD_OFF}")

    return Response(
        response=json.dumps(response),
        status=status,
        mimetype='text/json')

@app.route('/health', methods=["GET"])
def health():
    return "We are healthy!", 200

################################################################################

# Render.com makes many health checks and it pollutes the log.
# Silence that, it makes the logs on the dashboard prettier.

class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        return record.getMessage().find('"GET /health HTTP/1.1" 200') == -1

gunicorn_logger = logging.getLogger('gunicorn.access')
gunicorn_logger.addFilter(HealthCheckFilter())


# Allow running an usable instance locally while developing
# Use waitress-serve --host="127.0.0.1" --port=5000 GeminiForJanitors:app
# It's better than pushing to production and hoping for the best

if not PRODUCTION:
    from flask_cloudflared import start_cloudflared

    cloudflared_thread = threading.Thread(
        target=start_cloudflared,
        kwargs={ 'port': 5000, 'metrics_port': 5001, },
        daemon=True)

    cloudflared_thread.start()

################################################################################

print_settings()
