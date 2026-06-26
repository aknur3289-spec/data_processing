# MedArchive price parser backend

## Что есть в проекте

В проекте уже были рабочие парсеры медицинских прайсов:

- `parser/xlsx_parser.py` читает Excel-файлы `.xlsx/.xlsm`
- `parser/docx_parser.py` читает Word-файлы `.docx`
- `parser/parser_pdf_ocr.py` читает PDF и при необходимости может использовать OCR

Парсеры отвечают за самое сложное: найти строки услуг, названия, коды и цены. Их логика не переписывалась.

## Что добавлено

Добавлен backend на FastAPI в папке `backend/`.

Он нужен как единая точка входа для demo: можно загрузить один файл или ZIP-архив, а backend сам выберет нужный существующий парсер.

Новые файлы:

- `backend/main.py` - FastAPI приложение и endpoints
- `backend/parser_service.py` - adapter между API и существующими парсерами
- `backend/schemas.py` - общий формат ответа
- `backend/storage.py` - временное сохранение загруженных файлов
- `backend/requirements.txt` - зависимости для backend

## Что значит unified parser API

Раньше для каждого формата нужно было вручную вызывать свою функцию:

- Excel отдельно
- DOCX отдельно
- PDF отдельно

Теперь есть один API:

- `POST /parse` для одного файла
- `POST /parse/archive` для ZIP-архива

Backend сам понимает формат файла и вызывает правильный парсер.

## Что делает backend adapter

Adapter - это тонкий слой между HTTP API и парсерами.

Он:

1. Принимает файл от пользователя.
2. Проверяет расширение файла.
3. Вызывает существующий parser.
4. Приводит результат к одному общему формату.

Важно: adapter не меняет логику парсинга. Он только соединяет готовые парсеры с backend API.

## Как обрабатываются форматы

### XLSX / XLSM / XLS

Backend вызывает:

```python
parse_xlsx(file_path)
```

Это существующий Excel parser.

Примечание: текущий Excel parser работает через `openpyxl`, поэтому старые `.xls` файлы могут уйти в `needs_review`, если они не читаются этим parser.

### DOCX

Backend вызывает:

```python
parse_docx(file_path)
```

### PDF

Backend вызывает:

```python
process_pdf_job(...)
```

PDF parser сам решает, читать текст напрямую или использовать OCR fallback.

### ZIP

Backend распаковывает ZIP во временную папку, проходит по файлам внутри и каждый файл отправляет в нужный parser.

Поддерживаются файлы внутри ZIP:

- `.xlsx`
- `.xlsm`
- `.xls`
- `.docx`
- `.pdf`

## Common PriceItem schema

Разные парсеры возвращали данные немного по-разному. Backend приводит все строки к одному формату `PriceItem`.

Пример одной услуги:

```json
{
  "partner_name": "Клиника 1",
  "source_file": "Клиника 1 2026.pdf",
  "file_format": "pdf",
  "source_sheet": null,
  "source_page": 1,
  "effective_date": "2026-01-01",
  "service_code_source": "U1.1",
  "service_name_raw": "Консультация врача",
  "service_id": null,
  "price_resident_kzt": 10000,
  "price_sng_kzt": 10000,
  "price_nonresident_kzt": 15000,
  "price_original": 10000,
  "currency_original": "KZT",
  "is_verified": false,
  "verification_note": null,
  "is_active": true,
  "parse_status": "done",
  "parse_log": null,
  "extraction_method": "pymupdf_blocks"
}
```

Это важно, потому что frontend, matching и будущая база могут работать с одним JSON-форматом, независимо от исходного файла.

## Endpoints

### Health check

```http
GET /health
```

Ответ:

```json
{"status": "ok"}
```

### Парсинг одного файла

```http
POST /parse
```

Query params:

- `enable_ocr=true`
- `ocr_max_pages=1`

### Парсинг ZIP-архива

```http
POST /parse/archive
```

Query params:

- `enable_ocr=true`
- `ocr_max_pages=1`

## Как запустить

Из корня проекта:

```bash
cd /Users/madina/projects/medhackathon/data_processing
python3 -m pip install -r backend/requirements.txt
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Открыть Swagger UI в браузере:

```text
http://127.0.0.1:8000/docs
```

Важно: ссылку нужно открывать в браузере, не вводить как команду в терминале.

На macOS можно открыть так:

```bash
open http://127.0.0.1:8000/docs
```

## Как тестировать

### Через Swagger

1. Запустить backend.
2. Открыть `http://127.0.0.1:8000/docs`.
3. Проверить `GET /health`.
4. Открыть `POST /parse/archive`.
5. Нажать `Try it out`.
6. Загрузить `Хакатон.zip`.
7. Поставить:
   - `enable_ocr=true`
   - `ocr_max_pages=1`
8. Нажать `Execute`.

### Через curl

Проверка backend:

```bash
curl http://127.0.0.1:8000/health
```

Проверка ZIP:

```bash
curl -X POST "http://127.0.0.1:8000/parse/archive?enable_ocr=true&ocr_max_pages=1" \
  -F "file=@Хакатон.zip"
```

## Что смотреть в ответе

Главные поля:

- `summary.total_files` - сколько файлов было внутри архива
- `summary.done` - сколько файлов успешно разобрались
- `summary.needs_review` - сколько файлов требуют проверки
- `summary.items_count` - сколько строк услуг найдено
- `jobs` - статус по каждому файлу
- `items` - сами услуги в общем формате

`needs_review` не означает, что backend упал. Это значит, что файл открылся, но текущий parser не смог найти строки услуг.

## Что говорить на checkpoint

Коротко:

> У нас уже были отдельные парсеры для Excel, Word и PDF. Я добавила backend adapter на FastAPI, который не переписывает parser logic, а просто вызывает нужный parser по типу файла. Теперь можно загрузить один файл или целый ZIP архив, backend сам разберет все поддерживаемые форматы и вернет единый JSON со списком услуг.

Что показать:

1. Сначала сказать, что основа проекта - existing parsers.
2. Показать, какие форматы они читают: XLSX/XLSM, DOCX, PDF/OCR.
3. Потом показать FastAPI `/docs`.
4. Выполнить `GET /health`.
5. Выполнить `POST /parse/archive` с `Хакатон.zip`.
6. Показать `summary`: сколько файлов обработано и сколько услуг найдено.
7. Показать один объект из `items`, чтобы было видно общий формат `PriceItem`.

Почему это важно для demo:

- не нужно запускать каждый parser вручную;
- можно загрузить реальный архив клиник;
- результат сразу готов для frontend, matching или будущей базы данных;
- backend показывает status по каждому файлу, поэтому видно, что разобралось, а что требует ручной проверки.
