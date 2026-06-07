import os
import smtplib

import email.policy
from email.mime.text import MIMEText

import pandas as pd

from logger_util import logger


def run_send_email(new_rows=None) -> None:

    try:

        logger.info("start send email")

        recipients = [
            addr.strip()
            for addr in os.environ["EMAIL_TO"].split(",")
            if addr.strip()
        ]

        if not recipients:

            raise ValueError("EMAIL_TO 解析後沒有有效收件人")

        logger.info(f"recipients count={len(recipients)}")

        body = ""

        if new_rows is not None and len(new_rows) > 0:

            body += f"\n\n新增資料筆數：{len(new_rows)} 筆\n\n"

            body += new_rows[["city", "site_id", "road"]].to_csv(index=False)

            logger.info(f"email body includes {len(new_rows)} added rows")
        else:

            body += "本次比對無異動。"

            logger.info("email body indicates no changes")

        if new_rows is not None and len(new_rows) > 0:

            subject = f"[全國路名監控通知][有異動]新增筆數:{len(new_rows)}"

        else:

            subject = "[全國路名監控通知][無異動]"

        msg = MIMEText(body, _charset="utf-8", policy=email.policy.default)

        msg["Subject"] = subject

        msg["From"] = os.environ["EMAIL_USER"]

        msg["To"] = ", ".join(recipients)

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465
        ) as smtp:

            smtp.login(
                os.environ["EMAIL_USER"],
                os.environ["EMAIL_PASS"]
            )

            smtp.send_message(msg, to_addrs=recipients)

        logger.info("email sent")

    except Exception as e:

        logger.exception(f"email failed: {e}")

        raise


if __name__ == "__main__":
    run_send_email()
