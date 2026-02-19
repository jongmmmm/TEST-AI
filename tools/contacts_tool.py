"""
Google Contacts CRUD 도구 (People API + OAuth 2.0)
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE, GOOGLE_SCOPES

from typing import Dict, List, Optional

# Google API 관련
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


def _get_service():
    """People API 서비스 객체 생성"""
    creds = None
    token_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), GOOGLE_TOKEN_FILE)
    creds_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), GOOGLE_CREDENTIALS_FILE)

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, GOOGLE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                return None
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("people", "v1", credentials=creds)


def list_contacts(count: int = 20) -> Dict:
    """연락처 목록 조회"""
    service = _get_service()
    if not service:
        return {"error": "Google 인증 실패. credentials.json 파일을 확인하세요."}

    try:
        results = service.people().connections().list(
            resourceName="people/me",
            pageSize=count,
            personFields="names,emailAddresses,phoneNumbers,organizations",
            sortOrder="LAST_NAME_ASCENDING",
        ).execute()

        connections = results.get("connections", [])
        contacts = []
        for p in connections:
            names = p.get("names", [])
            name = names[0].get("displayName", "") if names else ""
            emails = [e["value"] for e in p.get("emailAddresses", []) if e.get("value")]
            phones = [ph["value"] for ph in p.get("phoneNumbers", []) if ph.get("value")]
            orgs = p.get("organizations", [])
            company = orgs[0].get("name", "") if orgs else ""
            title = orgs[0].get("title", "") if orgs else ""

            contacts.append({
                "resource_name": p.get("resourceName", ""),
                "name": name,
                "emails": emails,
                "phones": phones,
                "company": company,
                "job_title": title,
            })

        return {"success": True, "count": len(contacts), "contacts": contacts}
    except Exception as e:
        return {"error": str(e)}


def search_contacts(query: str) -> Dict:
    """연락처 검색"""
    service = _get_service()
    if not service:
        return {"error": "Google 인증 실패"}

    try:
        results = service.people().searchContacts(
            query=query,
            readMask="names,emailAddresses,phoneNumbers,organizations",
            pageSize=10,
        ).execute()

        people = results.get("results", [])
        contacts = []
        for item in people:
            p = item.get("person", {})
            names = p.get("names", [])
            name = names[0].get("displayName", "") if names else ""
            emails = [e["value"] for e in p.get("emailAddresses", []) if e.get("value")]
            phones = [ph["value"] for ph in p.get("phoneNumbers", []) if ph.get("value")]
            orgs = p.get("organizations", [])
            company = orgs[0].get("name", "") if orgs else ""
            title = orgs[0].get("title", "") if orgs else ""

            contacts.append({
                "resource_name": p.get("resourceName", ""),
                "name": name,
                "emails": emails,
                "phones": phones,
                "company": company,
                "job_title": title,
            })

        return {"success": True, "count": len(contacts), "contacts": contacts}
    except Exception as e:
        return {"error": str(e)}


def create_contact(
    given_name: str,
    family_name: str = "",
    email: str = None,
    phone: str = None,
    company: str = None,
    job_title: str = None,
) -> Dict:
    """연락처 추가"""
    service = _get_service()
    if not service:
        return {"error": "Google 인증 실패"}

    try:
        body = {
            "names": [{"givenName": given_name, "familyName": family_name}],
        }
        if email:
            body["emailAddresses"] = [{"value": email}]
        if phone:
            body["phoneNumbers"] = [{"value": phone}]
        if company or job_title:
            body["organizations"] = [{"name": company or "", "title": job_title or ""}]

        result = service.people().createContact(body=body).execute()
        return {
            "success": True,
            "message": f"연락처 '{given_name} {family_name}'을 추가했습니다.",
            "resource_name": result.get("resourceName", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def update_contact(
    resource_name: str,
    given_name: str = None,
    family_name: str = None,
    email: str = None,
    phone: str = None,
    company: str = None,
    job_title: str = None,
) -> Dict:
    """연락처 수정"""
    service = _get_service()
    if not service:
        return {"error": "Google 인증 실패"}

    try:
        # 기존 연락처 가져오기
        person = service.people().get(
            resourceName=resource_name,
            personFields="names,emailAddresses,phoneNumbers,organizations,metadata",
        ).execute()

        etag = person.get("etag", "")
        update_fields = []
        body = {"etag": etag}

        if given_name or family_name:
            names = person.get("names", [{}])
            name = names[0] if names else {}
            body["names"] = [{
                "givenName": given_name or name.get("givenName", ""),
                "familyName": family_name or name.get("familyName", ""),
            }]
            update_fields.append("names")

        if email is not None:
            body["emailAddresses"] = [{"value": email}]
            update_fields.append("emailAddresses")

        if phone is not None:
            body["phoneNumbers"] = [{"value": phone}]
            update_fields.append("phoneNumbers")

        if company is not None or job_title is not None:
            orgs = person.get("organizations", [{}])
            org = orgs[0] if orgs else {}
            body["organizations"] = [{
                "name": company if company is not None else org.get("name", ""),
                "title": job_title if job_title is not None else org.get("title", ""),
            }]
            update_fields.append("organizations")

        result = service.people().updateContact(
            resourceName=resource_name,
            updatePersonFields=",".join(update_fields),
            body=body,
        ).execute()

        return {"success": True, "message": f"연락처를 수정했습니다."}
    except Exception as e:
        return {"error": str(e)}


def delete_contact(resource_name: str) -> Dict:
    """연락처 삭제"""
    service = _get_service()
    if not service:
        return {"error": "Google 인증 실패"}

    try:
        service.people().deleteContact(resourceName=resource_name).execute()
        return {"success": True, "message": "연락처를 삭제했습니다."}
    except Exception as e:
        return {"error": str(e)}


# --- Tool 정의 ---

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_contacts",
            "description": "Google 주소록의 연락처 목록을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "가져올 연락처 수", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Google 주소록에서 이름이나 이메일로 연락처를 검색합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색어 (이름, 이메일 등)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_contact",
            "description": "Google 주소록에 새 연락처를 추가합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "given_name": {"type": "string", "description": "이름"},
                    "family_name": {"type": "string", "description": "성"},
                    "email": {"type": "string", "description": "이메일"},
                    "phone": {"type": "string", "description": "전화번호"},
                    "company": {"type": "string", "description": "회사"},
                    "job_title": {"type": "string", "description": "직책"},
                },
                "required": ["given_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_contact",
            "description": "Google 주소록의 기존 연락처를 수정합니다. resource_name은 list_contacts나 search_contacts로 얻습니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_name": {"type": "string", "description": "연락처 resource name (예: people/c12345)"},
                    "given_name": {"type": "string", "description": "이름"},
                    "family_name": {"type": "string", "description": "성"},
                    "email": {"type": "string", "description": "이메일"},
                    "phone": {"type": "string", "description": "전화번호"},
                    "company": {"type": "string", "description": "회사"},
                    "job_title": {"type": "string", "description": "직책"},
                },
                "required": ["resource_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_contact",
            "description": "Google 주소록에서 연락처를 삭제합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_name": {"type": "string", "description": "연락처 resource name"},
                },
                "required": ["resource_name"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "list_contacts": list_contacts,
    "search_contacts": search_contacts,
    "create_contact": create_contact,
    "update_contact": update_contact,
    "delete_contact": delete_contact,
}
