# NeXium для Intel Mac — исследовательский этап №2

**Целевая платформа: нативный Intel Mac, архитектура x86_64.** Apple Silicon пока не разрабатываем.

В репозитории находятся инструменты **первоначального переноса**, а не проверенная работающая версия NeXium. Наличие файла `.app` означает только успешную компиляцию, но не успешный запуск Nintendo Switch NRO.

## Источник

- Оригинальный NeXium: https://github.com/nexium-emu/nexium
- Лицензия оригинала: MIT.
- Проверяемая ревизия: `089562567a0a8760dfdd8420e1f57c35159a9219` (20 октября 2026).
- Исходники забираются непосредственно из upstream; пока нет утверждений о полноценном macOS-порте.

## Что сейчас проверяется

1. Синтаксис утилит и три синтетических сценария отчётности: нормальный выход, неуспешный выход, зависший процесс.
2. CI только на GitHub-hosted `macos-15-intel` с проверкой настоящего x86_64 железа (не Rosetta).
3. Rust/CMake сборка исходников NeXium с Dynarmic (`backend-dynarmic`).
4. Интерфейс eframe/wgpu на Metal и начальная Vulkan portability enumeration через MoltenVK.
5. Сохранение логов при **успехе или неуспехе** сборки.

Нет гарантий, что текущего набора исправлений достаточно: полный Vulkan-путь, память/JIT, передача кадров и обработка аудио ещё нуждаются в адаптации и реальных испытаниях.

## GitHub Actions

Открыть вкладку **Actions → NeXium Intel macOS experimental probe → Run workflow** для рабочей ветки.

Если выполнение не прошло, скачать артефакт `nexium-macos-intel-probe` и разобрать `build.log`. **Нельзя отмечать порт готовым**, пока не пройдены сборка и игровые проверки отдельно.

## Локальная сборка на настоящем Intel Mac

Установить Xcode Command Line Tools, Rust через rustup и Homebrew. Затем установить зависимости:

```sh
xcode-select --install
brew install cmake ninja pkgconf boost molten-vk vulkan-loader vulkan-tools
vulkaninfo --summary
bash macos_probe.sh
```

На старых версиях macOS инструменты или готовые пакеты Homebrew могут быть недоступны — это отдельный диагностируемый блокер.

Рабочий каталог: `nexium-macos-intel-work/`; лог: `nexium-macos-intel-work/build.log`. При **успешной** сборке получится `nexium-macos-intel-work/dist/NeXium-Intel-Experimental.app`. Он не подписан и не является релизной сборкой.

## Локальная проба личного NRO

**Только после успешной сборки**, на Intel Mac:

```sh
python3 scripts/nro_smoke_test.py \
  --exe ./nexium-macos-intel-work/dist/NeXium-Intel-Experimental.app/Contents/MacOS/nexium \
  --nro /путь/к/вашему/private-test.nro \
  --output ./nexium-intel-test-reports/first-test \
  --seconds 30
```

Выходные файлы: `smoke_result.json`, `nexium-console.log`, при наличии кадров `snapshots/*.bmp`.

Важно: статусы `exited_zero_unverified` и `timeout_alive_unverified` **не подтверждают игровой запуск**. Потребуются отдельные проверки игрового ввода, изображения, звука, движения и контрольных точек в наших ремейках. Синтетические тесты проверяют только корректность отчёта.

## Конфиденциальность

Никакие образы игр, пользовательские firmware/keys и приватные NRO не должны загружаться в публичный репозиторий либо CI. В `.gitignore` добавлены основные форматы, но перед коммитом всё равно проверять список файлов. Содержимое диагностических журналов также проверять на личные пути и данные.

## План следующих этапов

1. По первому реальному Intel CI определить конкретные ошибки сборки и исправить их в отдельном PR.
2. Проверить Vulkan через MoltenVK **во всех экземплярах Vulkan**, а не только GPU discovery; подтвердить фактические требования к API и расширениям.
3. Устроить вывод кадров через macOS-совместимый GUI fallback либо Cocoa/Metal.
4. Испытать домашний тестовый NRO и затем последовательно наши собственные NRO.
5. Упаковка, подпись, запуск двойным кликом и стабильные регрессионные проверки.

**Apple Silicon остаётся отложенной целью.**

## Этап №5 — 20 октября 2026: первый реальный Intel-сборочный блокер

GitHub Actions [run №39479780717](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39479780717) завершился ошибкой в **Dynarmic**, ещё до запуска NeXium:

```text
dynarmic/backend/x64/mig/mach_exc_server.h: file not found
failed to run custom build command for dynarmic-sys-mythrax v0.3.6
```

Причина: `vendor/CMakeLists.txt` опубликованного `dynarmic-sys-mythrax 0.3.6` компилирует macOS exception handler без генерации Mach RPC-файлов через `mig`.

Подготовлен **экспериментальный** фикс: `scripts/prepare_dynarmic_macos.py` копирует эту зависимость в отдельную директорию `nexium-macos-intel-work/dynarmic-sys-mythrax-macos` и добавляет CMake-шаг `mig` для Intel; Cargo использует локальный `[patch.crates-io]` в рабочей копии NeXium. Глобальный реестр Cargo не редактируется. Исправление требует подтверждения настоящей повторной Intel-сборкой.

Параллельно запускается CPU-вариант `backend-rustarmic`, который не должен зависеть от сборки Dynarmic. Оба варианта остаются **Intel x86_64**, не Apple Silicon.

Задания CI теперь разделяют компиляцию Dynarmic и Rustarmic, а старые запуски вытесняются актуальной ревизией. После сборки переходить к NRO-тестам можно только при наличии настоящего исполняемого файла и подтверждённого запуска.
