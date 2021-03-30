from logging import basicConfig
from typing import List, Dict, Union
from pydantic import BaseModel, Field

from opal_common.fetcher.events import FetcherConfig


class DataSourceEntry(BaseModel):
    """
    Data source configuration - where client's should retrive data from and how they should store it
    """
    # How to obtain the data
    url:str = Field(..., description="Url source to query for data")
    config:dict =  Field(None, description="Suggested fetcher configuration (e.g. auth or method) to fetch data with")
    # How to catalog data
    topics:List[str] = Field(None, description="topics the data applies to")
    # How to save the data
    # see https://www.openpolicyagent.org/docs/latest/rest-api/#data-api path is the path nested under <OPA_SERVER>/<version>/data
    dst_path:str = Field("", description="OPA data api path to store the document at")
    save_method:str = Field("PUT", description="Method used to write into OPA - PUT/PATCH")

class DataSourceConfig(BaseModel):
    """
    DataSources used as OPAL-server configuration
    """
    entries: List[DataSourceEntry] = Field(..., description="list of data sources and how to fetch from them")

class DataUpdate(BaseModel):
    """
    DataSources used as OPAL-server configuration
    Data update sent to clients
    """
    entries: List[DataSourceEntry] = Field(..., description="list of related updates the OPAL client should perform")
    reason: str = Field(None, description="Reason for triggering the update")



