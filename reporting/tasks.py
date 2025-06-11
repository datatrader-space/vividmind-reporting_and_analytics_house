# reporting_and_analytics/tasks.py
from celery import shared_task
import uuid
import datetime
import logging
from collections import defaultdict

# --- Essential Django Imports for Aggregation ---
from django.db import transaction
from django.db.models import Max, Min, Sum, Avg # <--- Ensure Avg, Max, Min, Sum are imported
from django.db.models.functions import Coalesce

from .models import Task, TaskAnalysisReport, TaskSummaryReport

logger = logging.getLogger(__name__)

@shared_task(bind=True, default_retry_delay=60, max_retries=3)
def process_single_task_summary(self, task_uuid_str: str):
    """
    Celery task to calculate and update/create the TaskSummaryReport for a single task.
    This task checks for new TaskAnalysisReports and re-aggregates the summary if needed.
    """
    try:
        task_uuid = uuid.UUID(task_uuid_str)
    except ValueError:
        logger.error(f"Invalid task_uuid_str provided to process_single_task_summary: {task_uuid_str}")
        return

    try:
        task_instance = Task.objects.get(uuid=task_uuid)
    except Task.DoesNotExist:
        logger.warning(f"Task with UUID {task_uuid_str} not found. Cannot process summary.")
        return

    logger.info(f"Processing summary for Task: '{task_instance.name if task_instance.name else task_instance.uuid}'")

    try:
        with transaction.atomic(): # Use atomic transaction for data consistency
            # Get the current summary state to determine the 'high-water mark'
            current_summary = TaskSummaryReport.objects.filter(task=task_instance).first()
            last_processed_datetime = current_summary.last_report_datetime if current_summary else None

            # Find new reports since the last summary update
            all_reports_for_task = TaskAnalysisReport.objects.filter(task=task_instance).order_by('-created_at')

            # Determine if new reports exist to warrant an update
            new_reports_exist = False
            if last_processed_datetime:
                if all_reports_for_task.filter(created_at__gt=last_processed_datetime).exists():
                    new_reports_exist = True
            elif all_reports_for_task.exists():
                # If no summary exists yet, but there are reports, then new_reports_exist is true
                new_reports_exist = True

            if not new_reports_exist:
                logger.info(f"No new TaskAnalysisReports found for task '{task_instance.name if task_instance.name else task_instance.uuid}'. Skipping update.")
                return

            # If no reports exist at all (e.g., all were deleted), remove the summary
            if not all_reports_for_task.exists():
                TaskSummaryReport.objects.filter(task=task_instance).delete()
                logger.info(f"No TaskAnalysisReports exist for task '{task_instance.name if task_instance.name else task_instance.uuid}', summary deleted.")
                return

            latest_report = all_reports_for_task.first() # Most recent report

            # --- Aggregation Logic ---
            aggregated_data = all_reports_for_task.aggregate(
                total_runs_initiated=Coalesce(Sum('runs_initiated'), 0),
                total_runs_completed=Coalesce(Sum('runs_completed'), 0),
                total_runs_failed_exception=Coalesce(Sum('runs_failed_exception'), 0),
                total_runs_incomplete=Coalesce(Sum('runs_incomplete'), 0),
                total_found_next_page_info_count=Coalesce(Sum('found_next_page_info_count'), 0),
                total_next_page_info_not_found_count=Coalesce(Sum('next_page_info_not_found_count'), 0),
                total_saved_file_count=Coalesce(Sum('saved_file_count'), 0),
                total_downloaded_file_count=Coalesce(Sum('downloaded_file_count'), 0),
                total_failed_download_count=Coalesce(Sum('failed_download_count'), 0),
                cumulative_total_runtime_seconds=Coalesce(Sum('total_task_runtime_seconds'), 0.0),
                average_runtime_seconds_per_run=Coalesce(Avg('total_task_runtime_seconds'), 0.0), # Fixed Avg import
                first_report_datetime=Min('created_at'),
                last_report_datetime=Max('created_at'), # This will be the new high-water mark
            )

            # Calculate has_next_page_info based on the specific new logic
            calculated_has_next_page_info = None
            if latest_report: # Ensure a latest report exists
                if (latest_report.found_next_page_info_count > 0 and
                    latest_report.next_page_info_not_found_count == 0):
                    calculated_has_next_page_info = True
                else:
                    calculated_has_next_page_info = False

            # Prepare aggregated JSON & Text Summaries (requires iteration)
            aggregated_scraped_data_dict = defaultdict(lambda: 0)
            aggregated_data_enrichment_dict = defaultdict(lambda: 0)
            all_non_fatal_errors_set = set()
            all_exceptions_set = set()
            all_specific_exception_reasons_set = set()
            all_failed_downloads_summary_set = set()

            for report in all_reports_for_task:
                # Safely iterate over JSONFields, checking if they are dictionaries
                if isinstance(report.scraped_data_summary, dict):
                    for key, value in report.scraped_data_summary.items():
                        if isinstance(value, (int, float)):
                            aggregated_scraped_data_dict[key] += value

                if isinstance(report.data_enrichment_summary, dict):
                    for key, value in report.data_enrichment_summary.items():
                        if isinstance(value, (int, float)):
                            aggregated_data_enrichment_dict[key] += value

                # Aggregate string-based summary fields, ensuring they are not None/empty strings
                if report.non_fatal_errors_summary:
                    all_non_fatal_errors_set.update(
                        msg.strip() for msg in report.non_fatal_errors_summary.split(';') if msg.strip()
                    )
                if report.exceptions_summary:
                    all_exceptions_set.update(
                        msg.strip() for msg in report.exceptions_summary.split(';') if msg.strip()
                    )
                if report.specific_exception_reasons:
                    all_specific_exception_reasons_set.update(
                        msg.strip() for msg in report.specific_exception_reasons.split(';') if msg.strip()
                    )
                if report.failed_downloads_summary:
                    all_failed_downloads_summary_set.update(
                        msg.strip() for msg in report.failed_downloads_summary.split(';') if msg.strip()
                    )

            # Convert sets to lists and defaultdicts to regular dicts for JSONField
            all_non_fatal_errors_list = list(all_non_fatal_errors_set)
            all_exceptions_list = list(all_exceptions_set)
            all_specific_exception_reasons_list = list(all_specific_exception_reasons_set)
            all_failed_downloads_summary_list = list(all_failed_downloads_summary_set)
            aggregated_scraped_data_final = dict(aggregated_scraped_data_dict)
            aggregated_data_enrichment_final = dict(aggregated_data_enrichment_dict)


            # --- Update or Create TaskSummaryReport ---
            summary_report, created = TaskSummaryReport.objects.update_or_create(
                task=task_instance,
                defaults={
                    # Aggregated Metrics
                    "total_runs_initiated": aggregated_data['total_runs_initiated'],
                    "total_runs_completed": aggregated_data['total_runs_completed'],
                    "total_runs_failed_exception": aggregated_data['total_runs_failed_exception'],
                    "total_runs_incomplete": aggregated_data['total_runs_incomplete'],
                    "total_found_next_page_info_count": aggregated_data['total_found_next_page_info_count'],
                    "total_next_page_info_not_found_count": aggregated_data['total_next_page_info_not_found_count'],
                    "total_saved_file_count": aggregated_data['total_saved_file_count'],
                    "total_downloaded_file_count": aggregated_data['total_downloaded_file_count'],
                    "total_failed_download_count": aggregated_data['total_failed_download_count'],
                    "cumulative_total_runtime_seconds": round(aggregated_data['cumulative_total_runtime_seconds'], 3),
                    "average_runtime_seconds_per_run": round(aggregated_data['average_runtime_seconds_per_run'], 3) if aggregated_data['average_runtime_seconds_per_run'] is not None else 0.0,

                    # Latest States (from latest_report)
                    "latest_overall_task_status": latest_report.overall_task_status if latest_report else None,
                    "latest_overall_bot_login_status": latest_report.overall_bot_login_status if latest_report else None,
                    "latest_last_status_of_task": latest_report.last_status_of_task if latest_report else None,
                    "latest_billing_issue_resolution_status": latest_report.billing_issue_resolution_status if latest_report else None,
                    "latest_report_start_datetime": latest_report.report_start_datetime if latest_report else None,
                    "latest_report_end_datetime": latest_report.report_end_datetime if latest_report else None,
                    "latest_total_task_runtime_text": latest_report.total_task_runtime_text if latest_report else None,
                    "run_id_of_latest_report": latest_report.run_id if latest_report else None,

                    # Specific metrics from the LAST RUN
                    "latest_scraped_data_summary": latest_report.scraped_data_summary if latest_report else {},
                    "latest_data_enrichment_summary": latest_report.data_enrichment_summary if latest_report else {},

                    # Aggregated JSON & Text Summaries
                    "aggregated_scraped_data": aggregated_scraped_data_final,
                    "aggregated_data_enrichment": aggregated_data_enrichment_final,
                    "all_non_fatal_errors": all_non_fatal_errors_list,
                    "all_exceptions": all_exceptions_list,
                    "all_specific_exception_reasons": all_specific_exception_reasons_list,
                    "all_failed_downloads_summary": all_failed_downloads_summary_list,

                    # Meta-Information about the aggregation
                    "total_reports_considered": all_reports_for_task.count(),
                    "first_report_datetime": aggregated_data['first_report_datetime'],
                    "last_report_datetime": aggregated_data['last_report_datetime'], # This is key for the next run's filter

                    # Calculated Boolean Field
                    "has_next_page_info": calculated_has_next_page_info,
                }
            )

            if created:
                logger.info(f"CREATED TaskSummaryReport for task '{task_instance.name if task_instance.name else task_instance.uuid}'.")
            else:
                logger.info(f"UPDATED TaskSummaryReport for task '{task_instance.name if task_instance.name else task_instance.uuid}'.")

        return f"Successfully processed summary for task {task_uuid_str}."

    except Exception as e:
        logger.error(f"Error processing summary for task '{task_uuid_str}': {e}", exc_info=True)
        # Allows Celery to retry the task
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