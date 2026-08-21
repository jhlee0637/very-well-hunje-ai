# 제출
## 제출 대상

제출 containerized multi-turn conversation driver를 제출합니다. Evaluator는 각 conversation turn을 service로 보냅니다. Driver는 conversation context를 활용해 접근 방식에 필요한 Model 또는 tool을 orchestrate하고 다음 assistant response를 반환해야 합니다.

## 제출 제약사항

Repository root에는 Dockerfile이 있어야 하며 evaluation VM에서 image build가 5분 이내에 완료되어야 합니다.
Container는 별도의 수동 작업 없이 시작되어야 하며 0.0.0.0:8000에서 service해야 합니다. Container port 8000만 평가합니다.
OpenAI-compatible API가 필요하며 최소한 GET /v1/models 및 POST /v1/chat/completions.

## 제출 전 checklist
- Branch: lunit/hackathon-submission
- Server: 0.0.0.0:8000
- Dockerfile: EXPOSE 8000
- Local build 및 실행: 아래 image tag는 local 예시입니다.
'''bash
docker build -t my-team-submission:local .
docker run --rm -p 8000:8000 my-team-submission:local
'''

- Dockerfile 예제
'''bash
FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
'''

# 규칙
- 개발 중에는 harness를 자유롭게 구성하고 선택할 수 있습니다.
- Evaluation은 외부 접근이 없는 완전히 격리된 환경 에서 실행됩니다.
- HealthBench benchmark를 과도하게 reverse engineering하는 행위는 금지됩니다. 관리자 code review에서 확인되면 해당 팀은 수상 자격을 잃습니다.

## Benchmark 및 evaluation 세부사항
- Hackathon 중, dashboard를 통해 주최 측이 지정한 검증 세트(validation set)에서 솔루션을 테스트하고 벤치마크 성능을 측정할 수 있습니다. 이를 활용해 솔루션을 debug하고, 제출물이 평가 서버에서 정상적으로 실행되는지 확인하시기 바랍니다.
- 이 마지막 제출을 dashboard를 통해 전송된 제출물을 최종 제출로 간주합니다. 각 팀의 최종 제출물은 운영진이 정의한 별도의 HealthBench holdout test set으로 평가합니다.
- 같은 제출물을 chat 품질에 대한 전문가 평가에도 사용합니다.
- Evaluation은 완전히 격리된 환경에서 실행되며 외부 접근은 허용되지 않습니다.

# Lunit Foundation Model Guide
## Lunit FM L2란?
 - L2는 Lunit 이 개발한 의료 특화 LLM 입니다.
 - 범용 chat model이 아닙니다. 다음 두 가지 특성 때문에 일반적인 Model과 다르게 동작합니다:
 	 - Retrieval과 generation의 두 단계로 동작하며, 각 단계마다 Model을 별도로 호출합니다.
	 - Retrieval 중 evidence와 관련 정보를 수집하도록 특정 tool set 으로 학습했습니다.
	 - 해당 tool은 이 Hackathon에서 제공하는 MCP tools입니다.
- 범용 LLM처럼 다루면 예상대로 동작하지 않을 가능성이 큽니다. 가장 큰 Challenge 는 이 Model을 제어하는 harness를 만드는 것이 될 것 입니다.
## 두 단계
- 일반적인 범용 LLM은 한 번에 질문을 읽고 , 생각하고, tool을 호출한 뒤 필요하면 답변합니다. L2는 이 과정을 명확히 두 단계로 나눕니다.
### Retrieval 단계
- 질문을 받으면 Model은 필요한 evidence를 판단하고 MCP tools로 검색·열람·관련 정보 수집을 반복합니다. 충분한 정보를 모으면 관련 정보가 있다고 판단한 item을 선택해 출력합니다.
- 최종 답변을 작성하지 않습니다 .
- 일부 MCP tool result에는 cite_uidfield가 있습니다. 이 field는 item을 citation 가능하게 표시하고 이후 Model이 item을 참조하는 방법입니다.
- Retrieval이 끝나면 Model은 content가 아니라 각 관련 item의 cite_uid 를 보고합니다: Model이 다음을 호출해야 단계가 끝납니다: finalize_retrieval.
- 이 함수는 MCP tool이 아닙니다. 직접 정의해 MCP tools와 함께 제공하고 system prompt에서 호출하도록 Model에 지시하세요.
'''
from typing import Literal
from pydantic import BaseModel, Field

class CitableItem(BaseModel):
    cite_uid: str
    relevance_score: float

class CitationSelection(BaseModel):
    status: Literal["sufficient", "partial", "no_evidence"]
    items: list[CitableItem] = Field(default_factory=list)
    note: str = ""

def finalize_retrieval(
    status: Literal["sufficient", "partial", "no_evidence"],
    items: list[CitableItem],
    note: str = "",
) -> CitationSelection:
    """Submit your final citation selection and end the retrieval phase.

    Call this only:
    - once you have gathered enough evidence to answer the query
    - the query does not need any retrieval
    - you exhausted the tool call budget and must end the retrieval
    """
    return CitationSelection(status=status, items=items, note=note)
'''
### Retrieval trajectory 예제
 - 사용자: 가이드라인에 따르면 만성 신장질환 환자에게 어떤 혈압 목표를 권고하나요?
 - L2: 
 '''
 #Tool call
 index_list_documents(corpus_tag="guideline", query="hypertension chronic kidney disease")
 #Tool result
 #12 documents, each with node_id, title, summary
 
 #Tool call
 index_get_relevant_nodes(corpus_tag="guideline", query="blood pressure target CKD", node_id="0823b")
 #Tool result
 #4 leaf nodes with their page ranges and ancestor chains

 #Tool call
 index_get_page_content(corpus_tag="guideline", doc_id="0823b", start_page=48, end_page=52)
 #Tool result
 #page text for pages 48-52, carrying cite_uid "cite-3f9a1c7d2e5b8046"

 #Tool call
 finalize_retrieval(
     status="sufficient",
     items=[{"cite_uid": "cite-3f9a1c7d2e5b8046", "relevance_score": 0.95}],
     note=""
 )
 #— Retrieval 단계 종료 —
 '''

### Generation 단계
 - 질문을 받으면 L2는 먼저 memory만으로 답할 수 있는지, 추가 정보가 필요한지 판단합니다.
 - 일반적인 의료 질문은 직접 답할 수 있습니다. 특정 guideline, 법률과 같은 질문에 정확히 답하려면 추가 정보가 필요합니다.
 - 이때 retrieval을 사용합니다. Generation 단계에는 다음 tool 하나만 제공해야 합니다: retrieve_relevant_content.
'''bash
def retrieve_relevant_content(query: str):
    """Retrieve relevant content to ground your answer. Pass a single, self-contained query."""
    # Run the retrieval stage here and return the relevant information.
'''
 - 이 tool은 retrieval 단계를 실행해 관련 정보를 모으고, 최종 답변을 생성하도록 Model에 전달합니다. Retrieval과 generation을 연결하는 방식은 자유롭게 설계할 수 있습니다.
### Generation trajectory 예제
 - 사용자: 가이드라인에 따르면 만성 신장질환 환자에게 어떤 혈압 목표를 권고하나요?
 - L2:
 '''
 #Tool call
 retrieve_relevant_content(query="recommended blood pressure target for adults with chronic kidney disease")
 #Tool result
 #status: sufficient
 #
 #[1]
 #source_type: guideline
 #url: https://example.org/guideline/0823b
 #title: 2024 Clinical Practice Guideline for the Management of Hypertension
 #content: In adults with chronic kidney disease, treat to a systolic blood pressure target of less
 #than 120 mmHg when tolerated, ...
 '''
 - L2:  가이드라인에 따르면 만성 신장질환 성인에게 내약 가능한 경우 수축기 혈압 120 mmHg 미만을 목표로 치료할 것을 권고합니다 [1].

## Tip
- 각 단계에 맞는 system prompt를 별도로 만들고 합치지 마세요.
- Retrieval에는 MCP tools와 finalize_retrieval. generation에는 retrieve_relevant_content 만 제공하여 최종 답변을 생성할 수 있도록 해주세요.
- Retrieval query는 그 자체로 완결되어야 합니다. “그 약의 용량은?” 같은 지시 대상을 해소한 뒤 retrieval에 전달하세요.
- Retrieval 중 tool call 횟수를 제한하세요.
- status 및 note 를 통해 retrieval에서 generation으로 정보를 전달할 수 있습니다.

## 제약사항
- L2는 single-turn 대화에 최적화되어 있지만 Hackathon에서는 multi-turn scenario도 평가합니다.
- Query rewriting, context summarization 등으로 이 제약을 완화하는 방법도 challenge의 일부입니다.
- 이 가이드는 L2의 권장 사용 방법이며 필수는 아닙니다. 규칙을 준수한다면 다른 system을 구성해도 됩니다.

# Model API
- Lunit FM endpoint URL: https://model.hackathon.lunit.io/
- Patient Simulator URL: https://patient.hackathon.lunit.io/

## Model API 사용 방법
 - API key는 ./secrets.json 파일을 참고하되 밸류값 자체는 출력하거나 코드에 복사하지 말 것.
 - Shell 환경에서 API 사용 방법
 '''shell
 export LUNIT_FM_API_URL="https://model.hackathon.lunit.io"
 export LUNIT_FM_API_KEY={very-well-hunje-ai_API_KEY 값 사용}
 export LUNIT_FM_MODEL="Lunit/L2-preview"
 '''
 - Chat Completions API 사용 방법
 '''
 curl "$LUNIT_FM_API_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LUNIT_FM_API_KEY" \
  -d '{
    "model": "'"${LUNIT_FM_MODEL}"'",
    "messages": [
      {"role": "system", "content": "You are a careful medical assistant."},
      {"role": "user", "content": "Summarize the key findings."}
    ]
  }'
[지원 parameter 참고](./SUPPORT_PARAMETER.md)

## Patient Simulator란?
 - Patient Simulator는 한국어 의료 대화에서 환자 또는 임상의 역할인 user 측을 재현하는 OpenAI-compatible 질문 생성기입니다.
 - Harness는 대화의 assistant입니다.
 - Simulator message는 user turn이고, system 응답은 assistant turn입니다.
 - 전체 conversation history를 client에 유지하고 매 turn마다 POST하세요. Session ID는 필요하지 않습니다.
### 첫 질문
 - 빈 messages array를 보내세요. 요청할 때마다 새 질문을 반환합니다.
'''
curl -s "https://patient.hackathon.lunit.io/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LUNIT_FM_API_KEY" \
  -d '{
    "model": "patient-simulator-ko",
    "messages": []
  }' \
  | jq -r '.choices[0].message.content'
'''
 - 새 질문만 필요하면 이 요청을 반복하세요. 동시 요청을 지원하며 한 번 호출하는 데 약 14초가 걸립니다.
### 후속 질문
 - 받은 질문과 system 답변을 표시된 그대로 추가한 뒤 전체 history를 다시 보내세요.
'''
 curl -s "https://patient.hackathon.lunit.io/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LUNIT_FM_API_KEY" \
  -d '{
    "model": "patient-simulator-ko",
    "messages": [
      {"role": "user", "content": "<received question>"},
      {"role": "assistant", "content": "<your system answer>"}
    ]
  }' \
  | jq -r '.choices[0].message.content'
'''
 - 후속 질문 생성에는 약 8초가 걸립니다.
 - 첫 질문을 정확히 보존하세요. 수정하면 conversation continuation이 깨질 수 있습니다.
 - 약 3 turn 후에 중단하세요. 대화가 길어지면 같은 질문을 반복할 수 있습니다.
 - 응답이 404이면 빈 messages array로 새 대화를 시작하세요. 응답이 502이면 요청을 다시 시도하세요.

# Lunit MCP tools 살펴보기
## MCP server 연결
 - 팀 API key를 export하고 Codex configuration에 server를 추가한 뒤 Codex를 재시작하고 /mcp 를 열어 연결을 확인하세요.
 - Shell 환경
 '''shell
 export LUNIT_FM_API_KEY="lunit_..."
 '''
 - Codex configuration
 '''toml
 ~/.codex/config.toml
 
 [mcp_servers.lunit_mcp]
 url = "https://mcp.hackathon.lunit.io/mcp"
 bearer_token_env_var = "LUNIT_FM_API_KEY"
 required = true
 tool_timeout_sec = 60
 '''
 - 다른 Streamable HTTP MCP client도 같은 endpoint 와 같은 인증 Authorization: Bearer <API_KEY> 을 이용하면 됩니다.
 - lunit_mcp 은 임의의 local server 이름입니다. 원하는 이름으로 바꿀 수 있습니다.
 - [Codex MCP configuration 참고](./CODEX_MCP_CONFIGURATION.md)

## 사용 가능한 MCP tools
 - Tool은 다음 mcp__lunit_mcp__prefix로 제공됩니다.
 
```markdown
| Tool | 출처 | 설명 |
|---|---|---|
| `adr_retrieve_drug_info` | `dailymed_26_08` (DailyMed) | 영문 brand name 또는 INN으로 공식 DailyMed drug label의 주요 section을 조회합니다. Warning, adverse reaction, interaction, source link를 포함합니다. |
| `hira_updates_search` | `hira_biz_infobank` · `hira_cancer_drug_notice` · `hira_cancer_drug_regimen` | 현행·개정 guidance, oncology notice, 인정된 off-label oncology regimen에서 HIRA 급여기준 고시와 공개 심의사례를 검색합니다. |
| `index_get_document_structure` | `hira` (249 docs) · `guideline` (120 docs) | HIRA 또는 clinical guideline 문서를 section tree로 탐색하며 시작 node부터 최대 50개 node와 page range를 반환합니다. |
| `index_get_page_content` | `hira` (249 docs) · `guideline` (120 docs) | 선택한 문서 page range의 원문을 반환합니다. Page는 1부터 시작하며 호출당 최대 20 page와 추출된 flowchart path를 조회할 수 있습니다. |
| `index_get_relevant_nodes` | `hira` (249 docs) · `guideline` (120 docs) | Query와 의미적으로 관련된 문서 section을 찾아 일치하는 문서, ancestor node, page range를 반환합니다. |
| `index_keyword_search` | `hira` (249 docs) · `guideline` (120 docs) | 대소문자 구분 없이 정확한 keyword로 문서 page를 검색하고 일치 term·출현 횟수로 순위를 매기며 pagination을 지원합니다. |
| `index_list_documents` | `hira` (249 docs) · `guideline` (120 docs) | 사용 가능한 HIRA와 clinical guideline collection에서 corpus 문서를 나열하거나 query 관련도 순으로 정렬합니다. |
| `kcd_get_name` | `kcd` (KCD-8 · KCD-9) | 정확한 KCD code의 공식 한글·영문 질병명을 반환합니다. KCD-8과 KCD-9을 지원하며 기본값은 KCD-9입니다. |
| `kcd_search_codes` | `kcd` (KCD-8 · KCD-9) | 한글 또는 영문 질병명으로 candidate KCD code를 유사 검색하며 KCD version을 선택할 수 있습니다. |
| `openapi_hira_disease_check_code` | HIRA Disease Master OpenAPI | 진단 code가 HIRA 청구에 유효한지 확인하고 code 완전성, 주상병, 성별, 연령, 감염병 제한을 반환합니다. |
| `openapi_hira_get_drug_price` | HIRA Drug Price OpenAPI | HIRA 약가 data에서 급여 등재 상태, 약가 code, 상한가를 조회하며 삭제 및 적용일 정보를 포함합니다. |
| `openapi_law_get_article` | Korean Law Information Center OpenAPI (`law.go.kr`) | 선택한 한국 법령 조문의 전문을 citation 가능한 형태로 조회하며 조문 시행일과 `law.go.kr` link를 포함합니다. |
| `openapi_law_list_articles` | Korean Law Information Center OpenAPI (`law.go.kr`) | 특정 한국 법령의 조문을 나열하고 조문 제목 filter를 지원하며 전문 조회용 stable article key를 반환합니다. |
| `openapi_law_search` | Korean Law Information Center OpenAPI (`law.go.kr`) | 한국 법령을 검색하고 법률·행정규칙·자치법규의 후속 조회에 필요한 MST identifier를 반환합니다. |
| `openapi_mfds_check_drug_permission` | MFDS Drug Approval OpenAPI | 부분 product name 검색으로 의약품의 현재 MFDS 허가 여부를 확인하고 유효 허가와 취하 허가를 구분합니다. |
| `openapi_mfds_find_drugs_by_ingredient` | MFDS Drug Approval OpenAPI | 동일 active ingredient를 사용하는 MFDS 허가 제품을 찾고 대체 candidate의 허가 상태를 반환합니다. |
| `openapi_mfds_get_drug_indication` | MFDS Product Approval Detail OpenAPI | 의약품의 MFDS 허가 indication을 조회하며 선택적으로 dosage, administration, warning, ATC data, contraindication을 반환합니다. |
| `rag_get_all_data_sources` | `pubmed_abstracts` · `hira_faq` · `faers_12q4_25q4` · `dailymed_26_08` · `kcd` | 사용 가능한 모든 SQL, vector, hybrid data source의 identifier와 용도를 나열합니다. |
| `rag_get_data_source_detail` | `pubmed_abstracts` · `hira_faq` · `faers_12q4_25q4` · `dailymed_26_08` · `kcd` | 하나의 SQL, vector 또는 hybrid data source에 대한 schema, table, column, metadata를 표시합니다. |
| `rag_sql_query` | `faers_12q4_25q4` · `dailymed_26_08` · `kcd` | 사용 가능한 FAERS, DailyMed, KCD dataset의 structured PostgreSQL data를 SQL로 조회합니다. |
| `rag_vector_query` | `pubmed_abstracts` · `hira_faq` | Vector 또는 dense-plus-sparse hybrid retrieval로 지원되는 Qdrant collection을 semantic similarity 기반 검색합니다. |
```

