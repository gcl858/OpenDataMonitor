import os
import smtplib

import email.policy
from email.mime.text import MIMEText

import pandas as pd

from logger_util import logger


def run_send_email(new_rows=None, year_rows=None) -> None:

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
        body += "\n     全國路名最新2年度列表\n"
        body += "===============================\n"
        # 只取year_rows前 2 筆，避免輸出過長
        for ad, roc, name, url in year_rows[:2]:
            body += f"{name}  {url}\n"

        body += "\n      路名異動比對結果\n"
        body += "===============================\n"
        if new_rows is not None and len(new_rows) > 0:
            body += f"\n新增資料筆數：{len(new_rows)} 筆\n"
            body += new_rows[["city", "site_id", "road"]].to_csv(index=False)
            logger.info(f"email body includes {len(new_rows)} added rows")
        else:
            body += "本次比對無異動。"
            logger.info("email body indicates no changes")

        body += "\n\n"

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
