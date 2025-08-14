# reporting_and_analytics/tasks.py
from celery import shared_task
import uuid
import datetime
import logging
from collections import defaultdict
import json

# --- Essential Django Imports for Aggregation ---
from django.db import transaction
from django.db.models import Max, Min, Sum, Avg # <--- Ensure Avg, Max, Min, Sum are imported
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.db.models import Max, Min
import logging

from .models import Task, TaskAnalysisReport, TaskSummaryReport,TaskReport,TaskSummaryReportNew

logger = logging.getLogger(__name__)

@shared_task(bind=True, default_retry_delay=60, max_retries=3)
def process_single_task_summary(self, task_uuid_str: str):
    try:
        task_instance = Task.objects.get(uuid=task_uuid_str)
        all_reports = TaskReport.objects.filter(task=task_instance).order_by('created_at')

        if not all_reports.exists():
            logger.warning(f"No reports found for task '{task_uuid_str}'.")
            return f"No reports to summarize for task {task_uuid_str}."

        # Only create summary after confirming reports exist
        summary, created = TaskSummaryReportNew.objects.get_or_create(task=task_instance)
        new_reports_qs = all_reports if created else all_reports.filter(created_at__gt=summary.updated_at)

        if not new_reports_qs.exists():
            logger.info(f"No new reports to process for task '{task_uuid_str}'.")
            return f"No new reports to process for task {task_uuid_str}."

        # === INIT FIELDS === #
        total_reports = all_reports.count()
        print(f"total report found: {total_reports}")
        critical_events = []
        total_critical_events = 0
        login_exceptions_summary = []
        login_exceptions_count = 0
        page_detection_exceptions_summary = []
        page_detection_exceptions_count = 0
        locate_element_exceptions_summary = []
        locate_element_exceptions_count = 0
        merged_page_load_details = {}

        total_login_attempts = 0
        successful_logins = 0
        failed_logins = 0
        total_login_time = 0.0
        total_2fa_attempts = 0
        total_2fa_successes = 0
        total_2fa_failures = 0
        total_2fa_time = 0.0
        total_attempt_failed = 0
        attempt_failed_errors = []
        failed_attempt_error_logs = []

        total_users_scraped = 0
        total_downloaded_files = 0
        total_storage_uploads = 0
        found_next_page_info_count = 0
        next_page_info_not_found_count = 0

        failed_downloads_details = []
        failed_to_download_file_count = 0
        storage_upload_failed = False
        task_completion_status = ""
        has_billing_exception = False
        specific_exception_reason = ""
        has_logged_in_status = False

        for report in all_reports:
            full = report.full_report or {}
            if isinstance(full, str):
                try:
                    full = json.loads(full)
                except json.JSONDecodeError:
                    continue

            total_critical_events += full.get('critical_events_count', 0)
            critical_events.extend(full.get('critical_events_summary', []))
            login_exceptions_summary.extend(full.get('login_exceptions_summary', []))
            login_exceptions_count += full.get('login_exceptions_count', 0)
            page_detection_exceptions_summary.extend(full.get('page_detection_exceptions_summary', []))
            page_detection_exceptions_count += full.get('page_detection_exceptions_count', 0)
            locate_element_exceptions_summary.extend(full.get('locate_element_exceptions_summary', []))
            locate_element_exceptions_count += full.get('locate_element_exceptions_count', 0)

            for url, details in full.get('page_load_details', {}).items():
                if url not in merged_page_load_details:
                    merged_page_load_details[url] = details
                else:
                    for key, val in details.items():
                        if isinstance(val, (int, float)):
                            merged_page_load_details[url][key] = merged_page_load_details[url].get(key, 0) + val

            if 'total_login_attempts' in full:
                total_login_attempts += full.get('total_login_attempts', 0)
                successful_logins += full.get('successful_logins', 0)
                failed_logins += full.get('failed_logins', 0)
                total_login_time += full.get('total_login_time', 0.0)
                total_2fa_attempts += full.get('2fa_attempts', 0)
                total_2fa_successes += full.get('2fa_successes', 0)
                total_2fa_failures += full.get('2fa_failures', 0)
                total_2fa_time += full.get('2fa_total_time', 0.0)
                total_attempt_failed += full.get('total_attempt_failed', 0)
                errors = full.get('attempt_failed_errors', [])
                attempt_failed_errors.extend([
                    err.get('type') for err in errors if isinstance(err, dict) and 'type' in err
                ])
                failed_attempt_error_logs.append({
                    "run_id": str(report.run_id),
                    "errors": errors,
                })

            scrape_summary = full.get('scraped_data_summary', {})
            total_users_scraped += scrape_summary.get('total_users_scraped', 0)
            total_downloaded_files += full.get('downloaded_file_count', 0)
            total_storage_uploads += full.get('storage_house_uploads', 0)
            found_next_page_info_count += full.get('found_next_page_info_count', 0)
            next_page_info_not_found_count += full.get('next_page_info_not_found_count', 0)
            failed_downloads_details.extend(full.get("failed_downloads_details", []))
            failed_to_download_file_count += full.get("failed_to_download_file_count", 0)
            storage_upload_failed |= full.get("storage_house_upload_failures", False)
            task_completion_status = full.get("task_completion_status", task_completion_status)
            has_billing_exception |= full.get("has_billing_exception", False)
            specific_exception_reason = full.get("specific_exception_reason", specific_exception_reason)
            # ✅ Track login status
            if full.get('bot_login_status_for_run') == 'Logged In':
                has_logged_in_status = True

        latest_report = all_reports.last()
        latest_full = latest_report.full_report or {}
        if isinstance(latest_full, str):
            try:
                latest_full = json.loads(latest_full)
            except json.JSONDecodeError:
                latest_full = {}

        start_ts = latest_report.report_start_datetime
        end_ts = latest_report.report_end_datetime

        # === ASSIGN SUMMARY === #
        summary.total_reports_considered = total_reports
        summary.first_report_datetime = all_reports.aggregate(Min('created_at'))['created_at__min']
        summary.last_report_datetime = all_reports.aggregate(Max('created_at'))['created_at__max']
        summary.total_critical_events = total_critical_events
        summary.critical_events_summary = critical_events
        summary.login_exceptions_summary = login_exceptions_summary
        summary.login_exceptions_count = login_exceptions_count
        summary.page_detection_exceptions_summary = page_detection_exceptions_summary
        summary.page_detection_exceptions_count = page_detection_exceptions_count
        summary.locate_element_exceptions_summary = locate_element_exceptions_summary
        summary.locate_element_exceptions_count = locate_element_exceptions_count
        summary.page_load_details = merged_page_load_details
        summary.has_next_page_info = latest_full.get('has_next_page_info')
        summary.latest_task_status = latest_full.get('status', latest_report.service or 'unknown')
        # ✅ Correct login status logic
        summary.latest_login_status = 'success' if has_logged_in_status or successful_logins > 0 else 'failed'
        summary.latest_report_start_datetime = start_ts
        summary.latest_report_end_datetime = end_ts
        summary.latest_total_task_runtime = (
            round((end_ts - start_ts).total_seconds(), 2)
            if (start_ts and end_ts) else 0.0
        )
        summary.run_id_of_latest_report = latest_report.run_id

        summary.total_login_attempts = total_login_attempts
        summary.successful_logins = successful_logins
        summary.failed_logins = failed_logins
        summary.total_login_time = total_login_time
        summary.total_2fa_attempts = total_2fa_attempts
        summary.total_2fa_successes = total_2fa_successes
        summary.total_2fa_failures = total_2fa_failures
        summary.total_2fa_time = total_2fa_time
        summary.total_attempt_failed = total_attempt_failed
        summary.attempt_failed_errors = attempt_failed_errors
        summary.failed_attempt_error_logs = failed_attempt_error_logs

        summary.total_users_scraped = total_users_scraped
        summary.total_downloaded_files = total_downloaded_files
        summary.total_storage_uploads = total_storage_uploads
        summary.found_next_page_info_count = found_next_page_info_count
        summary.next_page_info_not_found_count = next_page_info_not_found_count

        summary.failed_downloads_details = failed_downloads_details
        summary.failed_to_download_file_count = failed_to_download_file_count
        summary.storage_upload_failed = storage_upload_failed
        summary.task_completion_status = task_completion_status
        summary.has_billing_exception = has_billing_exception
        summary.specific_exception_reason = specific_exception_reason

        summary.updated_at = timezone.now()
        summary.save()

        logger.info(f"{'CREATED' if created else 'UPDATED'} TaskSummaryReport for task '{task_instance.name or task_uuid_str}'.")

        return f"Successfully processed summary for task {task_uuid_str}."

    except Exception as e:
        logger.error(f"Error processing summary for task '{task_uuid_str}': {e}", exc_info=True)
        raise self.retry(exc=e)




@shared_task(bind=True, default_retry_delay=300, max_retries=2)
def process_all_task_summaries(self):
    """
    Celery task to find all tasks that might need their summary reports updated
    and dispatches individual processing tasks for each.
    """
    logger.info("Starting process_all_task_summaries task.")

    # Get all tasks. In a production scenario, you might filter this
    # to only tasks that have new TaskAnalysisReports since their last summary update,
    # or tasks that are actively running. For simplicity, we'll iterate all.
    tasks_to_process = Task.objects.all()

    if not tasks_to_process.exists():
        logger.info("No tasks found to process summaries for.")
        return "No tasks found to process summaries for."

    for task in tasks_to_process:
        # Pass the task_uuid as a string for safety across Celery boundaries
        # This will trigger process_single_task_summary for each task
        process_single_task_summary.delay(str(task.uuid))
        logger.info(f"Dispatched summary processing for task: {task.uuid}")

    logger.info(f"Finished dispatching summaries for {tasks_to_process.count()} tasks.")
    return f"Dispatched {tasks_to_process.count()} task summary processing tasks."