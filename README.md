# 🏙️ Birnagar Municipality Civic Tech Platform (Mission Clean City)

A robust, secure, and highly scalable civic management platform built to bridge the gap between the citizens of Birnagar and their municipal administration. This platform handles real-time complaint tracking, secure citizen registration, automated issue assignment, and data-driven administrative analytics.

---

## 🌟 Major Focus & Objectives
The primary objective of this project is to create a **transparent, accountable, and highly secure digital ecosystem** for municipal governance. 

Major focuses include:
- **Accessibility:** A fully mobile-responsive interface for citizens to report issues from anywhere.
- **Accountability:** Real-time tracking of complaints from "Pending" to "Resolved," complete with resolution proof (photos) required from administrators.
- **Data Integrity:** Strict validation of user data (Aadhaar, Mobile) to prevent spam and duplicate accounts.
- **Administrative Efficiency:** Powerful dashboards with full-text search, bulk-actions, and automated analytics to help officials prioritize urban issues.

---

## 🛡️ Security & High-Risk Data Handling (CRITICAL)
Handling citizen data requires enterprise-grade security. This platform implements strict protocols for highly sensitive information:

- **Military-Grade Aadhaar Encryption:** Real Aadhaar numbers are **never** stored in plain text. They are encrypted using symmetric Fernet encryption before touching the database.
- **Blind Duplicate Detection:** To enforce "One-Aadhaar-One-Account" without exposing data, the system stores a one-way cryptographic hash of the Aadhaar number specifically for collision detection.
- **Protected Media Gatekeeper:** Uploaded profile photos and complaint evidence cannot be accessed directly via URL. A Django middleware gatekeeper ensures only authenticated owners or admins can view sensitive media.
- **Upload Rate Limiting & Validation:** File uploads are strictly validated by MIME type, size-limited (e.g., 100MB for videos, 75KB for compressed images), and rate-limited to prevent Denial of Service (DoS) attacks on the server storage.

---

## 🤖 Where AI is Used
Artificial Intelligence and Computer Vision are integrated directly into the image processing pipeline to improve data quality and reduce manual administrative review:

- **AI Face Detection & Auto-Cropping:** Using **OpenCV (Haar Cascades)**, the `ImageProcessor` service automatically scans uploaded citizen profile photos to detect human faces. If a face is found, the system intelligently calculates the bounding box and auto-crops the image to a perfect square centered on the user's face, ensuring professional-looking ID cards across the platform.
- **Smart Image Compression:** Automated, multi-phase JPEG compression algorithms ensure that high-resolution smartphone photos are aggressively compressed (e.g., down to 75KB) without losing visible forensic detail needed for complaint resolution.

---

## 🔐 Authentication & Access Control
- **OTP-Based Verification:** Registration relies on real-time SMS OTP verification integrated with the **Fast2SMS API**. 
- **Session Security:** OTPs are stored securely in encrypted server-side sessions with a strict expiry window (default 10 minutes).
- **Role-Based Access Control (RBAC):** Distinct `ADMIN` and `CITIZEN` roles. The system enforces strict route protection, preventing citizens from accessing analytics and admins from submitting dummy complaints.

---

## 💻 Technical Architecture

### Backend (Django / Python)
- **Service-Oriented Architecture:** Heavy business logic is extracted out of views and into a dedicated `services/` layer (e.g., `ComplaintService`, `UserService`), ensuring thin controllers and high testability.
- **Centralized Data Serialization:** Custom serializers ensure consistent data formatting for frontend rendering and future REST API expansion, guaranteeing sensitive fields (like passwords/encrypted Aadhaar) never leak into JSON payloads.
- **Optimized Queries:** Heavy use of `select_related` and `prefetch_related` to eliminate N+1 database querying issues, reducing dashboard load times from seconds to milliseconds.

### Frontend (HTML / Tailwind CSS)
- **Dynamic UI:** Built with Django Templates and utility-first Tailwind CSS for a modern, glassmorphic, and highly responsive design.
- **Advanced Admin Dashboard:** Features a JavaScript-powered multi-filter system (Date Ranges, Priorities, Status) and quick-preset badges, allowing admins to instantly drill down into critical urban issues.
- **Custom Error Handling:** Branded, user-friendly 400, 403, 404, and 500 error pages ensure citizens are gracefully redirected instead of seeing confusing server stack traces.

---

## 🚀 Setup & Installation (Local Development)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ronipaul2021/mission-clean-city-birnagar-municipality.git
   cd mission-clean-city-birnagar-municipality
   ```

2. **Set up the Virtual Environment:**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # source venv/bin/activate # Mac/Linux
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Copy `.env.example` to `.env` and fill in your secret keys (Aadhaar Encryption Key, Fast2SMS API, etc.)
   ```bash
   cp .env.example .env
   ```

5. **Run Migrations & Start Server:**
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```
