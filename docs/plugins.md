# AgentControl — Руководство по плагинам

## 1. Контур
- Entry point: `agentcontrol.plugins`.
- Контракт: объект с методом `register(registrar, context)`.
- Регистратор предоставляет `add_subparser(name, help_text, builder)` для добавления верхнеуровневой команды `agentcall`.
- Builder принимает `(argparse_parser, PluginContext)` и возвращает обработчик `Callable[[Namespace], int]`.

## 2. Минимальный пример
Репозиторий: `examples/plugins/agentcontrol-hello-plugin`
```python
from agentcontrol.plugins import PluginRegistrar, PluginContext

def register(registrar: PluginRegistrar, context: PluginContext) -> None:
    def builder(parser, ctx):
        parser.add_argument("--name", default="Agent")
        def handler(args):
            print(f"Hello, {args.name}!")
            return 0
        return handler
    registrar.add_subparser("hello-plugin", "Приветствие", builder)
```

## 3. Поток использования
```bash
pip install -e examples/plugins/agentcontrol-hello-plugin
agentcall plugins list
agentcall hello-plugin --name Agent
```

## 4. Рекомендации
- Поддерживайте идемпотентность и явные побочные эффекты.
- Используйте `record_event` для телеметрии, если важна наблюдаемость.
- Изменяемые настройки публикуйте через переменные `AGENTCONTROL_<PLUGIN>`.
- Покрывайте команды тестами и документируйте аргументы в README плагина.
