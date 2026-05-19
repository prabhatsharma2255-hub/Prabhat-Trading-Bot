"""
News Intelligence and Real-Time Sentiment Module

Data Sources:
- CryptoPanic (primary news feed)
- Fear & Greed Index
- CoinGecko Market Data
- RSS Feeds (cointelegraph, coindesk, decrypt, etc.)
- Mempool Space (on-chain data)
"""

import time
import logging
import hashlib
import re
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

try:
    import requests
except ImportError:
    print("requests not installed, installing...")
    import subprocess
    subprocess.run(['pip', 'install', 'requests'])
    import requests

try:
    import feedparser
except ImportError:
    print("feedparser not installed, installing...")
    import subprocess
    subprocess.run(['pip', 'install', 'feedparser'])
    import feedparser

import config

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    description: str
    source: str
    url: str
    published_at: datetime
    score: float = 0
    keywords: List[str] = None
    is_urgent: bool = False


class NewsEngine:
    def __init__(self):
        self.articles: List[Article] = []
        self.fear_greed_score = 50
        self.fear_greed_yesterday = 50
        self.community_sentiment = 50
        self.last_news_poll = 0
        self.last_fng_poll = 0
        self.last_coingecko_poll = 0
        self.last_rss_poll = 0
        self.last_mempool_poll = 0
        self.last_funding_poll = 0

        self.whale_event_bull = False
        self.whale_event_bear = False
        self.whale_event_expires = None

        self.black_swan_active = False
        self.black_swan_expires = None

        self.composite_sentiment = 0
        self.sentiment_label = "neutral"
        self.top_headlines: List[str] = []
        self.urgent_event = False
        self.urgent_direction = "none"

        self.funding_rate = 0
        self.funding_bias = "neutral"

        self._keyword_weights = self._build_keyword_weights()

        logger.info("NewsEngine initialized")

    def _build_keyword_weights(self) -> Dict[str, int]:
        return {
            "etf approved": 50,
            "bitcoin etf": 40,
            "sec approves": 45,
            "legal tender": 40,
            "microstrategy buys": 35,
            "saylor buys": 35,
            "nation adopts bitcoin": 40,
            "fed pivot": 35,
            "rate cut": 30,
            "blackrock bitcoin": 35,
            "institutional buy": 30,

            "bitcoin adoption": 20,
            "bullish": 15,
            "accumulation": 20,
            "all time high": 25,
            "breaking resistance": 20,
            "whale buy": 20,
            "elon bitcoin": 25,
            "elon musk btc": 25,
            "tesla bitcoin": 20,
            "paypal bitcoin": 15,
            "buy bitcoin": 15,
            "bitcoin rally": 15,
            "halving": 20,

            "sell bitcoin": -15,
            "bearish": -15,
            "bitcoin dump": -20,
            "whale sell": -20,
            "resistance": -10,
            "overbought": -15,
            "profit taking": -10,
            "bitcoin correction": -15,

            "bitcoin ban": -45,
            "sec sues": -40,
            "exchange hack": -50,
            "exchange bankrupt": -50,
            "exchange insolvent": -50,
            "government seizure": -40,
            "bitcoin illegal": -45,
            "china bans": -35,
            "binance hack": -45,
            "crypto ban": -40,
            "fed hawkish": -25,
            "rate hike": -25,
            "inflation surge": -20,
            "recession": -20,
            "war escalation": -25,
            "sanctions": -20,
        }

    def _source_credibility_multiplier(self, source: str) -> float:
        high_cred = ["cointelegraph", "coindesk", "bloomberg", "reuters", "financial times"]
        medium_cred = ["bitcoinmagazine", "decrypt", "newsbtc", "cryptonews"]

        source_lower = source.lower()
        for s in high_cred:
            if s in source_lower:
                return 1.3
        for s in medium_cred:
            if s in source_lower:
                return 1.1
        return 0.8

    def _recency_multiplier(self, published_at: datetime) -> float:
        now = datetime.now(timezone.utc)
        age_minutes = (now - published_at).total_seconds() / 60

        if age_minutes < 15:
            return 1.0
        elif age_minutes < 60:
            return 0.7
        elif age_minutes < 240:
            return 0.4
        else:
            return 0.1

    def score_article(self, title: str, description: str, source: str) -> Tuple[float, List[str], bool]:
        text = f"{title} {description}".lower()
        keywords_matched = []
        score = 0

        for keyword, weight in self._keyword_weights.items():
            if re.search(r'\b' + re.escape(keyword) + r'\b', text):
                keywords_matched.append(keyword)
                score += weight

        is_urgent = any(kw in text for kw in ["breaking", "just in", "urgent", "flash crash"])

        score *= self._source_credibility_multiplier(source)

        return score, keywords_matched, is_urgent

    def poll_cryptocompare(self) -> List[Article]:
        articles = []

        try:
            url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"

            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                news_data = data.get("Data")
                if not news_data or not isinstance(news_data, list):
                    return articles

                for item in news_data[:20]:
                    if not isinstance(item, dict):
                        continue

                    title = item.get("title", "")
                    source = item.get("source", "")
                    url = item.get("url", "")
                    body = item.get("body", "")[:200] if item.get("body") else ""

                    published_at = datetime.now(timezone.utc)
                    if "published_on" in item:
                        try:
                            published_at = datetime.fromtimestamp(int(item["published_on"]), tz=timezone.utc)
                        except:
                            pass

                    score, keywords, is_urgent = self.score_article(title, body, source)

                    article = Article(
                        title=title,
                        description=body,
                        source=source,
                        url=url,
                        published_at=published_at,
                        score=score,
                        keywords=keywords,
                        is_urgent=is_urgent
                    )
                    articles.append(article)

        except Exception as e:
            logger.error(f"CryptoCompare poll error: {e}")

        return articles

    def poll_newsapi(self) -> List[Article]:
        articles = []

        # FIXED: Use safe access to NEWSAPI_KEY
        newsapi_key = getattr(config, 'NEWSAPI_KEY', '')
        if not newsapi_key or newsapi_key == "your_key_here":
            return articles

        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": "Bitcoin OR BTC",
                "apiKey": newsapi_key,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for item in data.get("articles", [])[:20]:
                    title = item.get("title", "")
                    if not title or title == "[Removed]":
                        continue

                    source = item.get("source", {}).get("name", "unknown")
                    url = item.get("url", "")
                    description = item.get("description", "")[:200]

                    published_at = datetime.now(timezone.utc)
                    if "publishedAt" in item:
                        try:
                            published_at = datetime.fromisoformat(item["publishedAt"].replace("Z", "+00:00"))
                        except:
                            pass

                    score, keywords, is_urgent = self.score_article(title, description, source)

                    article = Article(
                        title=title,
                        description=description,
                        source=source,
                        url=url,
                        published_at=published_at,
                        score=score,
                        keywords=keywords,
                        is_urgent=is_urgent
                    )
                    articles.append(article)

        except Exception as e:
            logger.error(f"NewsAPI poll error: {e}")

        return articles

    def poll_coinmarketcap(self) -> List[Article]:
        articles = []

        try:
            url = "https://api.coinmarketcap.com/content/v1/news"
            headers = {"Accept": "application/json"}

            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for item in data.get("items", [])[:20]:
                    title = item.get("title", "")
                    source = item.get("source_name", "unknown")
                    url = item.get("url", "")
                    body = item.get("body", "")[:200]

                    published_at = datetime.now(timezone.utc)
                    if "published_at" in item:
                        try:
                            published_at = datetime.fromtimestamp(item["published_at"], tz=timezone.utc)
                        except:
                            pass

                    score, keywords, is_urgent = self.score_article(title, body, source)

                    article = Article(
                        title=title,
                        description=body,
                        source=source,
                        url=url,
                        published_at=published_at,
                        score=score,
                        keywords=keywords,
                        is_urgent=is_urgent
                    )
                    articles.append(article)

        except Exception as e:
            logger.error(f"CoinMarketCap poll error: {e}")

        return articles

    def poll_fear_greed(self) -> Tuple[int, int, str]:
        try:
            url = "https://api.alternative.me/fng/?limit=2"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    today_score = int(data["data"][0]["value"])
                    yesterday_score = int(data["data"][1]["value"])

                    trend = "flat"
                    if today_score > yesterday_score + 5:
                        trend = "rising"
                    elif today_score < yesterday_score - 5:
                        trend = "falling"

                    self.fear_greed_score = today_score
                    self.fear_greed_yesterday = yesterday_score

                    return today_score, yesterday_score, trend

        except Exception as e:
            logger.error(f"Fear & Greed poll error: {e}")

        return 50, 50, "flat"

    def poll_coingecko(self) -> int:
        try:
            url = "https://api.coingecko.com/api/v3/coins/bitcoin"
            params = {
                "localization": "false",
                "tickers": "false",
                "community_data": "true",
                "developer_data": "false"
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                sentiment = data.get("sentiment_votes_up_percentage", 50)
                self.community_sentiment = float(sentiment) if sentiment else 50
                return self.community_sentiment

        except Exception as e:
            logger.error(f"CoinGecko poll error: {e}")

        return 50

    def poll_rss_feeds(self) -> List[Article]:
        articles = []
        seen_hashes = set()

        feeds = [
            "https://cointelegraph.com/rss",
            "https://coindesk.com/arc/outboundfeeds/rss/",
            "https://decrypt.co/feed",
            "https://bitcoinmagazine.com/.rss/full/",
            "https://www.newsbtc.com/feed/"
        ]

        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:20]:
                    title = entry.get("title", "")
                    if not title:
                        continue

                    title_hash = hashlib.md5(title.encode()).hexdigest()
                    if title_hash in seen_hashes:
                        continue
                    seen_hashes.add(title_hash)

                    source = feed.feed.get("title", "unknown")
                    url = entry.get("link", "")

                    published_at = datetime.now(timezone.utc)
                    if hasattr(entry, "published"):
                        try:
                            published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                        except:
                            pass

                    score, keywords, is_urgent = self.score_article(title, "", source)

                    article = Article(
                        title=title,
                        description="",
                        source=source,
                        url=url,
                        published_at=published_at,
                        score=score,
                        keywords=keywords,
                        is_urgent=is_urgent
                    )
                    articles.append(article)

            except Exception as e:
                logger.error(f"RSS feed error ({feed_url}): {e}")

        return articles

    def poll_mempool(self) -> Dict:
        try:
            url = "https://mempool.space/api/v1/fees/recommended"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                return {
                    "fastest_fee": data.get("fastestFee", 1),
                    "halfHourFee": data.get("halfHourFee", 1),
                    "hourFee": data.get("hourFee", 1),
                    "economyFee": data.get("economyFee", 1)
                }
        except Exception as e:
            logger.error(f"Mempool poll error: {e}")

        return {}

    def get_composite_sentiment(self) -> Dict:
        news_articles = [a for a in self.articles if (datetime.now(timezone.utc) - a.published_at).total_seconds() < 7200]

        if news_articles:
            weighted_sum = sum(a.score * self._recency_multiplier(a.published_at) for a in news_articles)
            weight_total = sum(self._recency_multiplier(a.published_at) for a in news_articles)
            news_score = weighted_sum / weight_total if weight_total > 0 else 0
        else:
            news_score = 0

        fng = self.fear_greed_score
        if fng <= 20:
            fear_greed_score = -40
        elif fng <= 40:
            fear_greed_score = -20
        elif fng <= 60:
            fear_greed_score = 0
        elif fng <= 80:
            fear_greed_score = 20
        else:
            fear_greed_score = 40

        if self.community_sentiment > 65:
            community_score = 15
        elif self.community_sentiment < 35:
            community_score = -15
        else:
            community_score = 0

        self.composite_sentiment = (news_score * 0.50) + (fear_greed_score * 0.30) + (community_score * 0.20)

        if self.composite_sentiment > 40:
            self.sentiment_label = "strongly_bullish"
        elif self.composite_sentiment > 20:
            self.sentiment_label = "bullish"
        elif self.composite_sentiment > -20:
            self.sentiment_label = "neutral"
        elif self.composite_sentiment > -40:
            self.sentiment_label = "bearish"
        else:
            self.sentiment_label = "strongly_bearish"

        urgent_articles = [a for a in news_articles if a.is_urgent and (datetime.now(timezone.utc) - a.published_at).total_seconds() < 900]
        self.urgent_event = len(urgent_articles) > 0

        if self.urgent_event:
            avg_score = sum(a.score for a in urgent_articles) / len(urgent_articles)
            self.urgent_direction = "bull" if avg_score > 0 else "bear" if avg_score < 0 else "unknown"
        else:
            self.urgent_direction = "none"

        sorted_articles = sorted(news_articles, key=lambda x: x.score, reverse=True)[:3]
        self.top_headlines = [a.title[:60] + "..." if len(a.title) > 60 else a.title for a in sorted_articles]

        return {
            "composite": self.composite_sentiment,
            "sentiment_label": self.sentiment_label,
            "top_headlines": self.top_headlines,
            "urgent_event": self.urgent_event,
            "urgent_direction": self.urgent_direction,
            "fear_greed": self.fear_greed_score,
            "fear_greed_yesterday": self.fear_greed_yesterday,
            "community_sentiment": self.community_sentiment
        }

    def check_whale_events(self):
        recent_articles = [a for a in self.articles if (datetime.now(timezone.utc) - a.published_at).total_seconds() < 900]

        whale_keywords = ["elon", "musk", "saylor", "microstrategy", "blackrock", "fidelity bitcoin", "ark bitcoin"]

        for article in recent_articles:
            text = article.title.lower()
            if any(kw in text for kw in whale_keywords):
                if article.score > 25:
                    self.whale_event_bull = True
                    self.whale_event_expires = time.time() + (config.WHALE_EVENT_EXPIRY_HRS * 3600)
                elif article.score < -25:
                    self.whale_event_bear = True
                    self.whale_event_expires = time.time() + (config.WHALE_EVENT_EXPIRY_HRS * 3600)

        if self.whale_event_expires and time.time() > self.whale_event_expires:
            self.whale_event_bull = False
            self.whale_event_bear = False
            self.whale_event_expires = None

    def check_black_swan(self) -> bool:
        keywords = ["hack", "hacked", "exploit", "insolvent", "bankrupt", "frozen", "suspended withdrawals", "rug pull", "exit scam"]

        recent_articles = [a for a in self.articles if (datetime.now(timezone.utc) - a.published_at).total_seconds() < 1800]

        for article in recent_articles:
            text = (article.title + " " + article.description).lower()
            if any(kw in text for kw in keywords):
                if not self.black_swan_active:
                    self.black_swan_active = True
                    self.black_swan_expires = time.time() + (config.BLACK_SWAN_SUSPEND_HRS * 3600)
                    logger.warning(f"BLACK SWAN DETECTED: {article.title}")
                    return True

        if self.black_swan_expires and time.time() > self.black_swan_expires:
            self.black_swan_active = False
            self.black_swan_expires = None

        return False

    def get_sentiment_modifier(self, direction: str) -> Tuple[float, float, bool]:
        risk_multiplier = 1.0
        leverage_boost = 0
        blocked = False

        if direction == "LONG":
            if self.composite_sentiment > config.SENTIMENT_BOOST_THRESHOLD:
                leverage_boost = 1
            elif self.composite_sentiment < config.SENTIMENT_BLOCK_LONG:
                blocked = True
            elif self.composite_sentiment < -20:
                risk_multiplier = 0.7

        elif direction == "SHORT":
            if self.composite_sentiment < -config.SENTIMENT_BOOST_THRESHOLD:
                leverage_boost = 1
            elif self.composite_sentiment > config.SENTIMENT_BLOCK_SHORT:
                blocked = True
            elif self.composite_sentiment > 20:
                risk_multiplier = 0.7

        if self.fear_greed_score < config.FNG_EXTREME_FEAR and direction == "LONG":
            leverage_boost += 1
        elif self.fear_greed_score > config.FNG_EXTREME_GREED and direction == "SHORT":
            leverage_boost += 1
        elif self.fear_greed_score > config.FNG_EXTREME_GREED and direction == "LONG":
            risk_multiplier = 0.6

        if self.whale_event_bull and direction == "LONG":
            leverage_boost += 1
            risk_multiplier = 1.2
        elif self.whale_event_bull and direction == "SHORT":
            blocked = True
        elif self.whale_event_bear and direction == "SHORT":
            leverage_boost += 1
            risk_multiplier = 1.2
        elif self.whale_event_bear and direction == "LONG":
            blocked = True

        return risk_multiplier, leverage_boost, blocked

    def poll_all(self):
        now = time.time()

        if now - self.last_news_poll > config.NEWS_POLL_INTERVAL_MIN * 60:
            articles = []

            cc_articles = self.poll_cryptocompare()
            articles.extend(cc_articles)

            newsapi_articles = self.poll_newsapi()
            articles.extend(newsapi_articles)

            cmc_articles = self.poll_coinmarketcap()
            articles.extend(cmc_articles)

            if articles:
                self.articles.extend(articles)
                self.articles = self.articles[-100:]

            self.last_news_poll = now

        if now - self.last_rss_poll > config.RSS_POLL_INTERVAL_MIN * 60:
            rss_articles = self.poll_rss_feeds()
            if rss_articles:
                self.articles.extend(rss_articles)
                self.articles = self.articles[-100:]
            self.last_rss_poll = now

        if now - self.last_fng_poll > config.FNG_POLL_INTERVAL_MIN * 60:
            self.poll_fear_greed()
            self.last_fng_poll = now

        if now - self.last_coingecko_poll > config.COINGECKO_POLL_MIN * 60:
            self.poll_coingecko()
            self.last_coingecko_poll = now

        self.check_whale_events()
        self.get_composite_sentiment()

    def warm_up(self):
        logger.info("Warming up NewsEngine...")

        articles = []
        articles.extend(self.poll_cryptocompare())
        articles.extend(self.poll_rss_feeds())
        articles.extend(self.poll_coinmarketcap())

        if articles:
            self.articles.extend(articles)
            self.articles = self.articles[-100:]

        self.poll_fear_greed()
        self.poll_coingecko()

        self.get_composite_sentiment()

        logger.info(f"News warm - Sentiment: {self.sentiment_label} ({self.composite_sentiment:.1f}) | F&G: {self.fear_greed_score}")
