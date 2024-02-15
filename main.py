import openai
import requests
import os
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify
from requests_oauthlib import OAuth1Session
from requests_oauthlib import OAuth1

app = Flask(__name__)

# Initialize OpenAI using environment variables
openai.api_key = os.getenv('OPENAI_API_KEY')

# Setup for Twitter API credentials
consumer_key = os.getenv('TWITTER_API_KEY')
consumer_secret = os.getenv('TWITTER_API_SECRET_KEY')
access_token = os.getenv('TWITTER_ACCESS_TOKEN')
access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

# Twitter API v2 endpoint for creating tweets with OAuth1 authentication
create_tweet_url = "https://api.twitter.com/2/tweets"
auth = OAuth1(consumer_key, consumer_secret, access_token, access_token_secret)

def is_safe_prompt(prompt):
    """
    Evaluates if the generated prompt passes OpenAI's content filter, ensuring it adheres to content guidelines.
    """
    try:
        response = openai.Completion.create(
            engine="content-filter-alpha-c4",
            prompt=f"{prompt}\n--\nLabel:",
            temperature=0,
            max_tokens=1,
            top_p=1,
            logprobs=10
        )
        output_label = response.choices[0].text.strip()
        # "2" indicates unsafe content
        return output_label != "2"
    except Exception as e:
        print(f"Content filter error: {e}")
        return False

def generate_prompt_with_chatgpt(attempts=3):
    """
    Generates creative and safe prompts with ChatGPT, retrying up to 3 times for content that passes the safety filter.
    """
    for attempt in range(attempts):
        today = datetime.now().strftime("%B %d")
        prompt_text = f"Generate a creative and weird prompt for image generation based on significant historical events that occurred in the past on {today}."
        response = openai.Completion.create(
            engine="gpt-3.5-turbo-instruct",
            prompt=prompt_text,
            temperature=0.7,
            max_tokens=100,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )
        generated_prompt = response.choices[0].text.strip()
        if is_safe_prompt(generated_prompt):
            return generated_prompt
        print(f"Attempt {attempt + 1}: Unsafe prompt generated, retrying...")
    return "Unable to generate a safe prompt after multiple attempts."

def summarize_prompt_with_chatgpt(original_prompt, max_length=280):
    """
    Condenses the generated prompt to fit Twitter's character limit, ensuring it's suitable for tweet summaries.
    """
    try:
        instruction = f"Summarize the following in less than {max_length} characters for a Tweet:\n\n{original_prompt}. Include relevant hashtags like #AI, #TodayInHistory, and anything relevant to the theme."
        response = openai.Completion.create(
            engine="gpt-3.5-turbo-instruct",
            prompt=instruction,
            temperature=0.7,
            max_tokens=100,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )
        summary = response.choices[0].text.strip()
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."
        return summary
    except Exception as e:
        print(f"Error summarizing prompt: {e}")
        return original_prompt[:max_length - 3] + "..." if len(original_prompt) > max_length else original_prompt

def generate_image_with_dalle(prompt):
    """
    Creates a visual representation of the prompt using OpenAI's DALL·E, returning the image URL.
    """
    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size="1024x1024"
    )
    image_data = response['data'][0]
    return image_data['url']

def download_image(url):
    """
    Downloads an image from the specified URL and returns it as a bytes object for uploading.
    """
    response = requests.get(url)
    response.raise_for_status()
    return BytesIO(response.content)

def upload_media(image_url):
    """
    Uploads an image to Twitter and returns the media ID for reference in tweets.
    """
    upload_url = 'https://upload.twitter.com/1.1/media/upload.json'
    response = requests.get(image_url)
    files = {'media': response.content}
    response = requests.post(upload_url, auth=auth, files=files)
    if response.status_code == 200:
        return response.json().get('media_id_string')
    print("Failed to upload media:", response.text)
    return None

def post_tweet_v2(content, media_id):
    """
    Posts a tweet with the provided content and attached media using Twitter API v2.
    """
    try:
        twitter_session = OAuth1Session(consumer_key, consumer_secret, access_token, access_token_secret)
        response = twitter_session.post(create_tweet_url, json={"text": content, "media":{"media_ids": [media_id]}})
        if response.status_code == 201:
            tweet_data = response.json()
            return f"https://twitter.com/user/status/{tweet_data['data']['id']}"
        print(f"Failed to post tweet: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Error posting to Twitter: {e}")
    return None

@app.route('/post', methods=['GET'])
def run_bot_and_post():
    """
    Initiates the bot's workflow to generate a prompt, create an image, summarize for a tweet, upload the image to Twitter, and post the tweet.
    """
    try:
        prompt = generate_prompt_with_chatgpt()
        image_url = generate_image_with_dalle(prompt)
        post_title = summarize_prompt_with_chatgpt(prompt)
        media_id = upload_media(image_url)
        tweet_url = post_tweet_v2(post_title, media_id)
        if tweet_url:
            return jsonify({"message": "Tweet successfully posted.", "details": {"tweet_url": tweet_url, "prompt": prompt, "image_url": image_url, "post_title": post_title, "media_id": media_id}}), 200
        return jsonify({"message": "Failed to post tweet.", "details": {"prompt": prompt, "image_url": image_url, "post_title": post_title, "media_id": media_id}}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 8080)))
