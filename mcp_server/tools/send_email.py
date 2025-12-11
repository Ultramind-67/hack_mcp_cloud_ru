import os
import uuid
import time
import asyncio
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from mcp_server.mcp_instance import mcp
from mcp_server.utils import tool_schema

# Настройки из .env
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
CHECK_TIMEOUT = int(os.getenv("EMAIL_CHECK_TIMEOUT", 30))  # секунд
CHECK_INTERVAL = int(os.getenv("EMAIL_CHECK_INTERVAL", 5))  # секунд

async def _send_email(to: str, subject: str, body: str, unique_id: str) -> None:
    """Отправка email через SMTP"""
    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = to
    msg["Subject"] = f"[{unique_id}] {subject}"
    msg.attach(MIMEText(body, "plain"))
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        await asyncio.to_thread(server.login, EMAIL_USER, EMAIL_PASSWORD)
        await asyncio.to_thread(server.sendmail, EMAIL_USER, to, msg.as_string())
        server.quit()
        print(f"✅ Email отправлен поставщику {to} с ID: {unique_id}")
    except Exception as e:
        print(f"❌ Ошибка отправки email: {str(e)}")
        raise

async def _check_response(unique_id: str, supplier_email: str) -> str | None:
    """Проверка ответа через IMAP с таймаутом"""
    start_time = time.time()
    
    while time.time() - start_time < CHECK_TIMEOUT:
        try:
            # Подключаемся к IMAP
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            await asyncio.to_thread(mail.login, EMAIL_USER, EMAIL_PASSWORD)
            await asyncio.to_thread(mail.select, "INBOX")
            
            # Ищем непрочитанные письма от поставщика с нашим ID
            search_criteria = f'(UNSEEN FROM "{supplier_email}" SUBJECT "{unique_id}")'
            _, data = await asyncio.to_thread(mail.search, None, search_criteria)
            
            if data[0]:
                # Получаем первое подходящее письмо
                email_id = data[0].split()[0]
                _, msg_data = await asyncio.to_thread(mail.fetch, email_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                
                # Извлекаем текст из письма
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = msg.get_payload(decode=True).decode()
                
                # Помечаем письмо как прочитанное
                await asyncio.to_thread(mail.store, email_id, "+FLAGS", "\\Seen")
                mail.close()
                mail.logout()
                
                print(f"📨 Ответ получен от {supplier_email} (ID: {unique_id})")
                return body
            
            mail.close()
            mail.logout()
            
        except Exception as e:
            print(f"⚠️ Ошибка при проверке email: {str(e)}")
        
        # Ждем перед следующей проверкой
        await asyncio.sleep(CHECK_INTERVAL)
    
    print(f"⏳ Таймаут ожидания ответа от {supplier_email} (ID: {unique_id})")
    return None

@mcp.tool()
@tool_schema({
    "name": "send_supplier_email",
    "description": "Отправляет email поставщику с уточняющими вопросами и проверяет ответ",
    "parameters": {
        "type": "object",
        "properties": {
            "supplier_email": {
                "type": "string",
                "description": "Email поставщика",
                "format": "email"
            },
            "subject": {
                "type": "string",
                "description": "Тема письма"
            },
            "body": {
                "type": "string",
                "description": "Текст сообщения для поставщика"
            }
        },
        "required": ["supplier_email", "subject", "body"]
    }
})
async def send_supplier_email(supplier_email: str, subject: str, body: str) -> str:
    """Основной инструмент для отправки email и проверки ответа"""
    if not all([EMAIL_USER, EMAIL_PASSWORD]):
        return "❌ Ошибка: Не настроены почтовые реквизиты в .env"

    unique_id = str(uuid.uuid4())[:8]  # Короткий ID для отслеживания
    full_body = f"{body}\n\n---\nID запроса: {unique_id}"

    try:
        # 1. Отправляем email
        await _send_email(supplier_email, subject, full_body, unique_id)

        # 2. Проверяем ответ с таймаутом
        response = await _check_response(unique_id, supplier_email)

        if response:
            return f"✅ Ответ получен:\n{response}"
        return f"⏳ Ответ не получен за {CHECK_TIMEOUT} секунд. Проверьте почту вручную."

    except Exception as e:
        return f"❌ Критическая ошибка: {str(e)}\nПроверьте настройки почты в .env"