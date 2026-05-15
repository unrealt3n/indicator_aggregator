#!/usr/bin/env python3
import praw
import time
import os
from datetime import datetime

# ================= CONFIGURATION =================
# Use environment variables for credentials
CLIENT_ID     = os.environ.get("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
USERNAME      = os.environ.get("REDDIT_USERNAME")
PASSWORD      = os.environ.get("REDDIT_PASSWORD")
USER_AGENT    = "AndroidTermuxScheduler v1.0 by /u/YOUR_USERNAME"  # Change this

# Message details
TARGET_USER   = "recipient_username"        # Change this
MSG_SUBJECT   = "Your scheduled message"
MSG_BODY      = "Hello! This DM was sent automatically from Termux with retries."

# Target date and time (local device time)
TARGET_YEAR   = 2026
TARGET_MONTH  = 5    # May
TARGET_DAY    = 16
TARGET_HOUR   = 0    # 12am = midnight
TARGET_MINUTE = 0
TARGET_SECOND = 0

# Retry settings
MAX_RETRIES   = 5
RETRY_DELAY   = 60   # seconds
# =================================================

def send_reddit_dm(reddit_instance):
    """Send the DM using an already authenticated PRAW instance."""
    print(f"[{datetime.now()}] Sending message to {TARGET_USER}...")
    reddit_instance.redditor(TARGET_USER).message(MSG_SUBJECT, MSG_BODY)
    print(f"[{datetime.now()}] Message sent successfully.")

def wait_until_target():
    """Sleep until the target datetime (local)."""
    target = datetime(TARGET_YEAR, TARGET_MONTH, TARGET_DAY,
                      TARGET_HOUR, TARGET_MINUTE, TARGET_SECOND)
    now = datetime.now()
    
    if now >= target:
        print(f"Target time {target} has already passed. Exiting.")
        return False
    
    delta = target - now
    print(f"Current time: {now}")
    print(f"Waiting for {delta}. Will send at {target}")
    
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        sleep_sec = min(remaining, 60)
        time.sleep(sleep_sec)
    return True

if __name__ == "__main__":
    # Validate credentials
    if not all([CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD]):
        print("ERROR: Missing Reddit credentials. Set environment variables:")
        print("  REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD")
        exit(1)

    # Wait until the target time
    if not wait_until_target():
        exit(0)

    # Authenticate once
    print(f"[{datetime.now()}] Authenticating as {USERNAME}...")
    try:
        reddit = praw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT,
            username=USERNAME,
            password=PASSWORD
        )
        # Verify login
        me = reddit.user.me()
        print(f"[{datetime.now()}] Logged in as: {me}")
    except Exception as e:
        print(f"[{datetime.now()}] Authentication failed: {e}")
        exit(1)

    # Attempt to send with retries
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            send_reddit_dm(reddit)
            print(f"[{datetime.now()}] Done.")
            break  # Success – exit the retry loop
        except Exception as e:
            print(f"[{datetime.now()}] Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"[{datetime.now()}] All {MAX_RETRIES} attempts failed. Exiting.")
                exit(1)