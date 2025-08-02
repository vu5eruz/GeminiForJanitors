#!/usr/bin/env python3
# -*- coding: utf-8 -*-

################################################################################

import os
import sys


# Development requires an environment variable DEVELOPMENT to be set non-empty

if os.environ.get("DEVELOPMENT"):
    PRODUCTION = False
else:
    PRODUCTION = True

    # Production runs on gevent. Prevent issues with ssl monkey-patching.
    from gevent import monkey
    monkey.patch_all()


# Production requires XUID_SECRET to be set non-empty, Development can make one

XUID_SECRET = os.environ.get("XUID_SECRET")

if not XUID_SECRET:
    if PRODUCTION:
        print("!!! CRITICAL: Production deployment without a XUID_SECRET. Aborting. !!!")
        sys.exit(1)
    else:
        import secrets
        XUID_SECRET = secrets.token_bytes(32)

if isinstance(XUID_SECRET, str):
    XUID_SECRET = XUID_SECRET.encode('utf-8')


# Production must provide a Redis server, Development can use local

import redis

redis_client = None
if (redis_url := os.environ.get("REDIS_URL")):
    print("Using REDIS_URL =", redis_url)
    redis_client = redis.from_url(redis_url)
else:
    if PRODUCTION:
        print("!!! CRITICAL: Production deployment without a REDIS_URL. Aborting. !!!")
        sys.exit(1)
    else:
        print("REDIS_URL not found. Using non-persistent in-memory dictionary.")
        USER_STORAGE = dict()

################################################################################

import hashlib
import hmac
import json
import logging
import requests
import threading
import time
import traceback
from flask import Flask, Response, request
from flask_cors import CORS
from functools import wraps

################################################################################

SAFETY_SETTINGS_THRESHOLD = 'BLOCK_NONE'

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

REDIS_EXPIRY_TIME_IN_SECONDS = 30 * 24 * 60 * 60 

try:
    with open('prefill.txt') as prefill:
        PREFILL = prefill.read()
except FileNotFoundError:
    print("!!! WARNING: prefill.txt not found. Prefill feature won't work. !!!")
    PREFILL = ""

################################################################################

PROXY_AUTHORS = "undefinedundefined (vu5eruz on GitHub)"

PROXY_NAME = "GeminiForJanitors"

PROXY_VERSION = "2025.08.02"

PROXY_TITLE = f"{PROXY_NAME} ({PROXY_VERSION}) by {PROXY_AUTHORS}"

PROXY_BANNER = fr"""
***
# {PROXY_TITLE}
The proxy has been updated or has crashed and restarted. Your settings inside this proxy may have been reset.

You should see this message only once or twice. Your next request shouldn't include it.
If you don't want to see this message, switch your proxy URL to: https://geminiforjanitors.onrender.com/quiet/

You can now set up prefill with the commands `//prefill on` and `//prefill off`. It might help you reduce PROHIBITED_CONTENT errors.
"""

# HTML pro-tip: you can always omit <body> and <head> (screw IE9)
# See https://stackoverflow.com/a/5642982
# <html> is optional too, but lang=en is good manners
INDEX = fr"""<!doctype html>
<html lang=en>
<meta charset=utf-8>
<title>Google AI Studio Proxy for JanitorAI</title>
<h1>{PROXY_TITLE}</h1>
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

# User are anonymously identified by their XUID, which is use for keying.
# Storage (either Redis or local) maps XUIDs to a json (python dict) with their settings.
# If an XUID wasn't in the storage, that's a new user.

# Returns the user data (possibly an empty dict) and whether the user is new
def user_fetch(xuid):
    if redis_client:
        user_data_json = redis_client.get(xuid)
        if user_data_json:
            return json.loads(user_data_json), False
        return {}, True
    else: # Development fallback
        try:
            return USER_STORAGE[xuid], False
        except KeyError:
            return {}, True

def user_store(xuid, data):
    if redis_client:
        redis_client.set(xuid, json.dumps(data), ex=REDIS_EXPIRY_TIME_IN_SECONDS)
    else: # Development fallback
        USER_STORAGE[xuid] = data

################################################################################

def debug_print_json(obj):
    if DEBUG_PRINT_JSON and obj:
        print(f"{SGR_FORE_YELLOW}{json.dumps(obj, indent=4)}{SGR_FORE_DEFAULT}")

def print_settings():
    print()
    print(end=SGR_BOLD_ON + SGR_FORE_GREEN)
    print(PROXY_TITLE)
    print(f" * {PRODUCTION = }")
    print(f" * {SAFETY_SETTINGS_THRESHOLD = }")
    print(f" * {TOP_K = }")
    print(f" * {TOP_P = }")
    print(f" * {FREQUENCY_PENALTY = }")
    print(f" * {PRESENCE_PENALTY = }")
    print(f" * {DEBUG_PRINT_JSON = }")
    print(f" * {REQUEST_TIMEOUT_IN_SECONDS = }")
    print(f" * {REDIS_EXPIRY_TIME_IN_SECONDS = }")
    print(end=SGR_BOLD_OFF + SGR_FORE_DEFAULT)
    print()

def print_timed_message(message, prev_ref_time=None):
    current_ref_time = time.monotonic()

    delta_time_msg = ""
    if isinstance(prev_ref_time, float):
        delta_time_msg = f" ({current_ref_time - prev_ref_time:.0f} seconds)"

    print(f"{SGR_FORE_BLUE}[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}{delta_time_msg}{SGR_FORE_DEFAULT}")

    return current_ref_time

def make_xuid(user):
    xuid = hmac.new(XUID_SECRET, user.encode('utf-8'), hashlib.sha256).hexdigest()
    return xuid, xuid[:8].upper()

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

def proxy_response(message):
    return chat_response(f"<proxy>\n{message}\n</proxy>")

def handle_proxy():
    request_path = request.path
    option_quiet = 'quiet' in request_path

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

    jai_xuid, jai_xuid_short = make_xuid(jai_api_key)

    jai_xuid_data, jai_xuid_new = user_fetch(jai_xuid)

    gmtime = time.gmtime()
    jai_xuid_data['lastSeen'] = gmtime

    option_prefill = jai_xuid_data.get('usePrefill', False)

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

    # JanitorAI proxy test request is a single user message with "Just say TEST"
    # Other parameters are set to specific values, but these checks are enough

    jai_proxy_test = len(jai_messages) == 1 \
        and jai_messages[0].get('role', '') == 'user' \
        and jai_messages[0].get('content', '') == "Just say TEST"

    # Look for proxy commands on normal chat requests. There should be
    # - One system command (the bot description)
    # - One or more messages (user or assistant, i.e the chat)
    # - The latest message should be the user's

    if len(jai_messages) > 1 \
        and jai_messages[0].get('role', '') == 'system' \
        and jai_messages[-1].get('role', '') == 'user' \
        and jai_messages[-1].get('content', '').find(': //') != -1:

        # User's message looks like "<user's character name>: //<command> <one or more args>"
        # An user's character name can have spaces in it

        command = jai_messages[-1]['content'].lower().split(': //')[1].strip().split(' ')
        argcount = len(command) - 1

        print(f"Command from {jai_xuid_short}{' (new)' if jai_xuid_new else ''}", command)

        if command[0] == 'prefill':
            if argcount < 1:
                return proxy_response(f"Specify 'on' or 'off' after //prefill"), 200
            elif command[1] == 'on':
                option_prefill = True
            elif command[1] == 'off':
                option_prefill = False
            else:
                return proxy_response(f"Type 'on' or 'off', not '{command[1]}'"), 200

            jai_xuid_data['usePrefill'] = option_prefill 

            user_store(jai_xuid, jai_xuid_data)

            return proxy_response(
                f"Prefill is {'enabled' if option_prefill else 'disabled'}.\n" +
                "It may or may not help you with reducing errors.\n" +
                "This settings is in effect across all chats."
                "You can now remove the //prefill command from your message."
            ), 200
        else:
            return proxy_response(f"Unknown command //" + command[0]), 200

    # No proxy commands were present, lets continue as normal

    # JanitorAI message format needs to be converted to Google AI

    if jai_proxy_test or not option_prefill:
        gem_system_prompt = ''
    else:
        gem_system_prompt = PREFILL

    gem_chat_prompt_content = []
    gem_chat_prompt_length  = 0

    for msg in jai_messages:
        msg_content = msg.get('content', '<|empty|>')
        msg_role    = msg.get('role', 'user')

        if msg_role == 'assistant':
            msg_role = 'model' # Google AI convention

        if msg_role == 'system':
            gem_system_prompt += msg_content
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

    if jai_max_tokens > 0 and not jai_proxy_test:
        gem_config['maxOutputTokens'] = jai_max_tokens


    # Let's get this bread

    try:
        print(f"Sending request from {jai_xuid_short}{' (new)' if jai_xuid_new else ''} to Google AI...")

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

    gem_metadata = response_json.get('usageMetadata', {})
    gem_feedback = response_json.get('promptFeedback', {})

    if 'candidates' not in response_json or not response_json['candidates']:
        block_reason = gem_feedback.get('blockReason', 'UNKNOWN')
        message = f"Response blocked. Reason: {block_reason}"
        if block_reason == 'PROHIBITED_CONTENT':
            message += " (try using the '//prefill on' or '//prefill off' commands)"
        return error_message(message), 502

    gem_candidate = response_json['candidates'][0]

    gem_chat_response = ''
    gem_chat_thinking = ''

    for part in gem_candidate.get('content', {}).get('parts', [{}]):
        part_text = part.get('text', '')
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
    gem_finish_reason        = gem_candidate.get('finishReason', 'STOP')


    print(f"Chat/Prompt length {gem_chat_prompt_length} tokens {gem_chat_prompt_tokens} messages {len(gem_chat_prompt_content)}.")
    print(f"Response length {len(gem_chat_response)} tokens {gem_chat_response_tokens}.")
    print(f"Thinking length {len(gem_chat_thinking)} tokens {gem_chat_thinking_tokens}.")

    if gem_finish_reason == 'MAX_TOKENS':
        return error_message("Max tokens exceeded. Increase or remove token limit."), 502

    # All done and good

    if not jai_proxy_test:
        if jai_xuid_new:
            jai_xuid_data['firstSeen'] = gmtime

            if not option_quiet:
                gem_chat_response += PROXY_BANNER

        user_store(jai_xuid, jai_xuid_data)

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
@app.route('/quiet/', methods=['POST'])
@app.route('/quiet/chat/completions', methods=['POST'])
def proxy():
    print(f"{SGR_BOLD_ON}{SEPARATOR}{SGR_BOLD_OFF}")

    ref_time = print_timed_message(f"Processing {request.path} ...")

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
