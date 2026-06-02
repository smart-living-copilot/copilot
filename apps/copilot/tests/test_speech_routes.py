import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from copilot.core.settings import Settings
from copilot.speech.routes import router as speech_router


def _client(settings: Settings) -> TestClient:
    app = FastAPI()
    app.state.settings = settings
    app.include_router(speech_router)
    return TestClient(app)


class SpeechRoutesTestCase(unittest.TestCase):
    def test_tts_requires_internal_api_key_when_configured(self) -> None:
        with _client(Settings(internal_api_key="secret")) as client:
            response = client.post("/speech/tts", json={"text": "Hello"})

        self.assertEqual(response.status_code, 401)

    def test_tts_rejects_blank_text_after_trimming(self) -> None:
        with _client(Settings(internal_api_key="secret")) as client:
            response = client.post(
                "/speech/tts",
                json={"text": "   "},
                headers={"Authorization": "Bearer secret"},
            )

        self.assertEqual(response.status_code, 400)

    def test_tts_proxies_browser_playable_audio(self) -> None:
        upstream = httpx.Response(
            200,
            content=b"mp3-bytes",
            headers={"content-type": "audio/mpeg"},
        )
        settings = Settings(
            internal_api_key="secret",
            tts_speech_url="https://speech.example/v1/audio/speech",
            tts_model="tts-demo",
            tts_voice="thorsten",
            tts_speed=0.9,
        )

        with (
            _client(settings) as client,
            patch(
                "copilot.speech.routes._post_json",
                AsyncMock(return_value=upstream),
            ) as post_json,
        ):
            response = client.post(
                "/speech/tts",
                json={"text": "  Read this result.  "},
                headers={"Authorization": "Bearer secret"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"mp3-bytes")
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        post_json.assert_awaited_once()
        url, body = post_json.call_args.args
        self.assertEqual(url, "https://speech.example/v1/audio/speech")
        self.assertEqual(body["input"], "Read this result.")
        self.assertEqual(body["model"], "tts-demo")
        self.assertEqual(body["voice"], "thorsten")
        self.assertEqual(body["speed"], 0.9)
        self.assertEqual(body["response_format"], "mp3")
        self.assertEqual(post_json.call_args.kwargs["accept"], "audio/mpeg")

    def test_transcription_proxies_audio_upload(self) -> None:
        upstream = httpx.Response(
            200,
            json={"text": "The balcony door is closed."},
        )
        settings = Settings(
            internal_api_key="secret",
            stt_transcriptions_url="https://stt.example/v1/audio/transcriptions",
            stt_model="whisper-demo",
            stt_api_key="stt-secret",
            stt_language="en",
        )

        with (
            _client(settings) as client,
            patch(
                "copilot.speech.routes._post_multipart",
                AsyncMock(return_value=upstream),
            ) as post_multipart,
        ):
            response = client.post(
                "/speech/transcriptions",
                content=b"webm-bytes",
                headers={
                    "Authorization": "Bearer secret",
                    "Content-Type": "audio/webm",
                    "X-Filename": "answer.webm",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"text": "The balcony door is closed."})
        post_multipart.assert_awaited_once()
        url = post_multipart.call_args.args[0]
        self.assertEqual(url, "https://stt.example/v1/audio/transcriptions")
        self.assertEqual(
            post_multipart.call_args.kwargs["data"],
            {
                "model": "whisper-demo",
                "response_format": "text",
                "language": "en",
            },
        )
        filename, body, content_type = post_multipart.call_args.kwargs["files"]["file"]
        self.assertEqual(filename, "answer.webm")
        self.assertEqual(body, b"webm-bytes")
        self.assertEqual(content_type, "audio/webm")
        self.assertEqual(post_multipart.call_args.kwargs["api_key"], "stt-secret")
