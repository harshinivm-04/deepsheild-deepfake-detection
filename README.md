# DeepShield - AI-Based Deepfake Image & Video Detection

DeepShield is a Flask-based web application that detects potentially manipulated images and videos using a pretrained Vision Transformer (ViT) model. It includes user authentication, an interactive dashboard, and per-user scan history.

## Features

- **User Authentication:** Account creation and login with hashed passwords.
- **Interactive Dashboard:** Scan statistics, real-versus-fake distribution, and 14-day activity trends.
- **Image Detection:** Face cropping, prediction results, fake-probability scores, and Error Level Analysis (ELA) visualization.
- **Video Detection:** Samples 16 frames, analyzes individual frames, and displays a prediction timeline.
- **Scan History:** Search, filter, view, and delete previous scans, with CSV export support.
- **User-Specific History:** Keeps scan records organized by user.

## Technologies Used

- Python
- Flask
- PyTorch
- Hugging Face Transformers
- Vision Transformer (ViT)
- OpenCV
- NumPy
- Pillow
- HTML, CSS, and JavaScript
- SQLite

## How It Works

1. The user creates an account or logs in.
2. The user uploads an image or video for analysis.
3. For image analysis, the system uses face cropping and the trained detection model.
4. For video analysis, the system samples frames and combines per-frame fake probabilities.
5. The application displays the prediction and confidence information.
6. Scan results can be reviewed in the user's history.

## Installation

Clone or download this repository.

Create and activate a virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python app.py
```

Open `http://127.0.0.1:5000` in your browser.

The first run downloads the pretrained detection model, approximately 350 MB, and requires an internet connection.

## Model Details

The system uses a pretrained Vision Transformer fine-tuned for real-versus-fake face classification. OpenCV Haar Cascade is used for face cropping. Video detection samples frames and calculates the mean of their fake probabilities. Error Level Analysis provides an additional visual clue for image analysis.

## Limitations

- Predictions may be incorrect.
- Heavily compressed images and videos may reduce detection reliability.
- Non-face content may be less reliable because the model is designed for face classification.
- Error Level Analysis is an indicator, not definitive proof of manipulation.

## Project Status

Completed

## Disclaimer

This project is intended for educational and research purposes. Detection results should not be treated as definitive proof that media is authentic or manipulated.
