import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

def send_otp_email(email_address: str, otp: str) -> bool:
    """
    Send a 6-digit OTP to the provided email address.
    Returns True if successful, False otherwise.
    """
    subject = 'Your Registration OTP - Mission Clean City'
    message = (
        f"Dear Citizen,\n\n"
        f"Your One-Time Password (OTP) for Birnagar Municipality Civic Platform registration is: {otp}\n\n"
        f"This OTP is valid for {getattr(settings, 'OTP_EXPIRY_MINUTES', 10)} minutes. "
        f"Please do not share this code with anyone.\n\n"
        f"Regards,\n"
        f"Birnagar Municipality"
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@birnagarmunicipality.gov.in')
    
    try:
        sent = send_mail(
            subject,
            message,
            from_email,
            [email_address],
            fail_silently=False,
        )
        if sent:
            logger.info(f"OTP successfully sent to email: {email_address}")
            return True
        else:
            logger.error(f"Failed to send OTP to email: {email_address}")
            return False
    except Exception as e:
        logger.error(f"Exception while sending OTP to email {email_address}: {e}")
        return False
