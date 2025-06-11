DEFAULT_SETTINGS = {
    'phoneProviders': {
        'SMSPVA': {
            'api_key': ''
        }
    },
    'captchaProviders': {
        'ANTI_CAPTCHA': {
            'api_key': '',
            'api_secret': ''
        }
    }
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}