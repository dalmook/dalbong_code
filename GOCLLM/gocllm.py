# main.py
# pip install pycryptodomex fastapi uvicorn apscheduler requests pandas holidays langchain-openai cx_Oracle
import os
import json
import base64
import time
import math
import uuid
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import requests
import pandas as pd
import cx_Oracle
import uvicorn
import urllib3

from Cryptodome.Cipher import AES
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import store
import ui

from zoneinfo import ZoneInfo
import holidays
from langchain_openai import ChatOpenAI

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================
# 0) ENV (여기만 채우면 동작)
# =========================
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "goc")  # 토큰 비우면 오픈 모드
DASHBOARD_TITLE = os.getenv("DASHBOARD_TITLE", "GOC Issue Dashboard")

KNOX_HOST      = os.getenv("KNOX_HOST", "https://openapi.samsung.net")
KNOX_SYSTEM_ID = os.getenv("KNOX_SYSTEM_ID", "KCC10REST01591")
KNOX_TOKEN     = os.getenv("KNOX_TOKEN", "Bearer 0937decd-9394-38fe-bb5a-348d2d618c67")

ORACLE_HOST    = os.getenv("ORACLE_HOST", "gmgsdd09-vip.sec.samsung.net")
ORACLE_PORT    = int(os.getenv("ORACLE_PORT", "2541"))
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "MEMSCM")
ORACLE_USER    = os.getenv("ORACLE_USER", "memscm")
ORACLE_PW      = os.getenv("ORACLE_PW", "mem01scm")

PROXY_HTTP  = os.getenv("PROXY_HTTP", "")
PROXY_HTTPS = os.getenv("PROXY_HTTPS", "")
VERIFY_SSL  = os.getenv("VERIFY_SSL", "false").lower() == "true"

BIND_HOST = os.getenv("BIND_HOST", "12.52.147.157")
BIND_PORT = int(os.getenv("BIND_PORT", "9500"))

DASHBOARD_URL = os.getenv("DASHBOARD_URL", f"http://{BIND_HOST}:{BIND_PORT}/dashboard")
INFOCENTER_URL = os.getenv(
    "INFOCENTER_URL",
    "https://assistant.samsungds.net/#/main?studio_id=1245feb9-7770-4bdc-99d0-871f40a87536"
)
RIGHTPERSON_JSON_URL = os.getenv("RIGHTPERSON_JSON_URL", "http://12.52.146.94:7000/json/%EB%8B%B4%EB%8B%B9%EC%9E%90.json")
TERM_JSON_PATH = os.getenv("TERM_JSON_PATH", r"F:\Workspace\output.json")
TERM_ADMIN_ROOM_IDS = os.getenv("TERM_ADMIN_ROOM_IDS", "")  # 예

# ✅ 카드 recall(회수) 기능: 기본 OFF 권장(통신 오류 시스템 메시지 유발 가능)
ENABLE_RECALL = os.getenv("ENABLE_RECALL", "false").lower() == "true"

# LLM 대화 기본 동작
# - "off": /ask 또는 "질문:"만 LLM
# - "single": 1:1(SINGLE)에서는 /ask 없이도 모든 일반 텍스트를 LLM
# - "mention": 단체방(GROUP)은 멘션/접두어 있을 때만 LLM
# - "all": 단체방도 일반 텍스트면 LLM (비추)
LLM_CHAT_DEFAULT_MODE = os.getenv("LLM_CHAT_DEFAULT_MODE", "single")
LLM_GROUP_MENTION_TEXT = os.getenv("LLM_GROUP_MENTION_TEXT", "@공급망 챗봇")
LLM_GROUP_PREFIXES = [x.strip() for x in os.getenv("LLM_GROUP_PREFIXES", "봇,챗봇").split(",") if x.strip()]

# =========================
# LLM API Configuration (GaussO4)
# =========================
# 테스트 키 (운영 키로 변경하려면 아래 값만 수정)
LLM_API_KEY = os.getenv("LLM_API_KEY", "credential:TICKET-18ab56e4-99cb-4b44-af32-9ad78449fd80:ST0000101295-STG:Bg9vvJDsTo6w23jrHq6j-Q5Itu6yJRQhOmL8VIY3GE1w:-1:Qmc5dnZKRHNUbzZ3MjNqckhxNmotUTVJdHU2eUpSUWhPbUw4VklZM0dFMXc=:signature=O05mxEkLrDAYwCVLzbiPvgMmCmkLXU3oI9eDGZ6R7otW3C5dE0zssv5_a2knr8QYScmOD0v4IvnF4h2vXe2fQ3zLiM1p6qaK6fSRw0l5FDDYSo0BeXbd_cg==")
LLM_API_URL = os.getenv("LLM_API_URL", "http://apigw-stg.samsungds.net:8000/model-23/1/gausso4-instruct/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "GaussO4-instruct")
LLM_SEND_SYSTEM_NAME = os.getenv("LLM_SEND_SYSTEM_NAME", "test_api_1")
LLM_USER_TYPE = os.getenv("LLM_USER_TYPE", "bot")

# =========================
# RAG API Configuration
# =========================
# RAG API 키 (DS API HUB 키)
RAG_DEP_TICKET = os.getenv("RAG_DEP_TICKET", "credential:TICKET-e09692e2-45e3-46e7-ab4d-e75c06ef2b47:ST0000106045-PROD:n591JsqkTh-51wynrJeZ3Qbk2a5Oo2TfGDc9P6pAkN9Q:-1:bjU5MUpzcWtUaC01MXd5bnJKZVozUWJrMmE1T28yVGZHRGM5UDZwQWtOOVE=:signature=x-Dh7diDnQqQAVyfObfHxQoqHxyH7zGC4irZ9vA0Wgfi9zNURR853sMEXG5QcMnYUHXCclma5dGSMwDWSOgGQBvesPSHRz3zvarPfkcFqovLv6OgNZw_X5A==")
# RAG Portal 키
RAG_API_KEY = os.getenv("RAG_API_KEY", "rag-laeeKyA.KazNAgzjr-d1iK9rUClS2vdqKLZ4oOOcsOhhuR3tJaAYa3h73BE7SdjgLjxQsEtJCN6Oc7B1mJYq1Pu_ruTKmcmeujAVpmDxms44OdjGCeHGBTisaSFHdqyepsbEa3nw")
RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://apigw.samsungds.net:8000/ds_llm_rag/2/dsllmrag/elastic/v2")
# RAG 인덱스 목록 (쉼표로 구분, 나중에 추가 가능)
RAG_INDEXES = os.getenv("RAG_INDEXES", "rp-gocinfo_mail_jsonl")
RAG_PERMISSION_GROUPS = os.getenv("RAG_PERMISSION_GROUPS", "rag-public")
# RAG 후보는 top6까지만 가져오고, 최종 컨텍스트는 top3만 사용
RAG_NUM_RESULT_DOC = int(os.getenv("RAG_NUM_RESULT_DOC", "6"))   # vector search top_k
RAG_CONTEXT_DOCS = int(os.getenv("RAG_CONTEXT_DOCS", "3"))       # rerank 후 최종 반영 top_k
RAG_REWRITE_QUERY_COUNT = max(1, int(os.getenv("RAG_REWRITE_QUERY_COUNT", "2")))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.35"))
RAG_RECENCY_WEIGHT = float(os.getenv("RAG_RECENCY_WEIGHT", "0.28"))   # 최신성 가중치
RAG_RECENCY_HALF_LIFE_DAYS = float(os.getenv("RAG_RECENCY_HALF_LIFE_DAYS", "30"))  # 반감기(일)
RAG_MIN_RECENCY_SCORE = float(os.getenv("RAG_MIN_RECENCY_SCORE", "0.15"))  # 날짜 없을 때 최소점수
LLM_WORKER_COUNT = max(1, int(os.getenv("LLM_WORKER_COUNT", "4")))
LLM_MAX_CONCURRENT = max(1, int(os.getenv("LLM_MAX_CONCURRENT", "4")))
LLM_ALLOWED_USERS_SQL = os.getenv(
    "LLM_ALLOWED_USERS_SQL",
    "select sso_id as senderKnoxId from user"
)
LLM_ALLOWED_USERS_CACHE_TTL_SEC = max(0, int(os.getenv("LLM_ALLOWED_USERS_CACHE_TTL_SEC", "300")))

# ✅ SINGLE(1:1) 단축키 → URL
# ✅ SINGLE(1:1) 단축키(별칭 묶음) → URL
QUICK_LINK_ALIASES = [
    (["GSCM"], "🧭 GSCM", "https://dsgscm.sec.samsung.net/"),
    (["조성묵"], "🧭 조성묵", "mysingleim://ids=sungmook.cho&msg=7ZmI"),
    (["NSCM", "O9"], "📦 NSCM", "https://nextscm.sec.samsung.net/Kibo2#/P-Mix%20Item/DRAM/P-Mix%20Item%20(DRAM)"),
    (["EDM"], "🗂️ EDM", "https://edm2.sec.samsung.net/cc/#/home/efss/recent"),
    (["컨플","컨플루언스","CONF","CONFLUENCE"], "📚 컨플루언스", "https://confluence.samsungds.net/spaces/GOCMEM/pages/182884004/Global%EC%9A%B4%EC%98%81%ED%8C%80+%EB%A9%94%EB%AA%A8%EB%A6%AC"),
    (["SMDM","MDM"], "🗃️ SMDM", "http://smdm.samsungds.net/irj/portal"),
    (["이미지"], "🖼️ 이미지 공유", "https://img/home"),
    (["파워","파워BI","PB","POWERBI","POWER BI","BI"], "📊 Power BI", "http://10.227.100.251/Reports/browse"),
    (["DSASSISTANT","GPT"], "🤖 DS Assistant", "https://assistant.samsungds.net/#/main"),
    (["GITHUB","GIT","깃허브","깃헙"], "🧑‍💻 GitHub", "https://github.samsungds.net/SCM-Group-MEM/SCM_DO"),
    (["밥","식단","점심","아침","저녁","배고파"], "🍱 식단", "https://vkghrap.sec.samsung.net:5999/cis/info/cafeteria/mealMenuInfo.do?_menuId=AWiWxU1cAAEZgNXQ&_menuF=true"),
    (["버스","출퇴근","통근"], "🚌 출퇴근버스", "http://samsung.u-vis.com:8080/portalm/VISMain.do?method=main&pickoffice=0000011"),
    (["패밀리","패밀리넷","패넷","FAMILYNET"], "🏡 패밀리넷", "https://familynet.samsung.com/"),
    (["DSDN"], "💬 DSDN", "https://dsdn.samsungds.net/questions/space/scooldspace:all/"),
    (["이모지"], "😀 이모지 모음", "https://emojidb.org/"),
    (["MSTR"], "📈 MSTR", "https://dsdapmstrsvc.samsungds.net/Mstr/servlet/mstrWeb"),
    (["싱글","녹스","메일"], "🛡️ 싱글/Knox", "https://www.samsung.net/"),
    (["정보센터","정보"], "🗞️ GOC 정보센터", "https://assistant.samsungds.net/#/main?studio_id=1245feb9-7770-4bdc-99d0-871f40a87536"),
    (["근태","근무시간"], "⏱️ 근태", "https://ghrp.kr.sec.samsung.net/shcm/main/openpage?encMenuId=4fd503562d7a42abe598ecae64b53e5cd67df78992b2e2425605d89582270ae8&"),
    (["MPVOC","MP VOC"], "📝 MP VOC", "https://service-hub--sh-servicehub-prod.kspprd.dks.cloud.samsungds.net/sh/svoc/voc/vocReg?sysMapMstId=SSTM01090_MDLE05840_DVSN00120_CMPS00040_2025030415334402679&vocClassCode=RQTP0002"),
    (["NSCMVOC","NSCM VOC"], "📝 NSCM VOC", "https://service-hub--sh-servicehub-prod.kspprd.dks.cloud.samsungds.net/sh/svoc/voc/vocReg?sysMapMstId=SSTM00130_MDLE00740_DVSN00120_CMPS00040_2025030415334301856&vocClassCode=RQTP0002"),
]

def resolve_quick_link(key: str):
    k = (key or "").strip().upper()
    for aliases, title, url in QUICK_LINK_ALIASES:
        if k in [a.upper() for a in aliases]:
            return title, url
    return None, None


# =========================
# Dashboard token guard
# =========================
def _require_dashboard_token(token: str | None):
    if DASHBOARD_TOKEN:
        if (token or "") != DASHBOARD_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid token")

def _limit_utf8mb4_bytes(s: str, max_bytes: int = 128) -> str:
    if not s:
        return s
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return s
    cut = max_bytes
    while cut > 0:
        try:
            return b[:cut].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            cut -= 1
    return ""

# =========================
# 1) AES Cipher (Knox key 기반)
# =========================
class AESCipher:
    def __init__(self, key_hex: str):
        self.BS = 16
        raw = bytes.fromhex(key_hex)
        self.key = raw[0:32]
        self.iv  = raw[32:48]

    def _pad(self, b: bytes) -> bytes:
        pad_len = self.BS - (len(b) % self.BS)
        return b + bytes([pad_len]) * pad_len

    def _unpad(self, b: bytes) -> bytes:
        pad_len = b[-1]
        return b[:-pad_len]

    def encrypt(self, data: str) -> str:
        pt = self._pad(data.encode("utf-8"))
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        ct = cipher.encrypt(pt)
        return base64.b64encode(ct).decode("utf-8")

    def decrypt(self, data_b64: bytes) -> str:
        ct = base64.b64decode(data_b64)
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        pt = self._unpad(cipher.decrypt(ct))
        return pt.decode("utf-8", errors="ignore")


# =========================
# 2) Knox Messenger Client
# =========================
class KnoxMessenger:
    def __init__(self, host: str, systemId: str, token: str):
        self.host = host
        self.systemId = systemId
        self.token = token

        self.userID = ""
        self.x_device_id = ""
        self.key = ""  # getKeys()에서 채움

        self.session = requests.Session()
        # if PROXY_HTTP or PROXY_HTTPS:
        #     self.session.proxies = {}
        #     if PROXY_HTTP:
        #         self.session.proxies["http"] = PROXY_HTTP
        #     if PROXY_HTTPS:
        #         self.session.proxies["https"] = PROXY_HTTPS

    def recall_message(self, chatroom_id: int, msg_id: int, sent_time: int):
        api = "/messenger/message/api/v1.0/message/recallMessageRequest"
        requestid = int(round(time.time() * 1000))
        body = {
            "requestId": requestid,
            "chatroomId": int(chatroom_id),
            "msgId": int(msg_id),
            "sentTime": int(sent_time),
        }
        return self._post_encrypted(api, body)

    def device_regist(self, max_retries: int = 3, retry_delay: int = 5):
        API = "/messenger/contact/api/v1.0/device/o1/reg"
        header = {"Authorization": self.token, "System-ID": self.systemId}
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(self.host + API, headers=header, verify=VERIFY_SSL)
                print(f"[device_regist] Attempt {attempt + 1}/{max_retries} - Status: {response.status_code}")
                
                if response.status_code >= 500:
                    # 서버 에러 (502, 503 등) - 재시도
                    if attempt < max_retries - 1:
                        print(f"[device_regist] Server error {response.status_code}, retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise ValueError(f"API 서버 오류 (Status: {response.status_code}). 서버 상태를 확인하세요.")
                
                if not response.text or response.text.strip() == "":
                    raise ValueError(f"API 응답이 비어있습니다. Status: {response.status_code}")
                
                # HTML 응답 체크 (에러 페이지)
                if response.text.strip().startswith("<!DOCTYPE") or response.text.strip().startswith("<html"):
                    raise ValueError(f"API가 HTML 에러 페이지를 반환했습니다. Status: {response.status_code}\n서버 상태를 확인하세요.")
                
                data = json.loads(response.text)
                self.userID = str(data["userID"])
                self.x_device_id = str(data["deviceServerID"])
                print(f"[device_regist] Success - userID: {self.userID}, deviceServerID: {self.x_device_id}")
                return
                
            except json.JSONDecodeError as e:
                if attempt < max_retries - 1:
                    print(f"[device_regist] JSON 파싱 실패, 재시도 중... ({e})")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise ValueError(f"JSON 파싱 실패: {e}\n응답 내용: {response.text[:500]}")
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[device_regist] 오류 발생, 재시도 중... ({e})")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise

    def getKeys(self):
        API = "/messenger/msgctx/api/v1.0/key/getkeys"
        header = {"Authorization": self.token, "x-device-id": self.x_device_id}
        resp = self.session.get(self.host + API, headers=header, verify=VERIFY_SSL).text
        data = json.loads(resp)
        self.key = data["key"]

    def _post_encrypted(self, api: str, body_dict: dict, extra_headers: Optional[dict] = None) -> dict:
        header = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.token,
            "System-ID": self.systemId,
            "x-device-id": self.x_device_id,
            "x-device-type": "relation",
        }
        if extra_headers:
            header.update(extra_headers)

        requestid = int(round(time.time() * 1000))
        if "requestId" not in body_dict:
            body_dict["requestId"] = requestid

        cipher = AESCipher(self.key)
        enc_body = cipher.encrypt(json.dumps(body_dict, ensure_ascii=False))
        resp = self.session.post(self.host + api, headers=header, data=enc_body, verify=VERIFY_SSL).text

        rt = (resp or "").strip()
        dec = cipher.decrypt(rt.encode("utf-8"))
        return json.loads(dec)

    def send_text(self, chatroom_id: int, text: str):
        api = "/messenger/message/api/v1.0/message/chatRequest"
        requestid = int(round(time.time() * 1000))
        body = {
            "requestId": requestid,
            "chatroomId": int(chatroom_id),
            "chatMessageParams": [
                {"msgId": requestid, "msgType": 0, "chatMsg": text, "msgTtl": 3600}
            ],
        }
        return self._post_encrypted(api, body)

    def send_adaptive_card(self, chatroom_id: int, card: dict):
        api = "/messenger/message/api/v1.0/message/chatRequest"
        requestid = int(round(time.time() * 1000))
        card_str = json.dumps(card, ensure_ascii=False)
        payload = {"adaptiveCards": card_str}

        body = {
            "requestId": requestid,
            "chatroomId": int(chatroom_id),
            "chatMessageParams": [
                {
                    "msgId": requestid,
                    "msgType": 19,
                    "chatMsg": json.dumps(payload, ensure_ascii=False),
                    "msgTtl": 3600,
                }
            ],
        }
        return self._post_encrypted(api, body)

    def send_table_csv_msg7(self, chatroom_id: int, df: pd.DataFrame, title: str = "조회 결과"):
        api = "/messenger/message/api/v1.0/message/chatRequest"
        requestid = int(round(time.time() * 1000))

        chat_msg = ui.df_to_knox_csv_msg7(df, title=title)
        body = {
            "requestId": requestid,
            "chatroomId": int(chatroom_id),
            "chatMessageParams": [
                {
                    "msgId": requestid,
                    "msgType": 7,
                    "chatMsg": chat_msg,
                    "msgTtl": 3600,
                }
            ],
        }
        return self._post_encrypted(api, body)

    def resolve_user_ids_from_loginids(self, login_ids: List[str]) -> List[str]:
        api = "/messenger/contact/api/v1.0/profile/o1/search/loginid"
        header = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.token,
            "System-ID": self.systemId,
            "x-device-id": self.x_device_id,
            "x-device-type": "relation",
        }
        body = {"singleIdList": [{"singleId": x} for x in login_ids if x]}

        resp = self.session.post(self.host + api, headers=header, data=json.dumps(body), verify=VERIFY_SSL).text
        data = json.loads(resp)

        out = []
        for item in data.get("userSearchResult", {}).get("searchResultList", []):
            out.append(str(item["userID"]))
        return out

    def room_create(
        self,
        receivers_userid: List[str],
        *,
        chatType: int = 1,
        chatroom_title: Optional[str] = None,
    ) -> int:
        api = "/messenger/message/api/v1.0/message/createChatroomRequest"
        requestid = int(round(time.time() * 1000))

        body = {
            "requestId": requestid,
            "chatType": int(chatType),
            "receivers": receivers_userid,
        }
        if chatroom_title:
            body["chatroomTitle"] = _limit_utf8mb4_bytes(chatroom_title, 128)

        resp = self._post_encrypted(api, body)
        return int(resp["chatroomId"])


# =========================
# LLM Chatbot (GaussO4)
# =========================
# LangChain ChatOpenAI에서 필요한 더미 키
os.environ["OPENAI_API_KEY"] = "api_key"

def create_llm_chatbot(user_id: str = "bot"):
    """GaussO4 LLM 챗봇 인스턴스 생성"""
    headers = {
        "x-dep-ticket": LLM_API_KEY,
        "Send-System-Name": LLM_SEND_SYSTEM_NAME,
        "User-Id": user_id,
        "User-Type": LLM_USER_TYPE,
        "Prompt-Msg-Id": str(uuid.uuid4()),
        "Completion-Msg-Id": str(uuid.uuid4()),
    }
    
    llm = ChatOpenAI(
        base_url=LLM_API_URL,
        model=LLM_MODEL_NAME,
        max_tokens=2000,
        temperature=0.3,
        default_headers=headers
    )
    
    return llm
def _is_retryable_llm_error(e: Exception) -> bool:
    s = str(e)
    return (
        "Error code: 502" in s
        or "Error code: 503" in s
        or "Error code: 504" in s
        or "upstream server" in s.lower()
        or "invalid response" in s.lower()
    )

def llm_invoke_with_retry(llm, payload, *, attempts: int = 3, base_delay: float = 1.5):
    """
    payload: messages(list) 또는 str 모두 지원
    """
    last_err = None
    for i in range(1, attempts + 1):
        try:
            return llm.invoke(payload)
        except Exception as e:
            last_err = e
            if not _is_retryable_llm_error(e) or i == attempts:
                raise
            delay = base_delay * i  # simple backoff
            print(f"[LLM retry] attempt={i}/{attempts} err={e} sleep={delay}s")
            time.sleep(delay)
    raise last_err  # pragma: no cover

# =========================
# RAG Client
# =========================
class RagClient:
    """RAG API 클라이언트 (간소화 버전)"""
    
    def __init__(self, api_key: str, dep_ticket: str, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.sess = requests.Session()
        self.sess.headers.update({
            "Content-Type": "application/json",
            "x-dep-ticket": dep_ticket,
            "api-key": api_key,
        })
    
    def retrieve_rrf(
        self,
        index_name: str,
        query_text: str,
        num_result_doc: int = 3,
        permission_groups: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """RAG 문서 검색"""
        url = f"{self.base_url}/retrieve-rrf"
        payload = {
            "index_name": index_name,
            "permission_groups": permission_groups or ["rag-public"],
            "query_text": query_text,
            "num_result_doc": num_result_doc,
        }
        r = self.sess.post(url, data=json.dumps(payload, ensure_ascii=False), timeout=self.timeout)
        if 200 <= r.status_code < 300:
            return r.json()
        raise Exception(f"RAG API Error: {r.status_code} - {r.text}")


def create_rag_client() -> RagClient:
    """RAG 클라이언트 인스턴스 생성"""
    return RagClient(
        api_key=RAG_API_KEY,
        dep_ticket=RAG_DEP_TICKET,
        base_url=RAG_BASE_URL,
    )


def search_rag_documents(
    query: str,
    indexes: Optional[List[str]] = None,
    *,
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    RAG 문서 검색 (다중 인덱스 지원)
    
    Args:
        query: 검색 쿼리
        indexes: 검색할 인덱스 목록 (None이면 기본 인덱스 사용)
    
    Returns:
        검색 결과 문서 목록
    """
    if indexes is None:
        indexes = [x.strip() for x in RAG_INDEXES.split(",") if x.strip()]
    
    print(f"[RAG Search] Query: {query}")
    print(f"[RAG Search] Indexes: {indexes}")
    print(f"[RAG Search] Base URL: {RAG_BASE_URL}")
    num_result_doc = top_k or RAG_NUM_RESULT_DOC
    print(f"[RAG Search] Num Result Doc: {num_result_doc}")
    
    rag_client = create_rag_client()
    all_results = []
    
    for index in indexes:
        try:
            print(f"[RAG Search] Searching index: {index}")
            result = rag_client.retrieve_rrf(
                index_name=index,
                query_text=query,
                num_result_doc=num_result_doc,
                permission_groups=[RAG_PERMISSION_GROUPS],
            )
            print(f"[RAG Search] Result from {index}: {result}")
            # 결과에서 문서 추출 (Elasticsearch 응답 구조: hits.hits)
            if "hits" in result and isinstance(result["hits"], dict):
                hits = result["hits"].get("hits", [])
                for hit in hits:
                    if "_source" in hit:
                        doc = hit["_source"]
                        doc["_index"] = index  # 인덱스 정보 추가
                        doc["_score"] = hit.get("_score", 0)  # 점수 추가
                        all_results.append(doc)
                print(f"[RAG Search] Found {len(hits)} documents in {index}")
            else:
                print(f"[RAG Search] No 'hits' field in response from {index}")
        except Exception as e:
            print(f"[RAG Search Error] Index: {index}, Error: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"[RAG Search] Total results: {len(all_results)}")
    return all_results


DATE_FIELD_CANDIDATES = [
    "updated_at", "updated_date", "last_updated", "last_modified",
    "modified_at", "modified_date", "created_at", "created_date",
    "register_date", "reg_date", "date", "datetime", "timestamp",
    "mail_date", "page_updated_at", "page_created_at"
]
def _truncate_text(s: str, max_chars: int = 2200) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + " ..."
def _parse_doc_datetime_value(v: Any) -> Optional[datetime]:
    if v in (None, "", 0):
        return None
    if isinstance(v, (int, float)):
        try:
            ts = float(v)
            if ts > 1_000_000_000_000:  # ms
                ts = ts / 1000.0
            if ts > 0:
                return datetime.fromtimestamp(ts, tz=ZoneInfo("Asia/Seoul"))
        except Exception:
            pass
    s = str(v).strip()
    if not s:
        return None
    s_norm = s.replace("Z", "+00:00").replace("/", "-").replace(".", "-")
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d",
    ):
        try:
            dt = datetime.strptime(s_norm, fmt)
            return dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(s_norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return dt
    except Exception:
        return None
def _extract_doc_datetime(doc: Dict[str, Any]) -> Optional[datetime]:
    if not isinstance(doc, dict):
        return None
    for key in DATE_FIELD_CANDIDATES:
        if key in doc:
            dt = _parse_doc_datetime_value(doc.get(key))
            if dt:
                return dt
    meta = doc.get("metadata")
    if isinstance(meta, dict):
        for key in DATE_FIELD_CANDIDATES:
            if key in meta:
                dt = _parse_doc_datetime_value(meta.get(key))
                if dt:
                    return dt
    for k, v in doc.items():
        lk = str(k).lower()
        if any(token in lk for token in ("date", "time", "updated", "modified", "created", "ts")):
            dt = _parse_doc_datetime_value(v)
            if dt:
                return dt
    return None
def rerank_rag_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not documents:
        return []
    merged: Dict[str, Dict[str, Any]] = {}
    for doc in documents:
        key = str(
            doc.get("doc_id")
            or doc.get("id")
            or doc.get("confluence_mail_page_url")
            or doc.get("url")
            or f"{doc.get('title','')}|{doc.get('_index','')}"
        )
        raw_score = float(doc.get("_score") or 0.0)
        if key not in merged:
            item = dict(doc)
            item["_query_hits"] = 1
            item["_vector_score"] = raw_score
            merged[key] = item
        else:
            merged[key]["_query_hits"] += 1
            if raw_score > float(merged[key].get("_vector_score") or 0.0):
                keep_hits = merged[key]["_query_hits"]
                item = dict(doc)
                item["_query_hits"] = keep_hits
                item["_vector_score"] = raw_score
                merged[key] = item
    docs = list(merged.values())
    max_vec = max([float(d.get("_vector_score") or 0.0) for d in docs] or [1.0])
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    for d in docs:
        vec = float(d.get("_vector_score") or 0.0)
        vec_norm = vec / max_vec if max_vec > 0 else 0.0
        dt = _extract_doc_datetime(d)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
            age_days = max((now - dt.astimezone(ZoneInfo("Asia/Seoul"))).total_seconds() / 86400.0, 0.0)
            recency_score = max(
                RAG_MIN_RECENCY_SCORE,
                math.exp(-math.log(2) * age_days / max(RAG_RECENCY_HALF_LIFE_DAYS, 1.0))
            )
            d["_doc_date"] = dt.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
        else:
            recency_score = RAG_MIN_RECENCY_SCORE
            d["_doc_date"] = "날짜 정보 없음"
        query_hit_bonus = min(max(int(d.get("_query_hits") or 1) - 1, 0), 3) * 0.03
        combined_score = ((1 - RAG_RECENCY_WEIGHT) * vec_norm) + (RAG_RECENCY_WEIGHT * recency_score) + query_hit_bonus
        d["_vector_norm"] = round(vec_norm, 4)
        d["_recency_score"] = round(recency_score, 4)
        d["_combined_score"] = round(combined_score, 4)
    docs.sort(
        key=lambda x: (
            float(x.get("_combined_score", 0.0)),
            float(x.get("_vector_score", 0.0))
        ),
        reverse=True
    )
    return docs
RAG_MIN_COMBINED_SCORE = float(os.getenv("RAG_MIN_COMBINED_SCORE", str(RAG_SIMILARITY_THRESHOLD)))
RAG_MIN_KEYWORD_HITS = int(os.getenv("RAG_MIN_KEYWORD_HITS", "1"))

GENERAL_QUESTION_HINTS = [
    "날씨", "기온", "비와", "눈와", "환율", "주가", "뉴스", "시간", "몇시",
    "today", "weather", "temperature", "stock", "news", "time"
]

def _normalize_text_for_match(s: str) -> str:
    s = (s or "").lower().strip()
    for ch in [" ", "\n", "\t", ",", ".", ":", ";", "/", "\\", "(", ")", "[", "]", "{", "}", "-", "_", "?", "!"]:
        s = s.replace(ch, " ")
    return " ".join(s.split())

def _extract_query_keywords(question: str) -> List[str]:
    q = _normalize_text_for_match(question)
    toks = [t for t in q.split() if len(t) >= 2]
    stopwords = {
        "오늘", "어때", "뭐야", "알려줘", "조회", "관련", "대한", "the", "is", "are",
        "what", "when", "how", "why", "please"
    }
    return [t for t in toks if t not in stopwords]

def should_prefer_general_llm(question: str) -> bool:
    q = (question or "").lower()
    return any(h in q for h in GENERAL_QUESTION_HINTS)

def is_rag_result_relevant(question: str, top_docs: List[Dict[str, Any]]) -> bool:
    if not top_docs:
        return False

    top1 = top_docs[0]
    top_score = float(top1.get("_combined_score") or 0.0)

    title = str(top1.get("title") or "")
    content = str(top1.get("content") or top1.get("merge_title_content") or "")
    haystack = _normalize_text_for_match(title + " " + content)

    keywords = _extract_query_keywords(question)
    keyword_hits = sum(1 for kw in keywords if kw in haystack)

    # FW:/RE: 같은 전달메일성 제목은 약간 보수적으로
    noisy_title = title.strip().upper().startswith(("FW:", "RE:"))

    effective_threshold = max(RAG_SIMILARITY_THRESHOLD, RAG_MIN_COMBINED_SCORE)
    if top_score < effective_threshold:
        return False
    if keyword_hits < RAG_MIN_KEYWORD_HITS and noisy_title:
        return False
    if keywords and keyword_hits == 0:
        return False

    return True
    
def format_rag_context(documents: List[Dict[str, Any]], max_docs: int = 3) -> str:
    if not documents:
        return ""
    context_parts = []
    for i, doc in enumerate(documents[:max_docs], 1):
        title = doc.get("title", doc.get("doc_id", "")) or "제목 없음"
        content = doc.get("content", "") or doc.get("merge_title_content", "") or ""
        index = doc.get("_index", "")
        doc_date = doc.get("_doc_date", "날짜 정보 없음")
        combined = doc.get("_combined_score", doc.get("_score", 0))
        url = doc.get("confluence_mail_page_url", "") or doc.get("url", "")
        context_parts.append(
            f"[문서 {i}]\n"
            f"제목: {title}\n"
            f"문서일시: {doc_date}\n"
            f"종합점수: {combined}\n"
            f"인덱스: {index}\n"
            f"내용: {_truncate_text(content, 2200)}\n"
            f"출처: {url}"
        )
    return "\n\n".join(context_parts)


def retrieve_rag_documents_parallel(queries: List[str], *, top_k: int) -> List[Dict[str, Any]]:
    query_list = [q.strip() for q in queries if q and q.strip()]
    if not query_list:
        return []

    all_documents: List[Dict[str, Any]] = []
    max_workers = min(len(query_list), RAG_REWRITE_QUERY_COUNT, 2)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(search_rag_documents, query, top_k=top_k): query
            for query in query_list
        }
        for future in as_completed(future_map):
            query = future_map[future]
            try:
                docs = future.result()
                print(f"[RAG] 병렬 검색 완료: query={query} docs={len(docs)}")
                all_documents.extend(docs)
            except Exception as e:
                print(f"[RAG] 병렬 검색 실패: query={query} err={e}")

    return all_documents


LLM_BUSY_MESSAGE = "지금 이전 질문을 처리 중이에요. 답변이 끝난 뒤 다시 보내주세요."
llm_task_queue: "queue.Queue[dict]" = queue.Queue()
llm_task_state_lock = threading.Lock()
llm_pending_keys: set[str] = set()
llm_concurrency_limiter = threading.Semaphore(LLM_MAX_CONCURRENT)
llm_workers_started = False


def build_llm_task_keys(chatroom_id: int, sender_knox: str) -> List[str]:
    keys = [f"room:{chatroom_id}"]
    sender_key = (sender_knox or "").strip()
    if sender_key:
        keys.append(f"user:{sender_key}")
    return keys


def enqueue_llm_task(chatroom_id: int, question: str, sender_knox: str) -> bool:
    dedupe_keys = build_llm_task_keys(chatroom_id, sender_knox)
    with llm_task_state_lock:
        if any(key in llm_pending_keys for key in dedupe_keys):
            return False
        llm_pending_keys.update(dedupe_keys)

    try:
        llm_task_queue.put(
            {
                "chatroom_id": chatroom_id,
                "question": question,
                "sender_knox": sender_knox,
                "dedupe_keys": dedupe_keys,
            }
        )
        return True
    except Exception:
        _release_llm_task_keys(dedupe_keys)
        raise


def _release_llm_task_keys(dedupe_keys: List[str]):
    with llm_task_state_lock:
        for key in dedupe_keys:
            llm_pending_keys.discard(key)


def llm_worker_loop(worker_name: str):
    while True:
        task = llm_task_queue.get()
        try:
            process_llm_chat_background(
                task["chatroom_id"],
                task["question"],
                task["sender_knox"],
            )
        except Exception as e:
            print(f"[{worker_name}] unexpected worker error: {e}")
        finally:
            _release_llm_task_keys(task.get("dedupe_keys", []))
            llm_task_queue.task_done()


def start_llm_workers():
    global llm_workers_started
    if llm_workers_started:
        return

    with llm_task_state_lock:
        if llm_workers_started:
            return
        for idx in range(LLM_WORKER_COUNT):
            threading.Thread(
                target=llm_worker_loop,
                args=(f"llm-worker-{idx + 1}",),
                daemon=True,
                name=f"llm-worker-{idx + 1}",
            ).start()
        llm_workers_started = True


def _process_llm_chat_background_impl(chatroom_id: int, question: str, sender_knox: str):
    try:
        user_id = sender_knox if sender_knox else "bot"
        llm = create_llm_chatbot(user_id)

        # ✅ 일반/실시간 성격 질문은 RAG 자체를 스킵해서 호출/지연/오탐 줄이기
        prefer_general = should_prefer_general_llm(question)
        if prefer_general:
            from langchain_core.messages import SystemMessage, HumanMessage

            fallback_system_prompt = """
당신은 GOC 업무 지원 챗봇입니다.
이번 질문은 일반 지식/실시간 성격의 질문으로 판단하여 문서 검색 없이 일반 LLM 답변으로 안내합니다.
과도한 추측은 피하고, 불확실한 내용은 단정하지 마세요.

답변 형식
📌 한줄 요약
한 문장 요약

✅ 일반 답변
- 핵심 내용 2~5개

⚠️ 참고
- 이번 답변은 문서 기반이 아니라 일반 답변임을 짧게 안내
"""
            messages = [
                SystemMessage(content=fallback_system_prompt),
                HumanMessage(content=question)
            ]
            response = llm_invoke_with_retry(llm, messages, attempts=3, base_delay=1.5)
            answer = "📋 문서 기반 답변 미적용\n- 일반 지식/실시간 성격의 질문으로 판단했습니다.\n- 아래는 일반 LLM 답변입니다.\n\n" + response.content.strip()

            try:
                chatBot.send_text(chatroom_id, f"🤖 {answer}")
            except Exception as send_err:
                print("[send final answer failed]", send_err)
            return

        print(f"[RAG] 원문 질문: {question}")
        if len(question.strip()) <= 12:
            search_queries = [question]
        else:
            search_queries = rewrite_search_queries(question, llm)

        if question not in search_queries:
            search_queries = [question] + search_queries
        search_queries = search_queries[:RAG_REWRITE_QUERY_COUNT]
        print(f"[RAG] 재작성 질의들: {search_queries}")

        all_rag_documents = retrieve_rag_documents_parallel(
            search_queries,
            top_k=RAG_NUM_RESULT_DOC,
        )
        print(f"[RAG] 원시 후보 문서 수: {len(all_rag_documents)}")

        reranked_docs = rerank_rag_documents(all_rag_documents)[:RAG_NUM_RESULT_DOC]
        top_docs = reranked_docs[:RAG_CONTEXT_DOCS]

        print(f"[RAG] 재정렬 후 상위 문서 수: {len(top_docs)}")
        for i, d in enumerate(top_docs, 1):
            print(
                f"[RAG][TOP{i}] "
                f"title={d.get('title','')} | "
                f"combined={d.get('_combined_score')} | "
                f"vector={d.get('_vector_score')} | "
                f"date={d.get('_doc_date')}"
            )

        top_score = float(top_docs[0].get("_combined_score") or 0.0) if top_docs else 0.0
        skip_rag = top_score < RAG_SIMILARITY_THRESHOLD
        rag_context = "" if skip_rag else format_rag_context(top_docs, max_docs=RAG_CONTEXT_DOCS)
        print(f"[RAG] 컨텍스트 길이: {len(rag_context)}")
        print(f"[RAG] top_combined_score={top_score}, threshold={RAG_SIMILARITY_THRESHOLD}, skip_rag={skip_rag}")

        prefer_general = should_prefer_general_llm(question)
        rag_relevant = (not skip_rag) and is_rag_result_relevant(question, top_docs)

        print(f"[RAG] prefer_general={prefer_general}, rag_relevant={rag_relevant}")

        # 응답 생성
        if (not prefer_general) and rag_context and rag_relevant:
            from langchain_core.messages import SystemMessage, HumanMessage

            system_prompt = f"""
            당신은 GOC 업무 지원 챗봇입니다.
            반드시 아래 검색 문서를 최우선 근거로 사용하여 답변하세요.
            문서가 여러 개이면 종합점수(combined score)가 높은 문서, 즉 관련도가 높고 최신성이 높은 문서를 우선 반영하세요.

            [검색 문서]
            {rag_context}

            답변 규칙

            1. "📂 문서 기반 답변" 섹션에서는 반드시 문서에 있는 내용만 답변합니다.
            2. 문서에 없는 내용은 문서 기반 답변 섹션에 쓰지 않습니다.
            3. "💡 AI 의견" 섹션에서는 문서를 바탕으로 일반적인 해석, 보충 설명, 실무적 의미를 덧붙일 수 있습니다.
            4. AI 의견 섹션의 내용은 문서에 직접 적혀 있지 않을 수 있으므로, 반드시 참고용이라고 표시합니다.
            5. 문서 간 내용이 다르면 최신 문서 기준으로 정리합니다.
            6. 날짜, 기간, 수량, 조직명, 제품명 등은 최대한 구체적으로 적습니다.
            7. 마크다운 문법(**, ###, --- 등)은 사용하지 않습니다.
            8. 일반 텍스트 형식으로 작성합니다.
            9. 너무 장황하게 쓰지 말고, 실무자가 바로 읽을 수 있게 정리합니다.

            답변 형식

            📌 한줄 요약
            한 문장으로 핵심 요약

            📂 문서 기반 답변
            - 문서에 근거한 핵심 내용 2~5개
            - 문서에 없는 부분은 "문서에 해당 정보가 없습니다."로 표시

            💡 AI 의견
            - 문서를 읽고 이해하는 데 도움이 되는 일반 설명 또는 해석 1~3개
            - 단, 문서에 직접 없는 내용은 추정/해석이므로 단정하지 않음

            📂 근거 문서
            - 문서명 | 문서일시 | 핵심 근거 한줄

            ⚠️ 주의
            - "AI 의견"은 일반 LLM 보충 설명이며 문서 원문 자체는 아닙니다.

            🔗 GOC 이슈지
            https://confluence.samsungds.net/spaces/GOCMEM/pages/3150978308/%EC%9D%B4%EC%8A%88%EC%A7%80
            """

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=question)
            ]
            response = llm_invoke_with_retry(llm, messages, attempts=3, base_delay=1.5)
            answer = response.content.strip()

            if "💡 AI 의견" not in answer:
                answer += "\n\n💡 AI 의견\n- 문서의 핵심 내용을 이해하기 쉽게 보충 설명한 참고용 안내입니다.\n- 세부 판단은 반드시 위 문서 기반 답변과 원문 문서를 우선 확인해주세요."

            if "📂 근거 문서" not in answer:
                source_lines = []
                for doc in top_docs[:3]:
                    title = doc.get("title", "제목 없음")
                    doc_date = doc.get("_doc_date", "날짜 정보 없음")
                    url = doc.get("confluence_mail_page_url", "") or doc.get("url", "")
                    line = f"- {title} | {doc_date}"
                    if url:
                        line += f"\n  {url}"
                    source_lines.append(line)

                if source_lines:
                    answer += "\n\n📂 근거 문서\n" + "\n".join(source_lines)
        else:
            from langchain_core.messages import SystemMessage, HumanMessage

            print("[RAG] 문서 없음 fallback")

            fallback_system_prompt = """
당신은 GOC 업무 지원 챗봇입니다.
이번 질문은 문서 검색 결과가 없으므로 일반 LLM 답변으로 안내합니다.
과도한 추측은 피하고, 불확실한 내용은 단정하지 마세요.

답변 형식
📌 한줄 요약
한 문장 요약

✅ 일반 답변
- 핵심 내용 2~5개

⚠️ 참고
- 이번 답변은 문서 기반이 아니라 일반 답변임을 짧게 안내
"""
            messages = [
                SystemMessage(content=fallback_system_prompt),
                HumanMessage(content=question)
            ]
            response = llm_invoke_with_retry(llm, messages, attempts=3, base_delay=1.5)
            reason = "관련 문서를 찾지 못했습니다."
            
            if prefer_general:
                reason = "일반 지식/실시간 성격의 질문으로 판단했습니다."
            elif skip_rag:
                reason = f"검색 문서 유사도가 기준치({RAG_SIMILARITY_THRESHOLD})보다 낮았습니다."
            elif rag_context and not rag_relevant:
                reason = "검색 문서는 있었지만 질문과의 관련성이 낮았습니다."

            answer = f"📋 문서 기반 답변 미적용\n- {reason}\n- 아래는 일반 LLM 답변입니다.\n\n" + response.content.strip()

        try:
            chatBot.send_text(chatroom_id, f"🤖 {answer}")
        except Exception as send_err:
            print("[send final answer failed]", send_err)

    except Exception as e:
        print(f"[LLM Background Error] {e}")
        import traceback
        traceback.print_exc()
        try:
            chatBot.send_text(chatroom_id, f"LLM 응답 오류: {e}")
        except Exception as send_err:
            print("[send error message failed]", send_err)


def process_llm_chat_background(chatroom_id: int, question: str, sender_knox: str):
    with llm_concurrency_limiter:
        _process_llm_chat_background_impl(chatroom_id, question, sender_knox)

def rewrite_search_queries(question: str, llm: ChatOpenAI) -> List[str]:
    """
    LLM을 사용하여 질문을 검색 최적화 질의로 재작성
    
    Args:
        question: 사용자 질문
        llm: LLM 인스턴스
    
    Returns:
        재작성된 검색 질의 목록 (최대 2개)
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    
    system_prompt = """사용자의 질문을 문서 검색에 최적화된 질의로 재작성하세요.
다음 조건을 반영하여 정확히 2개의 검색 질의를 생성하세요:
1. 핵심 키워드 추출
2. 동의어/업무용 표현 보강
3. 너무 긴 문장은 짧은 검색 질의로 축약

각 질의는 줄바꿈으로 구분하세요. 다른 설명은 하지 마세요.

예시:
질문: "Apple의 공급망 투입 현황 알려줘"
답변:
Apple 공급망 투입 현황
Apple supply chain investment

질문: "삼성전자의 최신 반도체 생산량은?"
답변:
삼성전자 반도체 생산량
Samsung semiconductor production volume"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=question)
    ]
    
    try:
        response = llm_invoke_with_retry(llm, messages, attempts=2, base_delay=1.0)
        queries_text = response.content.strip()
        queries = []
        for q in queries_text.split('\n'):
            normalized = q.strip()
            if normalized and normalized not in queries:
                queries.append(normalized)

        if not queries:
            return [question]
        if len(queries) == 1:
            return [queries[0], question] if queries[0] != question else [question]
        return queries[:RAG_REWRITE_QUERY_COUNT]
    except Exception as e:
        print(f"[Query Rewrite Error] {e}")
        return [question]


# =========================
# 3) Action Parsing
# =========================
def parse_action_payload(info: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    chat_msg = info.get("chatMsg", "") or ""
    raw = chat_msg
    if " -->" in chat_msg:
        parts = chat_msg.split(" -->", 1)
        raw = parts[1].strip()

    # 1) 버튼/카드 payload(JSON) 우선
    if raw.strip().startswith("{"):
        try:
            payload = json.loads(raw)
            action = payload.get("action", "HOME")
            return action, payload
        except:
            pass

    txt = raw.strip()
    txt_u = txt.upper()

    chat_type = (info.get("chatType") or "").upper()

    # 2) ✅ SINGLE(1:1) 단축키 → URL
    if chat_type == "SINGLE":
        key = txt_u[1:] if txt_u.startswith("/") else txt_u
        title, url = resolve_quick_link(key)
        if url:
            return "OPEN_URL", {"title": title, "url": url}

    # ✅ 일부 버튼/시스템 트리거가 TEXT로 들어오는 케이스(예: chatMsg="INTRO")
    if txt_u in ("INTRO", "HOME"):
        return "INTRO", {}  # 아래 핸들러에서 ("HOME","INTRO")로 홈카드 처리됨

    if txt in ("홈", "/home"):
        return "HOME", {}
    if txt in ("바로가기", "/바로가기", "링크", "/links", "links"):
        return "QUICK_LINKS", {}
    if txt.startswith("/warn"):
        return "WARN_RUN", {}
    if txt.startswith("/issue"):
        return "ISSUE_FORM", {}

    # 4) 명시적 LLM 트리거 (/ask, 질문:) → SINGLE에서만 허용
    if chat_type == "SINGLE" and (txt.startswith("/ask ") or txt.startswith("질문:")):
        question = txt[5:] if txt.startswith("/ask ") else txt[3:]
        return "LLM_CHAT", {"question": question.strip()}

    # 5) /ask 없이도 대화처럼 LLM → SINGLE에서만
    # - 단, /로 시작하는 명령어는(미정의 명령 포함) LLM로 안 보냄
    if chat_type == "SINGLE":
        if not txt.startswith("/"):
            return "LLM_CHAT", {"question": txt}

    # 6) GROUP에서는 LLM로 절대 라우팅하지 않음
    return "NOOP", {}



# =========================
# 4) UI-state helpers (recall 카드)
# =========================
def extract_msgid_senttime(resp: dict):
    if not isinstance(resp, dict):
        return None, None

    pme = resp.get("processedMessageEntries")
    if isinstance(pme, list) and pme:
        x = pme[0] or {}
        mid = x.get("msgId")
        st  = x.get("sentTime")
        if mid is not None and st is not None:
            try:
                return int(mid), int(st)
            except:
                return mid, st

    for k in ("chatReplyResultList", "chatReplyResults", "resultList", "data", "results"):
        v = resp.get(k)
        if isinstance(v, list) and v:
            x = v[0] or {}
            mid = x.get("msgId") or x.get("messageId") or x.get("msgID")
            st  = x.get("sentTime") or x.get("sendTime") or x.get("sent_time")
            if mid is not None and st is not None:
                try:
                    return int(mid), int(st)
                except:
                    return mid, st

    mid = resp.get("msgId") or resp.get("messageId") or resp.get("msgID")
    st  = resp.get("sentTime") or resp.get("sendTime") or resp.get("sent_time")
    if mid is not None and st is not None:
        try:
            return int(mid), int(st)
        except:
            return mid, st

    return None, None


def send_issue_list_card(chatroom_id: int, issues: List[dict], *, scope_room_id: str, recall_prev: bool = True):
    if chatBot is None:
        print("[send_issue_list_card] KNOX 연결 안됨")
        return
    
    if recall_prev and ENABLE_RECALL:
        st = store.ui_get_issue_list_state(str(chatroom_id))
        if st and st.get("issue_list_msg_id") and st.get("issue_list_sent_time"):
            try:
                chatBot.recall_message(chatroom_id, int(st["issue_list_msg_id"]), int(st["issue_list_sent_time"]))
            except Exception as e:
                print("[recall issue_list card failed]", e)

        # ✅ D-day 계산 + 정렬(목표일 임박순) 보장
    for it in issues:
        it["d_day"] = store._dday(it.get("target_date", ""))

    issues.sort(key=lambda x: (999999 if x.get("d_day") is None else x.get("d_day"), int(x.get("issue_id", 0))))

    resp = chatBot.send_adaptive_card(chatroom_id, ui.build_issue_list_card(issues, room_id=str(scope_room_id)))

    mid, sent = extract_msgid_senttime(resp)
    if mid and sent:
        store.ui_set_issue_list_state(str(chatroom_id), mid, sent)


def send_issue_history_card(chatroom_id: int, *, scope_room_id: str, page: int, recall_prev: bool = False):
    if chatBot is None:
        print("[send_issue_history_card] KNOX 연결 안됨")
        return
    
    if recall_prev and ENABLE_RECALL:
        st = store.ui_get_history_state(str(chatroom_id))
        if st and st.get("history_msg_id") and st.get("history_sent_time"):
            try:
                chatBot.recall_message(chatroom_id, int(st["history_msg_id"]), int(st["history_sent_time"]))
            except Exception as e:
                print("[recall history card failed]", e)

    total = store.issue_count_all(str(scope_room_id))
    max_page = max(0, (total - 1) // store.HISTORY_PAGE_SIZE) if total > 0 else 0
    page = max(0, min(int(page), max_page))

    issues = store.issue_list_all_paged(str(scope_room_id), page, store.HISTORY_PAGE_SIZE)
    resp = chatBot.send_adaptive_card(
        chatroom_id,
        ui.build_issue_history_card(issues, page=page, total=total, page_size=store.HISTORY_PAGE_SIZE, room_id=str(scope_room_id))
    )

    mid, sent = extract_msgid_senttime(resp)
    if mid is not None and sent is not None:
        store.ui_set_history_state(str(chatroom_id), mid, sent)


# =========================
# 5) Oracle Query runner
# =========================
def run_oracle_query(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    dsn = cx_Oracle.makedsn(ORACLE_HOST, ORACLE_PORT, service_name=ORACLE_SERVICE)
    con = cx_Oracle.connect(user=ORACLE_USER, password=ORACLE_PW, dsn=dsn, encoding="UTF-8")
    try:
        return pd.read_sql(sql, con, params=params)
    finally:
        try:
            con.close()
        except Exception:
            pass

# (추가 코드 - 추가용)  ※ run_oracle_query 아래쪽에 추가
def _likeify2(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return ""
    return v if ("%" in v or "_" in v) else f"%{v}%"

def _ym6(s: str) -> str:
    s = "".join([c for c in (s or "") if c.isdigit()])
    return s[:6] if len(s) >= 6 else s

def run_oneview_ship(params: dict) -> pd.DataFrame:
    smon = _ym6(params.get("smon",""))
    emon = _ym6(params.get("emon",""))
    conv = (params.get("conv") or "deliverynum01").strip()
    qraw = (params.get("q") or "").strip()

    q = _likeify2(qraw.upper().replace(" ", ""))

    filter_map = {
        "deliverynum01": "a.DLVRY_NUM LIKE :q",
        "haitem01":      "a.SALE_ITEM_CODE LIKE :q",
        "haversion01":   "(b.DRAMVER LIKE :q OR b.NANDVER LIKE :q)",
        "hagc01":        "(a.GC_CODE LIKE :q OR a.GC_NAME LIKE :q)",
    }
    filter_clause = filter_map.get(conv, filter_map["deliverynum01"])

    sql = ui.SQL_ONEVIEW_SHIP_BASE.format(filter_clause=filter_clause)
    return run_oracle_query(sql, params={"smon": smon, "emon": emon, "q": q})

def run_pkgcode(params: dict) -> pd.DataFrame:
    raw = (params.get("q") or "").strip()
    q = raw.upper().replace(" ", "")

    like_q = _likeify2(q)

    # ✅ 입력에 따라 where_clause 분기 (원본 로직 그대로)
    if q.isalpha() and len(q) == 2:
        where_clause = "B.VERSION LIKE :q"
    elif len(q) == 3:
        where_clause = "A.PACK_CODE LIKE :q"
    else:
        where_clause = "(A.PACK_CODE||B.VERSION||B.PCBCODE) LIKE :q"

    sql = ui.SQL_PKGCODE_BASE.format(where_clause=where_clause)
    return run_oracle_query(sql, params={"q": like_q})


# (추가 코드 - 교체/추가용)
from difflib import SequenceMatcher

def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a or "", b or "").ratio()

def _clean_xa0(x):
    if isinstance(x, str):
        return x.replace("\xa0", " ")
    if isinstance(x, list):
        return [_clean_xa0(v) for v in x]
    if isinstance(x, dict):
        return {k: _clean_xa0(v) for k, v in x.items()}
    return x

def run_term_search(params: dict):
    q = (params.get("q") or "").strip()
    if not q:
        return ui.build_term_not_found_card(q)

    try:
        with open(TERM_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = _clean_xa0(data)
    except Exception:
        # 파일 못 읽으면 안내 카드
        return ui.build_term_not_found_card(q)

    qn = q.lower().replace(" ", "")

    exact = []
    starts = []
    scored = []

    for item in (data or []):
        term = (item.get("title") or "").strip()
        if not term:
            continue
        tn = term.lower().replace(" ", "")
        sim = _sim(tn, qn)

        rec = {
            "subject": (item.get("subject") or "").strip(),
            "term": term,
            "content": (item.get("content") or "").strip(),
            "link": (item.get("link") or "").strip(),
        }

        if term == q:
            exact.append((sim, rec))
        elif term.startswith(q):
            starts.append((sim, rec))
        elif qn in tn:
            scored.append((sim, rec))
        else:
            # 완전 불일치일 때도 유사도 높은 것 일부 포함(너무 낮으면 제외)
            if sim >= 0.70:
                scored.append((sim, rec))

    # 정렬/컷
    exact = sorted(exact, key=lambda x: x[0], reverse=True)[:5]
    starts = sorted(starts, key=lambda x: x[0], reverse=True)[:5]
    scored = sorted(scored, key=lambda x: x[0], reverse=True)[:9]

    merged = [r for _, r in (exact + starts + scored)]

    # 중복 제거(term+link 기준)
    seen = set()
    uniq = []
    for r in merged:
        key = (r.get("term",""), r.get("link",""))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    if not uniq:
        return ui.build_term_not_found_card(q)

    return ui.build_term_search_results_card(q, uniq)

def run_ps_query(params: dict) -> pd.DataFrame:
    """
    PS 파트조회 공용 러너
    - gubun: pscomp01 / psmodule01 / psmultichip01
    - conv : psfab02 / pseds03 / psasy04 / pstst05 / psmod06(모듈전용)
    - q    : 검색값
    """
    gubun = (params.get("gubun") or params.get("psgubun01") or "").strip()   # 구분
    conv  = (params.get("conv")  or params.get("psconv01")  or "").strip()   # 조회기준
    qraw  = (params.get("q")     or params.get("result")    or "").strip()   # 검색어

    if not qraw:
        return pd.DataFrame([{"Result": "코드 입력값이 비었습니다."}])
    if len(qraw.strip()) < 3:
        return pd.DataFrame([{"Result": "코드는 3자 이상 입력하세요."}])

    # ✅ MOD_CODE는 MODULE에서만 허용
    if conv == "psmod06" and gubun != "psmodule01":
        return pd.DataFrame([{"Result": "MOD_CODE(psmod06)는 MODULE에서만 조회 가능합니다."}])

    # ✅ 입력 normalize + like 처리 (바인딩)
    q = _likeify2(qraw.upper().replace(" ", ""))

    # ✅ gubun별 SQL 선택 + where 컬럼 맵(예전 코드와 동일한 컬럼들)
    if gubun == "pscomp01":
        sql = getattr(ui, "SQL_PS_COMP_BASE", "") or ""
        where_map = {
            "psfab02": "A.FOUT_CODE LIKE :q",
            "pseds03": "A.EFU_CODE  LIKE :q",
            "psasy04": "A.ABD_CODE  LIKE :q",
            "pstst05": "A.TFN_CODE  LIKE :q",
        }
        default_conv = "pseds03"

    elif gubun == "psmodule01":
        sql = getattr(ui, "SQL_PS_MODULE_BASE", "") or ""
        where_map = {
            "psfab02": "B.FAB_CODE  LIKE :q",
            "pseds03": "B.EFU_CODE  LIKE :q",
            "psasy04": "B.ABD_CODE  LIKE :q",
            "pstst05": "A.COMPCODE  LIKE :q",
            "psmod06": "A.PRODCODE  LIKE :q",
        }
        default_conv = "pseds03"

    elif gubun == "psmultichip01":
        sql = getattr(ui, "SQL_PS_MCP_BASE", "") or ""
        where_map = {
            "psfab02": "B.FOUT_CODE LIKE :q",
            "pseds03": "A.CHIPCODE  LIKE :q",
            "psasy04": "A.PRODCODE  LIKE :q",
            "pstst05": "C.TFN_CODE  LIKE :q",
        }
        default_conv = "pseds03"

    else:
        return pd.DataFrame([{"Result": f"알 수 없는 gubun: {gubun}"}])

    if not (sql or "").strip():
        return pd.DataFrame([{"Result": f"PS SQL이 비어있음: ui SQL 정의 확인 (gubun={gubun})"}])

    # ✅ conv가 이상하면 기본값으로
    where_clause = where_map.get(conv) or where_map.get(default_conv) or ""

    # ✅ SQL에 {where_clause}가 있으면 채워줌(없으면 그대로 실행)
    if "{where_clause}" in sql:
        sql = sql.format(where_clause=where_clause)

    return run_oracle_query(sql, params={"q": q})


# 기존 RUNNERS가 있으면 아래만 추가, 없으면 RUNNERS 선언 후 추가


RUNNERS: Dict[str, Any] = {}
RUNNERS["TERM_SEARCH"] = run_term_search
RUNNERS["ONEVIEW_SHIP"] = run_oneview_ship
RUNNERS["PKGCODE"] = run_pkgcode
RUNNERS["PS_QUERY"] = run_ps_query

llm_allowed_users_cache_lock = threading.Lock()
llm_allowed_users_cache: set[str] = set()
llm_allowed_users_cache_expire_at = 0.0


def _normalize_sender_knox_id(sender_knox: str) -> str:
    return (sender_knox or "").strip().lower()


def _fetch_llm_allowed_users() -> set[str]:
    if not (LLM_ALLOWED_USERS_SQL or "").strip():
        return set()

    df = run_oracle_query(LLM_ALLOWED_USERS_SQL)
    if df is None or df.empty:
        return set()

    target_col = None
    for col in df.columns:
        if str(col).lower() in ("senderknoxid", "sso_id", "ssoid"):
            target_col = col
            break
    if target_col is None:
        target_col = df.columns[0]

    allowed_users = set()
    for value in df[target_col].dropna().tolist():
        normalized = _normalize_sender_knox_id(str(value))
        if normalized:
            allowed_users.add(normalized)
    return allowed_users


def is_llm_allowed_user(sender_knox: str) -> bool:
    global llm_allowed_users_cache_expire_at

    normalized = _normalize_sender_knox_id(sender_knox)
    if not normalized:
        return False

    now_ts = time.time()
    with llm_allowed_users_cache_lock:
        if now_ts < llm_allowed_users_cache_expire_at:
            return normalized in llm_allowed_users_cache

    try:
        allowed_users = _fetch_llm_allowed_users()
    except Exception as e:
        print(f"[LLM allowlist load failed] {e}")
        return False

    expire_at = now_ts + LLM_ALLOWED_USERS_CACHE_TTL_SEC
    with llm_allowed_users_cache_lock:
        llm_allowed_users_cache.clear()
        llm_allowed_users_cache.update(allowed_users)
        llm_allowed_users_cache_expire_at = expire_at
        return normalized in llm_allowed_users_cache

def run_rightperson(params: dict) -> pd.DataFrame:
    q = (params.get("q") or "").strip()
    if not q:
        return pd.DataFrame([{"Result": "검색어를 입력하세요."}])

    # 1) Oracle
    df_oracle = run_oracle_query(ui.SQL_RIGHTPERSON_ORACLE)

    # 2) JSON (옵션)
    df_json = pd.DataFrame()
    if RIGHTPERSON_JSON_URL:
        try:
            r = requests.get(RIGHTPERSON_JSON_URL, timeout=5)
            r.raise_for_status()
            df_json = pd.DataFrame(r.json())
        except Exception:
            df_json = pd.DataFrame()

    cols = ["부서","담당제품","팀장","PL","TL","실무담당자","비고"]
    for df in (df_oracle, df_json):
        for c in cols:
            if c not in df.columns:
                df[c] = ""

    combined = pd.concat([df_json[cols], df_oracle[cols]], ignore_index=True)

    mask = (
        combined["부서"].astype(str).str.contains(q, case=False, na=False) |
        combined["담당제품"].astype(str).str.contains(q, case=False, na=False) |
        combined["팀장"].astype(str).str.contains(q, case=False, na=False) |
        combined["PL"].astype(str).str.contains(q, case=False, na=False) |
        combined["TL"].astype(str).str.contains(q, case=False, na=False) |
        combined["실무담당자"].astype(str).str.contains(q, case=False, na=False) |
        combined["비고"].astype(str).str.contains(q, case=False, na=False)
    )

    out = combined[mask].drop_duplicates().reset_index(drop=True)
    return out if not out.empty else pd.DataFrame([{"Result": f"검색 결과 없음: {q}"}])

RUNNERS["RIGHTPERSON"] = run_rightperson
# =========================
# 6) Sender userID / DM room
# =========================
def get_sender_user_id(info: dict) -> str | None:
    for k in ("senderUserId", "senderUserID", "senderUid", "senderId"):
        v = info.get(k)
        if v:
            return str(v)

    sk = (info.get("senderKnoxId") or "").strip()
    if sk.isdigit():
        return sk

    if sk:
        try:
            if chatBot is not None:
                ids = chatBot.resolve_user_ids_from_loginids([sk])
                if ids:
                    return str(ids[0])
        except:
            pass
    return None


def get_or_create_dm_room_for_user(
    sender_user_id: str,
    sender_name: str = "",
    *,
    chat_type: str | None = None,
    current_room_id: int | None = None,
) -> int | None:
    # ✅ 안전장치: SINGLE 컨텍스트면 "새로 만들지 말고" 현재 방을 DM으로 바인딩
    ct = (chat_type or "").upper()
    if ct == "SINGLE" and current_room_id:
        try:
            store.dm_set_room(sender_user_id, str(current_room_id))
        except Exception as e:
            print("[DM bind failed]", e)
        return int(current_room_id)

    cached = store.dm_get_room(sender_user_id)
    if cached:
        return int(cached)

    try:
        if chatBot is None:
            return None
        title = f"공급망봇 · {sender_name}".strip() if sender_name else None
        rid = chatBot.room_create([str(sender_user_id)], chatType=1, chatroom_title=title)
        store.dm_set_room(sender_user_id, str(rid))
        return int(rid)
    except Exception as e:
        print("[DM create failed]", e)
        return None


# ✅ (추가) 단체방에서 눌러도 UI/결과는 DM으로 보내는 라우터
def route_ui_room(chatroom_id: int, info: dict, sender_name: str = "") -> int:
    sender_user_id = get_sender_user_id(info)
    try:
        if (info.get("chatType") or "").upper() == "SINGLE" and sender_user_id:
            store.dm_set_room(str(sender_user_id), str(chatroom_id))  # ← 네 store 함수명에 맞춰 조정
    except Exception as e:
        print("[dm_room bind failed]", e)
    # ✅ SINGLE(1:1)은 원래 방에서 바로 응답
    chat_type = (info.get("chatType") or "").upper()
    if chat_type == "SINGLE":
        return chatroom_id

    # ✅ 단체방에서만 DM 라우팅
    if chat_type != "GROUP":
        return chatroom_id
    if not sender_user_id:
        return chatroom_id

    dm_room = get_or_create_dm_room_for_user(
    sender_user_id,
    sender_name,
    chat_type=chat_type,
    current_room_id=chatroom_id,
)

    return int(dm_room) if dm_room else chatroom_id



# =========================
# 7) Scheduler Jobs
# =========================
def job_issue_deadline_reminder_daily():
    today = datetime.now().date()
    issues = store.issue_list_open_all()
    if not issues:
        return

    to_send: Dict[str, List[Tuple[int, dict, str]]] = {}

    for it in issues:
        td = store._parse_ymd(it.get("target_date", ""))
        if not td:
            continue
        d = (td - today).days
        if d not in store.REMIND_DAYS:
            continue

        memo = f"D-{d}|{today.isoformat()}"
        if store.issue_event_exists(int(it["issue_id"]), "REMIND", memo):
            continue

        room = str(it.get("chatroom_id", "")).strip()
        if not room:
            continue

        to_send.setdefault(room, []).append((d, it, memo))

    if not to_send:
        return

    for room, items in to_send.items():
        try:
            if chatBot is None:
                print("[job_issue_deadline_reminder_daily] KNOX 연결 안됨, 건너뜀")
                continue
            items.sort(key=lambda x: (x[0], int(x[1]["issue_id"])))
            today_str = today.strftime("%Y-%m-%d")
            card = ui.build_issue_deadline_reminder_card([(d, it) for d, it, _memo in items], today_str)
            chatBot.send_adaptive_card(int(room), card)

            for _d, it, _memo in items:
                store.issue_event_add(int(it["issue_id"]), "REMIND", actor="BOT", memo=_memo)

        except Exception as e:
            print("job_issue_deadline_reminder_daily error:", e)


def job_warning_daily():
    rooms = store.get_watch_rooms()
    if not rooms:
        return

    try:
        if chatBot is None:
            print("[job_warning_daily] KNOX 연결 안됨, 건너뜀")
            return
        df = run_oracle_query(ui.SQL_WARN)
        msg = "⚠️ [워닝 테스트]\n" + ui.format_df_brief(df, 5)
        for rid in rooms:
            chatBot.send_text(int(rid), msg)
    except Exception as e:
        print("job_warning_daily error:", e)


# (바로 위 코드)
KR_HOLIDAYS = holidays.KR()  # 대한민국 공휴일(대체공휴일 포함)

def job_issue_summary_daily():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    today = now.date()

    # ✅ 토/일 + 공휴일 스킵
    if today.weekday() >= 5 or today in KR_HOLIDAYS:  # 5=토, 6=일
        return

    rooms = store.get_watch_rooms()
    if not rooms:
        return

    try:
        if chatBot is None:
            print("[job_issue_summary_daily] KNOX 연결 안됨, 건너뜀")
            return
        today_str = now.strftime("%Y-%m-%d")

        for rid in rooms:
            issues = store.issue_list_open(str(rid))
            if not issues:
                continue

            for it in issues:
                it["d_day"] = store._dday(it.get("target_date", ""))

            issues.sort(key=lambda x: (
                999999 if x.get("d_day") is None else x.get("d_day"),
                int(x.get("issue_id", 0))
            ))

            card = ui.build_issue_summary_card(issues, today_str=today_str, max_items=15)
            chatBot.send_adaptive_card(int(rid), card)

    except Exception as e:
        print("job_issue_summary_daily error:", e)

def run_warning_once_to_chatroom(chatroom_id: int):
    if chatBot is None:
        print("[run_warning_once_to_chatroom] KNOX 연결 안됨")
        return
    df = run_oracle_query(ui.SQL_WARN)
    if df is None or df.empty:
        chatBot.send_text(chatroom_id, "워닝 조건: 현재 0건 ✅")
    else:
        chatBot.send_text(chatroom_id, "⚠️ 워닝 결과\n" + ui.format_df_brief(df, 10))


# =========================
# 8) FastAPI App
# =========================
app = FastAPI()
scheduler = BackgroundScheduler(timezone="Asia/Seoul")
chatBot: KnoxMessenger  # startup에서 초기화

@app.get("/api/dashboard/rooms")
def api_dashboard_rooms(token: str | None = Query(default=None)):
    _require_dashboard_token(token)
    return {"rooms": store.list_watch_rooms()}

@app.get("/api/dashboard/summary")
def api_dashboard_summary(
    token: str | None = Query(default=None),
### PART 3/3
    room_id: str | None = Query(default=None),
):
    _require_dashboard_token(token)

    today = store._today()
    open_issues = store.issue_list_open_all()
    closed_recent = store.issue_list_closed_recent(days=60)

    if room_id:
        open_issues = [x for x in open_issues if str(x.get("chatroom_id","")) == str(room_id)]

    last_map = store.get_last_activity_map([int(x["issue_id"]) for x in open_issues])

    overdue = 0
    due_7 = 0
    due_3 = 0
    no_target = 0
    long_open_14 = 0
    owner_cnt = defaultdict(int)

    urgent_list = []
    old_list = []
    stale_list = []

    for it in open_issues:
        d = store._dday(it.get("target_date",""))
        age = store._age_days(it.get("created_at",""))
        owner = (it.get("owner") or "").strip() or "(미지정)"
        owner_cnt[owner] += 1

        if d is None:
            no_target += 1
        else:
            if d < 0:
                overdue += 1
            if 0 <= d <= 7:
                due_7 += 1
            if 0 <= d <= 3:
                due_3 += 1

        if age >= 14:
            long_open_14 += 1

        urgent_list.append({
            "issue_id": it["issue_id"],
            "title": it.get("title",""),
            "owner": it.get("owner",""),
            "target_date": it.get("target_date",""),
            "d_day": d,
            "url": it.get("url",""),
        })

        old_list.append({
            "issue_id": it["issue_id"],
            "title": it.get("title",""),
            "owner": it.get("owner",""),
            "created_at": it.get("created_at",""),
            "age_days": age,
            "url": it.get("url",""),
        })

        last_evt = last_map.get(int(it["issue_id"]), "") or it.get("created_at","")
        last_dt = store._parse_dt(last_evt)
        if last_dt:
            stale_days = (datetime.now().date() - last_dt.date()).days
            stale_list.append({
                "issue_id": it["issue_id"],
                "title": it.get("title",""),
                "owner": it.get("owner",""),
                "last_event_at": last_evt,
                "stale_days": stale_days,
                "url": it.get("url",""),
            })

    urgent_list.sort(key=lambda x: (999999 if x["d_day"] is None else x["d_day"], int(x["issue_id"])))
    old_list.sort(key=lambda x: (-x["age_days"], int(x["issue_id"])))
    stale_list.sort(key=lambda x: (-x["stale_days"], int(x["issue_id"])))

    owner_top = sorted(owner_cnt.items(), key=lambda kv: kv[1], reverse=True)[:8]
    owner_top = [{"owner": k, "open_cnt": v} for k, v in owner_top]

    series = store.build_week_series(
        created_rows=store.issue_list_all_any("OPEN") + closed_recent,
        closed_rows=closed_recent,
        weeks=8
    )

    cycle_days = []
    for it in closed_recent:
        c = store._parse_dt(it.get("created_at",""))
        e = store._parse_dt(it.get("closed_at",""))
        if c and e:
            cycle_days.append((e.date() - c.date()).days)
    avg_cycle = round(sum(cycle_days)/len(cycle_days), 1) if cycle_days else None

    kpi = {
        "open_total": len(open_issues),
        "overdue": overdue,
        "due_7": due_7,
        "due_3": due_3,
        "no_target": no_target,
        "long_open_14": long_open_14,
        "red_alert": overdue + due_3,
        "avg_cycle_days_60d": avg_cycle,
        "today": today.isoformat(),
    }

    return {
        "kpi": kpi,
        "owner_top": owner_top,
        "series": series,
        "urgent_top10": urgent_list[:10],
        "old_top10": old_list[:10],
        "stale_top10": stale_list[:10],
    }

@app.get("/api/dashboard/issues")
def api_dashboard_issues(
    token: str | None = Query(default=None),
    room_id: str | None = Query(default=None),
    status: str = Query(default="OPEN"),
    owner: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=0),
    size: int = Query(default=50),
):
    _require_dashboard_token(token)

    rows = store.issue_list_all_any(None if status == "ALL" else status)

    if room_id:
        rows = [r for r in rows if str(r.get("chatroom_id","")) == str(room_id)]
    if owner:
        rows = [r for r in rows if owner.lower() in (r.get("owner","") or "").lower()]
    if q:
        qq = q.lower()
        rows = [r for r in rows if qq in (r.get("title","") or "").lower() or qq in (r.get("content","") or "").lower()]

    for r in rows:
        r["d_day"] = store._dday(r.get("target_date",""))
        r["age_days"] = store._age_days(r.get("created_at",""))

    if status == "OPEN":
        rows.sort(key=lambda x: (999999 if x["d_day"] is None else x["d_day"], -x["age_days"], int(x["issue_id"])))
    else:
        rows.sort(key=lambda x: int(x["issue_id"]), reverse=True)

    total = len(rows)
    start = page * size
    end = start + size
    return {"total": total, "page": page, "size": size, "items": rows[start:end]}

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(token: str | None = Query(default=None)):
    if not DASHBOARD_TOKEN:
        t = token or ""
        return HTMLResponse(ui.DASHBOARD_HTML.replace("__DASHBOARD_TITLE__", DASHBOARD_TITLE).replace("__TOKEN__", t))

    if (token or "") == DASHBOARD_TOKEN:
        return HTMLResponse(ui.DASHBOARD_HTML.replace("__DASHBOARD_TITLE__", DASHBOARD_TITLE).replace("__TOKEN__", token or ""))

    return HTMLResponse(ui.DASHBOARD_LOGIN_HTML.replace("__DASHBOARD_TITLE__", DASHBOARD_TITLE))

# KNOX 재연결 함수
def job_knox_reconnect():
    global chatBot
    # 이미 연결되어 있으면 재시도 안함
    if chatBot is not None:
        return
    
    print("[knox_reconnect] KNOX 연결 시도...")
    try:
        new_chatBot = KnoxMessenger(host=KNOX_HOST, systemId=KNOX_SYSTEM_ID, token=KNOX_TOKEN)
        new_chatBot.device_regist()
        new_chatBot.getKeys()
        chatBot = new_chatBot
        print("[knox_reconnect] KNOX 연결 성공! chatBot 객체 재설정 완료")
    except Exception as e:
        print(f"[knox_reconnect] KNOX 연결 실패: {e}")


@app.on_event("startup")
def on_startup():
    global chatBot
    store.init_db()
    start_llm_workers()
    print(f"[startup] LLM workers started: workers={LLM_WORKER_COUNT}, max_concurrent={LLM_MAX_CONCURRENT}")

    # KNOX 연결 - 실패해도 앱은 계속 실행
    try:
        chatBot = KnoxMessenger(host=KNOX_HOST, systemId=KNOX_SYSTEM_ID, token=KNOX_TOKEN)
        chatBot.device_regist()
        chatBot.getKeys()
        print("[startup] KNOX 연결 성공")
    except Exception as e:
        print(f"[startup] KNOX 연결 실패: {e}")
        print("[startup] KNOX 기능은 사용할 수 없지만 앱은 계속 실행됩니다.")
        print("[startup] 5분마다 자동 재연결을 시도합니다.")
        chatBot = None  # KNOX 기능 비활성화

    # 스케줄러 시작
    try:
        scheduler.add_job(job_issue_summary_daily, CronTrigger(hour=8, minute=00), id="issue_summary", replace_existing=True)
        # scheduler.add_job(job_issue_deadline_reminder_daily, CronTrigger(hour=8, minute=35), id="issue_deadline_remind", replace_existing=True)
        # KNOX 재연결 작업: 5분마다 실행
        scheduler.add_job(job_knox_reconnect, CronTrigger(minute="*/5"), id="knox_reconnect", replace_existing=True)
        scheduler.start()
        print("[startup] 스케줄러 시작 성공 (KNOX 재연결: 5분마다)")
    except Exception as e:
        print(f"[startup] 스케줄러 시작 실패: {e}")

    print("[BOOT] main =", __file__)
    print("[BOOT] store=", store.__file__)
    print("[BOOT] ui   =", ui.__file__)

    print("[startup] ready")


@app.post("/message")
async def post_message(request: Request):
    # KNOX 연결 안 된 경우
    if chatBot is None:
        return {"ok": False, "error": "KNOX 연결 안됨"}
    
    body = await request.body()
    info = json.loads(AESCipher(chatBot.key).decrypt(body))
    print(info)

    chatroom_id = int(info["chatroomId"])
    sender_name = info.get("senderName", "") or ""
    sender_knox = info.get("senderKnoxId", "") or ""
    sender = sender_name if sender_name else sender_knox

    action, payload = parse_action_payload(info)

    if action == "NOOP":
        return {"ok": True}

    try:
        if action == "OPEN_URL":
            url = (payload.get("url") or "").strip()
            title = (payload.get("title") or "🔗 바로가기").strip()
            if url:
                chatBot.send_adaptive_card(chatroom_id, ui.build_quicklink_card(title, url))
            else:
                chatBot.send_text(chatroom_id, "링크가 비어있어요.")
            return {"ok": True}

        elif action in ("HOME", "INTRO"):
            chatBot.send_adaptive_card(chatroom_id, ui.build_home_card(dashboard_url=DASHBOARD_URL, infocenter_url=INFOCENTER_URL))


        elif action == "WARN_RUN":
            run_warning_once_to_chatroom(chatroom_id)

        elif action == "QUICK_LINKS":
            ui_room = route_ui_room(chatroom_id, info, sender_name)  # ✅ GROUP이면 DM, SINGLE이면 그대로
            chatBot.send_adaptive_card(ui_room, ui.build_quick_links_card(QUICK_LINK_ALIASES))
            return {"ok": True}
        
        # ---------- LLM Chatbot ----------
        elif action == "LLM_CHAT":
            if not is_llm_allowed_user(sender_knox):
                chatBot.send_adaptive_card(chatroom_id, ui.build_home_card(dashboard_url=DASHBOARD_URL, infocenter_url=INFOCENTER_URL))
                return {"ok": True}

            question = (payload.get("question") or "").strip()
            if not question:
                chatBot.send_text(chatroom_id, "질문 내용이 비어있습니다. /ask 질문내용 또는 질문:내용 형식으로 입력해주세요.")
                return {"ok": True}

            try:
                if not enqueue_llm_task(chatroom_id, question, sender_knox):
                    chatBot.send_text(chatroom_id, LLM_BUSY_MESSAGE)
                    return {"ok": True}

                # 먼저 안내 메시지 전송
                try:
                    chatBot.send_text(chatroom_id, "🤔 검색 중입니다. 잠시만 기다려주세요...")
                except Exception as send_err:
                    print("[send thinking message failed]", send_err)

                return {"ok": True}
            except Exception as e:
                print(f"[LLM Dispatch Error] {e}")
                import traceback
                traceback.print_exc()
                try:
                    chatBot.send_text(chatroom_id, f"LLM 요청 처리 오류: {e}")
                except Exception:
                    pass
                return {"ok": True}                

        
        # ---------- Generic Query Router ----------
        elif action in ui.ACTION_TO_QUERY:
            ui_room = route_ui_room(chatroom_id, info, sender_name)  # ✅ DM 우선

            mode, qkey = ui.ACTION_TO_QUERY[action]
            spec = ui.QUERY_REGISTRY[qkey]

            if mode == "FORM":
                chatBot.send_adaptive_card(ui_room, ui.build_query_form_card(spec))
                return {"ok": True}


            for f in spec.get("fields", []):
                if f.get("required") and not (payload.get(f["id"]) or "").strip():
                    chatBot.send_text(ui_room, f"필수값 누락: {f.get('label', f['id'])}")
                    chatBot.send_adaptive_card(ui_room, ui.build_query_form_card(spec))
                    return {"ok": True}

            params_builder = spec.get("params_builder")
            params = params_builder(payload) if callable(params_builder) else None

            # (수정 코드 - 교체용)
            result = RUNNERS[spec["runner"]](params or {}) if spec.get("runner") else run_oracle_query(spec["sql"], params=params)

            # ✅ runner가 AdaptiveCard(dict)로 주면 그대로 전송하고 종료
            if isinstance(result, dict) and result.get("type") == "AdaptiveCard":
                chatBot.send_adaptive_card(ui_room, result)
                return {"ok": True}

            df = result  # DataFrame으로 간주

            if spec.get("output") == "MSG7_TABLE":
                chatBot.send_table_csv_msg7(ui_room, df, title=spec.get("title","조회 결과"))
            else:
                chatBot.send_adaptive_card(ui_room, ui.df_to_table_card(df, title=spec.get("title","조회 결과")))

            return {"ok": True}
        
        # (추가 코드 - 교체/추가용)  ※ Generic Query Router 위쪽 아무 곳에 추가
        elif action == "TERM_UNKNOWN_SUBMIT":
            ui_room = route_ui_room(chatroom_id, info, sender_name)  # ✅ 누락 보완

            findword = (payload.get("findword") or "").strip()
            memo = (payload.get("memo") or "").strip()
            rooms = [x.strip() for x in TERM_ADMIN_ROOM_IDS.split(",") if x.strip().isdigit()]

            msg = f"📩 [용어 반영 요청]\n- 단어: {findword}\n- 요청자: {sender}\n" + (f"- 메모: {memo}\n" if memo else "")
            if rooms:
                for rid in rooms:
                    chatBot.send_text(int(rid), msg)
                chatBot.send_text(ui_room, "접수 완료 ✅ (담당자에게 전달했습니다)")
            else:
                chatBot.send_text(ui_room, "접수 완료 ✅ (TERM_ADMIN_ROOM_IDS 미설정이라 전달은 생략됨)")
            return {"ok": True}      

        # ---------- Issue ----------
        elif action == "ISSUE_FORM":
            scope = store.scope_room_id(chatroom_id, payload)          # ✅ 데이터 스코프(원래 단체방)
            ui_room = route_ui_room(chatroom_id, info, sender_name)    # ✅ UI는 DM (SINGLE이면 그대로)

            chatBot.send_adaptive_card(
                ui_room,
                ui.build_issue_form_card(sender_hint=sender, room_id=str(scope))
            )
            return {"ok": True}


        elif action == "ISSUE_CREATE":
            scope = store.scope_room_id(chatroom_id, payload)          # ✅ 데이터 스코프(원래 단체방)
            ui_room = route_ui_room(chatroom_id, info, sender_name)    # ✅ UI는 DM (SINGLE이면 그대로)
            origin_room = int(scope)

            title = (payload.get("title") or "").strip()
            content = (payload.get("content") or "").strip()
            url = (payload.get("url") or "").strip()
            occur_date = (payload.get("occur_date") or "").strip()
            target_date = (payload.get("target_date") or "").strip()
            owner = (payload.get("owner") or "").strip()

            if not title:
                chatBot.send_text(ui_room, "제목이 비어있습니다. 다시 발의해 주세요.")
                chatBot.send_adaptive_card(
                    ui_room,
                    ui.build_issue_form_card(sender_hint=sender, room_id=str(origin_room))
                )
                return {"ok": True}

            issue_id = store.issue_create(
                origin_room,
                title,
                content,
                url,
                occur_date,
                target_date,
                owner,
                sender
            )

            # ✅ 완료 메시지/UI 갱신은 ui_room(DM)으로
            chatBot.send_text(ui_room, f"✅ 이슈 등록 완료: #{issue_id} {title}")

            try:
                issues = store.issue_list_open(str(origin_room))
                send_issue_list_card(ui_room, issues, scope_room_id=str(origin_room), recall_prev=True)
            except Exception as e:
                print("[dm issue list refresh failed]", e)

            return {"ok": True}



        elif action == "ISSUE_LIST":
            scope = store.scope_room_id(chatroom_id, payload)          # ✅ 데이터 스코프(원래 단체방)
            ui_room = route_ui_room(chatroom_id, info, sender_name)    # ✅ UI는 DM

            issues = store.issue_list_open(str(scope))
            send_issue_list_card(ui_room, issues, scope_room_id=str(scope), recall_prev=True)
            return {"ok": True}


        elif action == "ISSUE_CLEAR":
            scope = store.scope_room_id(chatroom_id, payload)
            ui_room = route_ui_room(chatroom_id, info, sender_name)

            issue_id = payload.get("issue_id")
            if issue_id is None:
                chatBot.send_text(ui_room, "issue_id가 없습니다.")
                return {"ok": True}

            store.issue_clear(str(scope), int(issue_id), sender)
            chatBot.send_text(ui_room, f"✅ Clear 처리 완료: #{issue_id}")

            issues = store.issue_list_open(str(scope))
            send_issue_list_card(ui_room, issues, scope_room_id=str(scope), recall_prev=True)
            return {"ok": True}


        elif action == "ISSUE_EDIT_FORM":
            scope = store.scope_room_id(chatroom_id, payload)
            ui_room = route_ui_room(chatroom_id, info, sender_name)

            issue_id = payload.get("issue_id")
            if issue_id is None:
                chatBot.send_text(ui_room, "issue_id가 없습니다.")
                return {"ok": True}

            issue = store.issue_get(str(scope), int(issue_id))
            if not issue:
                chatBot.send_text(ui_room, f"해당 이슈를 찾을 수 없습니다: #{issue_id}")
                return {"ok": True}

            chatBot.send_adaptive_card(ui_room, ui.build_issue_edit_form_card(issue, room_id=str(scope)))
            return {"ok": True}


        elif action == "ISSUE_UPDATE":
            scope = store.scope_room_id(chatroom_id, payload)
            ui_room = route_ui_room(chatroom_id, info, sender_name)

            issue_id = payload.get("issue_id")
            if issue_id is None:
                chatBot.send_text(ui_room, "issue_id가 없습니다.")
                return {"ok": True}

            title = (payload.get("title") or "").strip()
            content = (payload.get("content") or "").strip()
            url = (payload.get("url") or "").strip()
            occur_date = (payload.get("occur_date") or "").strip()
            target_date = (payload.get("target_date") or "").strip()
            owner = (payload.get("owner") or "").strip()

            if not title:
                chatBot.send_text(ui_room, "제목이 비어있습니다.")
                issue = store.issue_get(str(scope), int(issue_id))
                if issue:
                    chatBot.send_adaptive_card(ui_room, ui.build_issue_edit_form_card(issue, room_id=str(scope)))
                return {"ok": True}

            store.issue_update(str(scope), int(issue_id), title, content, url, occur_date, target_date, owner, actor=sender)
            chatBot.send_text(ui_room, f"✅ 수정 완료: #{issue_id} {title}")

            issues = store.issue_list_open(str(scope))
            send_issue_list_card(ui_room, issues, scope_room_id=str(scope), recall_prev=True)
            return {"ok": True}


        elif action == "ISSUE_HISTORY":
            scope = store.scope_room_id(chatroom_id, payload)
            ui_room = route_ui_room(chatroom_id, info, sender_name)

            is_nav = ("page" in payload)
            page = int(payload.get("page", 0) or 0)
            send_issue_history_card(ui_room, scope_room_id=str(scope), page=page, recall_prev=is_nav)
            return {"ok": True}


        elif action == "ISSUE_DELETE":
            scope = store.scope_room_id(chatroom_id, payload)
            ui_room = route_ui_room(chatroom_id, info, sender_name)

            issue_id = payload.get("issue_id")
            if issue_id is None:
                chatBot.send_text(ui_room, "issue_id가 없습니다.")
                return {"ok": True}

            page = int(payload.get("page", 0) or 0)
            ok, msg = store.issue_delete(str(scope), int(issue_id), sender)
            if not ok:
                chatBot.send_text(ui_room, msg)

            send_issue_history_card(ui_room, scope_room_id=str(scope), page=page, recall_prev=True)
            return {"ok": True}


        # ---------- Watchroom ----------
        elif action == "WATCHROOM_FORM":
            ui_room = route_ui_room(chatroom_id, info, sender_name)
            chatBot.send_adaptive_card(ui_room, ui.build_watchroom_form_card())


        elif action == "WATCHROOM_CREATE":
            ui_room = route_ui_room(chatroom_id, info, sender_name)

            room_title = (payload.get("room_title") or "").strip()
            members_raw = (payload.get("members") or "").strip()
            note = (payload.get("note") or "").strip()


            if not members_raw:
                chatBot.send_text(chatroom_id, "참여자 SSO가 비어있습니다. 예: sungmook.cho,cc.choi")
                chatBot.send_adaptive_card(chatroom_id, ui.build_watchroom_form_card())
                return {"ok": True}

            members = [x.strip() for x in members_raw.replace("\n", ",").split(",") if x.strip()]
            user_ids = chatBot.resolve_user_ids_from_loginids(members)
            if not user_ids:
                chatBot.send_text(chatroom_id, "참여자 변환(userID)이 실패했습니다. SSO가 맞는지 확인해 주세요.")
                return {"ok": True}

            title_to_use = room_title or note or "공지방"
            new_room_id = chatBot.room_create(user_ids, chatType=1, chatroom_title=title_to_use)
            store.add_watch_room(str(new_room_id), created_by=sender, note=note, chatroom_title=title_to_use)

            chatBot.send_text(
                chatroom_id,
                f"✅ 공지방 생성 & 푸시대상 등록 완료\n- chatroomId: {new_room_id}\n- title: {title_to_use}\n- note: {note}"
            )
            chatBot.send_text(
                new_room_id,
                "📣 이 방은 봇이 생성한 공지/워닝/이슈 방입니다.\n- 워닝(스케줄) / 이슈요약(스케줄) 푸시 대상입니다.\n- @공급망 챗봇 으로 기능을 실행하세요."
            )
            chatBot.send_adaptive_card(new_room_id, ui.build_home_card(dashboard_url=DASHBOARD_URL, infocenter_url=INFOCENTER_URL))
            return {"ok": True}

        else:
            chatBot.send_text(chatroom_id, f"알 수 없는 action: {action}")
            chatBot.send_adaptive_card(chatroom_id, ui.build_home_card(dashboard_url=DASHBOARD_URL, infocenter_url=INFOCENTER_URL))

    except Exception as e:
        chatBot.send_text(chatroom_id, f"오류 발생: {e}")

    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host=BIND_HOST, port=BIND_PORT, workers=1)
