import asyncio
import threading
import requests
import json
import time
from datetime import datetime
from playwright.async_api import async_playwright
from flask import Flask, request, jsonify
from flask_cors import CORS
from keep_alive import keep_alive

app = Flask(__name__)
CORS(app)

SLACK_BOT_TOKEN = 'slack bot token'
SLACK_API_URL = 'https://slack.com/api/chat.postEphemeral'
SLACK_JOIN_URL = 'https://slack.com/api/conversations.join'
DATA_FILE = 'hour_stats.txt'
URL = "https://airtable.com/appOKDJk2ALKSisEM/shriBhjoCj83rYCGT"

async def get_rendered_content(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # headless mode is True
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_load_state('networkidle')

        await page.wait_for_selector('text="Hours pending review"', timeout=15000)
        await page.wait_for_selector('text="Hours approved in past 7 days"', timeout=15000)

        visible_text = await page.evaluate('() => document.body.innerText')
        await browser.close()
        return visible_text

def parse_data(text):
    lines = text.split('\n')
    hours_pending = None
    hours_approved = None
    for i, line in enumerate(lines):
        if line.strip() == "Hours pending review":
            try:
                hours_pending = int(lines[i+2].strip())
            except (IndexError, ValueError):
                print(f"Error parsing hours pending review. Line content: {lines[i+2] if i+2 < len(lines) else 'N/A'}")
        elif line.strip() == "Hours approved in past 7 days":
            try:
                hours_approved = int(lines[i+2].strip())
            except (IndexError, ValueError):
                print(f"Error parsing hours approved. Line content: {lines[i+2] if i+2 < len(lines) else 'N/A'}")

        if hours_pending is not None and hours_approved is not None:
            break

    return hours_pending, hours_approved

def send_slack_message(user_id, channel_id, response_text):
    payload = {
        "token": SLACK_BOT_TOKEN,
        "channel": channel_id,
        "user": user_id,
        "text": response_text
    }
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    response = requests.post(SLACK_API_URL, json=payload, headers=headers)
    print(f"Slack API response status: {response.status_code}")
    print(f"Slack API response body: {response.text}")
    return response.status_code

def join_channel(channel_id):
    payload = {
        "channel": channel_id
    }
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    response = requests.post(SLACK_JOIN_URL, json=payload, headers=headers)
    print(f"Slack Join API response status: {response.status_code}")
    print(f"Slack Join API response body: {response.text}")
    return response.status_code

def process_request(user_id, channel_id):
    try:
        join_status = join_channel(channel_id)
        if join_status != 200:
            print("Failed to join the channel")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        visible_text = loop.run_until_complete(get_rendered_content(URL))

        print("Visible text content:")
        print(visible_text)

        hours_pending, hours_approved = parse_data(visible_text)

        if hours_pending is None or hours_approved is None:
            response_text = "Failed to extract data from the page."
        else:
            response_text = f"Hours pending review: {hours_pending}\nHours approved in past 7 days: {hours_approved}"

        # follow-up message
        send_slack_message(user_id, channel_id, response_text)
    except Exception as e:
        print(f"An error occurred: {str(e)}")

def fetch_and_save_data():
    while True:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            visible_text = loop.run_until_complete(get_rendered_content(URL))
            hours_pending, hours_approved = parse_data(visible_text)

            if hours_pending is not None and hours_approved is not None:
                data = {
                    "timestamp": datetime.now().isoformat(),
                    "hours_pending": hours_pending,
                    "hours_approved": hours_approved
                }

                with open(DATA_FILE, 'a') as f:
                    json.dump(data, f)
                    f.write('\n')

            time.sleep(300)  # Sleep for 5 minutes
        except Exception as e:
            print(f"An error occurred while fetching and saving data: {str(e)}")
            time.sleep(60)  # if an error occurs, wait for 1 minute before retrying

@app.route('/api/hours', methods=['POST'])
def get_hours():
    try:
        data = request.form
        user_id = data.get('user_id')
        channel_id = data.get('channel_id')

        # acknowledge request immediately
        ack_response = {
            "response_type": "ephemeral",
            "text": "Processing your request, please wait..."
        }

        # start background thread to handle request
        threading.Thread(target=process_request, args=(user_id, channel_id)).start()

        return jsonify(ack_response)
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500

@app.route('/api/realtime', methods=['GET'])
def get_realtime_data():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        visible_text = loop.run_until_complete(get_rendered_content(URL))

        hours_pending, hours_approved = parse_data(visible_text)

        if hours_pending is None or hours_approved is None:
            return jsonify({"error": "Failed to extract data from the page."}), 500

        data = {
            "hours_pending": hours_pending,
            "hours_approved": hours_approved
        }

        return jsonify(data)
    except Exception as e:
        print(f"An error occurred while scraping realtime data: {str(e)}")
        return jsonify({"error": "An error occurred while fetching realtime data", "details": str(e)}), 500

@app.route('/')
def hello():
    return "Hello, World!"

@app.route('/ping')
def ping():
    return "pong"

@app.route('/api/stats', methods=['GET'])
def hour_stats():
    try:
        with open(DATA_FILE, 'r') as f:
            data = f.read()
        return data
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500

# API to fetch the output.log file content
@app.route('/api/logs', methods=['GET'])
def log_stats():
    try:
        with open('output.log', 'r') as f:
            data = f.read()
        return data
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500
    

@app.route('/api/statwebsite', methods=['POST'])
def stat_website():
    try:
        response_text = "Here is the link to Arcade Review Stats website: <https://pixelverseit.github.io/hackclub-arcade-tracker-htmlcssjs/stats.html>"
        button_text = "Visit Arcade Review Stats website"
        button_url = "https://pixelverseit.github.io/hackclub-arcade-tracker-htmlcssjs/stats.html"

        response = {
            "response_type": "ephemeral",
            "text": response_text,
            "attachments": [
            {
                "actions": [
                {
                    "type": "button",
                    "text": button_text,
                    "url": button_url
                }
                ]
            }
            ]
        }

        return jsonify(response)
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500
    
@app.route('/api/history', methods=['GET'])
def history():
    try:
        api_key = request.headers.get('Authorization')
        if api_key:
            url1 = "https://hackhour.hackclub.com/api/history/U07A928DDJQ"
            headers = {
                "Authorization": api_key,
                'Cache-Control': 'no-cache',
            }
            response = requests.get(url1, headers=headers)
            print(response.text)
            if response.status_code != 200:
                return jsonify({"error": "Failed to fetch history data from API", "details": response.text}), response.status_code
            return response.text, 200
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500

if __name__ == '__main__':
    # start the background thread for fetching and saving data
    threading.Thread(target=fetch_and_save_data, daemon=True).start()
    
    app.run(host='127.0.0.1', port=8096)
    keep_alive()
