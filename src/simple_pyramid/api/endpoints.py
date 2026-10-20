"""Пути эндпоинтов API «Пирамиды» (относительно ``.../api/v1/``)."""

LOGIN = "auth/login/"
GET_INSTANCES = "rdinstance/getinstances/"
GET_INSTANCE_INFO = "rdinstance/getinstanceinfo/"

METERDATA_READ = "meterdata/read/"
METERDATA_ACQUIRE = "meterdata/acquire/"

LOAD_LIMIT_STATES = "loadlimitmanagement/getmeterpointswithloadandlimitstate/"
LOAD_LIMIT_START_READ = "loadlimitmanagement/startasynctaskreadloadlimitstates/"
# Управление нагрузкой (включить/отключить). Не используется — нет прав на это действие.
LOAD_WRITE_STATE = "loadlimitmanagement/startasynctaskwriteloadstate/"

EVENTS_GET = "events/geteventsforobjects/"
EVENTS_START_READ = "events/startreadeventsasync/"

BACKGROUND_TASK = "backgroundtasks/getbackgroundtask/"
BACKGROUND_TASK_STATE = "backgroundtasks/getbackgroundtaskstate/"

REPORT_CREATE = "reports/createfilereportasync/"
REPORT_ARCHIVE = "reports/getarchivereport/"
