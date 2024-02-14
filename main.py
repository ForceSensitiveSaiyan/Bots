import openai
import tweepy
import requests
import os
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# Initialize OpenAI and Reddit clients using environment variables for sensitive information
openai.api_key = os.getenv('OPENAI_API_KEY')
# Twitter API setup
consumer_key = os.getenv('TWITTER_API_KEY')
consumer_secret = os.getenv('TWITTER_API_SECRET_KEY')
access_token = os.getenv('TWITTER_ACCESS_TOKEN')
access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

auth = tweepy.OAuth1UserHandler(
    consumer_key, consumer_secret,
    access_token, access_token_secret
)
twitter_api = tweepy.API(auth)

def is_safe_prompt(prompt):
    """
    Checks if the generated prompt is safe according to OpenAI's content filter.
    This helps ensure the generated content adheres to content policy guidelines.
    """
    try:
        response = openai.Completion.create(
            engine="content-filter-alpha-c4",
            prompt="" + prompt + "\n--\nLabel:",
            temperature=0,
            max_tokens=1,
            top_p=1,
            logprobs=10
        )
        output_label = response.choices[0].text.strip()
        return output_label != "2"  # Return False if content is flagged as unsafe
    except Exception as e:
        print(f"Content filter error: {e}")
        return False

def generate_prompt_with_chatgpt(attempts=3):
    """
    Generates creative prompts using ChatGPT, attempting up to 3 times to ensure
    content safety before giving up. This is to navigate around the content
    restrictions effectively.
    """
    for attempt in range(attempts):
        today = datetime.now().strftime("%B %d")
        prompt_text = f"Generate a creative and weird prompt for image generation based on significant historical events, births, and deaths that occurred in the past on {today}."
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
        else:
            print(f"Attempt {attempt + 1}: Unsafe prompt generated, retrying...")

    return "Unable to generate a safe prompt after multiple attempts."

def summarize_prompt_with_chatgpt(original_prompt, max_length=300):
    """
    Summarizes the generated prompt to ensure it fits within a specified character limit,
    making it suitable for titles or brief descriptions.
    """
    try:
        instruction = f"Summarize the following in less than {max_length} characters:\n\n{original_prompt}"
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
        print(f"An error occurred while summarizing the prompt: {e}")
        return original_prompt[:max_length - 3] + "..." if len(original_prompt) > max_length else original_prompt

def generate_image_with_dalle(prompt):
    """
    Generates an image based on the provided prompt using OpenAI's DALL·E.
    This leverages OpenAI's model to create visual content from textual input.
    """
    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size="1024x1024"
    )
    image_data = response['data'][0]
    image_url = image_data['url']
    return image_url

def download_image(url):
    """
    Helper function to download an image from a URL and return it as bytes.
    This is necessary because Tweepy's media_upload method requires a file or BytesIO object.
    """
    response = requests.get(url)
    response.raise_for_status()  # Raises an HTTPError if the response was an error
    return BytesIO(response.content)

def post_to_twitter(tweet_text, image_url):
    """
    Posts content to Twitter, including an optional image. The image is downloaded
    from the provided URL and uploaded to Twitter before posting the tweet.
    """
    try:
        # Download the image from the URL
        image_bytes = download_image(image_url)
        
        # Upload the image to Twitter
        media = twitter_api.media_upload(filename='image.jpg', file=image_bytes)
        
        # Post the tweet with the image
        status = twitter_api.update_status(status=tweet_text, media_ids=[media.media_id_string])
        
        return f"https://twitter.com/user/status/{status.id}"
    except Exception as e:
        print(f"Error posting to Twitter: {e}")
        return None

@app.route('/post', methods=['GET'])
def run_bot_and_post():
    """
    Flask route handler to trigger the bot's full workflow: generating a prompt,
    creating an image, summarizing the prompt for a title, and posting to Reddit.
    Accessible via a GET request to the '/post' endpoint.
    """
    try:
        prompt = generate_prompt_with_chatgpt()
        image_url = generate_image_with_dalle(prompt)
        post_title = summarize_prompt_with_chatgpt(prompt)
        print("prompt:", prompt)
        print("image_url:", image_url)
        print("post_title:", post_title)
        tweet_url = post_to_twitter(post_title, image_url)
        if tweet_url:
            return jsonify({"message": "Image posted to Twitter successfully.", "link":  tweet_url, "prompt": prompt, "ïmage_url": image_url, "post_title": post_title }), 200
        else:
            return jsonify({"message": "Image was not posted to Twitter :(.", "prompt": prompt, "ïmage_url": image_url, "post_title": post_title }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Starts the Flask application on the specified port, defaulting to 8080.
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
