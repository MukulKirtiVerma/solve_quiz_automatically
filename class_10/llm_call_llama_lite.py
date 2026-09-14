import os
import base64
import mimetypes
import requests
import dotenv

dotenv.load_dotenv()

invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"

stream = False

# =========================
# LOCAL IMAGE PATH
# =========================

image_path = "/Users/mukulkirtiverma/Downloads/Vishakha docs (1)/v_10th.jpg"


def encode_image(image_path):

    if not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Image not found:\n{image_path}"
        )

    # Detect image MIME type
    mime_type, _ = mimetypes.guess_type(image_path)

    if mime_type is None:
        mime_type = "image/jpeg"

    # Read and encode image
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(
            image_file.read()
        ).decode("utf-8")

    # Return Data URL
    return f"data:{mime_type};base64,{base64_image}"


# =========================
# ENCODE IMAGE
# =========================

print("Encoding image...")

image_data = encode_image(image_path)

print("Image encoded successfully")


# =========================
# API KEY
# =========================

api_key = os.getenv("NVIDIA_API_KEY_OLLAMA_LITE")

if not api_key:
    raise ValueError(
        "NVIDIA_API_KEY not found in .env file"
    )


# =========================
# HEADERS
# =========================

headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "text/event-stream" if stream else "application/json",
    "Content-Type": "application/json",
}


# =========================
# PAYLOAD
# =========================

payload = {
    "messages": [
        {
            "role": "user",

            "content": [
                {
                    "type": "image_url",

                    "image_url": {
                        "url": image_data
                    }
                },

                {
                    "type": "text",

                    "text": """
Analyze this image carefully.

Please tell me:

1. What is shown in the image?
2. Extract ALL visible text.
3. Identify important information.
4. Provide a clear summary.
"""
                }
            ]
        }
    ],

    "model": "meta/llama-3.2-11b-vision-instruct",

    "frequency_penalty": 0,

    "max_tokens": 2048,

    "presence_penalty": 0,

    "stream": stream,

    "temperature": 0.2,

    "top_p": 0.95
}


# =========================
# SEND REQUEST
# =========================

try:

    print("Sending request to NVIDIA API...")

    response = requests.post(
        invoke_url,
        headers=headers,
        json=payload,
        stream=stream,
        timeout=180
    )

    print("Status Code:", response.status_code)

    # Print error before raising exception
    if response.status_code != 200:

        print("\nERROR RESPONSE:")
        print(response.text)

        response.raise_for_status()


    # =========================
    # STREAM RESPONSE
    # =========================

    if stream:

        for line in response.iter_lines():

            if line:

                print(
                    line.decode("utf-8")
                )


    # =========================
    # NORMAL RESPONSE
    # =========================

    else:

        result = response.json()

        print("\nFULL RESPONSE:")
        print(result)

        try:

            answer = result["choices"][0]["message"]["content"]

            print("\n" + "=" * 70)
            print("AI ANSWER")
            print("=" * 70)

            print(answer)

        except (KeyError, IndexError, TypeError):

            print(
                "\nCould not extract AI answer."
            )


except requests.exceptions.RequestException as e:

    print("\nREQUEST FAILED:")
    print(e)