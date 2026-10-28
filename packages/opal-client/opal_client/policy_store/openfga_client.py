import aiohttp
from typing import Dict, Any, List

class OpenFGAPolicyClient:
    def __init__(self, fga_url: str, store_id: str, api_token: str = ''):
        self.fga_url = fga_url.rstrip('/')
        self.store_id = store_id
        self.headers = {'Authorization': f'Bearer {api_token}'} if api_token else {}

    async def write_tuples(self, writes: List[Dict[str, Any]]) -> bool:
        url = f'{self.fga_url}/stores/{self.store_id}/write'
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.post(url, json={'writes': {'tuple_keys': writes}}) as resp:
                return resp.status in [200, 201]
