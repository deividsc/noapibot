"""
TTS engine stub — edge_tts removed for GCP deployment.
TTS is not available in the Cloud Run environment.
"""

DEFAULT_VOICE = "es-ES-AlvaroNeural"


async def generate_speech(text: str, output_path: str, voice: str = DEFAULT_VOICE) -> bool:
    return False


async def get_voices() -> list:
    return []
