<?php
// ПОДКЛЮЧАЕМ DPD SDK
require __DIR__ . 'dpd_sdk/src/autoload.php';

// ПОЛУЧАЕМ ДАННЫЕ ОТ PYTHON
$input = json_decode(file_get_contents('php://input'), true);

// ЗАГРУЖАЕМ КОНФИГ С ВАШИМИ КЛЮЧАМИ DPD
$options = require __DIR__ . '/config.php';
$config = new \Ipol\DPD\Config\Config($options);

try {
    // 1. СОЗДАЕМ ОТПРАВКУ
    $shipment = new \Ipol\DPD\Shipment($config);

    // 2. УКАЗЫВАЕМ ГОРОДА
    $shipment->setSender('Россия', $input['city_from'], $input['city_from']);
    $shipment->setReceiver('Россия', $input['city_to'], $input['city_to']);

    // 3. ТИП ДОСТАВКИ
    // pickup_type: "door" - курьер заберет, "terminal" - сами привезете
    // delivery_type: "door" - до двери, "terminal" - самовывоз
    $shipment->setSelfPickup($input['pickup_type'] === 'terminal');
    $shipment->setSelfDelivery($input['delivery_type'] === 'terminal');

    // 4. ПАРАМЕТРЫ ПОСЫЛКИ (кг → граммы, см → мм)
    $weight_g = $input['weight_kg'] * 1000;
    $length_mm = $input['length_cm'] * 10;
    $width_mm = $input['width_cm'] * 10;
    $height_mm = $input['height_cm'] * 10;

    $goods = [[
        'NAME' => 'Посылка',
        'QUANTITY' => 1,
        'PRICE' => $input['declared_value'],
        'VAT_RATE' => 'Без НДС',
        'WEIGHT' => $weight_g,
        'DIMENSIONS' => [
            'LENGTH' => $length_mm,
            'WIDTH'  => $width_mm,
            'HEIGHT' => $height_mm
        ]
    ]];

    $shipment->setItems($goods, $input['declared_value']);

    // 5. РАСЧЕТ СТОИМОСТИ (ОФИЦИАЛЬНЫЙ DPD API)
    $calculator = $shipment->calculator();

    // Проверяем все доступные тарифы DPD
    $availableTariffs = [];
    $tariffCodes = ['PCL', 'ECO', 'CSM', 'ECN'];

    foreach ($tariffCodes as $code) {
        try {
            $tariff = $calculator->calculateWithTariff($code);
            if ($tariff && isset($tariff['COST']) && $tariff['COST'] > 0) {
                $availableTariffs[] = [
                    'code' => $code,
                    'name' => $tariff['SERVICE_NAME'] ?? $code,
                    'cost' => $tariff['COST'],
                    'days' => $tariff['DAYS'] ?? 'не указано',
                    'currency' => 'RUB'
                ];
            }
        } catch (Exception $e) {
            // Этот тариф не доступен для данного маршрута
            continue;
        }
    }

    // 6. ФОРМИРУЕМ ОТВЕТ
    if (empty($availableTariffs)) {
        $response = [
            'success' => false,
            'error' => 'DPD не осуществляет доставку по данному маршруту',
            'route' => $input['city_from'] . ' → ' . $input['city_to']
        ];
    } else {
        $response = [
            'success' => true,
            'service' => 'DPD',
            'route' => $input['city_from'] . ' → ' . $input['city_to'],
            'pickup' => $input['pickup_type'] === 'door' ? 'Забор курьером' : 'Самопривоз на терминал',
            'delivery' => $input['delivery_type'] === 'door' ? 'До двери' : 'Самовывоз из терминала',
            'weight' => $input['weight_kg'] . ' кг',
            'dimensions' => $input['length_cm'] . '×' . $input['width_cm'] . '×' . $input['height_cm'] . ' см',
            'value' => $input['declared_value'] . ' ₽',
            'tariffs' => $availableTariffs,
            'note' => 'Расчет через официальный DPD API'
        ];
    }

} catch (Exception $e) {
    $response = [
        'success' => false,
        'error' => 'Ошибка DPD API: ' . $e->getMessage(),
        'route' => $input['city_from'] . ' → ' . $input['city_to'],
        'note' => 'Проверьте ключи DPD в config.php'
    ];
}

// ОТПРАВЛЯЕМ ОТВЕТ В PYTHON
header('Content-Type: application/json; charset=utf-8');
echo json_encode($response, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);