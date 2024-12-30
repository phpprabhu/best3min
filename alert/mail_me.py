import config
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from smtplib import SMTP


def mail_me(subject, body_content):
    # Disabled mail, since its not used
    return
    message = MIMEMultipart()
    message['Subject'] = 'AusCheryTrade: ' + subject
    message['From'] = config.EMAIL_USER
    message['To'] = config.EMAIL_ME
    # message['Cc'] = config.EMAIL_CC

    message.attach(MIMEText(body_content, "html"))
    msg_body = message.as_string()

    server = SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(config.EMAIL_USER, config.EMAIL_PASS)
    server.sendmail(config.EMAIL_USER, [config.EMAIL_ME], msg_body)

    server.quit()