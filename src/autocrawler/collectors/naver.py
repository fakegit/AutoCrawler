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
    wait_and_click,
    wait_for_manual_captcha,
)

logger = logging.getLogger(__name__)

NAVER_SEARCH_URL = "https://search.naver.com/search.naver"

# NOTE: Verified against the live Naver image search DOM on 2026-08-29 and
# confirmed end-to-end (500 links collected, downloads succeeded). The old
# selector also required the thumbnail to sit inside a
# `div.tile_item._fe_image_tab_content_tile` wrapper, which under-matched
# real results on the current layout.
_THUMBNAIL_XPATH = '//img[@class="_fe_image_tab_content_thumbnail_image"]'


def collect_naver(keyword: str, config: CrawlConfig) -> list[str]:
    driver = build_driver(
        no_gui=config.no_gui, proxy=pick_proxy(config.proxy_list), user_data_dir=config.chrome_profile_dir
    )
    try:
        face_param = face_query_param(Site.NAVER) if config.face else ""
        url = build_query_url(NAVER_SEARCH_URL, "query", keyword, where="image", sm="tab_jum") + face_param
        driver.get(url)
        time.sleep(1)
        wait_for_manual_captcha(driver, config.no_gui)

        logger.info("Scrolling down")
        body = driver.find_element(By.TAG_NAME, "body")
        for _ in range(60):
            body.send_keys(Keys.PAGE_DOWN)
            time.sleep(0.2)

        logger.info("Scraping links")
        imgs = driver.find_elements(By.XPATH, _THUMBNAIL_XPATH)

        links = []
        for img in imgs:
            src = img.get_attribute("src")
            if src and not src.startswith("d"):  # skip data: URI placeholders
                links.append(src)

        links = remove_duplicates(links)
        logger.info("Collect links done. Site: naver, Keyword: %s, Total: %d", keyword, len(links))
        return links
    finally:
        driver.quit()


def collect_naver_full(keyword: str, config: CrawlConfig) -> list[str]:
    """Full-resolution mode.

    NOTE: the image-viewer selector below has NOT been re-verified against
    Naver's current DOM (only the thumbnail-mode selector above was). See
    README "How to fix issues" if this stops returning links.
    """
    driver = build_driver(
        no_gui=config.no_gui, proxy=pick_proxy(config.proxy_list), user_data_dir=config.chrome_profile_dir
    )
    try:
        logger.info("[Full Resolution Mode]")
        face_param = face_query_param(Site.NAVER) if config.face else ""
        url = build_query_url(NAVER_SEARCH_URL, "query", keyword, where="image", sm="tab_jum") + face_param
        driver.get(url)
        time.sleep(1)
        wait_for_manual_captcha(driver, config.no_gui)

        body = driver.find_element(By.TAG_NAME, "body")
        logger.info("Scraping links")

        # Click the first image to open the full-resolution viewer.
        wait_and_click(driver, _THUMBNAIL_XPATH)
        time.sleep(1)

        links: list[str] = []
        last_scroll = 0
        patience = 0
        xpath = '//img[@class="_fe_image_viewer_image_fallback_target"]'

        while patience < 100:
            try:
                imgs = driver.find_elements(By.XPATH, xpath)
                for img in imgs:
                    highlight(driver, img)
                    src = img.get_attribute("src")
                    if src and src not in links:
                        links.append(src)
                        logger.info("%d: %s", len(links), src)
            except StaleElementReferenceException:
                pass

            scroll = get_scroll_position(driver)
            if scroll == last_scroll:
                patience += 1
            else:
                patience = 0
                last_scroll = scroll

            body.send_keys(Keys.RIGHT)

        links = remove_duplicates(links)
        logger.info("Collect links done. Site: naver_full, Keyword: %s, Total: %d", keyword, len(links))
        return links
    finally:
        driver.quit()
