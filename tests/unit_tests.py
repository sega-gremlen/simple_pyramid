import pytest

from backend import backend_client, PyramidApiClient
from tests.conftest import SCENARIOS, SCENARIO_DESCRIPTIONS


scenario_ids = [f"{num}: {desc}" for num, desc in SCENARIO_DESCRIPTIONS.items()]


@pytest.mark.parametrize("scenario", SCENARIOS, indirect=True, ids=scenario_ids)
def test_get_instances(mocker, scenario, mock_fetch_instances, expected, input_data):
    """Тест функции get_instances"""
    
    # Подменяем метод fetch_instances на мок
    mock_fetch = mocker.patch.object(backend_client, 'fetch_instances')
    mock_fetch.return_value = mock_fetch_instances

    # Вызываем тестируемый метод
    result = backend_client.get_instances(input_data["meter_num"])

    # Проверяем, что fetch был вызван с правильным номером
    mock_fetch.assert_called_once_with(input_data["meter_num"])

    # Проверяем, что результат соответствует ожидаемому
    expected = {
        "instance_id": expected["instance_id"],
        "meter_model": expected["meter_model"],
        "meter_routes": expected["meter_routes"]
    }
    assert result == expected
    
    
@pytest.mark.parametrize("scenario", SCENARIOS, indirect=True, ids=scenario_ids)
def test_get_instance_info(mocker, scenario, mock_fetch_instance_info, expected, input_data):
    """Тест функции get_instance_info"""
    
    # Подменяем метод get_instance_info на мок
    mock_fetch = mocker.patch.object(backend_client, 'fetch_instance_info')
    mock_fetch.return_value = mock_fetch_instance_info
    
    # Вызываем тестируемый метод
    result = backend_client.get_instance_info(input_data["meter_id"])
    
    # Проверяем, что fetch был вызван с правильным номером
    mock_fetch.assert_called_once_with(input_data["meter_id"])
    
    # Проверяем, что результат соответствует ожидаемому
    expected = {
        "account_id": expected["account_id"],
        "address": expected["address"],
        "full_path": expected["full_path"]
    }
    assert result == expected
    
    
@pytest.mark.parametrize("scenario", SCENARIOS, indirect=True, ids=scenario_ids)
def test_get_meterdata_read(mocker, scenario, mock_fetch_meterdata_read, expected, input_data):
    """Тест функции get_meterdata_read"""
    
    # Подменяем метод get_instance_info на мок
    mock_fetch = mocker.patch.object(backend_client, 'fetch_meterdata_read')
    mock_fetch.return_value = mock_fetch_meterdata_read
    
    # Вызываем тестируемый метод
    result = backend_client.get_meterdata_read(input_data["meter_id"])
    
    # Проверяем, что fetch был вызван с правильным номером
    mock_fetch.assert_called_once_with(input_data["meter_id"])
    
    # Проверяем, что результат соответствует ожидаемому
    
    expected_fine_meter_values = {
        "A+": {
            "TO": {"value": expected["fine_meter_values"]["A+"]["TO"]["value"],
                   "datetime": PyramidApiClient.datetime_extracter(expected["fine_meter_values"]["A+"]["TO"]["datetime"])},
            "T1": {"value": expected["fine_meter_values"]["A+"]["T1"]["value"],
                   "datetime": PyramidApiClient.datetime_extracter(expected["fine_meter_values"]["A+"]["T1"]["datetime"])},
            "T2": {"value": expected["fine_meter_values"]["A+"]["T2"]["value"],
                   "datetime": PyramidApiClient.datetime_extracter(expected["fine_meter_values"]["A+"]["T2"]["datetime"])},
            },
        "A-": {
            "TO": {"value": expected["fine_meter_values"]["A-"]["TO"]["value"],
                   "datetime": PyramidApiClient.datetime_extracter(expected["fine_meter_values"]["A-"]["TO"]["datetime"])},
            "T1": {"value": expected["fine_meter_values"]["A-"]["T1"]["value"],
                   "datetime": PyramidApiClient.datetime_extracter(expected["fine_meter_values"]["A-"]["T1"]["datetime"])},
            "T2": {"value": expected["fine_meter_values"]["A-"]["T2"]["value"],
                   "datetime": PyramidApiClient.datetime_extracter(expected["fine_meter_values"]["A-"]["T2"]["datetime"])},
            },
        }
    
    
    expected = {
        "register_datetime": PyramidApiClient.datetime_extracter(expected["register_datetime"]).strftime("%d.%m.%Y %H:%M"),
        "fine_meter_values": expected_fine_meter_values,
    }
    assert result == expected
    
    
    
    