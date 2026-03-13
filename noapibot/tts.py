"""
TTS engine for NoApiBot (Text-to-Speech via Edge TTS).
"""
import edge_tts

DEFAULT_VOICE = "es-ES-AlvaroNeural"


async def generate_speech(text: str, output_path: str, voice: str = DEFAULT_VOICE) -> bool:
    """Generate speech from text and save to output_path."""
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return True
    except Exception as e:
        print(f"TTS Error: {e}")
        return False


async def get_voices() -> list:
    """List all available Spanish voices."""
    voices = await edge_tts.list_voices()
    return [{"Name": v["Name"], "Gender": v["Gender"]} for v in voices if "es-" in v["Locale"]]
