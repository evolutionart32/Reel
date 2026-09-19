# Reel

Рабочее пространство для монтажа видео с помощью агента.

## Скилл `video-use`

В репозиторий вшит скилл [browser-use/video-use](https://github.com/browser-use/video-use)
(upstream-ревизия `9575612`, 2026-08-30) — разговорный видеоредактор: транскрибация,
нарезка, цветокоррекция, оверлей-анимации, вшитые субтитры.

Лежит в `.claude/skills/video-use/`, поэтому подхватывается автоматически в любой сессии
этого репозитория — отдельная установка не нужна.

```
.claude/
├── settings.json              # регистрирует SessionStart-хук
├── hooks/session-start.sh     # ставит ffmpeg + Python-зависимости в облачной сессии
└── skills/video-use/
    ├── SKILL.md               # основной рабочий документ скилла
    ├── install.md             # инструкция апстрима по ручной установке
    ├── helpers/               # transcribe, pack_transcripts, timeline_view, render, grade
    ├── skills/manim-video/    # вендоренный скилл для Manim-анимаций
    └── tests/
```

## Что нужно перед первым монтажом

1. **ElevenLabs API-ключ** — транскрибация (Scribe) без него не работает.
   Возьмите ключ на https://elevenlabs.io/app/settings/api-keys и положите:

   ```bash
   printf 'ELEVENLABS_API_KEY=%s\n' "$KEY" > .claude/skills/video-use/.env
   chmod 600 .claude/skills/video-use/.env
   ```

   Файл в `.gitignore` — в git он не попадёт. Альтернатива: переменная окружения
   `ELEVENLABS_API_KEY`.

2. **ffmpeg / ffprobe** — ставятся хуком автоматически в облачных сессиях.
   Локально: `brew install ffmpeg` (macOS) или `apt-get install ffmpeg` (Debian/Ubuntu).

3. **Python-зависимости** (`requests`, `librosa`, `matplotlib`, `pillow`, `numpy`) —
   тоже ставятся хуком; вручную: `uv pip install -r` по `.claude/skills/video-use/pyproject.toml`.

Опционально и только по требованию конкретного проекта: `yt-dlp` (источники по URL),
Node.js 22+ (HyperFrames / Remotion), `manim` + LaTeX (Manim-слоты).

## Как пользоваться

Положите исходники в папку и скажите агенту, например: «смонтируй из этих дублей
лончевое видео» или «сделай инвентаризацию дублей и предложи стратегию».

Все результаты пишутся в `<папка_с_видео>/edit/` — репозиторий остаётся чистым.

## Обновление скилла

```bash
git clone --depth 1 https://github.com/browser-use/video-use /tmp/video-use
rsync -a --delete --exclude .git --exclude .env /tmp/video-use/ .claude/skills/video-use/
```
