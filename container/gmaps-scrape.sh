#!/bin/sh
# Wrapper for the baked-in google-maps-scraper: points Playwright at the bundled
# driver/browsers, then passes all arguments through.
export PLAYWRIGHT_BROWSERS_PATH=/opt/gmaps/browsers
export PLAYWRIGHT_DRIVER_PATH=/opt/gmaps/driver
unset PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
exec google-maps-scraper "$@"
