# Запрос на выгрузку GeoJSON map221/rs_2022 (ручной запуск)
import json
import sys
from pathlib import Path

# Allow imports from project root when run as: python Vector_py/request_geojsno.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import PROJECT_DIR
from collector.vector_mka_fetch import fetch_url_221_geojson, read_token

if __name__ == "__main__":
    token = read_token()
    if not token:
        print("Ошибка: токен не найден (Vector_py/token.md или VECTOR_MKA_TOKEN)")
        sys.exit(1)

    try:
        data = fetch_url_221_geojson(token)
        out_path = PROJECT_DIR / "url_222_wgs.geojson"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        print(f"Данные успешно сохранены в {out_path}")
    except Exception as exc:
        print(f"Ошибка запроса: {exc}")
        sys.exit(1)
