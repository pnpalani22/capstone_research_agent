from __future__ import annotations

import json
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any
from urllib import error, parse, request
from xml.etree import ElementTree as ET

from langchain_core.tools import tool
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

try:
    from langchain_tavily import TavilySearch
except ImportError:
    from langchain_community.tools.tavily_search import TavilySearchResults as TavilySearch


HTTP_TIMEOUT_SECONDS = 12
MAX_RESULT_COUNT = 5

_WEATHER_CODE_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

_SUPPORTED_SPORT_LEAGUES = {
    "nba": "basketball/nba",
    "wnba": "basketball/wnba",
    "nfl": "football/nfl",
    "nhl": "hockey/nhl",
    "mlb": "baseball/mlb",
}


def _compact_whitespace(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate(text: str, limit: int = 1800) -> str:
    text = _compact_whitespace(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _http_get_json(url: str) -> dict[str, Any]:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_get_text(url: str) -> str:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def _safe_http_json(url: str) -> tuple[dict[str, Any] | None, str]:
    try:
        return _http_get_json(url), ""
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return None, str(exc)


def _safe_http_text(url: str) -> tuple[str | None, str]:
    try:
        return _http_get_text(url), ""
    except (error.URLError, error.HTTPError, TimeoutError) as exc:
        return None, str(exc)


def _weather_code_description(code: int | None) -> str:
    if code is None:
        return "Unknown conditions"
    return _WEATHER_CODE_DESCRIPTIONS.get(int(code), f"Weather code {code}")


def _format_utc_timestamp(value: str) -> str:
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return value


def _espn_scoreboard_path(league: str) -> str | None:
    normalized = _compact_whitespace(league).lower()
    return _SUPPORTED_SPORT_LEAGUES.get(normalized)


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(minimum, min(maximum, number))


@tool("weather")
def weather(location: str, days: int = 3) -> str:
    """Get current weather and a short forecast for a location using Open-Meteo."""

    query = _compact_whitespace(location)
    if not query:
        return "Please provide a location, for example 'Delhi' or 'New York'."

    days = _safe_int(days, default=3, minimum=1, maximum=7)
    geocode_url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        + parse.urlencode({"name": query, "count": 1, "language": "en", "format": "json"})
    )
    geo_payload, geo_error = _safe_http_json(geocode_url)
    if not geo_payload:
        return f"Weather lookup failed for {query}: {geo_error}"

    matches = geo_payload.get("results") or []
    if not matches:
        return f"No weather location match found for {query}."

    match = matches[0]
    latitude = match.get("latitude")
    longitude = match.get("longitude")
    location_name = ", ".join(
        part
        for part in [
            match.get("name"),
            match.get("admin1"),
            match.get("country"),
        ]
        if part
    )

    forecast_params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "forecast_days": days,
        "timezone": "auto",
    }
    forecast_url = "https://api.open-meteo.com/v1/forecast?" + parse.urlencode(forecast_params)
    forecast_payload, forecast_error = _safe_http_json(forecast_url)
    if not forecast_payload:
        return f"Weather forecast lookup failed for {query}: {forecast_error}"

    lines = [f"Weather for {location_name or query}"]
    current = forecast_payload.get("current") or {}
    if current:
        lines.append(
            "Current: "
            + ", ".join(
                [
                    f"{current.get('temperature_2m')} C",
                    f"feels like {current.get('apparent_temperature')} C",
                    _weather_code_description(current.get("weather_code")),
                    f"wind {current.get('wind_speed_10m')} km/h",
                    f"humidity {current.get('relative_humidity_2m')}%",
                ]
            )
        )

    daily = forecast_payload.get("daily") or {}
    dates = daily.get("time") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    rain = daily.get("precipitation_probability_max") or []
    codes = daily.get("weather_code") or []

    for index, date in enumerate(dates[:days]):
        lines.append(
            f"{date}: high {highs[index]} C, low {lows[index]} C, "
            f"rain chance {rain[index]}%, {_weather_code_description(codes[index])}"
        )

    return "\n".join(lines)


@tool("news")
def news(query: str, limit: int = MAX_RESULT_COUNT) -> str:
    """Search recent news headlines using Google News RSS."""

    search_term = _compact_whitespace(query)
    if not search_term:
        return "Please provide a news topic or keyword."

    limit = _safe_int(limit, default=MAX_RESULT_COUNT, minimum=1, maximum=10)
    rss_url = (
        "https://news.google.com/rss/search?"
        + parse.urlencode(
            {
                "q": search_term,
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            }
        )
    )
    rss_text, rss_error = _safe_http_text(rss_url)
    if not rss_text:
        return f"News lookup failed for {search_term}: {rss_error}"

    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError as exc:
        return f"News feed parsing failed for {search_term}: {exc}"

    items = root.findall(".//item")
    if not items:
        return f"No recent news results found for {search_term}."

    lines = [f"Recent news for {search_term}"]
    for index, item in enumerate(items[:limit], start=1):
        title = _compact_whitespace(item.findtext("title"))
        link = _compact_whitespace(item.findtext("link"))
        source = _compact_whitespace(item.findtext("source"))
        pub_date = _format_utc_timestamp(_compact_whitespace(item.findtext("pubDate")))
        summary = _truncate(item.findtext("description") or "", 180)
        lines.append(f"{index}. {title}")
        if source:
            lines.append(f"   Source: {source}")
        if pub_date:
            lines.append(f"   Published: {pub_date}")
        if summary:
            lines.append(f"   Summary: {summary}")
        if link:
            lines.append(f"   Link: {link}")

    return "\n".join(lines)


@tool("politics")
def politics(topic: str, limit: int = MAX_RESULT_COUNT) -> str:
    """Search recent politics and government headlines using Google News RSS."""

    search_term = _compact_whitespace(topic)
    if not search_term:
        search_term = "politics government election congress senate house"

    limit = _safe_int(limit, default=MAX_RESULT_COUNT, minimum=1, maximum=10)
    focused_query = f"{search_term} politics government election congress senate house"
    rss_url = (
        "https://news.google.com/rss/search?"
        + parse.urlencode(
            {
                "q": focused_query,
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            }
        )
    )
    rss_text, rss_error = _safe_http_text(rss_url)
    if not rss_text:
        return f"Politics lookup failed for {search_term}: {rss_error}"

    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError as exc:
        return f"Politics feed parsing failed for {search_term}: {exc}"

    items = root.findall(".//item")
    if not items:
        return f"No recent politics results found for {search_term}."

    lines = [f"Recent politics coverage for {search_term}"]
    for index, item in enumerate(items[:limit], start=1):
        title = _compact_whitespace(item.findtext("title"))
        link = _compact_whitespace(item.findtext("link"))
        source = _compact_whitespace(item.findtext("source"))
        pub_date = _format_utc_timestamp(_compact_whitespace(item.findtext("pubDate")))
        summary = _truncate(item.findtext("description") or "", 180)
        lines.append(f"{index}. {title}")
        if source:
            lines.append(f"   Source: {source}")
        if pub_date:
            lines.append(f"   Published: {pub_date}")
        if summary:
            lines.append(f"   Summary: {summary}")
        if link:
            lines.append(f"   Link: {link}")

    return "\n".join(lines)


@tool("sports")
def sports(league: str, team: str = "", date: str = "") -> str:
    """Get live or recent scores for a supported sports league using ESPN's public scoreboard API."""

    league_path = _espn_scoreboard_path(league)
    if not league_path:
        supported = ", ".join(sorted(_SUPPORTED_SPORT_LEAGUES))
        return f"Unsupported league '{league}'. Supported leagues: {supported}."

    query: dict[str, Any] = {}
    if date:
        normalized_date = _compact_whitespace(date).replace("-", "")
        if len(normalized_date) == 8 and normalized_date.isdigit():
            query["dates"] = normalized_date
        else:
            return "Please use a date in YYYY-MM-DD format."

    scoreboard_url = f"https://site.api.espn.com/apis/site/v2/sports/{league_path}/scoreboard"
    if query:
        scoreboard_url += "?" + parse.urlencode(query)

    payload, lookup_error = _safe_http_json(scoreboard_url)
    if not payload:
        return f"Sports lookup failed for {league}: {lookup_error}"

    events = payload.get("events") or []
    if not events:
        return f"No games found for {league}."

    team_filter = _compact_whitespace(team).lower()
    lines = [f"Sports scoreboard for {league.upper()}"]
    if date:
        lines[0] += f" on {date}"
    for event in events:
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        competitors = competition.get("competitors") or []
        home = next((item for item in competitors if item.get("homeAway") == "home"), {})
        away = next((item for item in competitors if item.get("homeAway") == "away"), {})
        names = " ".join(
            [
                _compact_whitespace(home.get("team", {}).get("displayName")),
                _compact_whitespace(home.get("team", {}).get("shortDisplayName")),
                _compact_whitespace(away.get("team", {}).get("displayName")),
                _compact_whitespace(away.get("team", {}).get("shortDisplayName")),
            ]
        ).lower()
        if team_filter and team_filter not in names:
            continue

        status = competition.get("status", {}).get("type", {})
        headline = event.get("shortName") or event.get("name") or "Game"
        lines.append(f"- {headline}")
        lines.append(
            "  "
            + " vs ".join(
                [
                    f"{away.get('team', {}).get('displayName', 'Away')} {away.get('score', '')}".strip(),
                    f"{home.get('team', {}).get('displayName', 'Home')} {home.get('score', '')}".strip(),
                ]
            )
        )
        lines.append(
            "  "
            + ", ".join(
                part
                for part in [
                    status.get("description"),
                    competition.get("venue", {}).get("fullName"),
                    _format_utc_timestamp(event.get("date", "")),
                ]
                if part
            )
        )

    return "\n".join(lines) if len(lines) > 1 else f"No {league} games matched the requested filters."


def build_tools():
    """
    Create the external research tools used by the Deep Research Agent.

    Tools included:
    - Tavily search
      - purpose: search the live web for current or broad information
      - important config: max_results=5
      - typical input: a natural-language search query

    - Wikipedia search
      - purpose: retrieve encyclopedia-style background knowledge
      - typical input: a natural-language topic or entity name

    - Weather lookup
      - purpose: get current weather plus a short forecast for a location

    - News search
      - purpose: get recent headlines for a topic

    - Politics search
      - purpose: get recent politics and government coverage for a topic

    - Sports scoreboard
      - purpose: get recent or live scores for supported leagues

    Returns:
        list: a list of LangChain-compatible tool objects that can be
        bound to an LLM or passed into a ToolNode.
    """

    tavily_search = TavilySearch(
        max_results=5,
        include_answer=True,
        include_raw_content=True,
        include_images=False,
        search_depth="advanced",
    )
    wikipedia_search = WikipediaQueryRun(
        api_wrapper=WikipediaAPIWrapper(top_k_results=3, doc_content_chars_max=1800)
    )

    return [tavily_search, wikipedia_search, weather, news, politics, sports]
