# Gravity-16B-A3B-Base agent context

> 에이전트가 `trillionlabs/Gravity-16B-A3B-Base`의 구조, 용도, L1과의 차이를 빠르게 파악하기 위한 경량 스냅샷이다. 모델 가중치는 포함하지 않는다.

## Source

- Model: `trillionlabs/Gravity-16B-A3B-Base`
- Hugging Face: https://huggingface.co/trillionlabs/Gravity-16B-A3B-Base
- Parsed revision: `2b968cfd63c4b34c71b4f46599a584ddff6987f2`
- Snapshot date: 2026-08-21
- License: Apache-2.0
- Machine-readable snapshot: `./Gravity-16B-A3B-Base.json`

## What this model is

Gravity-16B-A3B-Base는 Trillion Labs와 Lunit Consortium이 random weights에서 약 5.5T tokens로 사전학습한 base causal language model이다. STEM과 의료 도메인에 높은 비중을 둔 sparse MoE 모델이며, Lunit의 의료 특화 L1 모델이 이 checkpoint를 기반으로 후속 학습되었다.

- Architecture: GravityMoE, DeepSeek 계열 sparse MoE with MLA
- Parameters: 16.24B total, 3.16B active per token
- Layers: 28
- Hidden size: 2,048
- Attention heads / KV heads: 16 / 16
- Experts: routed 64개 중 token당 top-8, shared 1개
- Context length: 32,768 tokens
- Vocabulary: 151,552
- Precision: bfloat16
- Tokenizer: GLM-4.5 기반, 영어·한국어 혼합 workload 고려

## L1과의 관계

| Property | Gravity-16B-A3B-Base | L1-16B-A3B |
|---|---|---|
| 역할 | 사전학습 base checkpoint | 의료·임상 특화 후속 학습 모델 |
| Instruction tuning | 없음 | 있음 |
| Safety alignment | 없음 | 모델 카드상 의료 사용 제약과 응답 동작 제공 |
| 권장 API 형태 | text completion | conversational generation |
| Thinking 응답 | 보장되지 않음 | `<think>...</think>` 동작을 명시 |
| 임상 의사결정 지원 | 직접 목적이 아님 | 주 용도로 명시 |

두 모델은 주요 architecture hyperparameter가 거의 같지만 학습 단계와 사용 계약이 다르다. Base 모델에 L1의 chat prompt나 임상 assistant 동작을 기대하면 안 된다.

## Architecture details

- Multi-head Latent Attention: `kv_lora_rank=512` low-rank KV compression
- MoE: 첫 layer는 dense MLP, 이후 layer는 64 routed experts와 1 shared expert 사용
- Routing: sigmoid score, auxiliary-loss-free balancing (`topk_method=noaux_tc`)
- RoPE: interleaved layout, base frequency `1,000,000`
- Dense intermediate size: 8,192
- MoE intermediate size: 1,408

## Agent-facing operational notes

1. 이 모델은 instruction-tuned chat model이 아니다. 기본 사용은 `/v1/completions` 또는 raw text continuation으로 본다.
2. tokenizer에 role, thinking, tool 관련 token이 존재하지만 이것만으로 chat/tool-use 능력이 학습되었다고 판단하면 안 된다.
3. upstream에는 `chat_template.jinja`와 `generation_config.json`이 없다. 별도 template을 임의 적용하면 품질이 달라질 수 있다.
4. `tokenizer_config.json`의 `model_max_length=128000`과 달리 model config 및 model card의 유효 context는 32,768이다. 안전한 기준은 32,768이다.
5. `trust_remote_code=True`가 필요하다. 프로덕션에서는 revision을 고정하고 remote Python code를 검토한다.
6. instruction tuning과 safety alignment가 없으므로 사실 오류, 편향, 유해 출력 가능성이 더 직접적이다.
7. 이 모델과 L1은 해커톤 endpoint의 `Lunit/L2-preview`가 아니다. L2의 retrieval/generation tool 계약을 이 base 모델에 적용하지 않는다.
8. 평가 환경은 외부 네트워크가 차단되므로 container runtime에 이 checkpoint를 다운로드하는 설계를 피한다.

## Repository footprint

원본 가중치는 4개 shard, 총 32,485,051,240 bytes(약 32.49GB)다. 이 문서 폴더에는 파생 Markdown/JSON만 저장한다.

| File group | Size | Included here |
|---|---:|---|
| `model-00001..00004.safetensors` | 32.49GB | 제외 |
| `tokenizer.json` | 19.97MB | 제외 |
| `model.safetensors.index.json` | 495KB | 제외 |
| `config.json` | 1.19KB | JSON에 구조화 |
| custom Python files | 약 6KB | hash와 경로만 기록 |
| tokenizer metadata | 약 8KB | 핵심 값과 hash 기록 |

## Reported evaluation snapshot

모델 카드가 instruction/post-training 전 base checkpoint에서 보고한 값이며 독립 재현 결과가 아니다.

| Benchmark | Metric | Score |
|---|---|---:|
| MMLU (5-shot) | acc | 73.0 |
| Global MMLU (EN) | acc | 73.5 |
| Global MMLU (KO) | acc | 65.8 |
| GPQA Main | acc | 38.4 |
| ARC-Challenge | acc_norm | 56.8 |
| HellaSwag | acc_norm | 77.9 |
| GSM8K | exact_match | 71.3 |
| HumanEval+ | pass@1 | 31.7 |
| MBPP+ | pass@1 | 73.3 |
| MedQA (4 options) | acc | 63.4 |
| CoQA | F1 | 77.5 |

## Hackathon takeaways and warnings

이 base checkpoint는 해커톤의 답변 모델 후보라기보다, 모델 선택과 harness 경계를 잘못 설계하지 않기 위한 비교 기준으로 참고한다.

### Directly useful guidance

- **Do not use the base checkpoint as a medical-answer fallback.** Instruction tuning과 safety alignment가 없으므로 L2 장애 시 Gravity Base가 환자 또는 임상의에게 직접 답하도록 전환하지 않는다. 장애 시에는 제한된 오류 응답이나 근거 부족 상태를 반환한다.
- **Special tokens do not prove tool-use capability.** Tokenizer에 role, thinking, observation, tool 관련 token이 있어도 tool schema 준수, 올바른 argument 생성, retrieval 종료 판단 능력을 의미하지 않는다. 실제 endpoint별 tool-call 동작을 별도로 검증한다.
- **Treat tokenizer and model limits separately.** Tokenizer metadata의 128,000과 model config의 32,768이 충돌한다. Harness의 context budget은 tokenizer 숫자 하나가 아니라 실제 serving endpoint의 제한, model config, 실패 테스트를 기준으로 정한다.
- **Keep raw completion and chat evaluation separate.** Base model의 text continuation 결과로 L1 또는 L2의 system prompt 품질을 판단하지 않는다. Prompt 비교는 같은 model, chat template, decoding 조건에서 수행한다.
- **Test Korean and English retrieval behavior independently.** 공개 Global MMLU의 한국어 점수가 영어보다 낮지만 이 수치는 retrieval query 품질을 직접 측정하지 않는다. 대신 한국어 질문, 영문 근거, 의학 약어, 혼합 언어 query를 별도 evaluation case로 둔다.
- **Avoid packaging local weights.** 약 32.49GB 가중치를 제출 image에 포함하거나 격리된 evaluation runtime에 다운로드하는 설계를 사용하지 않는다.
- **Prefer deterministic orchestration around the provided L2 endpoint.** Routing, call budget, timeout, retry, citation formatting은 Python state machine이 통제하고, 모델이 무제한 loop를 결정하게 하지 않는다.

### Conditional guidance for experimenting with Gravity Base

다음은 별도 GPU 환경에서 연구용 baseline으로 Gravity Base 자체를 실행할 때만 적용한다.

- Chat Completions보다 raw text completion을 기본 계약으로 보고 prompt와 stop sequence를 명시한다.
- 외부 safety layer와 출력 검증 없이 의료 사용자에게 응답을 노출하지 않는다.
- Tool calling, citation 생성, instruction following 능력을 기본 제공 기능으로 간주하지 않는다.
- Parsed revision을 고정하고 `trust_remote_code=True`로 실행되는 code와 dependency를 검토한다.
- bfloat16, 4개 weight shard, GPU memory, model load/cold-start 시간을 사전 측정한다.
- Benchmark를 재현할 때 few-shot 수, metric, prompt, decoding 조건을 함께 고정한다.

### Do not transfer these assumptions to L2

다음 Gravity Base 전용 정보는 `Lunit/L2-preview`의 runtime 계약이나 기본값으로 사용하지 않는다.

- 32,768-token context length와 GLM-4.5 tokenizer
- Raw `/v1/completions` 중심 사용 방식
- Instruction tuning과 safety alignment가 없다는 특성
- Chat template 및 generation config 부재
- GravityMoE/MLA architecture와 expert routing 설정
- `trust_remote_code=True` 및 로컬 Transformers loading 방식
- Base checkpoint의 MMLU, MedQA, CoQA 등 공개 benchmark 점수

L2의 conversation, retrieval/generation 단계, tool schema, 지원 parameter와 context 한도는 `../HACKATHON.md`, `../SUPPORT_PARAMETER.md` 및 실제 endpoint 검증 결과를 우선한다.

## Minimal inference reference

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "trillionlabs/Gravity-16B-A3B-Base"
revision = "2b968cfd63c4b34c71b4f46599a584ddff6987f2"

tokenizer = AutoTokenizer.from_pretrained(
    model_id,
    revision=revision,
    trust_remote_code=True,
)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    revision=revision,
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)

prompt = "The theory of relativity states that"
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
output = model.generate(**inputs, max_new_tokens=128, temperature=0.7, do_sample=True)
print(tokenizer.decode(output[0], skip_special_tokens=True))
```

## Refresh checklist

- upstream revision 및 license
- config/context length
- weight shard와 index 변경
- tokenizer metadata 및 special tokens
- remote-code file hash
- model card의 benchmark와 limitations
