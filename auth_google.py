"""
Google OAuth 인증 (WSL 환경용)
브라우저 URL을 출력하고, 인증 후 token.json을 저장합니다.
"""
import os

os.environ["OAUTHLIB_RELAX_TOKEN_SCOPES"] = "1"

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/calendar",
]

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")


def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"[오류] {CREDENTIALS_FILE} 파일이 없습니다.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)

    print("=" * 50)
    print("  Google OAuth 인증")
    print("=" * 50)
    print()
    print("아래 URL을 Windows 브라우저에 붙여넣기 하세요:")
    print()

    # 브라우저 자동 열기 비활성화, URL만 출력
    creds = flow.run_local_server(
        port=8090,
        open_browser=False,
        prompt="consent",
        access_type="offline",
    )

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print()
    print(f"인증 성공! {TOKEN_FILE} 저장 완료.")
    print("이제 python3 agent.py를 실행하세요.")


if __name__ == "__main__":
    main()
