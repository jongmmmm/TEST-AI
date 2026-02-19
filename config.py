# Ollama 설정
OLLAMA_API_URL = "http://192.168.0.13:11434"
OLLAMA_MODEL = "gpt-oss"

# Gmail 설정 (App Password)
GMAIL_EMAIL = ""          # 예: user@gmail.com
GMAIL_APP_PASSWORD = ""   # Google 계정 → 2단계 인증 → 앱 비밀번호

# Google OAuth 2.0 설정 (Contacts, Calendar용)
# Google Cloud Console에서 OAuth 클라이언트 ID 생성 후
# credentials.json 파일을 test/ 폴더에 저장
GOOGLE_CREDENTIALS_FILE = "credentials.json"
GOOGLE_TOKEN_FILE = "token.json"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/calendar",
]
