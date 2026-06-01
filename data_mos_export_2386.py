#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для выгрузки данных с data.mos.ru (сервис 2855)
в форматы GeoJSON и GeoPackage
"""

import requests
import json
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
from shapely import wkt
import pandas as pd
from typing import Dict, List, Any
import sys
import os
import ssl
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning

# Отключаем предупреждения SSL (для решения проблемы с сертификатами на macOS)
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

# Создаем контекст SSL без проверки сертификатов (временное решение)
ssl._create_default_https_context = ssl._create_unverified_context

# ============================================================================
# НАСТРОЙКИ
# ============================================================================
# Укажите здесь ваш API ключ от data.mos.ru
# Получить ключ можно на https://data.mos.ru в разделе для разработчиков
API_KEY = '66bae17c-d7bd-406c-93f2-649eb6d78c6b'  # Вставьте ваш ключ здесь

# ID сервиса для выгрузки
SERVICE_ID = 2386

# Префикс для выходных файлов
OUTPUT_PREFIX = "Data_mos_export_2386"
# ============================================================================


class DataMosDownloader:
    """Класс для загрузки данных с data.mos.ru"""
    
    BASE_URL = "https://apidata.mos.ru/v1/datasets"
    
    def __init__(
        self,
        service_id: int,
        api_key: str = None,
        timeout: int = 60,
        max_workers: int = 4,
        max_retries: int = 5,
    ):
        """
        Инициализация загрузчика
        
        Args:
            service_id: ID сервиса (например, 60562)
            api_key: API ключ (опционально, если требуется)
        """
        self.service_id = service_id
        self.api_key = api_key
        self.headers = {}
        self.timeout = timeout
        self.max_workers = max_workers
        self.page_size = 500

        # Настройка повторных попыток
        retry_strategy = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        
        # Создаем сессию с отключенной проверкой SSL
        self.session = requests.Session()
        
        # Отключаем проверку SSL для этой сессии
        self.session.verify = False
        
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=max_workers, pool_maxsize=max_workers)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _fetch_page(self, url: str, skip: int, top: int) -> Dict[str, Any]:
        """
        Загрузка одной страницы данных.
        """
        params = {'$skip': skip, '$top': top}
        if self.api_key:
            params['api_key'] = self.api_key

        # Для отладки - показываем URL без API ключа
        debug_params = params.copy()
        if 'api_key' in debug_params:
            debug_params['api_key'] = '***'
        debug_url = requests.Request('GET', url, params=debug_params).prepare().url
        print(f"Ссылка запроса: {debug_url}")

        try:
            response = self.session.get(url, headers=self.headers, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            payload = response.json()
            data = self._extract_features(payload)
            return {'skip': skip, 'top': top, 'data': data}
        except requests.exceptions.SSLError as e:
            print(f"SSL ошибка при загрузке страницы {skip}: {e}")
            print("Попробуйте обновить сертификаты командой: /Applications/Python\\ 3.9/Install\\ Certificates.command")
            raise
        except Exception as e:
            print(f"Ошибка при загрузке страницы {skip}: {e}")
            raise
    
    def get_data(self, limit: int = None) -> List[Dict]:
        """
        Получение данных с API
        
        Args:
            limit: Ограничение количества записей (None = все)
            
        Returns:
            Список словарей с данными
        """
        url = f"{self.BASE_URL}/{self.service_id}/features"
        print(f"Загрузка данных с {url}...")

        all_data = []
        # API data.mos.ru требует $skip >= 1
        next_skip = 1

        while True:
            if limit and len(all_data) >= limit:
                break

            tasks = []
            planned = 0
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                for _ in range(self.max_workers):
                    if limit:
                        remaining = limit - len(all_data) - planned
                        if remaining <= 0:
                            break
                        top = min(self.page_size, remaining)
                    else:
                        top = self.page_size

                    page_skip = next_skip + planned
                    tasks.append(executor.submit(self._fetch_page, url, page_skip, top))
                    planned += top

                if not tasks:
                    break

                # Обрабатываем результаты по мере их завершения
                for future in as_completed(tasks):
                    try:
                        result = future.result()
                        data = result['data']
                        top = result['top']

                        if not data:
                            continue

                        all_data.extend(data)
                        print(f"Загружено {len(all_data)} записей...")

                        if len(data) < top:
                            return all_data[:limit] if limit else all_data

                        if limit and len(all_data) >= limit:
                            return all_data[:limit]
                            
                    except Exception as e:
                        print(f"Ошибка при обработке результата: {e}")
                        continue

            next_skip += planned
            
            # Если загрузили меньше, чем запланировали - выходим
            if len([f for f in tasks if f.done()]) < len(tasks):
                break
        
        print(f"Всего загружено {len(all_data)} записей")
        return all_data

    def _extract_features(self, payload: Any) -> List[Dict]:
        """
        Извлечение массива features из ответа API.
        """
        if isinstance(payload, dict):
            # Пробуем разные возможные структуры ответа
            if 'features' in payload:
                features = payload.get('features', [])
                return features if isinstance(features, list) else []
            elif 'data' in payload:
                data = payload.get('data', [])
                return data if isinstance(data, list) else []
            elif 'Items' in payload:
                items = payload.get('Items', [])
                return items if isinstance(items, list) else []
        if isinstance(payload, list):
            return payload
        return []
    
    def extract_geometry(self, row: Dict) -> Any:
        """
        Извлечение геометрии из строки данных
        
        Args:
            row: Словарь с данными строки
            
        Returns:
            Объект Shapely geometry или None
        """
        # Попытка найти геометрию в различных форматах
        geometry = None
        
        # Проверка структуры Feature
        if row.get('type') == 'Feature' and 'geometry' in row:
            geom = row['geometry']
            if geom and geom.get('type') and geom.get('coordinates'):
                return self._geojson_to_shapely(geom)
        
        # Проверка различных возможных полей с геометрией в Cells
        if 'Cells' in row:
            cells = row['Cells']
            for field in ['geoData', 'GeoData', 'geometry', 'coordinates', 'wkt', 'geom']:
                if field in cells:
                    geom_data = cells[field]
                    if geom_data:
                        geometry = self._parse_geometry(geom_data)
                        if geometry:
                            return geometry
        
        # Проверка корневого уровня
        for field in ['geoData', 'GeoData', 'geometry', 'coordinates', 'wkt']:
            if field in row:
                geom_data = row[field]
                if geom_data:
                    geometry = self._parse_geometry(geom_data)
                    if geometry:
                        return geometry
        
        return None
    
    def _parse_geometry(self, geom_data: Any) -> Any:
        """
        Парсинг геометрии из различных форматов
        
        Args:
            geom_data: Данные геометрии (может быть строка, dict, list)
            
        Returns:
            Объект Shapely geometry или None
        """
        if not geom_data:
            return None
            
        if isinstance(geom_data, str):
            # Попытка парсинга WKT
            try:
                return wkt.loads(geom_data)
            except:
                pass
            
            # Попытка парсинга GeoJSON строки
            try:
                geom_dict = json.loads(geom_data)
                return self._geojson_to_shapely(geom_dict)
            except:
                pass
        
        elif isinstance(geom_data, dict):
            # GeoJSON формат
            return self._geojson_to_shapely(geom_data)
        
        elif isinstance(geom_data, list) and len(geom_data) >= 2:
            # Список координат (может быть точка или массив точек)
            try:
                if isinstance(geom_data[0], (int, float)):
                    # Обычная точка [lon, lat]
                    if len(geom_data) >= 2:
                        return Point(geom_data[0], geom_data[1])
                else:
                    # Линия или полигон (массив точек)
                    coords = []
                    for point in geom_data:
                        if isinstance(point, (list, tuple)) and len(point) >= 2:
                            coords.append((point[0], point[1]))
                    if coords:
                        if len(coords) == 1:
                            return Point(coords[0])
                        else:
                            return LineString(coords)
            except:
                pass
        
        return None
    
    def _geojson_to_shapely(self, geojson: Dict) -> Any:
        """
        Конвертация GeoJSON в Shapely geometry
        
        Args:
            geojson: Словарь с GeoJSON геометрией
            
        Returns:
            Объект Shapely geometry или None
        """
        if not geojson or not isinstance(geojson, dict):
            return None
            
        geom_type = geojson.get('type', '').lower()
        coordinates = geojson.get('coordinates', [])
        
        if not coordinates:
            return None
        
        try:
            if geom_type == 'point':
                if len(coordinates) >= 2:
                    return Point(coordinates[0], coordinates[1])
            elif geom_type == 'linestring':
                if len(coordinates) >= 2:
                    return LineString(coordinates)
            elif geom_type == 'polygon':
                if len(coordinates) >= 1:
                    return Polygon(coordinates[0])
            elif geom_type == 'multipoint':
                from shapely.geometry import MultiPoint
                points = [Point(coord[0], coord[1]) for coord in coordinates if len(coord) >= 2]
                return MultiPoint(points) if points else None
            elif geom_type == 'multilinestring':
                from shapely.geometry import MultiLineString
                lines = [LineString(line) for line in coordinates if len(line) >= 2]
                return MultiLineString(lines) if lines else None
            elif geom_type == 'multipolygon':
                from shapely.geometry import MultiPolygon
                polygons = [Polygon(poly[0]) for poly in coordinates if len(poly) >= 1]
                return MultiPolygon(polygons) if polygons else None
        except Exception as e:
            print(f"Ошибка при конвертации GeoJSON: {e}")
        
        return None
    
    def convert_to_geodataframe(self, data: List[Dict]) -> gpd.GeoDataFrame:
        """
        Конвертация данных в GeoDataFrame
        
        Args:
            data: Список словарей с данными
            
        Returns:
            GeoDataFrame
        """
        if not data:
            raise ValueError("Нет данных для конвертации")
        
        # Проверяем, не является ли ответ уже GeoJSON FeatureCollection
        if isinstance(data, dict) and 'features' in data:
            data = data['features']
        
        # Если данные уже в формате GeoJSON Features
        if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get('type') == 'Feature':
            gdf = gpd.GeoDataFrame.from_features(data, crs='EPSG:4326')
            if not gdf.empty:
                return gdf
        
        # Резервный путь для других форматов
        features = []
        skipped = 0
        
        for idx, row in enumerate(data):
            # Извлечение геометрии
            geometry = self.extract_geometry(row)
            
            if geometry is None:
                skipped += 1
                continue
            
            # Извлечение атрибутов
            attributes = {}
            
            # Обработка структуры Cells
            if 'Cells' in row:
                attributes = row['Cells'].copy()
            else:
                # Исключаем поля с геометрией из атрибутов
                exclude_fields = ['geoData', 'GeoData', 'geometry', 'coordinates', 'wkt', 'geom']
                attributes = {k: v for k, v in row.items() if k not in exclude_fields}
            
            # Добавление служебных полей
            if 'global_id' in row:
                attributes['global_id'] = row['global_id']
            if 'id' in row:
                attributes['id'] = row['id']
            
            features.append({
                'geometry': geometry,
                **attributes
            })
        
        if not features:
            raise ValueError(f"Не удалось извлечь геометрию ни из одной записи. "
                           f"Пропущено записей: {skipped}, всего записей: {len(data)}")
        
        if skipped > 0:
            print(f"Предупреждение: пропущено {skipped} записей без геометрии")
        
        # Создание GeoDataFrame
        gdf = gpd.GeoDataFrame(features, crs='EPSG:4326')
        
        return gdf
    
    def save_data(self, gdf: gpd.GeoDataFrame, output_prefix: str = "output"):
        """
        Сохранение данных в GeoJSON и GeoPackage
        
        Args:
            gdf: GeoDataFrame для сохранения
            output_prefix: Префикс для имен выходных файлов
        """
        geojson_file = f"{output_prefix}.geojson"
        gpkg_file = f"{output_prefix}.gpkg"
        
        print(f"\nСохранение данных...")
        print(f"GeoJSON: {geojson_file}")
        print(f"GeoPackage: {gpkg_file}")
        
        # Сохранение в GeoJSON
        try:
            gdf.to_file(geojson_file, driver='GeoJSON', encoding='utf-8')
            print(f"✓ GeoJSON сохранен: {len(gdf)} объектов")
        except Exception as e:
            print(f"Ошибка при сохранении GeoJSON: {e}")
        
        # Сохранение в GeoPackage
        try:
            gdf.to_file(gpkg_file, driver='GPKG', encoding='utf-8')
            print(f"✓ GeoPackage сохранен: {len(gdf)} объектов")
        except Exception as e:
            print(f"Ошибка при сохранении GeoPackage: {e}")
        
        # Вывод статистики
        print(f"\nСтатистика:")
        print(f"  Всего объектов: {len(gdf)}")
        if not gdf.empty:
            print(f"  Типы геометрии: {dict(gdf.geometry.type.value_counts())}")
            print(f"  Полей: {len(list(gdf.columns))}")
            print(f"  Список полей: {list(gdf.columns)[:10]}...")


def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Выгрузка данных с data.mos.ru в GeoJSON и GeoPackage'
    )
    parser.add_argument(
        '--service-id',
        type=int,
        default=60562,
        help='ID сервиса (по умолчанию: 60562)'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='API ключ (если требуется). Также можно использовать переменную окружения DATA_MOS_API_KEY'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='service_60562',
        help='Префикс для выходных файлов (по умолчанию: service_60562)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Ограничение количества записей (по умолчанию: все)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=60,
        help='Таймаут HTTP-запроса в секундах (по умолчанию: 60)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=2,  # Уменьшаем количество потоков для стабильности
        help='Количество параллельных запросов (по умолчанию: 2)'
    )
    parser.add_argument(
        '--retries',
        type=int,
        default=3,
        help='Количество повторов при сетевых ошибках (по умолчанию: 3)'
    )
    
    args = parser.parse_args()
    
    # Получение API ключа: приоритет - аргумент командной строки > переменная окружения > значение в коде
    api_key = args.api_key or os.getenv('DATA_MOS_API_KEY') or API_KEY
    
    # Получение ID сервиса: приоритет - аргумент командной строки > значение в коде
    service_id = args.service_id if args.service_id != 60562 else SERVICE_ID
    
    # Получение префикса для выходных файлов: приоритет - аргумент командной строки > значение в коде
    output_prefix = args.output if args.output != 'service_60562' else OUTPUT_PREFIX
    
    print("=" * 60)
    print("Загрузчик данных с data.mos.ru")
    print("=" * 60)
    
    if api_key:
        print(f"✓ API ключ найден: {api_key[:10]}...")
    else:
        print("⚠ API ключ не указан. Некоторые данные могут быть недоступны.")
        print("  Получить ключ можно на https://data.mos.ru")
    
    print(f"ID сервиса: {service_id}")
    print(f"Префикс файлов: {output_prefix}")
    print(f"Лимит записей: {args.limit if args.limit else 'без лимита'}")
    print("=" * 60)
    
    # Создание загрузчика
    downloader = DataMosDownloader(
        service_id,
        api_key,
        timeout=max(5, args.timeout),
        max_workers=max(1, args.workers),
        max_retries=max(0, args.retries),
    )
    
    # Загрузка данных
    try:
        data = downloader.get_data(limit=args.limit)
    except Exception as e:
        print(f"\n❌ Ошибка при загрузке данных: {e}")
        print("\nВозможные решения:")
        print("1. Проверьте подключение к интернету")
        print("2. Проверьте правильность API ключа")
        print("3. Убедитесь, что сервис с ID {service_id} существует")
        print("4. Обновите сертификаты: /Applications/Python\\ 3.9/Install\\ Certificates.command")
        sys.exit(1)
    
    if not data:
        print("❌ Данные не получены. Проверьте ID сервиса и доступность API.")
        sys.exit(1)
    
    print(f"✓ Загружено {len(data)} записей")
    
    # Конвертация в GeoDataFrame
    try:
        gdf = downloader.convert_to_geodataframe(data)
        print(f"✓ Создан GeoDataFrame с {len(gdf)} объектами")
    except Exception as e:
        print(f"❌ Ошибка при конвертации данных: {e}")
        print("\nПопытка сохранить сырые данные для анализа...")
        try:
            with open(f"{output_prefix}_raw.json", 'w', encoding='utf-8') as f:
                # Сохраняем первые 5 записей для анализа
                sample = data[:5] if len(data) > 5 else data
                json.dump(sample, f, ensure_ascii=False, indent=2)
            print(f"✓ Первые {len(sample)} записей сохранены в {output_prefix}_raw.json для анализа")
        except:
            print("⚠ Не удалось сохранить данные для анализа")
        sys.exit(1)
    
    # Сохранение данных
    try:
        downloader.save_data(gdf, output_prefix)
        print("\n✅ Готово!")
    except Exception as e:
        print(f"❌ Ошибка при сохранении данных: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()