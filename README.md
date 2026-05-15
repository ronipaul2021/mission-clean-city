<div align="center">
  <h1>🏙️ Mission Clean City — Birnagar Municipality</h1>
  <p><em>A Next-Generation Civic Tech Platform for Transparent & Accountable Governance</em></p>
  
  [![Python](https://img.shields.io/badge/Python-3.x-blue.svg?style=for-the-badge&logo=python&logoColor=white)]()
  [![Django](https://img.shields.io/badge/Django-Secure-092E20.svg?style=for-the-badge&logo=django&logoColor=white)]()
  [![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-Modern-38B2AC.svg?style=for-the-badge&logo=tailwind-css&logoColor=white)]()
  [![OpenCV](https://img.shields.io/badge/OpenCV-AI_Vision-5C3EE8.svg?style=for-the-badge&logo=opencv&logoColor=white)]()
</div>

<br />

> **Mission Clean City** is an enterprise-grade web application built to bridge the gap between citizens and municipal administrators. It digitizes the entire urban complaint lifecycle—from GPS-tagged problem reporting to verified, photo-backed resolutions.

---

## ✨ All Features

| 🏢 **For Administrators** | 🧑‍🤝‍🧑 **For Citizens** |
| :--- | :--- |
| **Advanced Dashboard:** Real-time metrics, KPI cards, and charts | **One-Tap Reporting:** Submit complaints with photos, videos, and live GPS coordinates |
| **Powerful Search:** Multi-parameter filtering (Date, Priority, Ward, Status) | **Live Tracking:** Follow issues from `Pending` to `In Progress` to `Resolved` |
| **Bulk Actions:** Update multiple issues simultaneously with notes & photo proofs | **Accountability:** Rate the quality of municipal work once an issue is resolved |
| **Suggestion Box:** Review, categorize, and act on citizen ideas | **Appeals:** Re-open terminated or unsatisfactorily resolved tickets |

---

## 🛡️ Enterprise Security & Data Protection (High-Risk Handling)

Handling municipal data requires absolute security. The platform implements rigorous protocols to protect citizen identity and prevent system abuse.

| Security Layer | Implementation Detail | Risk Mitigated |
| :--- | :--- | :--- |
| **Aadhaar Encryption** | Symmetric **Fernet Encryption** is used to encrypt real Aadhaar numbers before DB storage. | Identity theft in case of database breach. |
| **Blind Duplicate Detection** | A one-way cryptographic hash of the Aadhaar is stored to enforce "One-Account-Per-Citizen". | Spam accounts / System abuse. |
| **Protected Media Routing** | A custom Django middleware gatekeeper intercepts media requests, ensuring only authenticated owners/admins see profile/complaint photos. | Unauthorized public scraping of private images. |
| **Brute-Force Protection** | Strict rate-limiting on file uploads and registration endpoints (e.g., max 3 uploads/hour). | Server Denial of Service (DoS) and Storage Exhaustion. |
| **OTP Verification** | Secure Email-based verification with encrypted server-side sessions. | Fake identities & impersonation. |

---

## 🤖 AI & Computer Vision Integration

Artificial Intelligence is deeply integrated to automate administrative overhead and ensure high data quality.

| AI Feature | Technology | How It Works |
| :--- | :--- | :--- |
| **Facial Detection** | `OpenCV` (Haar Cascades) | Automatically scans uploaded citizen profile photos to detect human faces. |
| **Smart Auto-Cropping** | `cv2.CascadeClassifier` | If a face is found, the system calculates the exact bounding box and crops the image to a perfect, centered square ID format. |
| **Forensic Compression** | Pillow (`PIL`) | Multi-phase JPEG compression algorithm shrinks high-res 4K smartphone photos down to `75KB` without destroying crucial forensic details. |

---

## 💻 Technical Architecture & Stack

### 🛠️ Tech Stack

| Category | Technology |
| :--- | :--- |
| **Frontend** | HTML5, Tailwind CSS, JavaScript (Vanilla) |
| **Backend** | Python 3.x, Django 5.2.6 |
| **Database** | SQLite (Dev) / PostgreSQL (Prod) |
| **API Used** | SMTP (Email Delivery), Fast2SMS (Legacy Support) |
| **Auth Used** | Custom Django Auth, Email OTP Verification, Fernet Aadhaar Encryption |

### 🏛️ System Architecture
| Component | Description |
| :--- | :--- |
| **Service Layer Pattern** | Heavy business logic is decoupled from `views.py` into `services/` (e.g., `ComplaintService`), resulting in thin controllers and robust, testable logic. |
| **Data Serializers** | Custom serialization ensures sensitive fields (like encrypted Aadhaar or password hashes) never accidentally leak into templates or API payloads. |
| **Query Optimization** | Extensive use of `select_related` and `prefetch_related` completely eliminates N+1 query bottlenecks, dropping load times from seconds to milliseconds. |

### Frontend Experience (Tailwind CSS)
| Component | Description |
| :--- | :--- |
| **Glassmorphic UI** | Built with utility-first Tailwind CSS for a modern, responsive, and highly interactive user experience across all mobile devices. |
| **Dynamic Filters** | JavaScript-powered multi-filters allow admins to combine Date Ranges, Priorities, and Quick-Presets instantly. |
| **Custom Error Handling** | Branded `400`, `403`, `404`, and `500` error pages ensure a professional aesthetic even when things go wrong, hiding server stack traces. |

---

## 🚀 Local Development Setup

To get the platform running on your local machine, follow these steps:

```bash
# 1. Clone the repository
git clone https://github.com/ronipaul2021/mission-clean-city-birnagar-municipality.git
cd mission-clean-city-birnagar-municipality

# 2. Set up the Virtual Environment
python -m venv venv
venv\Scripts\activate  # On Windows
# source venv/bin/activate # On Mac/Linux

# 3. Install Dependencies
pip install -r requirements.txt

# 4. Configure Environment Variables
# Copy the example file and add your Secret Keys (Aadhaar, Fast2SMS)
cp .env.example .env

# 5. Build Database and Run
python manage.py migrate
python manage.py runserver
```

<div align="center">
  <br />
  <p><i>Developed with ❤️ for the citizens of Birnagar</i></p>
</div>
