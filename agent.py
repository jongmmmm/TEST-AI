"""
Ollama Tool Calling 에이전트
gpt-oss 모델 기반, Gmail/Contacts/Calendar CRUD 지원
"""
import json
import requests
from datetime import datetime

from config import OLLAMA_API_URL, OLLAMA_MODEL

# 도구 모듈 임포트
from tools.gmail_tool import (
    TOOL_DEFINITIONS as GMAIL_TOOLS,
    TOOL_FUNCTIONS as GMAIL_FUNCS,
)
from tools.contacts_tool import (
    TOOL_DEFINITIONS as CONTACTS_TOOLS,
    TOOL_FUNCTIONS as CONTACTS_FUNCS,
)
from tools.calendar_tool import (
    TOOL_DEFINITIONS as CALENDAR_TOOLS,
    TOOL_FUNCTIONS as CALENDAR_FUNCS,
)

# 모든 도구 합치기
ALL_TOOLS = GMAIL_TOOLS + CONTACTS_TOOLS + CALENDAR_TOOLS
ALL_FUNCTIONS = {**GMAIL_FUNCS, **CONTACTS_FUNCS, **CALENDAR_FUNCS}

SYSTEM_PROMPT = f"""당신은 업무 자동화 비서입니다. 오늘 날짜는 {datetime.now().strftime('%Y-%m-%d')}입니다.

사용 가능한 도구:
- Gmail: 이메일 검색, 읽기, 발송, 삭제
- Google 주소록: 연락처 조회, 검색, 추가, 수정, 삭제
- Google Calendar: 일정 조회, 생성, 수정, 삭제

규칙:
- 이메일 발송이나 일정 생성 전에 반드시 사용자에게 확인을 받으세요.
- 한국어로 답변하세요.
- 도구 실행 결과를 사용자에게 알기 쉽게 정리해서 보여주세요.
"""

MAX_TOOL_LOOPS = 10


def call_ollama(messages: list, tools: list = None) -> dict:
    """Ollama API 호출"""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools

    try:
        resp = requests.post(
            f"{OLLAMA_API_URL}/api/chat",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        print(f"\n[오류] Ollama 서버({OLLAMA_API_URL})에 연결할 수 없습니다.")
        print("서버가 실행 중인지 확인하세요.")
        return None
    except Exception as e:
        print(f"\n[오류] API 호출 실패: {e}")
        return None


def execute_tool(name: str, arguments: dict) -> str:
    """도구 실행"""
    func = ALL_FUNCTIONS.get(name)
    if not func:
        return json.dumps({"error": f"알 수 없는 도구: {name}"}, ensure_ascii=False)

    try:
        result = func(**arguments)
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        # 결과가 너무 길면 자르기
        if len(result_str) > 10000:
            result_str = result_str[:10000] + "...(truncated)"
        return result_str
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def agent_loop(user_input: str, messages: list) -> str:
    """에이전트 메인 루프: 사용자 입력 → LLM → 도구 실행 → 반복"""

    messages.append({"role": "user", "content": user_input})

    for i in range(MAX_TOOL_LOOPS):
        response = call_ollama(messages, tools=ALL_TOOLS)
        if not response:
            return "[오류] LLM 응답 없음"

        msg = response.get("message", {})
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls", None)

        # 메시지에 assistant 응답 추가
        assistant_msg = {"role": role, "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        # 도구 호출이 없으면 최종 응답
        if not tool_calls:
            return content

        # 도구 실행
        for tc in tool_calls:
            func_info = tc.get("function", {})
            tool_name = func_info.get("name", "")
            arguments = func_info.get("arguments", {})

            # arguments가 문자열이면 파싱
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except:
                    arguments = {}

            print(f"  🔧 {tool_name}({json.dumps(arguments, ensure_ascii=False)[:100]})")

            result = execute_tool(tool_name, arguments)

            # 도구 결과를 메시지에 추가
            messages.append({
                "role": "tool",
                "content": result,
            })

    return "[경고] 최대 도구 호출 횟수에 도달했습니다."


def main():
    print("=" * 50)
    print("  Google Agent (gpt-oss)")
    print(f"  모델: {OLLAMA_MODEL} @ {OLLAMA_API_URL}")
    print("  도구: Gmail, Contacts, Calendar")
    print("  종료: quit 또는 exit")
    print("=" * 50)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "종료"):
            print("종료합니다.")
            break

        response = agent_loop(user_input, messages)
        print(f"\n{response}")


if __name__ == "__main__":
    main()
