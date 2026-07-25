# Infinity_audiomodem

Проект для передачи файлов через звуковой канал между двумя ноутбуками.

## Быстрый старт на новом компьютере

1. Установите Python 3.11+
2. Откройте терминал в папке проекта
3. Установите зависимости:

```bash
python3 -m pip install -r requirements.txt
```

4. На первом ноутбуке отправьте файл:

```bash
python3 sender.py --file text.txt --play
```

5. На втором ноутбуке примите файл:

```bash
python3 receiver.py --listen 15 --out received.bin
```

## Новые команды

Отправка файла:

```bash
python3 sender.py --file text.txt --play
```

Отправка текста:

```bash
python3 sender.py --text "привет" --play
```

Приём и сохранение файла:

```bash
python3 receiver.py --out received.bin
```

Приём с явным временем прослушивания:

```bash
python3 receiver.py --listen 15 --out received.bin
```

Приём блоками по 10 секунд до обнаружения маркера завершения:

```bash
python3 receiver.py --chunk-seconds 10 --out received.bin
```

## Если `sounddevice` не ставится

На macOS иногда нужен PortAudio. Установите его через Homebrew:

```bash
brew install portaudio
```

На Windows можно сначала установить Microsoft Visual C++ Build Tools, если pip сообщает об ошибке сборки.

## Что нужно для работы

- динамик и микрофон
- тихая комната
- ноутбуки рядом друг с другом
