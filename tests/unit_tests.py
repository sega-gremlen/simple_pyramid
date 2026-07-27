from backend import backend_client


def test_get_instances(mocker, mock_fetch_instances):
    # Подменяем метод fetch_instances на мок
    mock_fetch = mocker.patch.object(backend_client, 'fetch_instances')
    mock_fetch.return_value = mock_fetch_instances

    # Вызываем тестируемый метод
    result = backend_client.get_instances("1536145")

    # Проверяем, что fetch был вызван с правильным номером
    mock_fetch.assert_called_once_with("1536145")

    # Проверяем, что результат соответствует ожидаемому
    expected = {
        "instance_id": "13516725",
        "meter_model": "РиМ 489.26 (СПОДЭС)",
        "meter_routes": ["Мегафон, +79270018410, 172.17.100.1, порт 4059"],
    }
    assert result == expected
    