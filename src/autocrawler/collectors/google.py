"""
Copyright 2018 YoongiKim

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

from __future__ import annotations

import logging
import time

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from ..config import CrawlConfig
from ..sites import Site, face_query_param
from .base import (
    build_driver,
    build_query_url,
    get_scroll_position,
    highlight,
    pick_proxy,
    remove_duplicates,
    scroll_until_stable,
    wait_and_click,
    wait_for_manual_captcha,
)

logger = logging.getLogger(__name__)

GOOGLE_SEARCH_URL = "https://www.google.com/search"

# NOTE: Verified against the live Google Images DOM on 2026-08-29 (the previous
# `//div[@jsname="dTDiAc"]/div[@jsname="qQjpJ"]//img` selector no longer matched
# anything). Thumbnails are consistently served from this CDN host, which is
# far more stable than Google's obfuscated, frequently-rotated CSS classes.
#
# `encrypted-tbn` also serves small favicon/site-icon images (e.g. for "related searches"
# chips) unrelated to search results. Google sets a real, non-empty `alt` (the source
# page's title) on actual result thumbnails and always leaves `alt=""` on these decorative
# icons - confirmed against live results: every real thumbnail was >= 259px wide with a
# non-empty alt, every icon was <= 46px wide with alt="". Filtering on `alt` here is a
# structural distinction Google makes itself, rather than an inferred size cutoff.
_THUMBNAIL_XPATH = '//img[starts-with(@src, "https://encrypted-tbn") and string-length(@alt) > 0]'


def collect_google(keyword: str, config: CrawlConfig) -> list[str]:
    driver = build_driver(
        no_gui=config.no_gui, proxy=pick_proxy(config.proxy_list), user_data_dir=config.chrome_profile_dir
    )
    try:
        face_param = face_query_param(Site.GOOGLE) if config.face else ""
        url = build_query_url(GOOGLE_SEARCH_URL, "q", keyword, source="lnms", tbm="isch") + face_param
        driver.get(url)
        time.sleep(1)
        wait_for_manual_captcha(driver, config.no_gui)

        logger.info("Scrolling down")
        scroll_until_stable(driver)

        logger.info("Scraping links")
        imgs = driver.find_elements(By.XPATH, _THUMBNAIL_XPATH)
        links = remove_duplicates([img.get_attribute("src") for img in imgs])

        logger.info("Collect links done. Site: google, Keyword: %s, Total: %d", keyword, len(links))
        return links
    finally:
        driver.quit()


def collect_google_full(keyword: str, config: CrawlConfig) -> list[str]:
    """Full-resolution mode.

    NOTE: unlike `collect_google`, these selectors have NOT been re-verified
    against Google's current DOM (see README "How to fix issues" if this
    stops returning links).
    """
    driver = build_driver(
        no_gui=config.no_gui, proxy=pick_proxy(config.proxy_list), user_data_dir=config.chrome_profile_dir
    )
    try:
        logger.info("[Full Resolution Mode]")
        face_param = face_query_param(Site.GOOGLE) if config.face else ""
        url = build_query_url(GOOGLE_SEARCH_URL, "q", keyword, tbm="isch") + face_param
        driver.get(url)
        time.sleep(1)
        wait_for_manual_captcha(driver, config.no_gui)

        # Click the first image to get full resolution images.
        wait_and_click(driver, '//div[@jsname="dTDiAc"]')
        time.sleep(1)

        body = driver.find_element(By.TAG_NAME, "body")
        logger.info("Scraping links")

        links: list[str] = []
        limit = config.limit or 10000
        last_scroll = 0
        patience = 0
        max_patience = 100
        # Google renders a compressed thumbnail first, then overlaps it with the full image.
        xpath = '//div[@jsname="figiqf"]//img[not(contains(@src,"gstatic.com"))]'

        while len(links) < limit:
            try:
                start = time.time()
                imgs = []
                while True:
                    imgs = body.find_elements(By.XPATH, xpath)
                    if imgs or time.time() - start > 5:
                        break
                    time.sleep(0.1)

                if imgs:
                    highlight(driver, imgs[0])
                    src = imgs[0].get_attribute("src")
                    if src and src not in links:
                        links.append(src)
                        logger.info("%d: %s", len(links), src)
            except KeyboardInterrupt:
                break
            except StaleElementReferenceException:
                pass

            scroll = get_scroll_position(driver)
            if scroll == last_scroll:
                patience += 1
            else:
                patience = 0
                last_scroll = scroll
            if patience >= max_patience:
                break

            body.send_keys(Keys.RIGHT)

        links = remove_duplicates(links)
        logger.info("Collect links done. Site: google_full, Keyword: %s, Total: %d", keyword, len(links))
        return links
    finally:
        driver.quit()
