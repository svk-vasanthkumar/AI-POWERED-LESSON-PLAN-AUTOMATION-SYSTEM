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


def send_verification_email(to_email: str, token: str, user_name: str = "User") -> bool:
    """Send an email verification link after self-registration."""
    frontend_url = settings.frontend_origins_list[0] if settings.frontend_origins_list else "http://localhost:5173"
    verify_link = f"{frontend_url}/verify-email?token={token}"

    subject = "Verify Your Email Address — EduAI"
    body_text = (
        f"Hi {user_name},\n\n"
        f"Welcome to EduAI! Please verify your email address by clicking the link below:\n"
        f"{verify_link}\n\n"
        f"This link will expire in 24 hours.\n\n"
        f"If you did not create an EduAI account, please ignore this email."
    )

    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #4f46e5, #7c3aed); border-radius: 12px 12px 0 0; padding: 28px 32px;">
          <h1 style="margin: 0; color: #fff; font-size: 22px; letter-spacing: -0.3px;">EduAI — Verify Your Email</h1>
        </div>
        <div style="background: #fff; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px; padding: 32px;">
          <p>Hi <strong>{user_name}</strong>,</p>
          <p>Welcome to <strong>EduAI — AI-Powered Lesson Plan Automation</strong>! To activate your account, please verify your email address by clicking the button below:</p>
          <div style="text-align: center; margin: 32px 0;">
            <a href="{verify_link}"
               style="background: linear-gradient(135deg, #4f46e5, #7c3aed); color: #fff; padding: 14px 32px; text-decoration: none;
                      border-radius: 8px; font-weight: 700; font-size: 15px; display: inline-block; letter-spacing: 0.3px;">
              ✉ Verify Email Address
            </a>
          </div>
          <p style="font-size: 0.88em; color: #6b7280;">If the button doesn't work, copy and paste this link into your browser:</p>
          <p style="font-size: 0.85em; word-break: break-all;">
            <a href="{verify_link}" style="color: #4f46e5;">{verify_link}</a>
          </p>
          <hr style="border: none; border-top: 1px solid #f3f4f6; margin: 24px 0;" />
          <p style="font-size: 0.82em; color: #9ca3af; margin: 0;">
            This link expires in <strong>24 hours</strong>. If you did not create an EduAI account, you can safely ignore this email.
          </p>
        </div>
      </body>
    </html>
    """

    return send_email(to_email, subject, body_text, body_html)



def format_change_diff_html(changes: dict) -> str:
    if not changes:
        return ""
    diff_rows = ""
    for k, v in changes.items():
        if isinstance(v, dict) and "old" in v and "new" in v:
            val_str = f"<span style='color:#ef4444;text-decoration:line-through;'>{v['old']}</span> &rarr; <span style='color:#10b981;font-weight:bold;'>{v['new']}</span>"
        else:
            val_str = str(v)
        diff_rows += f"<tr><td style='padding: 6px 12px; background: #f8fafc; font-weight: bold; border: 1px solid #e2e8f0;'>{k.replace('_', ' ').title()}</td><td style='padding: 6px 12px; border: 1px solid #e2e8f0;'>{val_str}</td></tr>"
    return f"""
    <table style="width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 0.9em;">
      {diff_rows}
    </table>
    """


def send_event_notification_email(to_email: str, notification_data: dict) -> bool:
    """Send a targeted email alert for an application event."""
    frontend_url = settings.frontend_origins_list[0] if settings.frontend_origins_list else "http://localhost:5173"
    
    title = notification_data.get("title", "EduAI System Alert")
    message = notification_data.get("message", "")
    actor_name = notification_data.get("actor_name", "System")
    severity = (notification_data.get("severity") or "INFO").upper()
    link = notification_data.get("link", "")
    metadata = notification_data.get("metadata") or {}
    
    full_link = f"{frontend_url}{link}" if link and link.startswith("/") else (link or frontend_url)
    
    severity_colors = {
        "SUCCESS": "#10b981",
        "WARNING": "#f59e0b",
        "ERROR": "#ef4444",
        "CRITICAL": "#dc2626",
        "INFO": "#4f46e5"
    }
    theme_color = severity_colors.get(severity, "#4f46e5")
    
    subject = notification_data.get("email_subject") or f"[{severity}] {title} - EduAI"
    
    body_text = f"EduAI Alert: {title}\n\n"
    body_text += f"{message}\n\n"
    body_text += f"Updated by: {actor_name}\n"
    if metadata.get("course_code"):
        body_text += f"Course: {metadata.get('course_code')} {metadata.get('course_name', '')}\n"
    if metadata.get("previous_value") and metadata.get("new_value"):
        body_text += f"Change: {metadata['previous_value']} -> {metadata['new_value']}\n"
    if full_link:
        body_text += f"\nView details: {full_link}\n"
        
    html_diff_table = format_change_diff_html(metadata)

    body_html = f"""
    <html>
      <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1e293b; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8fafc;">
        <div style="background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border: 1px solid #e2e8f0;">
          <div style="background-color: {theme_color}; padding: 20px; text-align: center; color: white;">
            <h2 style="margin: 0; font-size: 1.3rem;">EduAI Notification</h2>
            <span style="font-size: 0.8rem; background: rgba(255,255,255,0.2); padding: 3px 10px; border-radius: 12px; display: inline-block; margin-top: 6px;">{severity}</span>
          </div>
          <div style="padding: 24px;">
            <h3 style="margin-top: 0; color: #0f172a;">{title}</h3>
            <p style="font-size: 1rem; color: #334155; margin-bottom: 20px;">{message}</p>

            <div style="background-color: #f1f5f9; padding: 12px 16px; border-radius: 8px; font-size: 0.88rem; margin-bottom: 20px;">
              <div><strong>Updated By:</strong> {actor_name}</div>
              {f"<div><strong>Course:</strong> {metadata.get('course_code')} - {metadata.get('course_name', '')}</div>" if metadata.get('course_code') else ""}
            </div>

            {html_diff_table}

            <div style="text-align: center; margin: 30px 0 10px 0;">
              <a href="{full_link}" style="background-color: {theme_color}; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block;">View in Application</a>
            </div>
          </div>
          <div style="background-color: #f8fafc; padding: 15px; text-align: center; font-size: 0.78rem; color: #64748b; border-top: 1px solid #e2e8f0;">
            This is an automated notification from your institution's EduAI System.
          </div>
        </div>
      </body>
    </html>
    """
    return send_email(to_email, subject, body_text, body_html)

