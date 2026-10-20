import pytest
import json
from pathlib import Path
import sys


# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Имена файлов с тестовыми данными
INSTANCES_FILE = "instances.json"
INSTANCE_INFO_FILE = "instance_info.json"
METERDATA_READ_FILE = "meterdata_read.json"
METER_DAILY_DATA_FILE = "meter_daily_data.json"
EXPECTED = "expected.json"
INPUT_DATA = "input.json"

# Путь к папке с данными (относительно этого файла)
DATA_DIR = Path(__file__).parent / "data"

def load_json(scenario: str, filename: str) -> dict:
    """Загружает JSON-файл для конкретного сценария (папки с номером)."""
    file_path = DATA_DIR / scenario / filename
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
    
    
SCENARIO_DESCRIPTIONS_FILE = DATA_DIR / "scenario.json"
print(SCENARIO_DESCRIPTIONS_FILE)

def load_scenario_descriptions() -> dict:
    with open(SCENARIO_DESCRIPTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# Словарь описаний: ключи — имена папок (строки с числами)
SCENARIO_DESCRIPTIONS = load_scenario_descriptions()
SCENARIOS = list(SCENARIO_DESCRIPTIONS.keys())  # ["1", "2", ..., "6"]


@pytest.fixture
def scenario(request) -> str:
    """Возвращает имя текущего сценария (например, '1', '2', ...)."""
    return request.param

@pytest.fixture
def input_data(scenario):
    return load_json(scenario, INPUT_DATA)

@pytest.fixture
def mock_fetch_instances(scenario):
    return load_json(scenario, INSTANCES_FILE)

@pytest.fixture
def mock_fetch_instance_info(scenario):
    return load_json(scenario, INSTANCE_INFO_FILE)

@pytest.fixture
def mock_fetch_meterdata_read(scenario):
    return load_json(scenario, METERDATA_READ_FILE)

@pytest.fixture
def mock_fetch_meter_daily_data(scenario):
    return load_json(scenario, METER_DAILY_DATA_FILE)

@pytest.fixture
def expected(scenario):
    return load_json(scenario, EXPECTED)