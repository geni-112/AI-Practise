from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env',override=False)
RUNTIME=ROOT/'.runtime'; RUNTIME.mkdir(exist_ok=True)

@dataclass(frozen=True)
class Settings:
    demo:bool=os.getenv('DEMO_MODE','true').lower()=='true'
    data_backend:str=os.getenv('DATA_BACKEND','sqlite')
    model_provider:str=os.getenv('MODEL_PROVIDER','huawei_maas')
    model_name:str=os.getenv('MODEL_NAME','glm-5.3')
    model_base_url:str=os.getenv('MODEL_BASE_URL','')
    model_api_key:str=os.getenv('MODEL_API_KEY',os.getenv('HUAWEICLOUD_MODEL_API_KEY',''))
    model_timeout:int=int(os.getenv('MODEL_TIMEOUT','90'))
    metadata_url:str=os.getenv('OPENMETADATA_URL','http://127.0.0.1:8585')
    metadata_token:str=os.getenv('OPENMETADATA_TOKEN','')
    temporal_address:str=os.getenv('TEMPORAL_ADDRESS','127.0.0.1:7233')
    temporal_enabled:bool=os.getenv('TEMPORAL_ENABLED','true').lower()=='true'
    opa_url:str=os.getenv('OPA_URL','')
    oidc_issuer:str=os.getenv('OIDC_ISSUER','')
    oidc_audience:str=os.getenv('OIDC_AUDIENCE','nexo-api')
    oidc_jwks_url:str=os.getenv('OIDC_JWKS_URL','')
    region:str=os.getenv('HUAWEICLOUD_REGION','la-north-2')

settings=Settings()
