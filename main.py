import os, uuid, shutil
from pathlib import Path
from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from services.story_generator import make_story
from services.image_generator import create_scene_image
from services.video_builder import build_video

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="ToonStory AI", description="Create children's storyboards and cartoon videos.")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "ok", "app": "ToonStory AI"}

@app.post("/api/story")
async def generate_story(payload: dict):
    topic = str(payload.get("topic", "A brave little rabbit")).strip()[:180]
    age = str(payload.get("age", "4-8"))[:20]
    language = str(payload.get("language", "English"))[:40]
    if not topic:
        return JSONResponse({"error": "Please enter a story idea."}, status_code=400)
    story = make_story(topic, age, language)
    project_id = uuid.uuid4().hex[:12]
    project_dir = OUTPUT_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    scenes = []
    for i, scene in enumerate(story["scenes"], start=1):
        filename = f"scene_{i}.png"
        try:
            create_scene_image(scene["visual"], project_dir / filename, i)
            scene["image"] = f"/outputs/{project_id}/{filename}"
        except Exception:
            scene["image"] = ""
        scenes.append(scene)
    story["scenes"] = scenes
    story["project_id"] = project_id
    story["script_file"] = f"/outputs/{project_id}/script.txt"
    (project_dir / "script.txt").write_text(
        story["title"] + "\n\n" + "\n\n".join(f"Scene {i+1}: {s['narration']}" for i, s in enumerate(scenes)),
        encoding="utf-8"
    )
    return story

@app.post("/api/video")
async def generate_video(payload: dict):
    project_id = str(payload.get("project_id", "")).strip()
    if not project_id or "/" in project_id or "\\" in project_id or not (OUTPUT_DIR / project_id).is_dir():
        return JSONResponse({"error": "Generate a story first, then try video export."}, status_code=400)
    project_dir = OUTPUT_DIR / project_id
    images = sorted(project_dir.glob("scene_*.png"))
    if not images:
        return JSONResponse({"error": "No scene images found. Generate the story again."}, status_code=400)
    output = project_dir / "story_video.mp4"
    try:
        build_video(images, output)
    except Exception as exc:
        return JSONResponse({"error": f"Video export failed: {str(exc)[:240]}. Try a shorter story or retry."}, status_code=500)
    return {"video_url": f"/outputs/{project_id}/story_video.mp4", "message": "Video created. This MVP exports a silent cartoon slideshow; narration is available through the browser's Read Aloud button."}

@app.get("/api/download/{project_id}/script")
async def download_script(project_id: str):
    if "/" in project_id or "\\" in project_id:
        return JSONResponse({"error": "Invalid project ID"}, status_code=400)
    path = OUTPUT_DIR / project_id / "script.txt"
    if not path.is_file():
        return JSONResponse({"error": "Script not found"}, status_code=404)
    return FileResponse(path, filename="toonstory-script.txt", media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
