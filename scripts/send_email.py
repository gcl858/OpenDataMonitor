import os
import smtplib

from email.mime.text import MIMEText

from logger_util import logger

try:

    logger.info("start send email")

    msg = MIMEText(
        "政府 OpenData 已更新"
    )

    msg["Subject"] = "OpenData Changed"

    msg["From"] = os.environ["EMAIL_USER"]

    msg["To"] = os.environ["EMAIL_TO"]

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465
    ) as smtp:

        smtp.login(
            os.environ["EMAIL_USER"],
            os.environ["EMAIL_PASS"]
        )

        smtp.send_message(msg)

    logger.info("email sent")

except Exception as e:

    logger.exception(f"email failed: {e}")

    raise
