"""
NVIDIA Nemotron: Generalized AI Video Story & Prompt Generator
==============================================================

Install:
    pip install requests python-dotenv

Create a .env file:
    NVIDIA_API_KEY=your_nvidia_api_key

Run:
    python video_story_generator.py

The script supports:
1. Random story generation
2. Custom story input
3. Detailed scene-by-scene video prompts
4. JSON and TXT output
5. Optional reference image URL
"""

import os
import json
import random
import argparse
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

load_dotenv()

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL_NAME = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

API_KEY = os.getenv("nemotron-3-nano-omni-30b-a3b-reasoning")

if not API_KEY:
    raise RuntimeError(
        "NVIDIA_API_KEY is missing.\n"
        "Create a .env file containing:\n"
        "NVIDIA_API_KEY=your_actual_api_key"
    )


# ------------------------------------------------------------
# Random story generator
# ------------------------------------------------------------

RANDOM_STORY_ELEMENTS = {
    "protagonists": [
        "a curious nine-year-old girl named Tara",
        "a brave ten-year-old boy named Arin",
        "a small robot named Kibo",
        "a young fox named Ember",
        "an inventive village girl named Meera",
        "a shy dragon named Nilo",
    ],
    "settings": [
        "a quiet village beside an ancient forest",
        "a futuristic city floating above the clouds",
        "a mysterious island surrounded by glowing water",
        "a snowy mountain village",
        "an abandoned lighthouse beside a stormy sea",
        "a magical library hidden beneath an old town",
    ],
    "objects": [
        "a glowing blue seed",
        "a broken mechanical bird",
        "a tiny fallen star",
        "an ancient golden compass",
        "a mysterious music box",
        "a crystal containing a trapped light",
    ],
    "companions": [
        "a friendly fox",
        "a small flying drone",
        "a wise old owl",
        "a playful cloud creature",
        "a loyal mechanical dog",
        "a luminous butterfly",
    ],
    "goals": [
        "return it to its rightful home before sunrise",
        "restore its lost power before the village loses its light",
        "deliver it to the top of a distant mountain",
        "solve the mystery of its origin",
        "protect it from an approaching storm",
        "use it to save a forgotten place",
    ],
    "themes": [
        "friendship and courage",
        "hope and kindness",
        "curiosity and discovery",
        "teamwork and responsibility",
        "believing in oneself",
        "protecting nature",
    ],
}


def generate_random_story():
    """Create a new original story premise from random components."""

    protagonist = random.choice(RANDOM_STORY_ELEMENTS["protagonists"])
    setting = random.choice(RANDOM_STORY_ELEMENTS["settings"])
    object_name = random.choice(RANDOM_STORY_ELEMENTS["objects"])
    companion = random.choice(RANDOM_STORY_ELEMENTS["companions"])
    goal = random.choice(RANDOM_STORY_ELEMENTS["goals"])
    theme = random.choice(RANDOM_STORY_ELEMENTS["themes"])

    story = f"""
The main character is {protagonist}, who lives near {setting}.
One day, the character discovers {object_name}. The object contains
a hidden secret and needs help.

During the journey, the character meets {companion}. Together, they
travel through unfamiliar places, overcome a difficult obstacle, and
discover that the real challenge is connected to {theme}.

The story builds toward a meaningful climax in which they must
{goal}. The ending should be emotional, visually memorable, hopeful,
and suitable for a family audience.

Central theme: {theme}.
"""

    title = f"The Secret of {object_name.title()}"

    return title, story.strip()


# ------------------------------------------------------------
# User configuration
# ------------------------------------------------------------

def create_video_request(args):
    """Build the complete video request from command-line arguments."""

    if args.random_story:
        title, story = generate_random_story()
    elif args.story:
        title = args.title or "Custom Story"
        story = args.story
    else:
        title = "The Little Girl and the Lost Star"
        story = """
A nine-year-old girl named Mira lives in a small village near a forest.
One evening, she discovers a tiny fallen star glowing beside a river.
The star is weak and wants to return to the sky.

Mira travels through the forest, meets a friendly fox, crosses an old
wooden bridge, and reaches a hilltop. There, she helps the star return
to the night sky.

The story should feel emotional, magical, hopeful, and suitable for
children.
"""

    return {
        "title": title,
        "story": story,
        "duration_seconds": args.duration,
        "language": args.language,
        "video_style": args.style,
        "visual_quality": args.quality,
        "aspect_ratio": args.aspect_ratio,
        "target_video_model": args.target_model,
        "audience": args.audience,
        "number_of_scenes": args.scenes,
        "frame_rate": args.fps,
        "dialogue_required": not args.no_dialogue,
        "voiceover_required": not args.no_voiceover,
        "music_required": not args.no_music,
        "sound_effects_required": not args.no_sfx,
        "character_consistency_required": True,
        "reference_image_url": args.reference_image_url,
        "negative_prompt": """
low quality, blurry image, distorted anatomy, extra fingers,
inconsistent faces, changing clothes, changing character age,
flickering, jittery motion, unwanted text, subtitles, watermark,
logo, random objects, inconsistent lighting, broken perspective,
unnatural physics, duplicated characters
""",
        "additional_instructions": """
Maintain the same character appearance, clothing, age, proportions,
and color palette throughout all scenes. Maintain continuity of
locations, props, time of day, and lighting.

Every scene must logically continue from the previous scene.
Use clear visual storytelling, physically plausible movement,
cinematic composition, and expressive but natural acting.

Do not imitate a living artist's exact style. Do not use copyrighted
characters or copyrighted dialogue.
""",
    }


# ------------------------------------------------------------
# Prompt construction
# ------------------------------------------------------------

def build_prompt(video_request):
    request_json = json.dumps(
        video_request,
        indent=2,
        ensure_ascii=False
    )

    return f"""
You are an expert film director, screenwriter, storyboard artist,
cinematographer, animation director, sound designer, and AI
text-to-video prompt engineer.

Convert the following story and production requirements into a
complete, production-ready video-generation blueprint.

Return VALID JSON ONLY. Do not use Markdown fences.
Do not add explanations outside the JSON.

GENERAL REQUIREMENTS:
1. Respect the requested total duration.
2. Divide the story into logical scenes.
3. Scene durations must add up exactly to the requested duration.
4. Use the requested number of scenes when practical.
5. Keep the story understandable through visuals.
6. Preserve character identity and prop continuity.
7. Make each video prompt independently usable.
8. Do not claim that you rendered an actual video.
9. If dialogue is enabled, keep dialogue short enough for the scene.
10. If voiceover is enabled, write natural narration that fits the timing.
11. Use cinematic but concrete descriptions rather than vague adjectives.
12. Do not introduce unexplained characters, props, or locations.
13. Make action, movement, lighting, and physics plausible.
14. Keep the story suitable for the specified audience.
15. Do not use copyrighted characters or copyrighted dialogue.

TOP-LEVEL JSON FIELDS:
- project_title
- creative_summary
- story_logline
- estimated_total_duration_seconds
- aspect_ratio
- frame_rate
- language
- visual_style
- target_video_model
- global_character_bible
- global_world_bible
- global_visual_rules
- global_negative_prompt
- scene_list
- complete_voiceover_script
- complete_dialogue_script
- music_and_sound_design
- editing_and_postproduction_notes
- quality_control_checklist

CHARACTER BIBLE:
For every important character include:
- name
- approximate_age
- physical_appearance
- hairstyle_or_body_features
- clothing
- color_palette
- personality
- facial_expression_guidelines
- movement_guidelines
- continuity_rules

WORLD BIBLE:
Include:
- primary_locations
- architecture
- landscape
- weather
- time_period
- recurring_props
- environmental_color_palette
- lighting_rules

SCENE LIST:
For every scene include:
- scene_id
- start_time
- end_time
- duration_seconds
- scene_goal
- story_beat
- location
- time_of_day
- weather
- environment_description
- characters_present
- character_actions
- emotions
- camera_shot
- camera_angle
- camera_movement
- lens_or_visual_perspective
- composition
- lighting
- color_palette
- motion_and_physics
- dialogue
- voiceover
- sound_effects
- background_music
- transition_to_next_scene
- continuity_notes
- image_generation_prompt
- video_generation_prompt
- negative_prompt

VIDEO GENERATION PROMPT:
Each prompt must be self-contained and detailed. Include:
- character appearance
- environment
- action
- facial expressions
- body movement
- camera framing
- camera movement
- lighting
- atmosphere
- visual style
- temporal progression
- continuity requirements

The video-generation prompt must not depend on the model reading
another scene's prompt.

INPUT VIDEO REQUEST:
{request_json}
"""


# ------------------------------------------------------------
# NVIDIA API call
# ------------------------------------------------------------

def call_nvidia(prompt):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional video pre-production assistant. "
                    "Return only valid JSON when JSON is requested."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_tokens": 65536,
        "reasoning_budget": 16384,
        "temperature": 0.6,
        "top_p": 0.95,
        "stream": False,
    }

    response = requests.post(
        NVIDIA_API_URL,
        headers=headers,
        json=payload,
        timeout=900,
    )

    if not response.ok:
        raise RuntimeError(
            f"NVIDIA API error {response.status_code}:\n"
            f"{response.text}"
        )

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            "Unexpected API response:\n" +
            json.dumps(data, indent=2)
        )

    return parse_json_response(content)


def parse_json_response(content):
    """Parse JSON even if the model accidentally adds code fences."""

    content = content.strip()

    if content.startswith("```"):
        lines = content.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(lines).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Attempt to extract the largest JSON object.
        start = content.find("{")
        end = content.rfind("}")

        if start != -1 and end > start:
            candidate = content[start:end + 1]

            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        return {
            "parse_error": True,
            "raw_model_output": content,
        }


# ------------------------------------------------------------
# Output generation
# ------------------------------------------------------------

def save_json(data, path):
    Path(path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def scene_to_text(scene):
    lines = []

    lines.append(
        f"\nSCENE {scene.get('scene_id', '')} "
        f"[{scene.get('start_time', '')} - {scene.get('end_time', '')}]"
    )
    lines.append("=" * 80)

    ordered_fields = [
        "scene_goal",
        "story_beat",
        "location",
        "time_of_day",
        "environment_description",
        "characters_present",
        "character_actions",
        "emotions",
        "camera_shot",
        "camera_angle",
        "camera_movement",
        "lens_or_visual_perspective",
        "composition",
        "lighting",
        "color_palette",
        "motion_and_physics",
        "dialogue",
        "voiceover",
        "sound_effects",
        "background_music",
        "transition_to_next_scene",
        "continuity_notes",
        "image_generation_prompt",
        "video_generation_prompt",
        "negative_prompt",
    ]

    for field in ordered_fields:
        if field in scene:
            value = scene[field]

            if isinstance(value, (dict, list)):
                value = json.dumps(
                    value,
                    indent=2,
                    ensure_ascii=False
                )

            lines.append(f"\n{field.upper()}:\n{value}")

    return "\n".join(lines)


def create_text_report(plan, video_request):
    lines = []

    lines.append("AI VIDEO PRODUCTION BLUEPRINT")
    lines.append("=" * 80)
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append(f"Title: {video_request['title']}")
    lines.append(f"Duration: {video_request['duration_seconds']} seconds")
    lines.append(f"Style: {video_request['video_style']}")
    lines.append(f"Language: {video_request['language']}")
    lines.append(f"Aspect ratio: {video_request['aspect_ratio']}")
    lines.append("")

    for field in [
        "creative_summary",
        "story_logline",
        "global_character_bible",
        "global_world_bible",
        "global_visual_rules",
        "complete_voiceover_script",
        "complete_dialogue_script",
        "music_and_sound_design",
        "editing_and_postproduction_notes",
        "quality_control_checklist",
    ]:
        if field in plan:
            lines.append(f"\n{field.upper()}")
            lines.append("-" * 80)

            value = plan[field]

            if isinstance(value, (dict, list)):
                value = json.dumps(
                    value,
                    indent=2,
                    ensure_ascii=False
                )

            lines.append(str(value))

    for scene in plan.get("scene_list", []):
        lines.append(scene_to_text(scene))

    return "\n".join(lines)


# ------------------------------------------------------------
# Command-line interface
# ------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate AI video stories and scene prompts with NVIDIA Nemotron."
    )

    parser.add_argument(
        "--random-story",
        action="store_true",
        help="Generate a new random story premise."
    )

    parser.add_argument(
        "--title",
        default=None,
        help="Title for a custom story."
    )

    parser.add_argument(
        "--story",
        default=None,
        help="Custom story text."
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Total video duration in seconds."
    )

    parser.add_argument(
        "--scenes",
        type=int,
        default=8,
        help="Requested number of scenes."
    )

    parser.add_argument(
        "--language",
        default="English",
        help="Output language."
    )

    parser.add_argument(
        "--style",
        default="cinematic 3D animated fantasy",
        help="Visual style."
    )

    parser.add_argument(
        "--quality",
        default="high-detail, polished, feature-film quality",
        help="Visual quality description."
    )

    parser.add_argument(
        "--aspect-ratio",
        default="16:9",
        help="Video aspect ratio."
    )

    parser.add_argument(
        "--fps",
        type=int,
        default=24,
        help="Frame rate."
    )

    parser.add_argument(
        "--target-model",
        default="a modern text-to-video model",
        help="Target video-generation model."
    )

    parser.add_argument(
        "--audience",
        default="children and families",
        help="Target audience."
    )

    parser.add_argument(
        "--reference-image-url",
        default=None,
        help="Optional reference image URL for planning context."
    )

    parser.add_argument(
        "--no-dialogue",
        action="store_true",
        help="Disable character dialogue."
    )

    parser.add_argument(
        "--no-voiceover",
        action="store_true",
        help="Disable voiceover."
    )

    parser.add_argument(
        "--no-music",
        action="store_true",
        help="Disable background music."
    )

    parser.add_argument(
        "--no-sfx",
        action="store_true",
        help="Disable sound effects."
    )

    parser.add_argument(
        "--output-dir",
        default="video_output",
        help="Directory for generated files."
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.duration <= 0:
        raise ValueError("Duration must be greater than zero.")

    if args.scenes <= 0:
        raise ValueError("Number of scenes must be greater than zero.")

    video_request = create_video_request(args)

    print("\nGenerating video blueprint with NVIDIA Nemotron...")
    print(f"Title: {video_request['title']}")
    print(f"Duration: {video_request['duration_seconds']} seconds")
    print(f"Scenes: {video_request['number_of_scenes']}")

    prompt = build_prompt(video_request)
    plan = call_nvidia(prompt)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "video_plan.json"
    txt_path = output_dir / "video_plan.txt"
    request_path = output_dir / "video_request.json"

    save_json(plan, json_path)
    save_json(video_request, request_path)

    report = create_text_report(plan, video_request)
    txt_path.write_text(report, encoding="utf-8")

    print("\nGeneration complete.")
    print(f"JSON plan: {json_path.resolve()}")
    print(f"Text report: {txt_path.resolve()}")
    print(f"Input request: {request_path.resolve()}")

    if plan.get("parse_error"):
        print(
            "\nWARNING: The model response was not valid JSON. "
            "Check video_plan.json for the raw output."
        )


if __name__ == "__main__":
    main()
