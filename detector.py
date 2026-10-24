"""
DeepShield detection engine (v2)

What changed vs v1:
- TWO pretrained deepfake models are combined (ensemble) instead of one.
- Each model scores the face crop AND the full image; the higher fake score is kept.
- A tunable threshold (default 0.40) makes the detector less likely to call fakes "Real".
- HEATMAP: occlusion-sensitivity map showing which regions push the model toward "fake".
- Raw model outputs are printed in the terminal so you can see what each model said.

Tuning (optional, set before `python app.py`):
    set DEEPSHIELD_THRESHOLD=0.35     lower = flags more things as Fake
    set DEEPSHIELD_MODELS=modelA,modelB
"""
import os
import io
import threading

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageOps, ImageDraw

MODELS = [m.strip() for m in os.environ.get(
    "DEEPSHIELD_MODELS",
    "prithivMLmods/Deep-Fake-Detector-v2-Model,dima806/deepfake_vs_real_image_detection"
).split(",") if m.strip()]
THRESHOLD = float(os.environ.get("DEEPSHIELD_THRESHOLD", "0.40"))
MAX_FRAMES = 16
GRID = 5  # heatmap resolution (5x5 = 25 extra model passes)

_pipes = {}
_lock = threading.Lock()
_face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def get_pipe(model_id=None):
    model_id = model_id or MODELS[0]
    with _lock:
        if model_id not in _pipes:
            from transformers import pipeline
            print(f"[DeepShield] Loading model: {model_id} (first run downloads it)")
            _pipes[model_id] = pipeline("image-classification", model=model_id)
            print(f"[DeepShield] Ready: {model_id}")
    return _pipes[model_id]


def load_all():
    for m in MODELS:
        get_pipe(m)


def crop_face(pil):
    gray = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2GRAY)
    faces = _face.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
    if len(faces) == 0:
        return pil, False
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    m = int(0.25 * max(w, h))
    box = (max(x - m, 0), max(y - m, 0), min(x + w + m, pil.width), min(y + h + m, pil.height))
    return pil.crop(box), True


def _fake_from(out):
    fake = [o["score"] for o in out if "fake" in o["label"].lower() or "ai" == o["label"].lower()]
    if fake:
        return float(sum(fake))
    real = [o["score"] for o in out if "real" in o["label"].lower()]
    if real:
        return 1.0 - float(sum(real))
    raise RuntimeError(f"Model labels not recognised: {[o['label'] for o in out]}")


def calibrate(p):
    """Map raw score so THRESHOLD becomes 0.5 (app.py calls >=0.5 'Fake')."""
    if p < THRESHOLD:
        return 0.5 * p / THRESHOLD
    return 0.5 + 0.5 * (p - THRESHOLD) / (1 - THRESHOLD)


def fake_probability(face_img, full_img=None):
    views = [face_img] + ([full_img] if full_img is not None and full_img is not face_img else [])
    per_model = []
    for mid in MODELS:
        pipe = get_pipe(mid)
        scores = []
        for v in views:
            out = pipe(v, top_k=None)
            print(f"[DeepShield] {mid}: {[(o['label'], round(o['score'], 3)) for o in out]}")
            scores.append(_fake_from(out))
        per_model.append(max(scores))
    raw = 0.5 * float(np.mean(per_model)) + 0.5 * max(per_model)
    return float(calibrate(raw))


def ela(pil, quality=90):
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    diff = ImageChops.difference(pil, Image.open(buf).convert("RGB"))
    peak = max(e[1] for e in diff.getextrema()) or 1
    return ImageEnhance.Brightness(diff).enhance(255.0 / peak)


def heatmap(pil):
    """Occlusion sensitivity: grey out one patch at a time and see how much the
    model's 'fake' score drops. Big drop = that region drives the 'fake' verdict."""
    base = pil.convert("RGB")
    base.thumbnail((448, 448))
    w, h = base.size
    pipe = get_pipe(MODELS[0])
    p0 = _fake_from(pipe(base, top_k=None))
    grey = tuple(int(v) for v in np.array(base).reshape(-1, 3).mean(0))
    cw, ch = w / GRID, h / GRID

    variants = []
    for gy in range(GRID):
        for gx in range(GRID):
            v = base.copy()
            ImageDraw.Draw(v).rectangle(
                [int((gx - .5) * cw), int((gy - .5) * ch), int((gx + 1.5) * cw), int((gy + 1.5) * ch)], fill=grey)
            variants.append(v)
    outs = pipe(variants, top_k=None, batch_size=8)
    drops = np.array([p0 - _fake_from(o) for o in outs], dtype=np.float32).reshape(GRID, GRID)

    drops = np.clip(drops, 0, None)
    drops = drops / max(float(drops.max()), 0.05)  # 0.05 floor: tiny effects are not blown up
    hm = cv2.resize(drops, (w, h), interpolation=cv2.INTER_CUBIC)
    hm = np.clip(cv2.GaussianBlur(hm, (0, 0), 12), 0, 1)
    color = cv2.cvtColor(cv2.applyColorMap((hm * 255).astype(np.uint8), cv2.COLORMAP_JET), cv2.COLOR_BGR2RGB)
    alpha = (0.75 * hm)[..., None]
    out = np.array(base) * (1 - alpha) + color * alpha
    return Image.fromarray(out.astype(np.uint8))


def _save_thumb(pil, path):
    t = pil.copy()
    t.thumbnail((360, 360))
    t.save(path, quality=85)


def analyze_image(path, stem, out_dir):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((1600, 1600))
    face_img, found = crop_face(img)
    p = fake_probability(face_img, img if found else None)

    ela_name, heat_name, thumb_name = f"{stem}_ela.jpg", f"{stem}_heat.jpg", f"{stem}_thumb.jpg"
    ela(img).save(os.path.join(out_dir, ela_name), quality=90)
    heatmap(face_img).save(os.path.join(out_dir, heat_name), quality=90)
    _save_thumb(img, os.path.join(out_dir, thumb_name))
    return dict(fake_prob=p, face_found=found, frames=[], ela=ela_name, heat=heat_name, thumb=thumb_name)


def analyze_video(path, stem, out_dir):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        raise RuntimeError("video has no readable frames")

    probs, faces, first, worst, worst_p = [], 0, None, None, -1
    for i in np.linspace(0, total - 1, min(MAX_FRAMES, total)).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok:
            continue
        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        pil.thumbnail((1280, 1280))
        first = first or pil.copy()
        crop, found = crop_face(pil)
        faces += int(found)
        p = fake_probability(crop)
        probs.append(p)
        if p > worst_p:
            worst_p, worst = p, crop
    cap.release()
    if not probs:
        raise RuntimeError("could not read any frames")

    thumb_name, heat_name = f"{stem}_thumb.jpg", f"{stem}_heat.jpg"
    _save_thumb(first, os.path.join(out_dir, thumb_name))
    heatmap(worst).save(os.path.join(out_dir, heat_name), quality=90)  # most suspicious frame
    return dict(fake_prob=float(np.mean(probs)), face_found=faces > 0,
                frames=[round(p, 4) for p in probs], ela=None, heat=heat_name, thumb=thumb_name)