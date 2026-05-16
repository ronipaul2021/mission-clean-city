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

def send_registration_confirmation_email(email_address: str, name: str, citizen_id: str, mobile_number: str, password: str) -> bool:
    """
    Send a confirmation email after successful registration with credentials.
    """
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
        f"Please keep these credentials safe. You can now log in using your mobile number and the password above.\n\n"
        f"Regards,\n"
        f"Birnagar Municipality"
    )
    # Note: Mobile number is used for login, not email. I should clarify that.
    # Actually, the username is the mobile number.
    
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@birnagarmunicipality.gov.in')
    
    try:
        sent = send_mail(
            subject,
            message,
            from_email,
            [email_address],
            fail_silently=False,
        )
        return bool(sent)
    except Exception as e:
        logger.error(f"Exception while sending confirmation email to {email_address}: {e}")
        return False

def send_admin_registration_confirmation_email(email_address: str, name: str, employee_id: str, password: str) -> bool:
    """
    Send a confirmation email after successful admin registration with credentials.
    """
    subject = 'Admin Registration Successful - Mission Clean City'
    message = (
        f"Dear {name},\n\n"
        f"Congratulations! You have been successfully registered as a Municipal Admin on the Birnagar Municipality Civic Platform.\n\n"
        f"Your admin account credentials are as follows:\n"
        f"----------------------------------------\n"
        f"Employee ID (Username): {employee_id}\n"
        f"Password: {password}\n"
        f"----------------------------------------\n\n"
        f"Please keep these credentials safe. You can now log in using your Employee ID and the password above to access the Admin Dashboard.\n\n"
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
        return bool(sent)
    except Exception as e:
        logger.error(f"Exception while sending admin confirmation email to {email_address}: {e}")
        return False
