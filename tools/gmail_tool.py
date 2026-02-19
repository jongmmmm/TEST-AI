"""
Gmail IMAP/SMTP CRUD 도구
ai_worker/backend/app/utils/gmail.py 패턴 기반
"""
import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
from datetime import datetime
import re
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GMAIL_EMAIL, GMAIL_APP_PASSWORD


def _connect() -> Optional[imaplib.IMAP4_SSL]:
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        return imap
    except Exception as e:
        return None


def _decode_mime(s: str) -> str:
    if not s:
        return ""
    parts = []
    for word, enc in decode_header(s):
        if isinstance(word, bytes):
            parts.append(word.decode(enc or "utf-8", errors="ignore"))
        else:
            parts.append(word)
    return "".join(parts)


def _get_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition"))
            if "attachment" in cd:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    if ct == "text/plain":
                        body = payload.decode("utf-8", errors="ignore")
                        break
                    elif ct == "text/html" and not body:
                        body = payload.decode("utf-8", errors="ignore")
            except:
                pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except:
            pass
    # HTML 태그 제거
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body


def _encode_utf7(text: str) -> str:
    """IMAP Modified UTF-7 인코딩"""
    try:
        text.encode("ascii")
        return text.replace("&", "&-")
    except UnicodeEncodeError:
        pass
    import base64
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if 0x20 <= ord(ch) <= 0x7E and ch != "&":
            result.append(ch)
            i += 1
        elif ch == "&":
            result.append("&-")
            i += 1
        else:
            non_ascii = []
            while i < len(text) and not (0x20 <= ord(text[i]) <= 0x7E):
                non_ascii.append(text[i])
                i += 1
            if non_ascii:
                utf16 = "".join(non_ascii).encode("utf-16-be")
                b64 = base64.b64encode(utf16).decode("ascii").rstrip("=")
                result.append(f"&{b64}-")
    return "".join(result)


# --- Tool 함수들 ---

def search_emails(
    count: int = 10,
    mailbox: str = "INBOX",
    since_date: str = None,
    before_date: str = None,
    from_email: str = None,
    subject: str = None,
    unread_only: bool = False,
) -> Dict:
    """이메일 검색/조회"""
    imap = _connect()
    if not imap:
        return {"error": "Gmail 연결 실패. 이메일과 앱 비밀번호를 확인하세요."}

    try:
        imap.select(_encode_utf7(mailbox))

        criteria = []
        if since_date:
            d = datetime.strptime(since_date, "%Y-%m-%d")
            criteria.append(f'SINCE "{d.strftime("%d-%b-%Y")}"')
        if before_date:
            d = datetime.strptime(before_date, "%Y-%m-%d")
            criteria.append(f'BEFORE "{d.strftime("%d-%b-%Y")}"')
        if from_email:
            criteria.append(f'FROM "{from_email}"')
        if subject:
            criteria.append(f'SUBJECT "{subject}"')
        if unread_only:
            criteria.append("UNSEEN")

        query = " ".join(criteria) if criteria else "ALL"
        status, messages = imap.search(None, query)
        if status != "OK":
            return {"error": "검색 실패"}

        ids = messages[0].split()
        ids = ids[-count:][::-1]

        results = []
        for mid in ids:
            try:
                st, data = imap.fetch(mid, "(RFC822)")
                if st != "OK":
                    continue
                msg = email.message_from_bytes(data[0][1])
                from_h = msg.get("From", "")
                addr = email.utils.parseaddr(from_h)
                date_str = msg.get("Date", "")
                try:
                    dt = email.utils.parsedate_tz(date_str)
                    if dt:
                        date_str = datetime.fromtimestamp(
                            email.utils.mktime_tz(dt)
                        ).strftime("%Y-%m-%d %H:%M")
                except:
                    pass

                results.append({
                    "id": mid.decode(),
                    "subject": _decode_mime(msg.get("Subject", "")),
                    "from": addr[1],
                    "from_name": _decode_mime(addr[0]),
                    "to": email.utils.parseaddr(msg.get("To", ""))[1],
                    "date": date_str,
                })
            except:
                continue

        imap.close()
        imap.logout()
        return {"success": True, "count": len(results), "emails": results}

    except Exception as e:
        try:
            imap.close()
            imap.logout()
        except:
            pass
        return {"error": str(e)}


def read_email(email_id: str, mailbox: str = "INBOX") -> Dict:
    """이메일 본문 읽기"""
    imap = _connect()
    if not imap:
        return {"error": "Gmail 연결 실패"}

    try:
        imap.select(_encode_utf7(mailbox))
        st, data = imap.fetch(email_id, "(RFC822)")
        if st != "OK":
            return {"error": f"이메일 {email_id} 조회 실패"}

        msg = email.message_from_bytes(data[0][1])
        body = _get_body(msg)

        imap.close()
        imap.logout()
        return {
            "success": True,
            "id": email_id,
            "subject": _decode_mime(msg.get("Subject", "")),
            "body": body[:5000],
        }
    except Exception as e:
        try:
            imap.close()
            imap.logout()
        except:
            pass
        return {"error": str(e)}


def send_email(
    to_emails: List[str],
    subject: str,
    body: str,
    cc_emails: List[str] = None,
) -> Dict:
    """이메일 발송"""
    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_EMAIL
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject
        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        recipients = to_emails + (cc_emails or [])
        server.sendmail(GMAIL_EMAIL, recipients, msg.as_string())
        server.quit()

        return {
            "success": True,
            "message": f"{len(recipients)}명에게 이메일을 발송했습니다.",
        }
    except Exception as e:
        return {"error": str(e)}


def delete_email(email_id: str, mailbox: str = "INBOX") -> Dict:
    """이메일 삭제 (휴지통으로 이동)"""
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        imap.select(_encode_utf7(mailbox))

        trash = _encode_utf7("[Gmail]/Trash")
        imap.copy(email_id, trash)
        imap.store(email_id, "+FLAGS", "\\Deleted")
        imap.expunge()

        imap.close()
        imap.logout()
        return {"success": True, "message": f"이메일 {email_id}을 휴지통으로 이동했습니다."}
    except Exception as e:
        return {"error": str(e)}


# --- Tool 정의 (OpenAI 호환 형식) ---

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Gmail 이메일을 검색하고 조회합니다. 날짜, 발신자, 제목 등으로 필터링할 수 있습니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "가져올 이메일 개수", "default": 10},
                    "mailbox": {"type": "string", "description": "메일함 (INBOX, [Gmail]/Sent Mail 등)", "default": "INBOX"},
                    "since_date": {"type": "string", "description": "이 날짜 이후 (YYYY-MM-DD)"},
                    "before_date": {"type": "string", "description": "이 날짜 이전 (YYYY-MM-DD)"},
                    "from_email": {"type": "string", "description": "발신자 이메일"},
                    "subject": {"type": "string", "description": "제목 키워드"},
                    "unread_only": {"type": "boolean", "description": "안읽은 메일만", "default": False},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_email",
            "description": "특정 이메일의 본문을 읽습니다. search_emails로 얻은 email_id를 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email_id": {"type": "string", "description": "이메일 ID"},
                    "mailbox": {"type": "string", "description": "메일함", "default": "INBOX"},
                },
                "required": ["email_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "이메일을 발송합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_emails": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "수신자 이메일 목록",
                    },
                    "subject": {"type": "string", "description": "제목"},
                    "body": {"type": "string", "description": "본문"},
                    "cc_emails": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "참조 이메일 목록",
                    },
                },
                "required": ["to_emails", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_email",
            "description": "이메일을 휴지통으로 이동합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email_id": {"type": "string", "description": "삭제할 이메일 ID"},
                    "mailbox": {"type": "string", "description": "메일함", "default": "INBOX"},
                },
                "required": ["email_id"],
            },
        },
    },
]

# 도구 이름 → 함수 매핑
TOOL_FUNCTIONS = {
    "search_emails": search_emails,
    "read_email": read_email,
    "send_email": send_email,
    "delete_email": delete_email,
}
