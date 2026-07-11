"""
SLINGSHOT FastAPI server — main.py
==================================
Wires ADK's LiveRequestQueue to the browser over a WebSocket (audio + video + text
up; audio + transcripts + tool render_commands down). The real-time task lifecycle
(FIRST_EXCEPTION, aclosing, per-connection queue) follows the standard ADK Live-API
streaming pattern (framework boilerplate). The domain (multi-agent planetary defense) and
everything it renders is new SLINGSHOT work.

Run:  cd app && uvicorn main:app --reload
"""
import asyncio
import base64
from contextlib import aclosing
import json
import logging
import os

from dotenv import load_dotenv
# load_dotenv before importing the agent package so env (model, project) is set at import.
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.genai import types

from slingshot_mission import root_agent, log_ai_interaction

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("slingshot")

APP_NAME = "slingshot"
DEMO_AGENT_MODEL = os.environ.get("DEMO_AGENT_MODEL", "")

session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)

app = FastAPI(title="SLINGSHOT — Planetary Defense Mission Control")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def console():
    """Serve the mission-control console."""
    return FileResponse("static/index.html")


@app.get("/api/health")
async def health():
    # NB: not "/healthz" — Google Front End reserves that path and 404s it before it
    # reaches the app. "/api/health" reaches the app normally.
    return {"status": "ok", "app": APP_NAME, "model": DEMO_AGENT_MODEL}


@app.post("/api/briefing")
async def api_briefing(request: Request):
    """Generate a threat-briefing image (NB2 Lite) for a NEO. Returns {kind, src, caption}.
    Used by the console's INTEL step so the briefing is really generated, not mocked."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    os.makedirs("static/assets/gen", exist_ok=True)
    from slingshot_mission import media, data
    neo = body if body.get("name") else data.get_cached_neo()
    return await asyncio.to_thread(media.generate_briefing_image, neo)


@app.post("/api/impact")
async def api_impact(request: Request):
    """Generate an impact/deflection simulation (Omni Flash) for a NEO. Returns {kind, src, caption}."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    os.makedirs("static/assets/gen", exist_ok=True)
    from slingshot_mission import media, data
    neo = body if body.get("name") else data.get_cached_neo()
    return await asyncio.to_thread(media.generate_impact_video, neo, bool(body.get("deflected", True)))


@app.websocket("/ws/{user_id}/{session_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, session_id: str):
    """One WebSocket per Flight session. Two concurrent tasks bridge browser <-> Gemini."""
    await websocket.accept()
    logger.info("WebSocket connected: user=%s session=%s", user_id, session_id)

    # Audio-capable models: native-audio OR the Live preview models ('live' in the id).
    model_l = DEMO_AGENT_MODEL.lower()
    is_audio = any(k in model_l for k in ("native", "live", "audio"))

    if is_audio:
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")  # deep male mission-control voice
                )
            ),
        )
    else:
        run_config = RunConfig(streaming_mode=StreamingMode.BIDI, response_modalities=["TEXT"])

    session = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if session is None:
        session = await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        logger.info("Created session %s", session_id)

    live_request_queue = LiveRequestQueue()

    async def upstream_task():
        """Browser -> Gemini: buffered PCM audio (100ms), JPEG frames, and text."""
        _CHUNK = 3200  # 100ms @ 16kHz s16le mono
        buf = bytearray()
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                buf.extend(message["bytes"])
                while len(buf) >= _CHUNK:
                    chunk = bytes(buf[:_CHUNK]); del buf[:_CHUNK]
                    live_request_queue.send_realtime(types.Blob(data=chunk, mime_type="audio/pcm"))
            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "text" and payload.get("content"):
                    live_request_queue.send_content(
                        types.Content(role="user", parts=[types.Part(text=payload["content"])]))
                elif payload.get("type") == "image_frame" and payload.get("data"):
                    b64 = payload["data"].split(",", 1)[-1]
                    live_request_queue.send_realtime(types.Blob(data=base64.b64decode(b64), mime_type="image/jpeg"))

    async def downstream_task():
        """Gemini -> Browser: events (audio, transcripts, function-call render_commands)."""
        _flight_said, _capcom_said = "", ""
        async with aclosing(runner.run_live(
            session=session, live_request_queue=live_request_queue, run_config=run_config,
        )) as live_events:
            try:
                async for event in live_events:
                    event_json = event.model_dump_json(exclude_none=True, by_alias=True)
                    await websocket.send_text(event_json)
                    ev = json.loads(event_json)
                    it = (ev.get("inputTranscription", {}) or {}).get("text")
                    ot = (ev.get("outputTranscription", {}) or {}).get("text")
                    if it: _flight_said = it
                    if ot: _capcom_said = ot
                    if ev.get("turnComplete") or ev.get("turn_complete"):
                        entry = log_ai_interaction(_flight_said, _capcom_said)
                        if entry:
                            await websocket.send_text(json.dumps({"type": "ai_log", "entry": entry}))
                        _flight_said, _capcom_said = "", ""
            except (ValueError, KeyError, TypeError) as exc:
                logger.warning("Recoverable live error: %s", exc)
                try:
                    await websocket.send_text(json.dumps({"type": "error", "message": f"Session error: {exc}"}))
                except Exception:
                    pass
                raise

    up = asyncio.create_task(upstream_task())
    down = asyncio.create_task(downstream_task())
    done, pending = await asyncio.wait([up, down], return_when=asyncio.FIRST_EXCEPTION)
    try:
        for task in done:
            task.result()
    except WebSocketDisconnect:
        logger.info("Client disconnected: %s", session_id)
    except Exception as exc:
        logger.error("Live session error %s: %s", session_id, exc, exc_info=True)
    finally:
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        live_request_queue.close()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("Session closed: %s", session_id)
