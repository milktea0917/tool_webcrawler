# tool_webcrawler
An easy tool for crawling web.

# How to use
- base
  ```
  python webcrawler.py --web <website_url>
  ```
  > <website_url>: means the target we want to crawl.

- custom 1. Depth、2. Max Pages、3. Limit traffic、4. Output Json
  ```
  python webcrawler.py --web <website_url> --max-depth 2 --max-pages 30 --delay 1 --output custom.json
  ```

- custom 1. The content_link we are interested. 2. The content_link we are not interested
  ```
  python webcrawler.py --web <website_url> --include '(^|/)interested(/|$)' --exclude 'not_interested'
  ```
  >  1. The content_link we are interested： /interested/
  >  2. The content_link we are not interested： ?not_interested

- when the website are dynamic loaded or using JS
  ```
  python webcrawler.py --web https://example.com --render --headless
  ```
  > using Selenium headless
