import random


class UserAgent:
    """
    Generate User-Agent strings.
    Format: <product> / <product-version> <comment>
    """
    PLATFORMS = ['windows', 'macos', 'linux']

    WINDOWS = [
        'Windows NT 10.0; Win64; x64;',
    ]

    MACOS = [
        'Macintosh; Intel Mac OS X 13_0',  # Ventura
        'Macintosh; Intel Mac OS X 12_6',  # Monterey
        'Macintosh; Intel Mac OS X 10_15_7',  # Catalina
    ]

    LINUX = [
        'X11; Linux x86_64;'
    ]

    BROWSERS = ['chrome', 'firefox', 'safari']

    CHROME = [
        '(%s) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36',
        '(%s) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36'
    ]

    FIREFOX = [
        '(%s; rv:106.0) Gecko/20100101 Firefox/106.0',
        '(%s; rv:105.0) Gecko/20100101 Firefox/105.0',
    ]

    SAFARI = [
        '(%s) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15',
        '(%s) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15',
    ]

    @classmethod
    def generate(cls, browser):
        if browser == 'random':
            browser = random.choice(cls.BROWSERS)

        if browser == 'chrome':
            ua = random.choice(cls.CHROME)
            platform = random.choice(cls.WINDOWS + cls.MACOS + cls.LINUX)
        elif browser == 'firefox':
            ua = random.choice(cls.FIREFOX)
            platform = random.choice(cls.WINDOWS + cls.MACOS + cls.LINUX)
        elif browser == 'safari':
            ua = random.choice(cls.SAFARI)
            platform = random.choice(cls.MACOS)
        else:
            raise RuntimeError(f'Unknown browser requested: {browser}')

        return 'Mozilla 5.0 ' + ua % platform
