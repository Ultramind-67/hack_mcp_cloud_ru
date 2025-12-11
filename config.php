<?php
return [
    'KLIENT_NUMBER' => '1009013004',
    'KLIENT_KEY'    => 'a6619b35-38da-4f5c-8278-53f0d345f2d7',
    'KLIENT_CURRENCY' => 'RUB',

    // Настройки по умолчанию
    'WEIGHT'  => 1000, // 1 кг в граммах
    'LENGTH'  => 500,  // 50 см в мм
    'WIDTH'   => 300,  // 30 см в мм
    'HEIGHT'  => 200,  // 20 см в мм

    // Режим работы (false = боевой режим)
    'IS_TEST' => false,

    // База данных для городов DPD
    'DB' => [
        'DSN' => 'sqlite:' . __DIR__ . '/dpd.db',
    ],
];