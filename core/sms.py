import requests
from django.conf import settings


def send_otp_sms(mobile_number, otp):
    """
    Sends a 6-digit OTP via Fast2SMS to the given Indian mobile number.
    Returns True on success, False on failure.
    """
    url = "https://www.fast2sms.com/dev/bulkV2"

    payload = {
        "variables_values": str(otp),
        "route": "otp",
        "numbers": str(mobile_number),
    }
    headers = {
        "authorization": settings.FAST2SMS_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        result = response.json()
        print(f"[Fast2SMS] Response for {mobile_number}: {result}")
        return result.get("return", False)
    except Exception as e:
        print(f"[Fast2SMS] SMS sending failed: {e}")
        return False
