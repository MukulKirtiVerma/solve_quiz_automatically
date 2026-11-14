import os
import base64
import mimetypes
import time
import random
import requests
import dotenv

dotenv.load_dotenv()

INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

STREAM = False

IMAGE_PATH = "/Users/mukulkirtiverma/Downloads/Vishakha docs (1)/v_10th.jpg"

MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"


def encode_image(image_path):
    """Convert local image to base64 data URL."""

    if not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Image file not found:\n{image_path}"
        )

    mime_type, _ = mimetypes.guess_type(image_path)

    if mime_type is None:
        mime_type = "image/jpeg"

    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(
            image_file.read()
        ).decode("utf-8")

    return f"data:{mime_type};base64,{base64_image}"


def call_nvidia_api(payload, headers, max_retries=6):
    """
    Call NVIDIA API with automatic retry for temporary server errors.
    """

    retry_statuses = {429, 500, 502, 503, 504}

    for attempt in range(1, max_retries + 1):

        try:
            print(
                f"\nSending request... "
                f"Attempt {attempt}/{max_retries}"
            )

            response = requests.post(
                INVOKE_URL,
                headers=headers,
                json=payload,
                timeout=180
            )

            # Success
            if response.status_code == 200:
                return response

            # Retry temporary server/rate-limit errors
            if response.status_code in retry_statuses:

                print(
                    f"Temporary API error: "
                    f"{response.status_code}"
                )

                print("Response:")
                print(response.text[:2000])

                if attempt == max_retries:
                    response.raise_for_status()

                # Exponential backoff + small random delay
                wait_time = min(
                    2 ** attempt + random.uniform(0, 1),
                    60
                )

                print(
                    f"Retrying in {wait_time:.1f} seconds..."
                )

                time.sleep(wait_time)
                continue

            # Non-retryable error
            print(
                f"\nAPI Error: {response.status_code}"
            )
            print(response.text)

            response.raise_for_status()

        except requests.exceptions.Timeout:

            print("Request timed out.")

            if attempt == max_retries:
                raise

            wait_time = min(2 ** attempt, 60)

            print(
                f"Retrying in {wait_time} seconds..."
            )

            time.sleep(wait_time)

        except requests.exceptions.RequestException as e:

            print(f"Request failed: {e}")

            if attempt == max_retries:
                raise

            wait_time = min(2 ** attempt, 60)

            print(
                f"Retrying in {wait_time} seconds..."
            )

            time.sleep(wait_time)

    raise RuntimeError(
        "Maximum retries exceeded."
    )


def main():

    # Check API key
    api_key = os.getenv("NVIDIA_API_KEY")

    if not api_key:
        raise ValueError(
            "NVIDIA_API_KEY is missing.\n"
            "Add it to your .env file:\n\n"
            "NVIDIA_API_KEY=your_api_key_here"
        )

    print("Encoding image...")

    image_data = encode_image(IMAGE_PATH)

    print("Image encoded successfully.")
    print(f"Image data size: {len(image_data):,} characters")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": (
            "text/event-stream"
            if STREAM
            else "application/json"
        ),
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,

        "messages": [
            {
                "role": "user",

                "content": [
                    {
                        "type": "text",

                        "text": """
Analyze this image carefully.

Please provide:

1. What is shown in the image?
2. Extract ALL visible text exactly as accurately as possible.
3. Summarize the important information.
4. If this is an educational certificate, document, marksheet,
   ID, or form, identify its important fields and values.

Return the result in a clear structured format.
"""
                    },

                    {
                        "type": "image_url",

                        "image_url": {
                            "url": image_data
                        }
                    }
                ]
            }
        ],

        # Much more reasonable for image analysis
        "max_tokens": 4096,

        # Reduce unnecessary reasoning load
        "reasoning_budget": 2048,

        "stream": STREAM,

        "temperature": 0.2,
        "top_p": 0.95
    }

    response = call_nvidia_api(
        payload=payload,
        headers=headers
    )

    print("\nRequest successful!\n")

    if STREAM:

        for line in response.iter_lines():

            if line:

                decoded = line.decode("utf-8")

                print(decoded)

    else:

        result = response.json()

        # Print the complete API response
        print(result)

        # Print only the model answer
        try:

            answer = (
                result["choices"][0]
                ["message"]
                ["content"]
            )

            print("\n" + "=" * 80)
            print("MODEL ANSWER")
            print("=" * 80)
            print(answer)

        except (
            KeyError,
            IndexError,
            TypeError
        ):

            print(
                "\nCould not extract message content."
            )


if __name__ == "__main__":
    main()