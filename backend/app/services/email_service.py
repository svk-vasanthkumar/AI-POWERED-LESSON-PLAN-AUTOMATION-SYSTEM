import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config.settings import settings


def send_email(to_email: str, subject: str, body_text: str, body_html: str = None) -> bool:
    """Send an email using configured SMTP settings."""
    # If no SMTP server is configured, simulate it.
    if not settings.SMTP_SERVER:
        print(f"\n{'='*50}")
        print(f"📧 [SIMULATED] EMAIL SENT TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print(f"{'='*50}")
        print(body_text)
        if body_html:
            print("\n[HTML VERSION ATTACHED]")
        print(f"{'='*50}\n")
        return True

    msg = MIMEMultipart("mixed")
    msg["From"] = settings.SMTP_USERNAME
    msg["To"] = to_email
    msg["Subject"] = subject
    
    if body_html:
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body_text, "plain", "utf-8"))
        alt.attach(MIMEText(body_html, "html", "utf-8"))
        msg.attach(alt)
    else:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def send_password_reset_email(to_email: str, token: str) -> bool:
    """Send a password reset link to the user."""
    # We will hardcode the frontend URL for now, or derive it from CORS
    frontend_url = settings.frontend_origins_list[0] if settings.frontend_origins_list else "http://localhost:5173"
    reset_link = f"{frontend_url}/reset-password?token={token}"
    
    subject = "Password Reset Request - EduAI"
    body_text = (
        f"You have requested to reset your password.\n\n"
        f"Please click the link below to set a new password:\n"
        f"{reset_link}\n\n"
        f"If you did not request this, please ignore this email.\n"
        f"This link will expire in 15 minutes."
    )
    
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #4f46e5;">EduAI Password Reset</h2>
        <p>You recently requested to reset your password for your EduAI account. Click the button below to set a new password:</p>
        <div style="text-align: center; margin: 30px 0;">
          <a href="{reset_link}" style="background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Reset Password</a>
        </div>
        <p style="font-size: 0.9em; color: #666;">If the button doesn't work, copy and paste this link into your browser:<br>
        <a href="{reset_link}">{reset_link}</a></p>
        <p style="font-size: 0.9em; color: #666;">If you did not request a password reset, please ignore this email or contact support if you have questions.</p>
        <p style="font-size: 0.8em; color: #999; margin-top: 40px;">This link will expire in 15 minutes.</p>
      </body>
    </html>
    """
    
    return send_email(to_email, subject, body_text, body_html)


def send_security_alert_email(to_email: str) -> bool:
    """Send an alert that the password was changed."""
    subject = "Security Alert - Password Changed"
    body_text = (
        f"Your EduAI password was recently changed.\n\n"
        f"If you did not make this change, please contact your administrator immediately."
    )
    
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #e11d48;">Security Alert</h2>
        <p>Your EduAI password was recently changed.</p>
        <p style="font-weight: bold; margin-top: 20px;">If you did not make this change, please contact your administrator immediately.</p>
      </body>
    </html>
    """
    return send_email(to_email, subject, body_text, body_html)
