import asyncio
import logging
import httpx

from typing import Any
from uuid import uuid4

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
)

async def main():
    timeout_config = httpx.Timeout(5 * 60.0)
    base_url = 'https://8ef1e8aa-ed62-4e92-ba2c-cc301adbdbcf-agent.ai-agent.inference.cloud.ru'
    async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
        httpx_client.headers['Authorization'] = 'Bearer <token>'
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=base_url,
        )
        public_card =  await resolver.get_agent_card()
        client = A2AClient(
            httpx_client=httpx_client,
            agent_card=public_card,
        )
        send_message_payload: dict[str, Any] = {
            'message': {
                'role': 'user',
                'parts': [
                    {'kind': 'text', 'text': 'Найди топ поставщиков в МСК мебели'}
                ],
                'messageId': uuid4().hex,
            },
        }
        request = SendMessageRequest(
            id=str(uuid4()), params=MessageSendParams(**send_message_payload)
        )
        response = await client.send_message(request)
        print(response.model_dump(mode='json', exclude_none=True))

if __name__ == "__main__":
    asyncio.run(main())