import os

from celery import Celery
from django.conf import settings
import eventlet
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vividmind.settings")

celery_app = Celery('vividmind')
celery_app.config_from_object('django.conf:settings', namespace='CELERY')
celery_app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

celery_app.conf.beat_schedule = {
 
    'communicate_tasks_with_worker': {
        'task': 'sessionbot.tasks.communicate_tasks_with_worker',
        'schedule': crontab(minute='*/5'),
    },
 }

"""
    'automation_servers_monitor': {
        'task': 'cloud.tasks.automation_servers_monitor',
        'schedule': crontab(minute='*/5'),
    },
    'proxy_pool_monitor': {
        'task': 'login.tasks.proxy_pool_monitor',
        'schedule': crontab(minute='*/2'),
    },


    'bulkcampaign_monitor':
    {
       'task':'operationsession.tasks.bulk_campaign.bulkcampaign_monitor',
       'schedule':crontab(minute='*/60'),

    },

    'login_profile_monitor':
    {
        'task':'operationsession.tasks.bulk_campaign.process_login_profile_handler',
        'schedule':crontab(minute='*/180'),

    },

    'scrape_task_monitor':
    {
        'task':'operationsession.tasks.bulk_campaign.scrapetask_monitor',
        'schedule':crontab(minute='*/180'),

    },

    'updater_for_scraped_data_in_worker_servers':
    {
        'task':'operationsession.tasks.bulk_campaign.data_updater',
         'schedule':crontab(minute='*/180'),
        

    },
     'cache_most_requested_end_points':
    {
        'task':'operationsession.tasks.bulk_campaign.cache_most_requested_end_points',
         'schedule':crontab(minute='*/180'),
        

    }
}
 """