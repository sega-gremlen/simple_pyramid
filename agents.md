# Agent Settings

# @description: Эта настройка определяет, может ли агент удалять комментарии из кода.
# @values: true, false
# @default: false
preserve_comments = true

# @description: Язык, на котором агент должен отвечать.
# @values: "русский", "английский"
# @default: "русский"
language = "русский"

# @description: Что делать при возникновении ошибки.
# @values: "stop", "rollback", "continue"
# @default: "stop"
on_error = "stop"

# @description: Как применять изменения в коде.
# @values: "apply", "diff", "branch"
# @default: "apply"
apply_changes = "apply"

# @description: Устанавливать ли недостающие зависимости.
# @values: "always", "never", "ask"
# @default: "ask"
install_dependencies = "ask"

# @description: Максимальная глубина поиска файлов.
# @values: integer
# @default: 3
max_search_depth = 3
