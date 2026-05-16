# 🏙️ Mission Clean City - Birnagar Municipality
**Advanced Civic Management & AI-Powered Support Platform**

Mission Clean City is a comprehensive digital platform designed for **Birnagar Municipality** to streamline civic operations, waste management, and citizen engagement. It features a professional administration dashboard and an intelligent AI assistant to serve the community 24/7.

---

## 🛠️ Technology Stack

| Category | Technology |
| :--- | :--- |
| **Frontend** | HTML5, JavaScript (Vanilla), TailwindCSS/CSS3 |
| **Backend** | Python 3.x, Django 5.x |
| **AI Engine** | Birni AI (Bytez Proxy + Google Gemini Flash) |
| **Database** | SQLite (Development) / PostgreSQL (Production) |
| **Authentication** | Django Auth + Secure OTP Verification (Email) |
| **Services** | SMTP Email, Bytez Unified Model Protocol |

---

## ✨ Key Features

### 🤖 Birni AI Civic Assistant
- **Resilient Architecture**: Uses a dual-path API (Bytez + Google Fallback) to ensure 100% uptime.
- **Civic Intelligence**: Pre-trained on Birnagar's ward system, municipality contact info, and registration procedures.
- **Glassmorphic UI**: High-end floating chat widget with modern animations and responsive design.

### 📋 Management Modules
- **Ward-wise Reporting**: Citizens can report issues specific to any of the 14 wards.
- **Encrypted Data**: Sensitive information like Aadhaar numbers are encrypted at rest.
- **Real-time Notifications**: Automated email and SMS alerts for civic updates and OTPs.
- **Admin Dashboard**: Comprehensive control panel for municipality administrators to track and resolve complaints.

---

## 🚀 Quick Start

### 1. Installation
```bash
# Clone the repository
git clone <your-repo-url>
cd Final-BM

# Setup Virtual Environment
python -m venv venv
source venv/bin/activate  # venv\Scripts\activate on Windows

# Install Dependencies
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file in the root directory and add the following:
```env
# Core Settings
SECRET_KEY=your_secret_key
DEBUG=True

# AI API Keys
BYTEZ_API_KEY=your_bytez_token
GEMINI_API_KEY=your_google_gemini_key

# Email
EMAIL_HOST_PASSWORD=your_app_password
```

### 3. Run Server
```bash
python manage.py migrate
python manage.py runserver
```

---

## 🛡️ Security & Privacy
- **AES Encryption**: Used for sensitive citizen identifiers.
- **OTP Protection**: Secured login and registration via two-factor authentication.
- **Protected Media**: Images and documents uploaded by citizens are stored in a secured directory accessible only to authorized staff.


