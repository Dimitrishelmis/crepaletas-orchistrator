from datetime import datetime

from security import BASE_DIR, REPORT_DIR, safe_path
from agents import generate_with_ollama, generate_with_openai, looks_like_bad_greek
from db import save_generated_post

IMAGES_DIR = BASE_DIR / "assets" / "images"


def pick_image_for_topic(topic: str):
    topic_lower = topic.lower()

    keyword_map = {
        "kids": ["kids", "party", "children", "birthday", "παιδ"],
        "wedding": ["wedding", "γάμος", "γαμ"],
        "baptism": ["baptism", "βάπτιση", "βαπτισ"],
        "school": ["school", "σχολ"],
        "festival": ["festival", "food", "πανηγ", "φεστιβάλ"],
        "sweet": ["sweet", "γλυκ"],
        "savory": ["savory", "αλμυρ"],
    }

    if not IMAGES_DIR.exists():
        return None, None

    all_images = [
        img for img in IMAGES_DIR.glob("*")
        if img.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
    ]

    if not all_images:
        return None, None

    for label, words in keyword_map.items():
        if any(word in topic_lower for word in words):
            matching = [img for img in all_images if label in img.name.lower()]
            if matching:
                selected = matching[0]
                return selected.name, f"http://127.0.0.1:8000/assets/images/{selected.name}"

    selected = all_images[0]
    return selected.name, f"http://127.0.0.1:8000/assets/images/{selected.name}"


def build_marketing_prompt(topic: str, platform: str, language: str):
    return f"""
You are a professional social media marketer for Crepaletas in Greece.

Create a {platform} post in {language}.

Topic:
{topic}

Business context:
Η Crepaleta είναι γεμιστή βάφλα, γλυκιά ή αλμυρή. Δεν είναι παγωτό.
Είναι κατάλληλη για παιδικά πάρτι, βαπτίσεις, γάμους, σχολικές εκδηλώσεις, food festivals και private events.

Return ONLY this:

CAPTION:
Maximum 2 short Greek sentences.

HASHTAGS:
Maximum 6 hashtags.

CTA:
One short sentence.

Rules:
Write natural Greek as used in Greece.
Do not sound translated from English.
Do not over-explain.
Do not use long paragraphs.
Do not mention that you are AI.
Keep it short, clean, and ready to post.
"""


def generate_marketing_post(topic: str, platform: str = "Instagram", language: str = "Greek"):
    prompt = build_marketing_prompt(topic, platform, language)

    generated_text = generate_with_ollama(prompt)
    provider = "ollama"

    if looks_like_bad_greek(generated_text):
        polish_prompt = f"""
Rewrite the following Greek Instagram post so it sounds natural, short, and professional in Greece.

Rules:
- Keep it very short.
- Maximum 2 short sentences for the caption.
- Maximum 6 hashtags.
- Natural Greek only.
- No long explanations.
- Keep it suitable for Crepaletas, a filled waffle product for events.
- Do not mention that you are AI.

Text to improve:
{generated_text}
"""
        try:
            generated_text = generate_with_openai(polish_prompt)
            provider = "openai_fallback"
        except Exception:
            provider = "ollama_openai_failed"

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"post_{timestamp}.txt"
    file_path = safe_path(REPORT_DIR, filename)

    image_file, image_url = pick_image_for_topic(topic)

    content = (
        "Generated Marketing Post\n"
        f"Time: {timestamp}\n"
        f"Topic: {topic}\n"
        f"Platform: {platform}\n"
        f"Language: {language}\n"
        f"Provider: {provider}\n"
        f"Image file: {image_file}\n"
        f"Image URL: {image_url}\n\n"
        f"{generated_text}\n"
    )

    file_path.write_text(content, encoding="utf-8")

    post_id = save_generated_post(
        topic=topic,
        platform=platform,
        language=language,
        content=generated_text,
        file_path=str(file_path),
        image_file=image_file,
        image_url=image_url,
        provider=provider
    )

    return {
        "id": post_id,
        "created": True,
        "provider": provider,
        "file": str(file_path),
        "content": generated_text,
        "image_file": image_file,
        "image_url": image_url
    }
