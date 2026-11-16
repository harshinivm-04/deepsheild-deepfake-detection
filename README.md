# DeepShield - AI-Based Deepfake Image & Video Detection

Flask web app with login, per-user scan history, an interactive dashboard,
real-world photo detection and video detection.

## Folder structure
```
DeepShield/
  app.py            Flask backend (auth, API, history DB)
  detector.py       Detection engine (pretrained ViT + face crop + ELA + video frames)
  requirements.txt
  templates/        login.html, dashboard.html
  static/           css/style.css, js/app.js
  uploads/          created automatically (your scanned files)
  deepshield.db     created automatically (users + history)
```

## Run it
```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000 -> Create account -> New scan.

First start downloads the model (~350 MB, needs internet, one time only).
Watch the terminal for "Model ready" before your first scan.

## Features
- Sign in / create account (hashed passwords, private per-user history)
- Overview: live counters, real-vs-fake donut (click a slice to filter history), 14-day trend
- New scan: drag & drop photo or video, scanning animation, animated confidence ring
- Photos: face crop, verdict, fake-probability meter, Error-Level-Analysis map toggle
- Videos: 16 frames sampled, per-frame timeline chart, click a point to jump the video
- History: search, filter (Real / Fake / Photos / Videos), open details, delete, export CSV

## Swap the model (optional)
```bash
set DEEPSHIELD_MODEL=prithivMLmods/Deep-Fake-Detector-v2-Model
```

## Viva notes
- Model: pretrained Vision Transformer fine-tuned for real-vs-fake faces (transfer learning)
- Face cropping: OpenCV Haar cascade, since the model is trained on faces
- Video: frame sampling + mean of per-frame fake probability
- ELA: re-saves as JPEG and amplifies the difference; a hint, not proof
- Limits: no detector is perfect; heavily compressed or non-face content is less reliable
