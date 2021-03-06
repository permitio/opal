from logging import basicConfig
from typing import List, Dict, Union
from pydantic import BaseModel, Field

from opal.fetcher.events import FetcherConfig


class DataSourceEntry(BaseModel):
    """
    Data source configuration - where 
    """
    url:str = Field(..., description="Url source to query for data")
    # see https://www.openpolicyagent.org/docs/latest/rest-api/#data-api path is the path nested under <OPA_SERVER>/<version>/data
    dst_path:str = Field("", description="OPA data api path to store the document at")
    save_method:str = Field("PUT", description="Method used to write into OPA - PUT/PATCH")
    config:FetcherConfig =  Field(None, description="Suggested fetcher configuration (e.g. auth or method) to fetch data with")

class DataUpdate(BaseModel):
    entries: List[DataSourceEntry] = Field(..., description="list of related updates the OPAL client should perform")
    reason: str = Field(None, description="Reason for triggering the update")


class DataConfig(BaseModel):
    """

    """
    topic_map: Dict[str, DataSourceEntry]