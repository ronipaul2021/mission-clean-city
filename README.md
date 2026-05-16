# 🏙️ Mission Clean City - Birnagar Municipality
> **Elite Civic Governance & AI-Augmented Platform for a Smarter Birnagar**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.0+-green.svg)](https://www.djangoproject.com/)
[![AI](https://img.shields.io/badge/AI-Google_Gemini-orange.svg)](https://deepmind.google/technologies/gemini/)
[![Security](https://img.shields.io/badge/Security-Aadhaar_Encrypted-red.svg)](#security--privacy)

**Mission Clean City** is a state-of-the-art civic management ecosystem designed for the **Birnagar Municipality (Nadia, West Bengal)**. It bridges the gap between citizens and administration by leveraging Artificial Intelligence to professionalize civic reporting and ensure data-driven governance.

---

## 💎 Pro Features

### 🤖 Intelligent Core (Birni AI)
*   **AI Writing Assistant**: Automatically transforms informal citizen notes into structured, professional municipal reports using **Google Gemini 1.5 Flash**.
*   **Birni Chatbot**: A 24/7 civic assistant pre-trained on municipal protocols, ward systems (14 Wards), and contact directories.
*   **Dual-Path Resilience**: Hybrid AI architecture utilizing the Bytez Unified API with a direct Google Gemini fallback for 100% uptime.

### 🗺️ GIS & Visual Infrastructure
*   **Real-time Incident Mapping**: Integrated Leaflet-based GIS interface allowing citizens to pin exact locations.
*   **Auto-Geocoding**: Automatic address resolution from map coordinates to streamline administrative dispatch.
*   **Smart Media Processing**: AI-powered face detection for profile photos and automated image compression (under 75KB) for storage efficiency.

### 📊 Executive Analytics Dashboard
*   **Ward-wise KPIs**: Interactive charts (Chart.js) tracking complaint density and resolution rates across all 14 wards.
*   **Work Order Engine**: One-click professional PDF/Print generation for field workers and administrative review.
*   **Citizen Directory**: Advanced filtering system to manage verified residents.

---

## 🛠️ Technical Stack

*   **Backend**: Python / Django (Robust, Scalable, Secure)
*   **Frontend**: Vanilla JavaScript (ES6+), Premium CSS3 (Glassmorphism), Tailwind Design Patterns.
*   **AI Engine**: Google Gemini Pro / Flash via REST integration.
*   **Database**: SQLite (Default) with Production-ready PostgreSQL schema.
*   **GIS**: Leaflet.js / OpenStreetMap / Google Maps Tiles.

---

## 🛡️ Security & Privacy (Pro Grade)

*   **Aadhaar Encryption**: Sensitive identifiers are protected at rest using **Fernet Symmetric Encryption**.
*   **Key Rotation Support**: Built-in support for rotating encryption keys without data loss.
*   **OTP Verification**: Multi-flow OTP system (Registration, Password Reset, Email Update) using secure SMTP.
*   **Rate Limiting**: Session-based upload protection and login lockout mechanisms to prevent brute-force attacks.

---

## 🚀 Setup & Installation

### 1. Environment Setup
```bash
# Clone and enter directory
git clone https://github.com/ronipaul2021/mission-clean-city.git
cd mission-clean-city

# Create Virtual Environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install Dependencies
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file in the root directory:
```env
# Core
SECRET_KEY=your_secure_key
DEBUG=True

# AI Configuration
BYTEZ_API_KEY=your_key
GEMINI_API_KEY=your_key

# Email (SMTP)
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com

# Encryption
AADHAAR_ENCRYPTION_KEY=generate_using_fernet
```

### 3. Initialize
```bash
python manage.py migrate
python manage.py createsuperuser  # For Django admin access
python manage.py runserver
```

---

## 🏛️ Municipality Alignment
This platform is architected to support the **"Nirmal Bangla"** vision, ensuring that Birnagar remains a pioneer in digital urban cleanliness and citizen satisfaction in the Nadia district.

---
**Developed for Birnagar Municipality** | *Empowering Citizens, Enabling Administration.*
