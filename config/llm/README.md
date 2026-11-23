# LLM 연결 (외부 API + 자체 모델)

ConT의 모든 모듈은 `cont.llm.get_provider().complete(messages)` 한 가지 방법으로만 LLM을 부른다.
어떤 모델을 쓸지는 코드가 아니라 설정이 정한다.

| 파일 | 내용 |
|---|---|
| `providers.yaml` | 공용 목록 (git에 올라감, 키 없음) |
| `providers.local.yaml` | 개인·현장 전용 추가 목록 (git 제외) |
| `.env` 또는 OS 환경 변수 | 실제 API 키 (`OPENAI_API_KEY` 등) |

- 고르기: `CONT_LLM_PROVIDER=anthropic` (없으면 `default`)
- **새 공급자 추가**: OpenAI 형식(`/chat/completions`)을 지원하면 `type: openai_compatible`에 `base_url`만 바꿔 추가한다 (Ollama, vLLM, OpenRouter, Upstage, DeepSeek, Groq, xAI 등).
- 형식이 다른 공급자나 자체 모델 서버는 `cont.llm.register_type("이름", 클래스)`로 타입을 하나 추가한다. 다른 코드는 바꾸지 않는다.
- 외부 API와 자체 모델 비교는 같은 평가 세트를 공급자만 바꿔 돌린다.

