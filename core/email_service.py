import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@birnagarmunicipality.gov.in')


def send_otp_email(email_address: str, otp: str, purpose: str = 'Verification') -> bool:
    """
    Send a 6-digit OTP to the provided email address.
    purpose: short label for the subject, e.g. 'Registration', 'Password Reset'.
    Returns True if successful, False otherwise.
    """
    subject = f'Your {purpose} OTP - Mission Clean City'
    message = (
        f"Dear User,\n\n"
        f"Your One-Time Password (OTP) for Birnagar Municipality Civic Platform is: {otp}\n\n"
        f"This OTP is valid for {getattr(settings, 'OTP_EXPIRY_MINUTES', 10)} minutes. "
        f"Please do not share this code with anyone.\n\n"
        f"Regards,\n"
        f"Birnagar Municipality"
    )
    try:
        sent = send_mail(subject, message, _FROM_EMAIL, [email_address], fail_silently=False)
        if sent:
            logger.info("OTP (%s) successfully sent to: %s", purpose, email_address)
            return True
        logger.error("Failed to send OTP (%s) to: %s", purpose, email_address)
        return False
    except Exception as e:
        logger.error("Exception sending OTP (%s) to %s: %s", purpose, email_address, e)
        return False


def send_registration_confirmation_email(
    email_address: str, name: str, citizen_id: str, mobile_number: str, password: str
) -> bool:
    """Send a confirmation email after successful citizen registration with credentials."""
    subject = 'Registration Successful - Mission Clean City'
    message = (
        f"Dear {name},\n\n"
        f"Congratulations! You have successfully registered with the Birnagar Municipality Civic Platform.\n\n"
        f"Your account credentials are as follows:\n"
        f"----------------------------------------\n"
        f"Citizen ID: {citizen_id}\n"
        f"Mobile Number (Username): {mobile_number}\n"
        f"Password: {password}\n"
        f"----------------------------------------\n\n"
        f"Please keep these credentials safe. You can now log in using your mobile number and password above.\n\n"
        f"Regards,\n"
        f"Birnagar Municipality"
    )
    try:
        sent = send_mail(subject, message, _FROM_EMAIL, [email_address], fail_silently=False)
        return bool(sent)
    except Exception as e:
        logger.error("Exception sending confirmation email to %s: %s", email_address, e)
        return False


def send_admin_registration_confirmation_email(
    email_address: str, name: str, employee_id: str, password: str
) -> bool:
    """Send a confirmation email after successful admin registration with credentials."""
    subject = 'Admin Registration Successful - Mission Clean City'
    message = (
        f"Dear {name},\n\n"
        f"Congratulations! You have been successfully registered as a Municipal Admin on the Birnagar Municipality Civic Platform.\n\n"
        f"Your admin account credentials are as follows:\n"
        f"----------------------------------------\n"
        f"Employee ID (Username): {employee_id}\n"
        f"Password: {password}\n"
        f"----------------------------------------\n\n"
        f"Please keep these credentials safe. You can now log in using your Employee ID and password above.\n\n"
        f"Regards,\n"
        f"Birnagar Municipality"
    )
    try:
        sent = send_mail(subject, message, _FROM_EMAIL, [email_address], fail_silently=False)
        return bool(sent)
    except Exception as e:
        logger.error("Exception sending admin confirmation email to %s: %s", email_address, e)
        return False
