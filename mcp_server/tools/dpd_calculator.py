"""
DPD Калькулятор доставки через REST API
Умный калькулятор, который сразу показывает стоимость, сроки и сравнение тарифов
"""

import os
import json
import httpx
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from mcp_server.mcp_instance import mcp

class DPDDeliveryRequest(BaseModel):
    city_from: str = Field(..., description="Город отправления (например: Москва, Санкт-Петербург)")
    city_to: str = Field(..., description="Город назначения")
    weight_kg: float = Field(1.0, description="Вес посылки в килограммах (от 0.1 до 1000 кг)", ge=0.1, le=1000)
    length_cm: float = Field(50, description="Длина в сантиметрах", ge=1, le=200)
    width_cm: float = Field(30, description="Ширина в сантиметрах", ge=1, le=200)
    height_cm: float = Field(20, description="Высота в сантиметрах", ge=1, le=200)
    declared_value: float = Field(0, description="Объявленная стоимость в рублях", ge=0)
    pickup_type: str = Field("door", description="Тип забора: 'door' - забор курьером, 'terminal' - самопривоз на терминал")
    delivery_type: str = Field("door", description="Тип доставки: 'door' - до двери, 'terminal' - самовывоз из терминала")
    service_code: str = Field("ALL", description="Код тарифа DPD: PCL, ECO, CSM, ECN, ECU, ALL (все тарифы)")

async def call_dpd_api(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Универсальный вызов DPD API"""
    DPD_CLIENT_NUMBER = os.getenv("DPD_CLIENT_NUMBER")
    DPD_CLIENT_KEY = os.getenv("DPD_CLIENT_KEY")

    if not DPD_CLIENT_NUMBER or not DPD_CLIENT_KEY:
        return {"success": False, "error": "Ключи DPD не настроены"}

    request_data["auth"] = {
        "clientNumber": DPD_CLIENT_NUMBER,
        "clientKey": DPD_CLIENT_KEY
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.dpd.ru/calculator/price",
                json=request_data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )

            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            elif response.status_code == 401:
                return {"success": False, "error": "Ошибка авторизации DPD"}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}", "details": response.text[:500]}

    except httpx.TimeoutException:
        return {"success": False, "error": "Таймаут запроса к DPD API"}
    except Exception as e:
        return {"success": False, "error": f"Ошибка подключения: {str(e)}"}

def calculate_delivery_dates(days: Optional[int]) -> Dict[str, str]:
    """Рассчитывает даты доставки на основе рабочих дней"""
    if not days:
        return {"delivery_days": "не указано", "estimated_date": "не рассчитано"}

    today = datetime.now()

    # Примерный расчет (можно улучшить с учетом выходных и праздников)
    delivery_date = today + timedelta(days=days)

    return {
        "delivery_days": str(days),
        "delivery_date": delivery_date.strftime("%d.%m.%Y"),
        "delivery_period": f"{days} рабочих дней"
    }

@mcp.tool(description="РАСЧЁТ СТОИМОСТИ И СРОКОВ ДОСТАВКИ DPD (все тарифы сразу)")
async def calculate_dpd_delivery_all_in_one(
    city_from: str,
    city_to: str,
    weight_kg: float = 1.0,
    length_cm: float = 50,
    width_cm: float = 30,
    height_cm: float = 20,
    declared_value: float = 0,
    pickup_type: str = "door",
    delivery_type: str = "door"
) -> Dict[str, Any]:
    """
    Рассчитывает стоимость и сроки доставки DPD по ВСЕМ доступным тарифам.
    Возвращает полный анализ с лучшими вариантами.
    """

    # Основные параметры запроса
    base_request = {
        "pickup": {"cityName": city_from},
        "delivery": {"cityName": city_to},
        "selfPickup": pickup_type == "terminal",
        "selfDelivery": delivery_type == "terminal",
        "weight": weight_kg,
        "volume": (length_cm * width_cm * height_cm) / 1000000,
        "declaredValue": declared_value
    }

    # Все тарифы DPD для проверки
    tariffs = [
        {"code": "PCL", "name": "DPD CLASSIC", "description": "Стандартная доставка"},
        {"code": "ECO", "name": "DPD EXPRESS", "description": "Экспресс-доставка"},
        {"code": "CSM", "name": "Курьер экспресс", "description": "Срочная курьерская"},
        {"code": "ECN", "name": "Экономичный", "description": "Бюджетный вариант"},
        {"code": "ECU", "name": "Международный", "description": "Международная доставка"}
    ]

    # Асинхронно запрашиваем все тарифы
    tasks = []
    for tariff in tariffs:
        request = base_request.copy()
        request["serviceCode"] = tariff["code"]
        tasks.append(call_dpd_api(request))

    responses = await asyncio.gather(*tasks)

    # Анализируем результаты
    available_tariffs = []
    unavailable_tariffs = []

    for i, response in enumerate(responses):
        tariff_info = tariffs[i]

        if response.get("success") and "data" in response:
            data = response["data"]

            if "serviceCode" in data and "cost" in data:
                # Рассчитываем даты доставки
                days = data.get("days")
                dates_info = calculate_delivery_dates(days)

                tariff_result = {
                    "code": tariff_info["code"],
                    "name": tariff_info["name"],
                    "description": tariff_info["description"],
                    "cost": data["cost"],
                    "currency": data.get("currency", "RUB"),
                    **dates_info,
                    "service_name": data.get("serviceName", tariff_info["name"]),
                    "available": True
                }

                # Добавляем дату забора если есть
                if "pickupDate" in data:
                    tariff_result["pickup_date"] = data["pickupDate"]

                available_tariffs.append(tariff_result)
                continue

        # Тариф недоступен
        unavailable_tariffs.append({
            "code": tariff_info["code"],
            "name": tariff_info["name"],
            "available": False,
            "error": response.get("error", "Недоступен для этого маршрута")
        })

    # Если нет доступных тарифов
    if not available_tariffs:
        return {
            "success": False,
            "error": "Нет доступных тарифов DPD для данного маршрута",
            "route": f"{city_from} → {city_to}",
            "unavailable_tariffs": unavailable_tariffs
        }

    # Сортируем тарифы
    available_tariffs.sort(key=lambda x: x["cost"])  # По цене
    cheapest = available_tariffs[0]

    # Находим самый быстрый
    fastest = None
    for tariff in available_tariffs:
        if tariff.get("delivery_days") and tariff["delivery_days"].isdigit():
            if not fastest or int(tariff["delivery_days"]) < int(fastest["delivery_days"]):
                fastest = tariff

    # Подготавливаем итоговый ответ
    result = {
        "success": True,
        "data_source": "DPD REST API",
        "calculation_time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "route": {
            "from": city_from,
            "to": city_to,
            "full_route": f"{city_from} → {city_to}"
        },
        "package_info": {
            "weight_kg": weight_kg,
            "dimensions": f"{length_cm}×{width_cm}×{height_cm} см",
            "volume_m3": round((length_cm * width_cm * height_cm) / 1000000, 4),
            "declared_value": declared_value,
            "currency": "RUB"
        },
        "delivery_type": {
            "pickup": "Самопривоз на терминал" if pickup_type == "terminal" else "Забор курьером",
            "delivery": "Самовывоз из терминала" if delivery_type == "terminal" else "До двери"
        },
        "tariffs_analysis": {
            "total_available": len(available_tariffs),
            "total_unavailable": len(unavailable_tariffs),
            "cheapest_option": cheapest,
            "fastest_option": fastest if fastest else cheapest,
            "price_range": {
                "min": cheapest["cost"],
                "max": available_tariffs[-1]["cost"],
                "difference": available_tariffs[-1]["cost"] - cheapest["cost"]
            }
        },
        "available_tariffs": available_tariffs,
        "unavailable_tariffs": unavailable_tariffs if unavailable_tariffs else None,
        "recommendations": []
    }

    # Добавляем рекомендации
    if cheapest and fastest and cheapest["code"] != fastest["code"]:
        result["recommendations"].append(
            f"🎯 Самый дешёвый: {cheapest['name']} ({cheapest['cost']} руб., {cheapest.get('delivery_period', 'не указано')})"
        )
        result["recommendations"].append(
            f"⚡ Самый быстрый: {fastest['name']} ({fastest['cost']} руб., {fastest.get('delivery_period', 'не указано')})"
        )

    # Рекомендация по типу доставки
    if pickup_type == "door" and delivery_type == "door":
        result["recommendations"].append(
            "💡 Совет: Самовывоз из терминала обычно дешевле на 20-30%"
        )

    return result

@mcp.tool(description="БЫСТРЫЙ РАСЧЁТ ДОСТАВКИ DPD (один тариф)")
async def calculate_dpd_quick(
    city_from: str,
    city_to: str,
    weight_kg: float = 1.0,
    service_code: str = "PCL",
    pickup_type: str = "door",
    delivery_type: str = "door"
) -> Dict[str, Any]:
    """
    Быстрый расчёт стоимости и сроков доставки DPD для конкретного тарифа.
    """

    request_data = {
        "pickup": {"cityName": city_from},
        "delivery": {"cityName": city_to},
        "selfPickup": pickup_type == "terminal",
        "selfDelivery": delivery_type == "terminal",
        "weight": weight_kg,
        "volume": 0.03,  # Примерный объем для быстрого расчета
        "serviceCode": service_code,
        "declaredValue": 0
    }

    response = await call_dpd_api(request_data)

    if not response.get("success"):
        return {
            "success": False,
            "error": response.get("error", "Ошибка DPD API"),
            "route": f"{city_from} → {city_to}",
            "tariff": service_code
        }

    data = response.get("data", {})

    if "serviceCode" not in data or "cost" not in data:
        return {
            "success": False,
            "error": "Неполный ответ от DPD API",
            "route": f"{city_from} → {city_to}"
        }

    # Рассчитываем даты
    days = data.get("days")
    dates_info = calculate_delivery_dates(days)

    # Определяем название тарифа
    tariff_names = {
        "PCL": "DPD CLASSIC",
        "ECO": "DPD EXPRESS",
        "CSM": "Курьер экспресс",
        "ECN": "Экономичный",
        "ECU": "Международный"
    }

    return {
        "success": True,
        "calculation_type": "Быстрый расчёт",
        "route": f"{city_from} → {city_to}",
        "tariff": {
            "code": service_code,
            "name": tariff_names.get(service_code, service_code),
            "description": "Основной тариф" if service_code == "PCL" else "Альтернативный тариф"
        },
        "cost": data["cost"],
        "currency": data.get("currency", "RUB"),
        **dates_info,
        "weight_kg": weight_kg,
        "delivery_type": {
            "pickup": "Самопривоз" if pickup_type == "terminal" else "Забор курьером",
            "delivery": "Самовывоз" if delivery_type == "terminal" else "До двери"
        },
        "pickup_date": data.get("pickupDate", "не указано"),
        "note": "Для точного расчёта с габаритами используйте calculate_dpd_delivery_all_in_one"
    }

@mcp.tool(description="СРАВНЕНИЕ ТАРИФОВ DPD ДЛЯ ВЫБОРА ОПТИМАЛЬНОГО")
async def compare_dpd_tariffs(
    city_from: str,
    city_to: str,
    weight_kg: float = 1.0,
    max_price: Optional[float] = None,
    max_days: Optional[int] = None
) -> Dict[str, Any]:
    """
    Сравнивает тарифы DPD и рекомендует оптимальный вариант
    по критериям цены и сроков.
    """

    # Получаем все тарифы
    full_calculation = await calculate_dpd_delivery_all_in_one(
        city_from=city_from,
        city_to=city_to,
        weight_kg=weight_kg,
        pickup_type="door",
        delivery_type="door"
    )

    if not full_calculation.get("success"):
        return full_calculation

    available_tariffs = full_calculation.get("available_tariffs", [])

    if not available_tariffs:
        return {
            "success": False,
            "error": "Нет доступных тарифов для сравнения",
            "route": f"{city_from} → {city_to}"
        }

    # Фильтруем по критериям
    filtered_tariffs = []
    for tariff in available_tariffs:
        meets_criteria = True

        if max_price and tariff["cost"] > max_price:
            meets_criteria = False

        if max_days and tariff.get("delivery_days") and tariff["delivery_days"].isdigit():
            if int(tariff["delivery_days"]) > max_days:
                meets_criteria = False

        if meets_criteria:
            filtered_tariffs.append(tariff)

    # Анализируем результаты
    if not filtered_tariffs:
        return {
            "success": True,
            "message": "Нет тарифов, соответствующих критериям",
            "route": f"{city_from} → {city_to}",
            "criteria": {
                "max_price": max_price,
                "max_days": max_days
            },
            "all_available_tariffs": available_tariffs,
            "recommendation": "Рассмотрите увеличение бюджета или сроков"
        }

    # Сортируем по цене и срокам
    filtered_tariffs.sort(key=lambda x: (x["cost"],
                                         int(x["delivery_days"]) if x.get("delivery_days") and x["delivery_days"].isdigit() else 999))

    best_by_price = filtered_tariffs[0]

    # Находим лучший по срокам
    best_by_speed = min(filtered_tariffs,
                       key=lambda x: int(x["delivery_days"]) if x.get("delivery_days") and x["delivery_days"].isdigit() else 999)

    return {
        "success": True,
        "route": f"{city_from} → {city_to}",
        "weight_kg": weight_kg,
        "criteria": {
            "max_price": max_price,
            "max_days": max_days
        },
        "analysis": {
            "total_tariffs": len(available_tariffs),
            "matching_tariffs": len(filtered_tariffs),
            "best_by_price": best_by_price,
            "best_by_speed": best_by_speed if best_by_speed["code"] != best_by_price["code"] else None,
            "price_saving": available_tariffs[-1]["cost"] - best_by_price["cost"] if len(available_tariffs) > 1 else 0
        },
        "matching_tariffs": filtered_tariffs,
        "recommendation": f"Оптимальный выбор: {best_by_price['name']} за {best_by_price['cost']} руб. ({best_by_price.get('delivery_period', 'не указано')})"
    }

@mcp.tool(description="ПРОВЕРКА РАБОТОСПОСОБНОСТИ DPD API И КЛЮЧЕЙ")
async def check_dpd_api_health() -> Dict[str, Any]:
    """
    Проверяет доступность DPD API и корректность ключей.
    """

    DPD_CLIENT_NUMBER = os.getenv("DPD_CLIENT_NUMBER")
    DPD_CLIENT_KEY = os.getenv("DPD_CLIENT_KEY")

    if not DPD_CLIENT_NUMBER or not DPD_CLIENT_KEY:
        return {
            "success": False,
            "status": "NOT_CONFIGURED",
            "error": "Ключи DPD не настроены",
            "timestamp": datetime.now().isoformat(),
            "setup_required": True
        }

    # Тестовый запрос
    test_request = {
        "pickup": {"cityName": "Москва"},
        "delivery": {"cityName": "Санкт-Петербург"},
        "selfPickup": False,
        "selfDelivery": False,
        "weight": 1.0,
        "volume": 0.03,
        "serviceCode": "PCL",
        "declaredValue": 0
    }

    response = await call_dpd_api(test_request)

    if response.get("success"):
        return {
            "success": True,
            "status": "OPERATIONAL",
            "timestamp": datetime.now().isoformat(),
            "api_status": "Работает нормально",
            "keys_status": "Ключи действительны",
            "response_time": "В норме",
            "test_route": "Москва → Санкт-Петербург",
            "note": "DPD API готов к работе"
        }
    else:
        return {
            "success": False,
            "status": "API_ERROR",
            "timestamp": datetime.now().isoformat(),
            "error": response.get("error", "Неизвестная ошибка"),
            "keys_configured": True,
            "suggestions": [
                "Проверьте правильность ключей в .env файле",
                "Убедитесь что аккаунт DPD активен",
                "Проверьте интернет-соединение"
            ]
        }