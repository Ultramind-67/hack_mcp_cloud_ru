import os
import asyncio
import httpx
from dotenv import load_dotenv

# Загружаем ключи
load_dotenv()

CLIENT_NUMBER = os.getenv("DPD_CLIENT_NUMBER")
CLIENT_KEY = os.getenv("DPD_CLIENT_KEY")
URL = "https://ws.dpd.ru/services/calculator2"


async def test_real_dpd():
    print("=" * 60)
    print("💎 ФИНАЛЬНЫЙ ТЕСТ DPD (С КОДАМИ РЕГИОНОВ)")
    print("=" * 60)

    if not CLIENT_NUMBER or not CLIENT_KEY:
        print("❌ ОШИБКА: Нет ключей в .env")
        return

    # XML запрос с ЯВНЫМ указанием regionCode (77 и 78)
    # Это именно то исправление, которое мы внесли в агента
    payload = f"""
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns="http://dpd.ru/ws/calculator/2012-03-20">
       <soapenv:Header/>
       <soapenv:Body>
          <ns:getServiceCost2>
             <request>
                <auth>
                   <clientNumber>{CLIENT_NUMBER}</clientNumber>
                   <clientKey>{CLIENT_KEY}</clientKey>
                </auth>
                <pickup>
                   <cityName>Москва</cityName>
                   <regionCode>77</regionCode>
                   <countryCode>RU</countryCode>
                </pickup>
                <delivery>
                   <cityName>Санкт-Петербург</cityName>
                   <regionCode>78</regionCode>
                   <countryCode>RU</countryCode>
                </delivery>
                <selfPickup>false</selfPickup>
                <selfDelivery>false</selfDelivery>
                <weight>2.5</weight>
                <serviceCode>PCL</serviceCode>
                <declaredValue>0</declaredValue>
             </request>
          </ns:getServiceCost2>
       </soapenv:Body>
    </soapenv:Envelope>
    """

    headers = {"Content-Type": "text/xml; charset=utf-8"}

    print(f"📡 Отправка запроса (Москва [77] -> СПб [78], 2.5 кг)...")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(URL, content=payload.encode('utf-8'), headers=headers)

            print(f"HTTP Статус: {response.status_code}")

            # Смотрим, что внутри
            response_text = response.text

            if "<cost>" in response_text:
                # Вытаскиваем цену грубым парсингом для наглядности
                import re
                cost = re.search(r'<cost>(.*?)</cost>', response_text).group(1)
                days = re.search(r'<days>(.*?)</days>', response_text).group(1)

                print("\n✅ УСПЕХ! РЕАЛЬНЫЙ API ОТВЕТИЛ:")
                print(f"💰 Стоимость: {cost} руб.")
                print(f"🚚 Срок: {days} дн.")
                print("\n(Это НЕ эмуляция, это данные от сервера DPD)")

            elif "Fault" in response_text:
                print("\n⚠️ СЕРВЕР ВЕРНУЛ ОШИБКУ БИЗНЕС-ЛОГИКИ:")
                print(response_text)
            else:
                print("\n❓ НЕПОНЯТНЫЙ ОТВЕТ:")
                print(response_text)

    except Exception as e:
        print(f"\n❌ ОШИБКА СОЕДИНЕНИЯ: {e}")


if __name__ == "__main__":
    asyncio.run(test_real_dpd())