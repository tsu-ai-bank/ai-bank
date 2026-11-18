import logging
import socket
import ipaddress
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

__all__ = ["BaseParser", "RobotsDisallowedError"]

logger = logging.getLogger(__name__)


class RobotsDisallowedError(Exception):
    """robots.txt запрещает запрос этого URL для нашего User-Agent."""


class BaseParser:
    """Общее для всех парсеров: HTTP-политика, robots.txt, фильтр текста.

    Потомок обязан определить:
      * collect()          - ходить в сеть только через self.fetch(), вернуть текст;
      * extract_metadata() - заполнить title, description, publication_date
                             из полученных данных (теги HTML, поля JSON, ...).
    Остальное делает база: run() фильтрует текст, is_fresh() говорит, нужен ли
    документ, save() отдаёт его дальше.
    """
    USER_AGENT = "TsuIndustryParser/1.0 (+https://industry-tasks.tsu.ru/; bot@example.org)"
    TIMEOUT = (5, 20)          # (соединение, чтение) секунды
    REQUEST_DELAY = 1.0        # минимальная пауза между запросами к одному хосту, секунды
    DELAY_JITTER = 0.3         # случайная добавка, чтобы запросы не шли с одинаковыми промежутками
    RESPECT_ROBOTS = True

    MAX_REDIRECTS = 5
    RETRY_ATTEMPTS = 3                              # всего попыток на один URL
    RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
    RETRY_BACKOFF = 2.0                             # базовое время ожидания между попытками
    MAX_RETRY_WAIT = 60.0                           
    MAX_CRAWL_DELAY = 60.0                     
    ROBOTS_TTL = 24 * 3600                         
    ROBOTS_ERROR_TTL = 5 * 60  
                         # 5xx / сетевая ошибка: повторить позже
    MAX_BYTES = 5 * 1024 * 1024        # лимит тела ответа после распаковки, байты    ROBOTS_MAX_BYTES = 512 * 1024      # лимит для robots.txt    MAX_DOWNLOAD_TIME = 60.0           # общий лимит чтения тела, секунды
    ROBOTS_MAX_BYTES = 512 * 1024      # лимит для robots.txt
    MAX_DOWNLOAD_TIME = 60.0           # общий лимит чтения тела, секунды
    MAX_AGE_DAYS = 60          # старше - старая публикация; нет даты - считается свежей
    
    EMAIL_MASK = "[EMAIL]"
    PHONE_MASK = "[PHONE]"

    _CONTROL_RE = re.compile(r"[\x00-\x08\x0e-\x1b\x7f\U000000ad\U0000200b-\U0000200f\U0000202a-\U0000202e\U00002060\U00002066-\U00002069"  r"\U0000feff\U0000fffd\U000e0000-\U000e007f" r"\ue000-\uf8ff]")
    _SPACES_RE = re.compile(r"[\U000000a0\U00001680\U00002000-\U0000200a\U0000202f\U0000205f\U00003000]")
    _EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)
    _EMAIL_OBFUSCATED_RE = re.compile(
        r"(?<![\w.+-])[\w.+-]+\s*[\[(]\s*(?:at|собака)\s*[\])]\s*"
        r"[\w-]+(?:\s*(?:\.|[\[(]\s*(?:dot|точка)\s*[\])])\s*[\w-]+)+",
        re.I,
    )
    # телефон-кандидат: необязательные +/00, цифры через пробел . - ( )
    _PHONE_RE = re.compile(        r"(?<![\w.])(?:\+|00)?\d(?:(?:[ \t\U000000a0()\U00002010-\U00002015-]|\.(?=\d)){0,2}\d){6,}(?!\w)"    )
    # городской номер без кода: 123-45-67 (3-2-2 цифры, разделители обязательны)
    _LOCAL_PHONE_RE = re.compile(        r"(?<![\w.,-])(?<!\d )\d{3}[-\U00002010-\U00002015 ]\d{2}[-\U00002010-\U00002015 ]\d{2}(?![\w-]|[.,]\d| \d)"    )
    # дата внутри телефоноподобного совпадения (2024-01-15 12:30, 15.01.2024 12:30)
    _DATE_INSIDE_RE = re.compile(
        r"(?<!\d)(?:\d{4}[-.]\d{2}[-.]\d{2}|\d{2}[-.]\d{2}[-.]\d{4})(?!\d)"
    )
    # число сразу после этих слов - идентификатор, а не телефон
    _ID_CONTEXT_RE = re.compile(
        r"(?:инн|огрнип|огрн|кпп|окпо|окато|октмо|бик)[^0-9]{0,6}$", re.I
    )
    # число из одних цифр всё же телефон: РФ-мобильный 7/8 + 10 цифр, 9XXXXXXXXX, 00 + номер
    _BARE_PHONE_RE = re.compile(r"^(?:[78]\d{10}|9\d{9}|00\d{10,13})$")
    # сумма с разрядами «1 250 000 000»: не телефон
    _PRICE_RE = re.compile(r"\d{1,3}(?: \d{3}){3,}")
    _RU_MONTHS = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
        "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11,
        "декабря": 12,
    }
    _RU_DATE_RE = re.compile(
        r"(\d{1,2})\s+(" + "|".join(_RU_MONTHS) + r")\s+(\d{4})(?:\D+(\d{1,2}):(\d{2}))?",
        re.I,
    )

    # состояние, общее для ВСЕХ парсеров процесса
    _lock = threading.Lock()
    _last_request: dict[str, float] = {}
    # ключ -> (правила, crawl_delay, срок годности по монотонным часам)
    _robots_cache: dict[str, tuple[RobotFileParser, Optional[float], float]] = {}

     # свойства, нужные любому потомку: ОБЪЯВЛЕНЫ, не определены.
    title: Optional[str]                    # тег <title> / поле заголовка
    description: Optional[str]              # тег description / поле краткого описания
    publication_date: Optional[datetime]    # с таймзоной или None
    text: str                               # определяет run()

    def __init__(
        self,
        url: str,
        organization: str,
        *,
        user_agent: Optional[str] = None,
        timeout=None,
        delay: Optional[float] = None,
        respect_robots: Optional[bool] = None,
        session: Optional[requests.Session] = None,
    ):
        self._url = url
        self._organization = organization
        self.user_agent = user_agent or self.USER_AGENT
        self.timeout = self.TIMEOUT if timeout is None else timeout
        self.delay = self.REQUEST_DELAY if delay is None else delay
        self.respect_robots = (
            self.RESPECT_ROBOTS if respect_robots is None else respect_robots
        )
        self._own_session = session is None
        self._session = requests.Session() if session is None else session
        self._session.headers["User-Agent"] = self.user_agent  # setdefault оставил бы "python-requests"
        self.text = ""

    @property
    def organization(self) -> str:
        return self._organization

    @property
    def url(self) -> str:
        return self._url

    @property
    def domain(self) -> str:
        """Хост из url в нижнем регистре (выводится из url, разойтись с ним не может)."""
        return (urlparse(self._url).hostname or "").lower()

    def close(self) -> None:
        def close(self) -> None:
            if self._own_session:            
                self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # только объявлены: у потомков (HTML, API) логика разная
    def collect(self) -> str:
        """Сбор текста. Вызывать extract_metadata(). Только через self.fetch()."""
        raise NotImplementedError("collect() must be defined by the child class")

    def extract_metadata(self, payload) -> None:
        """Заполнить self.title, self.description, self.publication_date до очистки от HTML."""
        raise NotImplementedError("extract_metadata() must be defined by the child class")

    def fix_encoding(self, resp) -> None:
        """Определяем кодировку, если она не указана"""
        content_type = resp.headers.get("Content-Type", "").lower()
        if (resp.encoding or "").lower() == "iso-8859-1" and "charset" not in content_type:
            resp.encoding = resp.apparent_encoding

    def parse_retry_after(self, value) -> Optional[float]:
        """Сколько секунд ждать перед повтором (заголовок Retry-After: секунды или дата)."""
        if not value:
            return None
        value = value.strip()
        if value.isascii() and value.isdigit():      
            return float(value)
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:                     # например, "-0000": считаем UTC
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    @staticmethod
    def _origin(url: str) -> tuple:
        """(схема, хост, порт): креды привязываем к нему, а не к netloc."""
        p = urlparse(url)
        return p.scheme, (p.hostname or "").lower(), p.port or (443 if p.scheme == "https" else 80)

    @staticmethod
    def _safe_url(url: str) -> str:
        """URL без query и fragment для логов и исключений (в query бывают ключи)."""
        return url.split("#", 1)[0].split("?", 1)[0]

    def _check_public(self, url: str) -> None:
        """Только http(s) и только публичные адреса: без localhost, частных сетей, 169.254.169.254."""
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise ValueError(f"unsupported URL: {self._safe_url(url)}")
        port = p.port or (443 if p.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(p.hostname, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise requests.ConnectionError(f"DNS lookup failed for {p.hostname}") from exc
        for info in infos:
            if not ipaddress.ip_address(info[4][0]).is_global:
                raise ValueError(f"non-public address for {p.hostname}")

    def _read_limited(self, resp, limit: Optional[int] = None) -> None:
        """Прочитать тело потоком: не больше `limit` байт (после распаковки) и не дольше MAX_DOWNLOAD_TIME."""
        limit = limit or self.MAX_BYTES
        declared = resp.headers.get("Content-Length", "")
        if declared.isascii() and declared.isdigit() and int(declared) > limit:
            resp.close()
            raise ValueError("response too large")
        deadline = time.monotonic() + self.MAX_DOWNLOAD_TIME
        chunks, size = [], 0
        for chunk in resp.iter_content(65536):
            size += len(chunk)
            if size > limit or time.monotonic() > deadline:
                resp.close()
                raise ValueError("response too large or too slow")
            chunks.append(chunk)
        resp._content = b"".join(chunks)

    def _robots_for(self, url: str) -> tuple[RobotFileParser, Optional[float]]:
        """Разобрать robots.txt по URL с кэшем (TTL: сутки, при ошибке - 5 минут).
        Если получить не удалось - запрещаем всё."""
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        key = f"{origin}|{self.user_agent}"         # правила зависят от имени бота

        with self._lock:
            cached = self._robots_cache.get(key)
        if cached and cached[2] > time.monotonic():
            return cached[0], cached[1]

        rp = RobotFileParser()
        robots_url = f"{origin}/robots.txt"
        ttl = self.ROBOTS_TTL
        try:
            resp = self._download_robots(robots_url)
            try:
                code = resp.status_code
                if code == 200:
                    self.fix_encoding(resp)
                    rp.parse(resp.text.splitlines())
                elif code in (401, 403):
                    rp.disallow_all = True
                elif code in (408, 429) or code >= 500:
                    rp.disallow_all = True               # временная ошибка: не «разрешено всё» на сутки
                    ttl = self.ROBOTS_ERROR_TTL
                elif 400 <= code < 500:
                    rp.allow_all = True                  # файла нет - разрешено всё
                else:
                    rp.disallow_all = True               
                    ttl = self.ROBOTS_ERROR_TTL
            finally:
                resp.close()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("robots.txt unavailable for %s: %s", origin, exc)
            rp.disallow_all = True                       # проверить не можем - не ходим
            ttl = self.ROBOTS_ERROR_TTL

        crawl_delay = rp.crawl_delay(self.user_agent)
        crawl_delay = float(crawl_delay) if crawl_delay else None
        with self._lock:
            self._robots_cache[key] = (rp, crawl_delay, time.monotonic() + ttl)
        return rp, crawl_delay

    def _download_robots(self, robots_url: str) -> requests.Response:
        """robots.txt: проверка публичного IP, редиректы вручную, тело ограничено ROBOTS_MAX_BYTES."""
        url = robots_url
        for _ in range(self.MAX_REDIRECTS + 1):
            self._check_public(url)
            resp = self._session.get(url, timeout=self.timeout, allow_redirects=False, stream=True)
            if not resp.is_redirect:
                if resp.status_code == 200:
                    self._read_limited(resp, self.ROBOTS_MAX_BYTES)
                return resp
            resp.close()
            url = urljoin(url, resp.headers["Location"])
        raise requests.TooManyRedirects(f"more than {self.MAX_REDIRECTS} redirects for robots.txt")    
    def can_fetch(self, url: Optional[str] = None) -> bool:
        """Разрешён ли URL для User-Agent?"""
        url = url or self._url
        if not self.respect_robots:
            return True
        rp, _ = self._robots_for(url)
        return rp.can_fetch(self.user_agent, url)

    def _wait_for_slot(self, url: str, crawl_delay: Optional[float]) -> None:
        """Выдержать паузу не меньше `delay` между запросами к одному хосту
        (Crawl-delay из robots.txt главнее, если он больше). Общая для всех парсеров процесса."""
        host = urlparse(url).netloc.lower()
        pause = max(self.delay, min(crawl_delay or 0.0, self.MAX_CRAWL_DELAY))   
        while True:
            with self._lock:
                now = time.monotonic()
                wait = self._last_request.get(host, 0.0) + pause - now
                if wait <= 0:
                    self._last_request[host] = now   # слот занят под замком
                    break
            time.sleep(wait + random.uniform(0, self.DELAY_JITTER))   # спим вне замка

    def _retry_wait(self, attempt: int, resp=None) -> Optional[float]:
        """Секунды до следующей попытки; None - не повторять."""
        wait = self.parse_retry_after(resp.headers.get("Retry-After")) if resp is not None else None
        if wait is None:
            wait = self.RETRY_BACKOFF * 2 ** (attempt - 1) + random.uniform(0, 1)
        return None if wait > self.MAX_RETRY_WAIT else wait

    def _get_once(self, url: str, **kwargs) -> requests.Response:
        """Один запрос без редиректов: robots.txt, паузы, повторы при сетевых ошибках и 429/5xx."""
        crawl_delay = None
        if self.respect_robots:
            rp, crawl_delay = self._robots_for(url)
            if not rp.can_fetch(self.user_agent, url):
                raise RobotsDisallowedError(f"robots.txt disallows {self._safe_url(url)}")

        for attempt in range(1, self.RETRY_ATTEMPTS + 1):
            self._wait_for_slot(url, crawl_delay)    # каждая попытка выдерживает паузу
            last = attempt == self.RETRY_ATTEMPTS
            try:
                resp = self._session.get(url, allow_redirects=False, stream=True, **kwargs)
            except requests.exceptions.SSLError:
                raise                               
            except (requests.ConnectionError, requests.Timeout) as exc:
                wait = None if last else self._retry_wait(attempt)
                if wait is None:
                    raise
                logger.warning("%s: %s; retry in %.1fs", self._safe_url(url), type(exc).__name__, wait)
                time.sleep(wait)
                continue

            if resp.status_code in self.RETRY_STATUSES and not last:
                wait = self._retry_wait(attempt, resp)
                if wait is not None:
                    logger.warning("%s: HTTP %s; retry in %.1fs", self._safe_url(url), resp.status_code, wait)
                    resp.close()
                    time.sleep(wait)
                    continue
            return resp      # успех, фатальная ошибка или попытки кончились

        raise RuntimeError("unreachable")            
    def fetch(self, url: Optional[str] = None, **kwargs) -> requests.Response:
        """GET с robots.txt, ограничением частоты, User-Agent, таймаутами, повторами и редиректами
        (robots.txt и пауза - на каждом шаге). Креды - только через kwargs (`headers=`, `params=`),
        не в URL; при редиректе на другой origin (схема, хост, порт) не передаются.
        Адрес должен быть публичным; тело читается с лимитом MAX_BYTES.
        Бросает RobotsDisallowedError, requests.HTTPError (4xx/5xx после повторов),
        requests.TooManyRedirects, ValueError (непубличный адрес, большой ответ)."""
        url = url or self._url
        kwargs.setdefault("timeout", self.timeout)
        kwargs.pop("allow_redirects", None)          # редиректы обрабатываем сами
        first_origin = self._origin(url)
        for _ in range(self.MAX_REDIRECTS + 1):
            self._check_public(url)
            resp = self._get_once(url, **kwargs)
            if not resp.is_redirect:
                if 300 <= resp.status_code < 400:    # 3xx без Location (например, 304): не успех
                    resp.close()
                    raise requests.HTTPError(f"unexpected HTTP {resp.status_code}", response=resp)
                try:
                    resp.raise_for_status()
                except requests.HTTPError:
                    resp.close()                     # при stream=True иначе соединение остаётся занятым
                    raise
                self._read_limited(resp)
                self.fix_encoding(resp)
                return resp
            resp.close()
            url = urljoin(url, resp.headers["Location"])
            if urlparse(url).scheme not in ("http", "https"):
                raise requests.exceptions.InvalidURL(f"redirect to unsupported URL: {self._safe_url(url)}")
            kwargs.pop("params", None)               # Location уже содержит полный адрес
            if self._origin(url) != first_origin:
                for name in ("headers", "auth", "cookies"):   # ключи на чужой origin не отдаём
                    kwargs.pop(name, None)
        raise requests.TooManyRedirects(f"more than {self.MAX_REDIRECTS} redirects")
   
    # фильтр текста. HTML теги убирать до вызова run()
  
    def remove_control_chars(self, text: str) -> str:
        """Убрать control/zero-width/bidi/soft-hyphen; нестандартные пробелы -> обычный пробел."""        
        return self._SPACES_RE.sub(" ", self._CONTROL_RE.sub("", text))

    def _mask_phone(self, m) -> str:
        """Решить по одному совпадению: маскировать или оставить (даты, ИНН/ОГРН, метки времени, номера заказов остаются)."""
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if not 10 <= len(digits) <= 15 or self._DATE_INSIDE_RE.search(raw) or self._PRICE_RE.fullmatch(raw):
            return raw
        before = m.string[max(0, m.start() - 15):m.start()]
        if self._ID_CONTEXT_RE.search(before):
            return raw
        if raw.isdigit() and not self._BARE_PHONE_RE.match(digits):
            return raw
        return self.PHONE_MASK

    def mask_personal_data(self, text: str) -> str:
        """E-mail (в т.ч. 'a [at] b [dot] ru') -> [EMAIL], телефоны -> [PHONE]."""
        text = text.replace("\x00", "")      # \x00 ниже служит меткой
        dates: list[str] = []

        def keep(m) -> str:
            dates.append(m.group(0))
            return f"\x00{len(dates) - 1}\x00"

        text = self._EMAIL_OBFUSCATED_RE.sub(self.EMAIL_MASK, text)
        text = self._EMAIL_RE.sub(self.EMAIL_MASK, text)
        text = self._DATE_INSIDE_RE.sub(keep, text)      # даты прячем: иначе они склеиваются с соседним номером
        text = self._PHONE_RE.sub(self._mask_phone, text)
        text = self._LOCAL_PHONE_RE.sub(self.PHONE_MASK, text)
        return re.sub(r"\x00(\d+)\x00", lambda m: dates[int(m.group(1))], text)

    def clean_text(self, text: Optional[str]) -> str:
        """Базовый фильтр перед сохранением: control-символы, маска ПД, пробелы -> одиночные."""
        if not text:
            return ""
        text = self.remove_control_chars(text)
        text = self.mask_personal_data(text)     # до схлопывания пробелов: в телефонах бывают пробелы
        return re.sub(r"\s+", " ", text).strip()

    def clean_field(self, value: Optional[str]) -> Optional[str]:
        """clean_text для коротких полей (title, description); None, если пусто."""
        return self.clean_text(value) or None

    # даты
    def parse_date(self, value) -> Optional[datetime]:
        """Строка -> datetime с таймзоной или None.

        Понимает ISO 8601, RFC 2822, dd.mm.yyyy и «8 ноября 2026 12:30».
        Без таймзоны - считаем UTC; будущее (дальше суток) и даты до 1990 отбрасываются"""
        if not value:
            return None
        if isinstance(value, float) and abs(value) < 1e15:            
            value = int(value)                               
        value = " ".join(str(value).split())
        dt = None
        try:                                                    
            dt = datetime.fromisoformat(value)
        except ValueError:
            pass
        if dt is None and value.isascii() and value.isdigit() and len(value) in (10, 13):
            try:                                             
                dt = datetime.fromtimestamp(int(value) / (1000 if len(value) == 13 else 1), timezone.utc)
            except (OverflowError, OSError, ValueError):
                dt = None
        if dt is None:                                          # RFC 2822
            try:
                dt = parsedate_to_datetime(value)
            except (TypeError, ValueError, IndexError):
                pass
        if dt is None:                                          # «8 ноября 2026 12:30»
            m = self._RU_DATE_RE.search(value)
            if m:
                try:
                    dt = datetime(
                        int(m.group(3)), self._RU_MONTHS[m.group(2).lower()],
                        int(m.group(1)), int(m.group(4) or 0), int(m.group(5) or 0),
                    )
                except ValueError:
                    dt = None
        if dt is None:                                          
            for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%d/%m/%Y"):
                try:
                    dt = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt > datetime.now(timezone.utc) + timedelta(days=1) or dt.year < 1990:
            return None
        return dt

    def is_recent(self, published: Optional[datetime], max_age_days: int) -> bool:
        """Не старше max_age_days. Нет даты -> True."""
        if published is None:
            return True
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - published <= timedelta(days=max_age_days)

    def is_fresh(self, max_age_days: Optional[int] = None) -> bool:
        """Документ не старше MAX_AGE_DAYS (60) или max_age_days. Нет даты -> True."""
        limit = self.MAX_AGE_DAYS if max_age_days is None else max_age_days
        return self.is_recent(getattr(self, "publication_date", None), limit)

    # конвейер
    def run(self) -> str:
        """collect -> фильтр. Фильтр здесь, чтобы потомок не забыл: text, title, description."""
        self.text = self.clean_text(self.collect())
        self.title = self.clean_field(getattr(self, "title", None))
        self.description = self.clean_field(getattr(self, "description", None))
        pd = getattr(self, "publication_date", None)        
        self.publication_date = pd if pd is None or isinstance(pd, datetime) else self.parse_date(pd)
        return self.text

    def to_dict(self) -> dict:
        """7 полей для следующего этапа: organization, url, domain, title, description, publication_date, text."""
        return {
            "organization": self.organization,
            "url": self.url,
            "domain": self.domain,
            "title": getattr(self, "title", None),
            "description": getattr(self, "description", None),
            "publication_date": getattr(self, "publication_date", None),
            "text": self.text,
        }

    def save(self, documents: Optional[list[dict]] = None) -> None:
        """Отдать данные дальше через save_raw_documents"""
        from storage import save_raw_documents  # TODO: реальный путь модуля

        save_raw_documents(documents if documents is not None else [self.to_dict()])
