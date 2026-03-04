 
Health Check
클러스터 상태를 검사하는 API입니다.
green	모든 노드가 정상 작동 중인 상태
yellow	인덱스의 복제본이 누락된 상태
red	인덱스의 복제본과 원본 데이터 모두 누락된 상태(즉, 데이터가 유실된 상태)
Index Information
인덱스의 health 상태, 크기, 문서 수 등의 정보를 조회하는 API입니다.
index_name	검색할 인덱스명(또는 별칭)입니다. 여러 인덱스일 경우 쉼표로 구분하며 와일드카드(*)를 지원합니다.
Health Check
This is an API which check the status of the Elasticsearch cluster
green	All nodes are functioning normally
yellow	Some of replicas are missed
red	Original data and all replicas are missed
Index Information
This is an API which shows status of a given index, size, number of documents and so on.
index_name	The index name (or alias) to be searched. Multiple indexes are separated by commas and wildcard character (*) is supported.
문서 한 건당 한 번씩 호출합니다.
data 필드
doc_id, title, content 필드를 포함하지 않으면 에러가 발생합니다.
content의 크기는 1MB보다 작아야 합니다.
permission_groups 필드를 포함하지 않으면 ["ds"]로 저장됩니다.
created_time 필드를 포함하지 않으면 현재 시간이 저장됩니다.
chunk_factor 필드
chunk_factor 필드를 포함하지 않으면 기본 값이 적용됩니다. (파라미터 소개의 기본 값 참고)
100 <= chunk_size <= 8000
50 <= chunk_overlap < chunk_size
{
  "index_name": "rp-some-index",
  "data": {
    "doc_id": "ABCD00001",
    "title": "예시 제목",
    "content": "예시 컨텐츠",
    "permission_groups": [
      "ds"
    ],
    "created_time": "2025-05-29T17:03:00.242+09:00",
    "additionalField1": "...",
    "additionalField2": "..."
  },
  "chunk_factor": {
    "logic": "fixed_size",
    "chunk_size": 100,
    "chunk_overlap": 50,
    "separator": " "
  }
}
문서에 특수문자 및 제어문자는 제거해 주세요.
추후 검색에서 사용할 'permission_groups' 필드와, 문서 추가 시 사용 할 'permission_groups' 필드가 매칭 됩니다.
'chunk_factor'에 chunk_size와 chunk_overlap 크기를 0으로 사용할 수 없습니다.
파라미터	타입	필수값	기본 값	예시	설명
index_name	str	
문서를 저장할 인덱스명 입니다.
data	Mapping	doc_id (str)	O	-	'AAAA0001'	문서의 고유한 ID (중복될 수 없는 값)
title (str)	O	-	'반도체란'	 
content (str)	O	-	'반도체는 영어로 semiconductor로 ....'	
'chunk_factor' 파라미터에 맞게 적당한 길이로 잘립니다. 각각의 문서는 같은 'doc_id'을 가지고, chunk_id(=_id)로 구분됩니다.
생성된'merge_title_content' 형식은 "title [SEP] content" 따릅니다. 기존 'content'는 저장되지 않고 삭제됩니다.
데이터의 크기는 1MB보다 작아야 합니다.
permission_groups (List[str])	
['ds']	['ds']	 필드가 없을 경우 ['ds'] 등록
created_time (str)	
(현재 시간)
2025-05-01T01:00:00.001+09:00	'2025-05-01'	 필드가 없을 경우 현재 시간을 ISO 형식으로 등록
url (List[str])	
-	['www.example.com', 'www.samsungds.net']	 
다른 필드 추가 가능	
 
chunk_factor
Mapping	logic	 	'fixed_size'	 	문서를 일정 길이로 자릅니다.
chunk_size	
100	 	100 token 씩 자릅니다. (100 <= chunk_size <= 8000)
chunk_overlap	 	50	 	50 token씩 overlap이 존재합니다. (50 <= chunk_overlap < chunk_size)
separator	 	' ' (공백)	 	token 구분자 입니다.
문서 한 건당 한 번씩 호출합니다.
data 필드
doc_id, chunk_id, title, merge_title_content, v_merge_title_content 필드를 포함하지 않으면 에러가 발생합니다.
merge_title_content의 크기는 1MB보다 작아야 합니다.
permission_groups 필드를 포함하지 않으면 ["ds"]로 저장됩니다.
created_time 필드를 포함하지 않으면 현재 시간이 저장됩니다.
{
  "index_name": "rp-some-index",
  "data": {
    "doc_id": "ABCD00001",
    "chunk_id": "ABCD00001_000001",
    "title": "예시 제목",
    "merge_title_content": "예시 제목 <SEP> 컨텐츠 내용이 들어갑니다.",
    "v_merge_title_content": [0.12322878, 0.387727, ... -0.8867332],
    "permission_groups": [
      "ds"
    ],
    "created_time": "2025-05-29T17:03:00.242+09:00",
    "additionalField1": "...",
    "additionalField2": "..."
  }
}
문서에 특수문자 및 제어문자는 제거해 주세요.
추후 검색에서 사용할 'permission_groups' 필드와, 문서 추가 시 사용 할 'permission_groups' 필드가 매칭 됩니다.
파라미터	타입	필수값	기본 값	예시	설명
index_name	str	
문서를 저장할 인덱스명 입니다.
data	Mapping	doc_id (str)	O	-	'AAAA0001'	문서의 고유한 ID (중복될 수 없는 값)
chunk_id (str)	O	-	'AAAA0001_000001'	 
title (str)	O	-	'반도체란'	 
v_merge_title_content (List[float])	O	-	[0.343, 0.23113, 0.8973, -0.2343, ... -0.3343]	
BGE-M3 임베딩 모델로 임베딩된 dense vector 리스트
merge_title_content(str)	O	-	'반도체는 영어로 semiconductor로 ....'	
임베딩 된 문장. 데이터의 크기는 1MB보다 작아야 합니다.
permission_groups (List[str])	
['ds']	['ds']	 필드가 없을 경우 ['ds'] 등록
created_time (str)	
(현재 시간)
2025-05-01T01:00:00.001+09:00	'2025-05-01'	 필드가 없을 경우 현재 시간을 ISO 형식으로 등록
url (List[str])	
-	['www.example.com', 'www.samsungds.net']	 
다른 필드 추가 가능	
 
If 'doc_id', 'title', and 'content' are not included in the 'data' field, an error occurs.
If 'data.permission_groups' is not included, ["ds"] will be registered in the permission_groups.
If 'data.created_time' is not included, current ISO time string will be registered in the created_time. 
{
  "index_name": "rp-some-index",
  "data": {
    "doc_id": "ABCD00001",
    "chunk_id": "ABCD00001_000001",
    "title": "예시 제목",
    "merge_title_content": "예시 제목 <SEP> 컨텐츠 내용이 들어갑니다.",
    "v_merge_title_content": [0.12322878, 0.387727, ... -0.8867332],
    "permission_groups": [
      "ds"
    ],
    "created_time": "2025-05-29T17:03:00.242+09:00",
    "additionalField1": "...",
    "additionalField2": "..."
  }
}
Please remove special characters in your documents.
The 'permission_groups' field, which will be used in retrieval API, matches the 'permission_groups' field, which is used when adding document.
You can not use '0' in the both 'chunk_size' and 'chunk_overlap' fields.
100 < chunk_size <= 8000
50 < chunk_overlap < chunk_size
content < 1MB
파라미터	타입	기본 값	예시	설명
index_name	str	
Index name, if you use more than 2, it should be seprated by ',' (ex. 'rp-index-1,rp-index-2')
data	Mapping	doc_id	-	'AAAA0001'	Unique document ID
title	-	'What is the semiconductor'	 
content	-	'Semiconductor is ....'	
It will be chunked in the length of 'chunk_factor' parameter.
Each chunk has the same 'doc_id'.
Internally, we generate a new field named 'merge_title_content' which combines 'title' and 'content_parsed' like "title [SEP] content_parsed"
permission_groups	-	['ds']	 
created_time	-	'2025-05-01'	 
chunk_factor
Mapping	logic	'fixed_size'	 	It means that your document will be chunked with a fixed size
chunk_size	100	 	Size of each chunk
chunk_overlap	50	 	Overlapping size between adjacent chunks
separator	' '	 	Token separator
If doc_id, chunk_id, title, merge_title_content, v_merge_title_content are not included in the 'data' field, an error occurs.
If 'data.permission_groups' is not included, ["ds"] will be registered in the permission_groups.
If 'data.created_time' is not included, current ISO time string will be registered in the created_time. 
{
  "index_name": "rp-some-index",
  "data": {
    "doc_id": "ABCD00001",
    "title": "예시 제목",
    "content": "예시 컨텐츠",
    "permission_groups": [
      "ds"
    ],
    "created_time": "2025-05-29T17:03:00.242+09:00",
    "additionalField1": "...",
    "additionalField2": "..."
  },
  "chunk_factor": {
    "logic": "fixed_size",
    "chunk_size": 100,
    "chunk_overlap": 50,
    "separator": " "
  }
}
Please remove special characters in your documents.
The 'permission_groups' field, which will be used in retrieval API, matches the 'permission_groups' field, which is used when adding document.
파라미터	Type	Default	Example	Detail
index_name	str	O	'rp-test-index'	Index name, if you use more than 2, it should be seprated by ',' (ex. 'rp-index-1,rp-index-2')
data	Mapping	doc_id	O	'AAAA0001'	Unique document ID
chunk_id (str)	O	'AAAA0001_000001'	
title	O	'What is the semiconductor'	 
v_merge_title_content (List[float])	O	[0.343, 0.23113, 0.8973, -0.2343, ... -0.3343]	Vector list which is embedded by 'BGE-M3' embedding model.
merge_title_content(str)	O	'Semiconductor is ....'	Sentence which is used for embedding.
permission_groups	-	['ds']	 
created_time	-	'2025-05-01'	 
other custom fields... (freely)	-	
 
텍스트 일치 검색 (BM25 알고리즘 기반) 입니다.
permission_groups의 권한에 매칭 되는 문서만 검색할 수 있습니다.
모든 문서들은 json형식으로 저장되어 있습니다. 검색 시 특수문자 및 제어문자는 제거해 주세요.
파라미터	필수	타입	기본값	설명
index_name	O	str	-	검색할 인덱스명(또는 별칭)입니다. 여러 인덱스일 경우 쉼표로 구분하며 와일드카드(*)를 지원합니다.
query_text	O	str	-	검색할 내용입니다.
permission_groups	O	List[str]	-	조회 권한입니다.
num_result_doc	
int	5	반환할 문서 수입니다.
fields_exclude	
List[str]	["v_merge_content_title"]	반환 문서에서 제외할 필드명입니다.
벡터화 된 공간에서 사용자 질문과 K-Nearest Neighborhood 알고리즘 기반으로 비슷한 문서들을 반환합니다.
permission_groups의 권한에 매칭 되는 문서만 검색할 수 있습니다.
모든 문서들은 json형식으로 저장되어 있습니다. 검색 시 특수문자 및 제어문자는 제거해 주세요.
KNN 검색을 사용할 경우, 검색 쿼리 임베딩 모델과 문서 임베딩 모델이 상이한 경우에는 검색 결과가 좋지 않을 수 있습니다.
filter는 필드 값과 검색 대상 값의 쌍으로 구성됩니다. 이 때 검색 대상 값은 항상 배열이어야 하고 검색 대상 값 사이에는 OR 조건 비교를 합니다. 또한 2개 이상의 필드를 필터링 대상으로 지정할 수도 있으며, AND 조건 검색으로 필터링합니다.  
   다음 예제는 creator_id가 gildong.hong이고 tags 목록에 rag 또는 llm이 포함되는 문서만 필터링하는 예제입니다.
{"creator_id": ["gildong.hong"], "tags": ["rag", "llm"]}
파라미터	필수	타입	기본값	설명
index_name	O	str	-	검색할 인덱스명(또는 별칭)입니다. 여러 인덱스일 경우 쉼표로 구분하며 와일드카드(*)를 지원합니다.
query_text	O	str	-	검색할 내용입니다.
permission_groups	O	List[str]	-	조회 권한입니다.
num_result_doc	
int	5	반환할 문서 수입니다.
fields_exclude	
List[str]	["v_merge_content_title"]	반환 문서에서 제외할 필드명입니다.
filter	
json	{}	문서 검색 필터입니다.
BM25와 KNN 방식을 동시에 사용한 하이브리드(hybrid) 검색입니다.
permission_groups의 권한에 매칭 되는 문서만 검색할 수 있습니다.
모든 문서들은 json형식으로 저장되어 있습니다. 검색 시 특수문자 및 제어문자는 제거해 주세요.
KNN 검색을 사용할 경우, 검색 쿼리 임베딩 모델과 문서 임베딩 모델이 상이한 경우에는 검색 결과가 좋지 않을 수 있습니다.
filter는 필드 값과 검색 대상 값의 쌍으로 구성됩니다. 이 때 검색 대상 값은 항상 배열이어야 하고 검색 대상 값 사이에는 OR 조건 비교를 합니다. 또한 2개 이상의 필드를 필터링 대상으로 지정할 수도 있으며, AND 조건 검색으로 필터링합니다.  
   다음 예제는 creator_id가 gildong.hong이고 tags 목록에 rag 또는 llm이 포함되는 문서만 필터링하는 예제입니다.
{"creator_id": ["gildong.hong"], "tags": ["rag", "llm"]}
파라미터	필수	타입	기본값	설명
index_name	O	str	-	검색할 인덱스명(또는 별칭)입니다. 여러 인덱스일 경우 쉼표로 구분하며 와일드카드(*)를 지원합니다.
query_text	O	str	-	검색할 내용입니다.
permission_groups	O	List[str]	-	조회 권한입니다.
num_result_doc	
int	5	반환할 문서 수입니다.
fields_exclude	
List[str]	["v_merge_content_title"]	반환 문서에서 제외할 필드명입니다.
filter	
json	{}	문서 검색 필터입니다.
하이브리드 방식에서 BM25와 KNN의 비율을 조정해 검색합니다.
permission_groups의 권한에 매칭 되는 문서만 검색할 수 있습니다.
모든 문서들은 json형식으로 저장되어 있습니다. 검색 시 특수문자 및 제어문자는 제거해 주세요.
KNN 검색을 사용할 경우, 검색 쿼리 임베딩 모델과 문서 임베딩 모델이 상이한 경우에는 검색 결과가 좋지 않을 수 있습니다.
filter는 필드 값과 검색 대상 값의 쌍으로 구성됩니다. 이 때 검색 대상 값은 항상 배열이어야 하고 검색 대상 값 사이에는 OR 조건 비교를 합니다. 또한 2개 이상의 필드를 필터링 대상으로 지정할 수도 있으며, AND 조건 검색으로 필터링합니다.  
   다음 예제는 creator_id가 gildong.hong이고 tags 목록에 rag 또는 llm이 포함되는 문서만 필터링하는 예제입니다.
{"creator_id": ["gildong.hong"], "tags": ["rag", "llm"]}
파라미터	필수	타입	기본값	설명
index_name	O	str	-	검색할 인덱스명(또는 별칭)입니다. 여러 인덱스일 경우 쉼표로 구분하며 와일드카드(*)를 지원합니다.
query_text	O	str	-	검색할 내용입니다.
permission_groups	O	List[str]	-	조회 권한입니다.
bm25_boost	
float	0.02531451142318286	BM25 검색에 부여할 가중치 값입니다.
knn_boost	
float	7.980074401837717	KNN 검색에 부여할 가중치 값입니다.
num_result_doc	
int	5	반환할 문서 수입니다.
fields_exclude	
List[str]	["v_merge_content_title"]	반환 문서에서 제외할 필드명입니다.
filter	
json	{}	문서 검색 필터입니다.
필드를 특정한 텍스트 일치 검색(BM25 알고리즘 기반) 입니다.
permission_groups의 권한에 매칭 되는 문서만 검색할 수 있습니다.
모든 문서들은 json형식으로 저장되어 있습니다. 검색 시 특수문자 및 제어문자는 제거해 주세요.
파라미터	필수	타입	기본값	설명
index_name	O	str	-	검색할 인덱스명(또는 별칭)입니다. 여러 인덱스일 경우 쉼표로 구분하며 와일드카드(*)를 지원합니다.
field	O	str	-	검색할 필드명입니다.
query_text	O	str	-	검색할 내용입니다.
permission_groups	O	List[str]	-	조회 권한입니다.
num_result_doc	
int	5	반환할 문서 수입니다.
operator	
str	"OR"	query_text의 각 단어(토큰) 매칭 방법입니다. OR 또는 AND를 사용합니다.
fields_exclude	
List[str]	["v_merge_content_title"]	반환 문서에서 제외할 필드명입니다.
필드를 특정한 텍스트 일치 검색(Exact Match) 입니다.
permission_groups의 권한에 매칭 되는 문서만 검색할 수 있습니다.
모든 문서들은 json형식으로 저장되어 있습니다. 검색 시 특수문자 및 제어문자는 제거해 주세요.
파라미터	필수	타입	기본값	설명
index_name	O	str	-	검색할 인덱스명(또는 별칭)입니다. 여러 인덱스일 경우 쉼표로 구분하며 와일드카드(*)를 지원합니다.
field	O	str	-	검색할 필드명입니다.
query_text	O	str	-	검색할 내용입니다.
permission_groups	O	List[str]	-	조회 권한입니다.
num_result_doc	
int	5	반환할 문서 수입니다.
fields_exclude	
List[str]	["v_merge_content_title"]	반환 문서에서 제외할 필드명입니다.
Keyword search based (BM25 algorithm) 
You can only retrieve documents matched with the values in the field 'permission_groups'.
Please remove all special characters in your query.
Name of parameters	Essential	Type	Default	Explanation
index_name	O	str	-	Index name to retrieve
query_text	O	str	-	Question
permission_groups	O	List[str]	-	Permission groups
num_result_doc	
int	5	Number of retrieved results
fields_exclude	
List[str]	["v_merge_content_title"]	Fields which are excluded in the result.
KNN(K-Nearest Neighborhood)
You can only retrieve documents matched with the values in the field 'permission_groups'.
Please remove all special characters in your query.
When using KNN search, if the search query embedding model and the document embedding model are different, the search results may not be good.
The filter consists of a pair of field values and search target values. In this case, the search target value should always be an array, and OR condition comparison is performed between the search target values. You can also specify two or more fields as filtering targets, and filter with AND condition search. 
The following example filters only documents where creator_id is gildong.hong and the tags list includes rag or llm.
{"creator_id": ["gildong.hong"], "tags": ["rag", "llm"]}
Name of parameters	Essential	Type	Default	Explanation
index_name	O	str	-	Index name to retrieve
query_text	O	str	-	Question
permission_groups	O	List[str]	-	Permission groups
num_result_doc	
int	5	Number of retrieved results
fields_exclude	
List[str]	["v_merge_content_title"]	Fields which are excluded in the result.
filter	
json	{}	Document search filter
Hybrid Search (BM25+ KNN)
You can only retrieve documents matched with the values in the field 'permission_groups'.
Please remove all special characters in your query.
When using KNN search, if the search query embedding model and the document embedding model are different, the search results may not be good.
The filter consists of a pair of field values and search target values. In this case, the search target value should always be an array, and OR condition comparison is performed between the search target values. You can also specify two or more fields as filtering targets, and filter with AND condition search. 
The following example filters only documents where creator_id is gildong.hong and the tags list includes rag or llm.
{"creator_id": ["gildong.hong"], "tags": ["rag", "llm"]}
Name of parameters	Essential	Type	Default	Explanation
index_name	O	str	-	Index name to retrieve
query_text	O	str	-	Question
permission_groups	O	List[str]	-	Permission groups
num_result_doc	
int	5	Number of retrieved results
fields_exclude	
List[str]	["v_merge_content_title"]	Fields which are excluded in the result.
filter	
json	{}	Document search filter
You can adjust the ratio between BM25 and KNN.
You can only retrieve documents matched with the values in the field 'permission_groups'.
Please remove all special characters in your query.
When using KNN search, if the search query embedding model and the document embedding model are different, the search results may not be good.
The filter consists of a pair of field values and search target values. In this case, the search target value should always be an array, and OR condition comparison is performed between the search target values. You can also specify two or more fields as filtering targets, and filter with AND condition search. 
The following example filters only documents where creator_id is gildong.hong and the tags list includes rag or llm.
{"creator_id": ["gildong.hong"], "tags": ["rag", "llm"]}
Name of parameters	Essential	Type	Default	Explanation
index_name	O	str	-	Index name to retrieve
query_text	O	str	-	Question
permission_groups	O	List[str]	-	Permission groups
bm25_boost	
float	0.02531451142318286	Ratio of bm25
knn_boost	
float	7.980074401837717	Ratio of KNN
num_result_doc	
int	5	Number of retrieved results
fields_exclude	
List[str]	["v_merge_content_title"]	Fields which are excluded in the result.
filter	
json	{}	Document search filter
Query match by specified field (BM25 algorithm) 
You can only retrieve documents matched with the values in the field 'permission_groups'.
Please remove all special characters in your query.
Name of parameters	Essential	Type	Default	Explanation
index_name	O	str	-	Index name to retrieve
field	O	str	-	Field name to retrieve
query_text	O	str	-	Question
permission_groups	O	List[str]	-	Permission groups
num_result_doc	
int	5	Number of retrieved results
operator	
str	"OR"	Matching method for each word (token) in query_text. OR or AND is used.
fields_exclude	
List[str]	["v_merge_content_title"]	Fields which are excluded in the result.
Query term (exact match) by specified field
You can only retrieve documents matched with the values in the field 'permission_groups'.
Please remove all special characters in your query.
Name of parameters	Essential	Type	Default	Explanation
index_name	O	str	-	Index name to retrieve
field	O	str	-	Field name to retrieve
query_text	O	str	-	Question
permission_groups	O	List[str]	-	Permission groups
num_result_doc	
int	5	Number of retrieved results
fields_exclude	
List[str]	["v_merge_content_title"]	Fields which are excluded in the result.
기존 사용자의 권한 (문서 추가 시, 사용했던 'permission_groups' 값)에 매칭되는 문서를 모두 삭제합니다.
권한 및 문서의 'doc_id'값 (문서 추가 시, 사용했던 'id'값을 의미)을 정확하게 기재해야 합니다.
한번 삭제 시, 복원 불가합니다.
파라미터
타입	기본값	설명
index_name	str	-	대상 인덱스명입니다.
permission_groups	List[str]	-	저장한 문서의 권한입니다.
doc_id	str	-	인덱스에 저장한 문서의 id입니다.
It will delete all documents which are matched with the vaules in 'permission_groups'.
You should use the right 'doc_id' of your documents.
You can not restore after delete once.
Name of parameters
Type	Default	Explanation
index_name	str	-	Index name
permission_groups	List[str]	-	Permission groups
doc_id	str	-	Document ID to be deleted
 
