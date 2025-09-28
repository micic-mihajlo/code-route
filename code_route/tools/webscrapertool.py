import re

import requests
from bs4 import BeautifulSoup, Comment

from .base import BaseTool


class WebScraperTool(BaseTool):
    name = "webscrapertool"
    description = '''
    An enhanced web scraper that fetches a web page, extracts and returns its main textual content,
    along with the page title and meta description if available. It attempts to identify the main
    article content more intelligently, remove navigational and advertising elements, and preserve
    heading structure for context. Useful for obtaining cleaner, more relevant textual information.
    '''

    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the webpage to scrape"
            }
        },
        "required": ["url"]
    }

    def execute(self, **kwargs) -> str:
        url = kwargs.get("url")

        try:
            headers = {
                'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/91.0.4472.124 Safari/537.36')
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            for elem in soup(["script", "style", "noscript", "iframe", "svg", "canvas", "object"]):
                elem.decompose()

            for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
                comment.extract()

            main_container = (
                soup.find('main') or
                soup.find('article') or
                soup.find(attrs={'id': re.compile(r'(main|content|article)', re.I)}) or
                soup.find(attrs={'class': re.compile(r'(main|content|article)', re.I)})
            )

            if not main_container:
                main_container = soup.find('body')
            if not main_container:
                main_container = soup

            for tag_name in ["nav", "footer", "aside", "form", "header"]:
                for elem in main_container.find_all(tag_name):
                    elem.decompose()

            for elem in main_container.find_all(attrs={'class': re.compile(r'(sidebar|nav|menu|ad|advert)', re.I)}):
                elem.decompose()
            for elem in main_container.find_all(attrs={'id': re.compile(r'(sidebar|nav|menu|ad|advert)', re.I)}):
                elem.decompose()

            for elem in main_container.find_all(lambda e: (e.name not in ['h1','h2','h3','h4','h5','h6','p','div','ul','ol','li','section','article','main'] and not e.get_text(strip=True))):
                elem.decompose()

            title_elem = soup.find('title')
            page_title = title_elem.get_text(strip=True) if title_elem else ''

            meta_desc = ''
            desc_tag = soup.find('meta', attrs={"name": "description"})
            if desc_tag and desc_tag.get('content'):
                meta_desc = desc_tag['content'].strip()

            block_elements = ['p','h1','h2','h3','h4','h5','h6','li','section','article','main','div']
            text_chunks = []
            for elem in main_container.find_all(block_elements):
                block_text = elem.get_text(" ", strip=True)
                if block_text:
                    text_chunks.append(block_text)

            cleaned_text = "\n\n".join(text_chunks)

            if not cleaned_text.strip():
                return "No readable content found on the webpage."

            output_parts = []
            if page_title:
                output_parts.append(f"Title: {page_title}")
            if meta_desc:
                output_parts.append(f"Description: {meta_desc}")
            output_parts.append("Content:")
            output_parts.append(cleaned_text)

            final_output = "\n\n".join(output_parts)

            return final_output

        except requests.RequestException as e:
            return f"Error scraping the webpage: {e!s}"
        except Exception as e:
            return f"An unexpected error occurred: {e!s}"
