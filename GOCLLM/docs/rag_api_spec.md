
# RAG API Specification

사내 RAG 시스템에서 문서를 **저장(Indexing)** 하고 **검색(Retrieval)** 하기 위한 API 명세입니다.

---

# 1. Cluster Health Check

Elasticsearch 클러스터 상태 확인 API

### 상태 종류

| 상태     | 설명                             |
| ------ | ------------------------------ |
| green  | 모든 노드 정상                       |
| yellow | 일부 replica 누락                  |
| red    | 원본 + replica 모두 누락 (데이터 유실 상태) |

---

# 2. Index Information

인덱스 상태, 크기, 문서 수 등을 조회합니다.

### Parameter

| 이름         | 타입     | 설명                      |
| ---------- | ------ | ----------------------- |
| index_name | string | 조회할 인덱스명 (와일드카드 `*` 가능) |

예시

```
rp-gocinfo-mail
rp-gocinfo-*
```

---

# 3. Document Indexing (문서 저장)

문서를 RAG 검색 인덱스에 추가합니다.

문서 추가 시 **자동으로 chunking**이 수행됩니다.

---

## Request Body

```json
{
  "index_name": "rp-some-index",
  "data": {
    "doc_id": "ABCD00001",
    "title": "예시 제목",
    "content": "예시 컨텐츠",
    "permission_groups": ["ds"],
    "created_time": "2025-05-29T17:03:00.242+09:00"
  },
  "chunk_factor": {
    "logic": "fixed_size",
    "chunk_size": 100,
    "chunk_overlap": 50,
    "separator": " "
  }
}
```

---

## Required Fields

| Field   | Type   | 설명       |
| ------- | ------ | -------- |
| doc_id  | string | 문서 고유 ID |
| title   | string | 문서 제목    |
| content | string | 문서 내용    |

---

## Optional Fields

| Field             | Type      | Default | 설명         |
| ----------------- | --------- | ------- | ---------- |
| permission_groups | list[str] | ["ds"]  | 조회 권한      |
| created_time      | string    | 현재 시간   | 문서 생성 시간   |
| url               | list[str] | -       | 원본 링크      |
| custom fields     | any       | -       | 자유롭게 추가 가능 |

---

## Chunking 옵션

| Field         | 설명                       |
| ------------- | ------------------------ |
| logic         | chunking 방식 (fixed_size) |
| chunk_size    | chunk 크기 (100 ~ 8000)    |
| chunk_overlap | chunk overlap (50 이상)    |
| separator     | 토큰 구분자                   |

### 규칙

```
100 <= chunk_size <= 8000
50 <= chunk_overlap < chunk_size
```

---

# 4. Vector Document Insert (이미 임베딩된 문서 저장)

이미 임베딩된 벡터를 직접 저장할 수도 있습니다.

Embedding Model: **BGE-M3**

---

## Request Example

```json
{
  "index_name": "rp-some-index",
  "data": {
    "doc_id": "ABCD00001",
    "chunk_id": "ABCD00001_000001",
    "title": "예시 제목",
    "merge_title_content": "예시 제목 <SEP> 컨텐츠 내용",
    "v_merge_title_content": [0.123, -0.234, 0.456],
    "permission_groups": ["ds"],
    "created_time": "2025-05-29T17:03:00.242+09:00"
  }
}
```

---

## Required Fields

| Field                 | 설명               |
| --------------------- | ---------------- |
| doc_id                | 문서 ID            |
| chunk_id              | chunk ID         |
| title                 | 문서 제목            |
| merge_title_content   | title + content  |
| v_merge_title_content | embedding vector |

---

# 5. BM25 Keyword Search

텍스트 기반 검색 (BM25)

---

## Request Parameters

| Parameter         | Required | Type | Default                   | 설명      |
| ----------------- | -------- | ---- | ------------------------- | ------- |
| index_name        | O        | str  | -                         | 검색할 인덱스 |
| query_text        | O        | str  | -                         | 검색어     |
| permission_groups | O        | list | -                         | 조회 권한   |
| num_result_doc    |          | int  | 5                         | 반환 문서 수 |
| fields_exclude    |          | list | ["v_merge_content_title"] | 제외 필드   |

---

# 6. Vector Search (KNN)

벡터 유사도 기반 검색

---

## Request Parameters

| Parameter         | Required | Type | Default |
| ----------------- | -------- | ---- | ------- |
| index_name        | O        | str  | -       |
| query_text        | O        | str  | -       |
| permission_groups | O        | list | -       |
| num_result_doc    |          | int  | 5       |
| filter            |          | json | {}      |

---

## Filter Example

```
{
  "creator_id": ["gildong.hong"],
  "tags": ["rag", "llm"]
}
```

조건

* 동일 필드 → OR
* 다른 필드 → AND

---

# 7. Hybrid Search (BM25 + KNN)

BM25와 Vector Search를 결합한 검색 방식

---

## Request Parameters

| Parameter         | Required | Type | Default |
| ----------------- | -------- | ---- | ------- |
| index_name        | O        | str  | -       |
| query_text        | O        | str  | -       |
| permission_groups | O        | list | -       |
| num_result_doc    |          | int  | 5       |
| filter            |          | json | {}      |

---

# 8. Weighted Hybrid Search

BM25와 KNN 가중치 조절 가능

---

## Request Parameters

| Parameter  | Type  | Default | 설명       |
| ---------- | ----- | ------- | -------- |
| bm25_boost | float | 0.025   | BM25 가중치 |
| knn_boost  | float | 7.98    | KNN 가중치  |

---

# 9. Field Match Search (BM25)

특정 필드 기반 검색

---

## Request Parameters

| Parameter  | Required | 설명       |
| ---------- | -------- | -------- |
| field      | O        | 검색 대상 필드 |
| query_text | O        | 검색어      |
| operator   |          | OR / AND |

---

# 10. Exact Match Search

특정 필드에 대해 정확히 일치하는 값 검색

---

## Parameters

| Parameter  | 설명        |
| ---------- | --------- |
| field      | 검색 대상 필드  |
| query_text | 정확히 일치할 값 |

---

# 11. Document Delete

문서 삭제 API

⚠ 삭제 후 복구 불가

---

## Request Parameters

| Parameter         | Type | 설명        |
| ----------------- | ---- | --------- |
| index_name        | str  | 인덱스 이름    |
| permission_groups | list | 권한        |
| doc_id            | str  | 삭제할 문서 ID |

---

# 12. Important Rules

### 문서 크기 제한

```
content < 1MB
merge_title_content < 1MB
```

---

### 특수문자 제거

검색 및 문서 저장 시 **특수문자 및 제어문자 제거 필요**

---

### Permission Groups

검색 시 문서는 **permission_groups 일치 조건**으로 필터링됩니다.

예

```
permission_groups = ["ds"]
```

---

# 13. Retrieval Best Practices

추천 검색 방식

```
Hybrid Search (BM25 + KNN)
```

이유

* 키워드 매칭
* 의미 기반 유사도

동시에 활용 가능

---

# 14. Example Query

```json
{
  "index_name": "rp-gocinfo-mail",
  "query_text": "HBM 이슈",
  "permission_groups": ["ds"],
  "num_result_doc": 10
}
```

---

# 15. Notes

* 모든 문서는 JSON 형식
* 검색 시 특수문자 제거 필요
* filter는 AND / OR 규칙 적용
* 임베딩 모델: **BGE-M3**

