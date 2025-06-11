# reporting_and_analytics/management/commands/update_task_summaries.py

import uuid
import datetime
import logging
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Avg, Max, Min, Sum
from django.db.models.functions import Coalesce

from reporting.models import Task, TaskAnalysisReport, TaskSummaryReport

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Updates or creates TaskSummaryReports for tasks based on their TaskAnalysisReports. Can process all tasks or a single specified task.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--task_uuid',
            type=str,
            help='Optional: Specify a single Task UUID to update its summary report.',
            nargs='?', # Makes the argument optional
        )

    def handle(self, *args, **options):
        task_uuid_str = options.get('task_uuid')

        if task_uuid_str:
            try:
                task_uuid = uuid.UUID(task_uuid_str)
                task_instance = Task.objects.get(uuid=task_uuid)
                self.stdout.write(self.style.SUCCESS(f"Processing summary for single Task: '{task_instance.name}' (UUID: {task_uuid_str})"))
                self._process_single_task_summary(task_instance)
            except ValueError:
                raise CommandError(f"Invalid Task UUID format: {task_uuid_str}")
            except Task.DoesNotExist:
                raise CommandError(f"Task with UUID '{task_uuid_str}' not found.")
        else:
            self.stdout.write(self.style.SUCCESS("Starting to process summaries for all tasks."))
            tasks_to_process = Task.objects.all()
            if not tasks_to_process.exists():
                self.stdout.write(self.style.WARNING("No tasks found to process summaries for."))
                return

            for task in tasks_to_process:
                self.stdout.write(f"  Attempting to process summary for Task: '{task.name}' ({task.uuid})")
                self._process_single_task_summary(task)
            self.stdout.write(self.style.SUCCESS("Finished processing summaries for all tasks."))

    def _process_single_task_summary(self, task_instance: Task):
        """
        Internal method to calculate and update/create the TaskSummaryReport for a single task.
        This mirrors the logic from the Celery task.
        """
        try:
            with transaction.atomic(): # Ensure atomicity for this task's summary update
                current_summary = TaskSummaryReport.objects.filter(task=task_instance).first()
                last_processed_datetime = current_summary.last_report_datetime if current_summary else None

                all_reports_for_task = TaskAnalysisReport.objects.filter(task=task_instance).order_by('-created_at')

                new_reports_exist = False
                if last_processed_datetime:
                    # Check if there are any reports newer than the last processed one
                    if all_reports_for_task.filter(created_at__gt=last_processed_datetime).exists():
                        new_reports_exist = True
                elif all_reports_for_task.exists():
                    # If no summary exists yet, but there are reports, then new_reports_exist is true
                    new_reports_exist = True

                if not new_reports_exist:
                    self.stdout.write(self.style.NOTICE(f"    No new TaskAnalysisReports found for task '{task_instance.name}'. Skipping update."))
                    return

                if not all_reports_for_task.exists():
                    TaskSummaryReport.objects.filter(task=task_instance).delete()
                    self.stdout.write(self.style.WARNING(f"    No TaskAnalysisReports exist for task '{task_instance.name}', summary deleted."))
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
                    average_runtime_seconds_per_run=Coalesce(Avg('total_task_runtime_seconds'), 0.0),
                    first_report_datetime=Min('created_at'),
                    last_report_datetime=Max('created_at'),
                )

                calculated_has_next_page_info = None
                if latest_report:
                    if (latest_report.found_next_page_info_count > 0 and
                        latest_report.next_page_info_not_found_count == 0):
                        calculated_has_next_page_info = True
                    else:
                        calculated_has_next_page_info = False

                aggregated_scraped_data_dict = defaultdict(lambda: 0)
                aggregated_data_enrichment_dict = defaultdict(lambda: 0)
                all_non_fatal_errors_set = set()
                all_exceptions_set = set()
                all_specific_exception_reasons_set = set()
                all_failed_downloads_summary_set = set()

                for report in all_reports_for_task:
                    # --- FIX START ---
                    if isinstance(report.scraped_data_summary, dict):
                        for key, value in report.scraped_data_summary.items():
                            if isinstance(value, (int, float)):
                                aggregated_scraped_data_dict[key] += value

                    if isinstance(report.data_enrichment_summary, dict):
                        for key, value in report.data_enrichment_summary.items():
                            if isinstance(value, (int, float)):
                                aggregated_data_enrichment_dict[key] += value
                    # --- FIX END ---

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

                        "latest_overall_task_status": latest_report.overall_task_status if latest_report else None,
                        "latest_overall_bot_login_status": latest_report.overall_bot_login_status if latest_report else None,
                        "latest_last_status_of_task": latest_report.last_status_of_task if latest_report else None,
                        "latest_billing_issue_resolution_status": latest_report.billing_issue_resolution_status if latest_report else None,
                        "latest_report_start_datetime": latest_report.report_start_datetime if latest_report else None,
                        "latest_report_end_datetime": latest_report.report_end_datetime if latest_report else None,
                        "latest_total_task_runtime_text": latest_report.total_task_runtime_text if latest_report else None,
                        "run_id_of_latest_report": latest_report.run_id if latest_report else None,

                        "latest_scraped_data_summary": latest_report.scraped_data_summary if latest_report else {},
                        "latest_data_enrichment_summary": latest_report.data_enrichment_summary if latest_report else {},

                        "aggregated_scraped_data": aggregated_scraped_data_final,
                        "aggregated_data_enrichment": aggregated_data_enrichment_final,
                        "all_non_fatal_errors": all_non_fatal_errors_list,
                        "all_exceptions": all_exceptions_list,
                        "all_specific_exception_reasons": all_specific_exception_reasons_list,
                        "all_failed_downloads_summary": all_failed_downloads_summary_list,

                        "total_reports_considered": all_reports_for_task.count(),
                        "first_report_datetime": aggregated_data['first_report_datetime'],
                        "last_report_datetime": aggregated_data['last_report_datetime'],

                        "has_next_page_info": calculated_has_next_page_info,
                    }
                )

                if created:
                    self.stdout.write(self.style.SUCCESS(f"    CREATED TaskSummaryReport for task '{task_instance.name}'."))
                else:
                    self.stdout.write(self.style.SUCCESS(f"    UPDATED TaskSummaryReport for task '{task_instance.name}'."))

        except Exception as e:
            logger.exception(f"Error processing summary for task '{task_instance.name}' (UUID: {task_instance.uuid}): {e}")
            self.stdout.write(self.style.ERROR(f"    ERROR processing summary for task '{task_instance.name}': {e}"))