import pytest
import json
from pathlib import Path
import sys


# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Имена файлов с тестовыми данными
INSTANCES_FILE = "instances.json"
INSTANCE_INFO_FILE = "instance_info.json"
METER_DAILY_DATA_FILE = "meter_daily_data.json"
METERDATA_READ_FILE = "meterdata_read.json"

# Путь к папке с данными (относительно этого файла)
DATA_DIR = Path(__file__).parent / "data"


def load_json(filename: str) -> dict:
    """Загружает JSON-файл из папки data и возвращает словарь."""
    file_path = DATA_DIR / filename
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_fetch_instances():
    """Возвращает словарь с данными из instances.json."""
    return load_json(INSTANCES_FILE)


@pytest.fixture
def mock_fetch_instance_info():
    """Возвращает словарь с данными из instance_info.json."""
    return load_json(INSTANCE_INFO_FILE)


@pytest.fixture
def mock_fetch_meterdata_read():
    """Возвращает словарь с данными из meterdata_read.json."""
    return load_json(METERDATA_READ_FILE)


@pytest.fixture
def mock_fetch_meter_daily_data():
    """Возвращает словарь с данными из meter_daily_data.json."""
    return load_json(METER_DAILY_DATA_FILE)