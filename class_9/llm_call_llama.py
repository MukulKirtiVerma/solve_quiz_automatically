import os
import time
import random
import requests
import dotenv

dotenv.load_dotenv()

INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

STREAM = False

MODEL = "meta/llama-3.2-90b-vision-instruct"


def call_nvidia_api(payload, headers, max_retries=6):

    # Temporary errors that can be retried
    retry_statuses = {429, 500, 502, 503, 504}

    for attempt in range(1, max_retries + 1):

        try:
            print(f"\nSending request... Attempt {attempt}/{max_retries}")

            response = requests.post(
                INVOKE_URL,
                headers=headers,
                json=payload,
                stream=STREAM,
                timeout=180
            )

            # Success
            if response.status_code == 200:
                return response

            # Retry temporary errors
            if response.status_code in retry_statuses:

                print(f"\nTemporary API error: {response.status_code}")

                print("\nServer response:")
                print(response.text[:3000])

                if attempt == max_retries:
                    response.raise_for_status()

                # Exponential backoff
                wait_time = min(
                    (2 ** attempt) + random.uniform(0, 1),
                    60
                )

                print(f"\nRetrying in {wait_time:.1f} seconds...")

                time.sleep(wait_time)

                continue

            # Other errors should not be retried
            print(f"\nAPI Error: {response.status_code}")
            print(response.text)

            response.raise_for_status()

        except requests.exceptions.Timeout:

            print("\nRequest timed out.")

            if attempt == max_retries:
                raise

            wait_time = min(2 ** attempt, 60)

            print(f"Retrying in {wait_time} seconds...")

            time.sleep(wait_time)

        except requests.exceptions.RequestException as e:

            print(f"\nRequest failed: {e}")

            if attempt == max_retries:
                raise

            wait_time = min(2 ** attempt, 60)

            print(f"Retrying in {wait_time} seconds...")

            time.sleep(wait_time)

    raise RuntimeError("Maximum retries exceeded.")


def main():

    api_key = os.getenv("NVIDIA_API_KEY2")

    if not api_key:
        raise ValueError(
            "NVIDIA_API_KEY not found.\n\n"
            "Add this to your .env file:\n"
            "NVIDIA_API_KEY=your_api_key"
        )

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
        "messages": [
            {
                "role": "user",

                "content": [
                    {
                        "type": "image_url",

                        "image_url": {
                            "url": (
                                "https://assets.ngc.nvidia.com/"
                                "products/api-catalog/phi-3-5-vision/"
                                "example1a.jpg"
                            )
                        }
                    },

                    {
                        "type": "text",

                        "text": "Is there a car in this image?"
                    }
                ]
            }
        ],

        "model": MODEL,

        "frequency_penalty": 0,

        "max_tokens": 512,

        "presence_penalty": 0,

        "stream": STREAM,

        "temperature": 1,

        "top_p": 1
    }

    response = call_nvidia_api(
        payload,
        headers
    )

    print("\nRequest successful!\n")

    if STREAM:

        for line in response.iter_lines():

            if line:

                print(
                    line.decode("utf-8")
                )

    else:

        result = response.json()

        print("\nFULL RESPONSE:")
        print(result)

        # Print only the AI answer
        try:

            answer = (
                result["choices"][0]
                ["message"]["content"]
            )

            print("\n" + "=" * 60)
            print("AI ANSWER:")
            print("=" * 60)

            print(answer)

        except (KeyError, IndexError, TypeError):

            print(
                "\nCould not extract answer from response."
            )


if __name__ == "__main__":
    main()