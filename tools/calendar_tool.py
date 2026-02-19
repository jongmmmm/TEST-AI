"""
Google Calendar CRUD 도구 (Calendar API + OAuth 2.0)
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE, GOOGLE_SCOPES

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


def _get_service():
    """Calendar API 서비스 객체 생성"""
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

    return build("calendar", "v3", credentials=creds)


def list_events(days_ahead: int = 7, max_results: int = 20) -> Dict:
    """일정 목록 조회"""
    service = _get_service()
    if not service:
        return {"error": "Google 인증 실패. credentials.json 파일을 확인하세요."}

    try:
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        items = result.get("items", [])
        events = []
        for ev in items:
            start = ev.get("start", {})
            end = ev.get("end", {})
            events.append({
                "id": ev.get("id", ""),
                "summary": ev.get("summary", "(제목 없음)"),
                "start": start.get("dateTime", start.get("date", "")),
                "end": end.get("dateTime", end.get("date", "")),
                "location": ev.get("location", ""),
                "description": ev.get("description", ""),
                "attendees": [
                    a.get("email", "") for a in ev.get("attendees", [])
                ],
            })

        return {"success": True, "count": len(events), "events": events}
    except Exception as e:
        return {"error": str(e)}


def create_event(
    summary: str,
    start_datetime: str,
    end_datetime: str = None,
    description: str = None,
    location: str = None,
    attendees: List[str] = None,
) -> Dict:
    """일정 생성

    Args:
        summary: 일정 제목
        start_datetime: 시작 시간 (YYYY-MM-DDTHH:MM:SS 또는 YYYY-MM-DD)
        end_datetime: 종료 시간 (없으면 시작 + 1시간)
        description: 설명
        location: 장소
        attendees: 참석자 이메일 목록
    """
    service = _get_service()
    if not service:
        return {"error": "Google 인증 실패"}

    try:
        # 시작/종료 시간 처리
        if "T" in start_datetime:
            start = {"dateTime": start_datetime, "timeZone": "Asia/Seoul"}
            if not end_datetime:
                # 기본 1시간
                st = datetime.fromisoformat(start_datetime)
                end_datetime = (st + timedelta(hours=1)).isoformat()
            end = {"dateTime": end_datetime, "timeZone": "Asia/Seoul"}
        else:
            # 종일 일정
            start = {"date": start_datetime}
            end = {"date": end_datetime or start_datetime}

        body = {
            "summary": summary,
            "start": start,
            "end": end,
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]

        event = service.events().insert(calendarId="primary", body=body).execute()
        return {
            "success": True,
            "message": f"일정 '{summary}'을 생성했습니다.",
            "event_id": event.get("id", ""),
            "link": event.get("htmlLink", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def update_event(
    event_id: str,
    summary: str = None,
    start_datetime: str = None,
    end_datetime: str = None,
    description: str = None,
    location: str = None,
) -> Dict:
    """일정 수정"""
    service = _get_service()
    if not service:
        return {"error": "Google 인증 실패"}

    try:
        # 기존 이벤트 가져오기
        event = service.events().get(calendarId="primary", eventId=event_id).execute()

        if summary:
            event["summary"] = summary
        if start_datetime:
            if "T" in start_datetime:
                event["start"] = {"dateTime": start_datetime, "timeZone": "Asia/Seoul"}
            else:
                event["start"] = {"date": start_datetime}
        if end_datetime:
            if "T" in end_datetime:
                event["end"] = {"dateTime": end_datetime, "timeZone": "Asia/Seoul"}
            else:
                event["end"] = {"date": end_datetime}
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location

        updated = service.events().update(
            calendarId="primary", eventId=event_id, body=event
        ).execute()

        return {
            "success": True,
            "message": f"일정을 수정했습니다.",
            "event_id": updated.get("id", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def delete_event(event_id: str) -> Dict:
    """일정 삭제"""
    service = _get_service()
    if not service:
        return {"error": "Google 인증 실패"}

    try:
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return {"success": True, "message": "일정을 삭제했습니다."}
    except Exception as e:
        return {"error": str(e)}


# --- Tool 정의 ---

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": "Google Calendar에서 향후 일정 목록을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "description": "오늘부터 며칠 후까지 조회할지", "default": 7},
                    "max_results": {"type": "integer", "description": "최대 결과 수", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Google Calendar에 새 일정을 만듭니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "일정 제목"},
                    "start_datetime": {
                        "type": "string",
                        "description": "시작 시간 (YYYY-MM-DDTHH:MM:SS 또는 종일 일정은 YYYY-MM-DD)",
                    },
                    "end_datetime": {"type": "string", "description": "종료 시간 (없으면 시작+1시간)"},
                    "description": {"type": "string", "description": "설명"},
                    "location": {"type": "string", "description": "장소"},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "참석자 이메일 목록",
                    },
                },
                "required": ["summary", "start_datetime"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_event",
            "description": "Google Calendar의 기존 일정을 수정합니다. event_id는 list_events로 얻습니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "일정 ID"},
                    "summary": {"type": "string", "description": "제목"},
                    "start_datetime": {"type": "string", "description": "시작 시간"},
                    "end_datetime": {"type": "string", "description": "종료 시간"},
                    "description": {"type": "string", "description": "설명"},
                    "location": {"type": "string", "description": "장소"},
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "Google Calendar에서 일정을 삭제합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "삭제할 일정 ID"},
                },
                "required": ["event_id"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "list_events": list_events,
    "create_event": create_event,
    "update_event": update_event,
    "delete_event": delete_event,
}
