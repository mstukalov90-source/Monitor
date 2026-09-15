# Документация MONITOR — маршруты OSRM (Android)

Сервис строит маршруты **по дорогам Москвы** (граф OpenStreetMap, лицензия ODbL). Профили: автомобиль, велосипед, пеший.

Это **не** публичный M2M API. Ключ `MONITOR_API_KEY` **не нужен**. Доступ только из корпсети или VPN-приложения на планшете — так же, как к полевым фото, но **порт 80**, не `:8000`.

Смежники через `https://monitor-crm.mggt.ru` этот сервис **не** видят (`403`).

## Подключение

| Параметр | Значение |
|----------|----------|
| Base URL | `http://172.21.198.219/osrm` |
| Протокол | HTTP (без TLS) |
| Auth | нет |
| Сеть | корпсеть `172.21.0.0/16` или VPN-app |
| Таймаут nginx | 60 с |

В `AndroidManifest` / Network Security Config разрешите cleartext для `172.21.198.219` (как уже сделано для `:8000`).

Не вызывайте порты `:5000`–`:5002` с устройства — они слушают только `127.0.0.1` на сервере.

## Профили

Сегмент в URL выбирает тип маршрута:

| URL-профиль | Алиасы | Смысл |
|-------------|--------|--------|
| `driving` | `car` | автомобиль |
| `bike` | `bicycle`, `cycling` | велосипед |
| `foot` | `walking` | пешком |

## Координаты

Формат OSRM: **`longitude,latitude`** (WGS84), не как в Android `Location` (`latitude` / `longitude`).

Точки в пути разделяются **точкой с запятой**. В URL её лучше кодировать как `%3B`.

Покрытие — **город Москва**. Точки за пределами графа сервис не проложит (ошибка или срыв на край сети).

## Построить маршрут

**Запрос:**

`GET http://172.21.198.219/osrm/route/v1/{profile}/{lon},{lat}%3B{lon},{lat}`

Минимум две точки (старт и финиш). Можно больше: `A%3BB%3BC`.

Полезные query-параметры:

| Параметр | Рекомендация для карты | Описание |
|----------|------------------------|----------|
| `overview` | `full` | геометрия всего маршрута (`false` — без линии) |
| `geometries` | `geojson` | массив `[lon, lat]` в `coordinates` |
| `steps` | `true`, если нужны манёвры | пошаговые инструкции |
| `alternatives` | `false` (по умолчанию) | дополнительные варианты |

**Пример (curl), Кремль → точка восточнее:**

```bash
curl -sS "http://172.21.198.219/osrm/route/v1/driving/37.6173,55.7558%3B37.65,55.76?overview=full&geometries=geojson"
```

Вело / пеший — замените `driving` на `bike` или `foot`.

**Ответ при успехе (`200`):**

```json
{
  "code": "Ok",
  "waypoints": [
    { "location": [37.6173, 55.7558], "name": "…" },
    { "location": [37.65, 55.76], "name": "…" }
  ],
  "routes": [
    {
      "distance": 2636.4,
      "duration": 354.2,
      "geometry": {
        "type": "LineString",
        "coordinates": [[37.6173, 55.7558], [37.6181, 55.7560]]
      },
      "legs": []
    }
  ]
}
```

| Поле | Единицы |
|------|---------|
| `routes[0].distance` | метры |
| `routes[0].duration` | секунды |
| `geometry.coordinates` | `[lon, lat]` — для полилинии на карте переставьте в `LatLng(lat, lon)` |

Точки старта/финиша OSRM **притягивает к ближайшей дороге** профиля (`waypoints[].location` может отличаться от GPS).

## Другие методы (тот же Base URL)

Путь после `/osrm` — стандартный [OSRM HTTP API v1](http://project-osrm.org/docs/v5.24.0/api/#).

| Назначение | Пример пути |
|------------|-------------|
| Маршрут | `/route/v1/driving/{coords}` |
| Ближайшая точка на графе | `/nearest/v1/driving/{lon},{lat}` |
| Матрица времён | `/table/v1/driving/{coords}` |
| Привязка трека GPS | `/match/v1/driving/{coords}` |
| Оптимальный обход точек | `/trip/v1/driving/{coords}` |

## Коды ответов

| HTTP | `code` в JSON | Что делать |
|------|----------------|------------|
| `200` | `Ok` | маршрут есть |
| `400` | `InvalidQuery`, `InvalidValue`, `NoRoute`, `NoSegment` | проверить lon/lat порядок, покрытие Москвы, что точки на дороге |
| `403` | — (тело nginx) | нет VPN / не корпсеть |
| `404` | — | неверный путь (нет `/osrm/…/v1/{profile}/`) |
| `502` / `504` | — | бэкенд недоступен; повторить позже |

## Android (OkHttp)

```kotlin
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

enum class OsrmProfile(val path: String) {
    Driving("driving"),
    Bike("bike"),
    Foot("foot"),
}

fun buildRouteUrl(
    fromLon: Double,
    fromLat: Double,
    toLon: Double,
    toLat: Double,
    profile: OsrmProfile,
): String {
    val coords = "$fromLon,$fromLat;$toLon,$toLat"
    return "http://172.21.198.219/osrm/route/v1/${profile.path}/$coords"
        .toHttpUrl()
        .newBuilder()
        .addQueryParameter("overview", "full")
        .addQueryParameter("geometries", "geojson")
        .addQueryParameter("steps", "false")
        .build()
        .toString()
}

fun fetchRoute(url: String): JSONObject {
    val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()
    val request = Request.Builder()
        .url(url)
        .header("Accept", "application/json")
        .get()
        .build()
    client.newCall(request).execute().use { response ->
        val body = response.body?.string().orEmpty()
        if (response.code == 403) {
            throw IllegalStateException("OSRM: нет доступа (включите VPN)")
        }
        if (!response.isSuccessful) {
            throw IllegalStateException("OSRM HTTP ${response.code}: $body")
        }
        val json = JSONObject(body)
        if (json.optString("code") != "Ok") {
            throw IllegalStateException("OSRM code=${json.optString("code")}")
        }
        return json
    }
}
```

`HttpUrl` сам закодирует `;` в `%3B`.

Полилиния (MapKit / OSMDroid / Google Maps):

```kotlin
fun routeLatLngs(routeJson: JSONObject): List<Pair<Double, Double>> {
    val coords = routeJson
        .getJSONArray("routes")
        .getJSONObject(0)
        .getJSONObject("geometry")
        .getJSONArray("coordinates")
    return (0 until coords.length()).map { i ->
        val pair = coords.getJSONArray(i)
        val lon = pair.getDouble(0)
        val lat = pair.getDouble(1)
        lat to lon
    }
}
```

Из `android.location.Location`: в URL передавайте `location.longitude` **первым**, `location.latitude` — вторым.

## Проверка с планшета (VPN)

```bash
curl -sS "http://172.21.198.219/osrm/nearest/v1/driving/37.6173,55.7558"
# "code":"Ok"

curl -sS "http://172.21.198.219/osrm/route/v1/foot/37.6173,55.7558%3B37.65,55.76?overview=false"
# "code":"Ok"
```

Без VPN ожидайте **403**.

Карта OSM © участники OpenStreetMap, [ODbL](https://opendatacommons.org/licenses/odbl/).
