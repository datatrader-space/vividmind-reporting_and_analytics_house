# reporting_and_analytics/management/commands/run_alert_check_sync.py

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings
import datetime
import json
import logging

# Import models from the 'reporting' app
from reporting.models import TaskSummaryReport, TaskAnalysisReport, Task
from reporting.slack_utils import send_structured_slack_message

logger = logging.getLogger(__name__)

# Configuration for Alert Throttling (no longer directly used for deduplication, but kept for context)
ALERT_COOLDOWN_PERIOD_HOURS = 6

class Command(BaseCommand):
    help = 'Runs the alert checking logic synchronously, bypassing Celery worker, with deduplication disabled.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--task_uuid',
            type=str,
            help='Optional: Filter for a specific Task UUID to check alerts for.',
            default=None
        )
        parser.add_argument(
            '--force-alert',
            action='store_true',
            help='This flag now only applies if you re-enable deduplication in the future. Currently, all alerts are forced.',
        )

    def handle(self, *args, **kwargs):
        task_uuid_filter = kwargs.get('task_uuid')
        force_alert = kwargs.get('force_alert') # This flag is now redundant for its original purpose

        self.stdout.write(f"Starting synchronous alert check (Deduplication disabled)...")
        if task_uuid_filter:
            self.stdout.write(f"Filtering for Task UUID: {task_uuid_filter}")

        # Define the time window for recently updated summaries (last 24 hours)
        recent_update_threshold = timezone.now() - datetime.timedelta(hours=24)

        # Query for TaskSummaryReports, optionally filtered by task_uuid
        if task_uuid_filter:
            try:
                task = Task.objects.get(uuid=task_uuid_filter)
                reports_to_check = TaskSummaryReport.objects.filter(
                    task=task,
                    updated_at__gte=recent_update_threshold
                ).select_related('task')
            except Task.DoesNotExist:
                raise CommandError(f"Task with UUID '{task_uuid_filter}' does not exist.")
        else:
            reports_to_check = TaskSummaryReport.objects.filter(
                updated_at__gte=recent_update_threshold
            ).select_related('task')

        if not reports_to_check.exists():
            self.stdout.write(self.style.WARNING("No recently updated TaskSummaryReports found to check."))
            return

        for report_summary in reports_to_check:
            self.stdout.write(f"\n--- Checking Task: {report_summary.task.name or report_summary.task.uuid} (Summary ID: {report_summary.pk}) ---")

            should_alert_dev = False
            should_alert_client = False
            should_alert_manager = False

            dev_reasons = []
            client_performance_metrics = [] # New list for client performance metrics
            client_issue_reasons = []       # New list for client issue reasons
            manager_reasons = []

            dev_details = []

            # --- 1. Check Bot Login Status from TaskSummaryReport ---
            if report_summary.latest_overall_bot_login_status == 'Logged Out':
                should_alert_dev = True
                should_alert_client = True # Client needs to know about bot issues
                should_alert_manager = True
                dev_reasons.append("Bot Login Status: *Logged Out*")
                manager_reasons.append(f"Bot Login Failure for task: *{report_summary.task.name or report_summary.task.uuid}*")
                client_issue_reasons.append(f"Bot Status: Your *Bot for '{report_summary.task.name or 'Unnamed Task'}'* is currently *Logged Out*.")
                dev_details.append(f"Bot for Task `{report_summary.task.name or report_summary.task.uuid}` reported being logged out.")
                self.stdout.write(self.style.WARNING("  [Condition Met] Bot Login Status: Logged Out"))

            # --- 2. Check Task Status from TaskSummaryReport (latest overall status) ---
            if report_summary.latest_overall_task_status not in ['Completed', 'Running', 'Initiated', 'Idle']:
                should_alert_dev = True
                should_alert_client = True
                dev_reasons.append(f"Overall Task Status: *{report_summary.latest_overall_task_status}*")
                client_issue_reasons.append(f"Task Status: Task *'{report_summary.task.name or 'Unnamed Task'}'* has an unusual status: *{report_summary.latest_overall_task_status}*.")
                dev_details.append(f"Task Summary indicates status: `{report_summary.latest_overall_task_status}`.")
                self.stdout.write(self.style.WARNING(f"  [Condition Met] Overall Task Status: {report_summary.latest_overall_task_status}"))


            # --- 3. Check for Exceptions/Errors from TaskSummaryReport (aggregated lists) ---
            actual_exceptions = [e for e in report_summary.all_exceptions if e and "No exceptions across all runs" not in e and "N/A" not in e]
            if actual_exceptions:
                should_alert_dev = True
                should_alert_manager = True
                should_alert_client = True # Client should know about critical, unresolved issues
                dev_reasons.append("Aggregated Exceptions Detected.")
                manager_reasons.append(f"Exceptions detected in task: *{report_summary.task.name or report_summary.task.uuid}*")
                client_issue_reasons.append(f"System Issue: Your task *'{report_summary.task.name or 'Unnamed Task'}'* encountered an *unresolved system issue*.")
                dev_details.append(f"```Aggregated Exceptions:\n{json.dumps(actual_exceptions, indent=2)}```")
                self.stdout.write(self.style.WARNING("  [Condition Met] Aggregated Exceptions found"))

            actual_specific_exception_reasons = [r for r in report_summary.all_specific_exception_reasons if r and "N/A" not in r]
            if actual_specific_exception_reasons:
                should_alert_dev = True
                should_alert_manager = True
                should_alert_client = True # Client should know about critical errors
                dev_reasons.append("Aggregated Specific Exception Reasons Found.")
                manager_reasons.append(f"Specific exceptions in task: *{report_summary.task.name or report_summary.task.uuid}*")
                client_issue_reasons.append(f"System Issue: Your task *'{report_summary.task.name or 'Unnamed Task'}'* encountered a *specific critical error*.")
                dev_details.append(f"```Aggregated Specific Exception Reasons:\n{json.dumps(actual_specific_exception_reasons, indent=2)}```")
                self.stdout.write(self.style.WARNING("  [Condition Met] Aggregated Specific Exception Reasons found"))

            actual_non_fatal_errors = [e for e in report_summary.all_non_fatal_errors if e and "No non-fatal errors across all runs" not in e]
            if actual_non_fatal_errors:
                should_alert_dev = True
                dev_reasons.append("Aggregated Non-Fatal Errors Detected.")
                dev_details.append(f"```Aggregated Non-Fatal Errors:\n{json.dumps(actual_non_fatal_errors, indent=2)}```")
                self.stdout.write(self.style.WARNING("  [Condition Met] Aggregated Non-Fatal Errors found"))

            if report_summary.total_runs_failed_exception > 0:
                should_alert_dev = True
                should_alert_client = True
                should_alert_manager = True
                dev_reasons.append(f"Total Runs Failed (Exception): {report_summary.total_runs_failed_exception}")
                client_issue_reasons.append(f"Performance Issue: Your task *'{report_summary.task.name or 'Unnamed Task'}'* had *{report_summary.total_runs_failed_exception} failed attempts*.")
                manager_reasons.append(f"Task *{report_summary.task.name or report_summary.task.uuid}* had {report_summary.total_runs_failed_exception} failed runs.")
                dev_details.append(f"Summary shows {report_summary.total_runs_failed_exception} runs failed due to exceptions.")
                self.stdout.write(self.style.WARNING(f"  [Condition Met] Total Runs Failed (Exception): {report_summary.total_runs_failed_exception}"))

            if report_summary.total_failed_download_count > 0:
                should_alert_dev = True
                should_alert_manager = True
                should_alert_client = True # Client should know about data download failures
                dev_reasons.append(f"Total Failed Downloads: {report_summary.total_failed_download_count}")
                manager_reasons.append(f"Failed downloads in task: *{report_summary.task.name or report_summary.task.uuid}*")
                client_issue_reasons.append(f"Data Issue: *{report_summary.total_failed_download_count} files failed to download* for task *'{report_summary.task.name or 'Unnamed Task'}'*.")
                dev_details.append(f"Summary shows {report_summary.total_failed_download_count} failed downloads.")
                self.stdout.write(self.style.WARNING(f"  [Condition Met] Total Failed Downloads: {report_summary.total_failed_download_count}"))

            # --- 4. Check Metrics for Scraping and Enrichment (handling string or dict) ---
            latest_scraped_count = 0
            if isinstance(report_summary.latest_scraped_data_summary, dict):
                latest_scraped_count = report_summary.latest_scraped_data_summary.get('total_count', 0)
                # Add specific scraped metrics if they exist and are relevant for client
                if 'total_users_scraped' in report_summary.latest_scraped_data_summary:
                    client_performance_metrics.append(f"Total Users Scraped: *{report_summary.latest_scraped_data_summary['total_users_scraped']}*")
                if 'total_posts_scraped' in report_summary.latest_scraped_data_summary:
                    client_performance_metrics.append(f"Total Posts Scraped: *{report_summary.latest_scraped_data_summary['total_posts_scraped']}*")
                # Add a general scraped count if no specific ones or if it's the primary metric
                if 'total_count' in report_summary.latest_scraped_data_summary and not client_performance_metrics:
                     client_performance_metrics.append(f"Total Records Scraped: *{report_summary.latest_scraped_data_summary['total_count']}*")
            elif isinstance(report_summary.latest_scraped_data_summary, str):
                if "No scraped data reported" in report_summary.latest_scraped_data_summary:
                    latest_scraped_count = 0
                    client_performance_metrics.append("Total Records Scraped: *0*")
                else:
                    try:
                        parsed_data = json.loads(report_summary.latest_scraped_data_summary)
                        if isinstance(parsed_data, dict):
                            latest_scraped_count = parsed_data.get('total_count', 0)
                            if 'total_users_scraped' in parsed_data:
                                client_performance_metrics.append(f"Total Users Scraped: *{parsed_data['total_users_scraped']}*")
                            if 'total_posts_scraped' in parsed_data:
                                client_performance_metrics.append(f"Total Posts Scraped: *{parsed_data['total_posts_scraped']}*")
                            if 'total_count' in parsed_data and not client_performance_metrics:
                                client_performance_metrics.append(f"Total Records Scraped: *{parsed_data['total_count']}*")
                        else:
                            self.stdout.write(self.style.WARNING(f"  Warning: latest_scraped_data_summary for Task {report_summary.task.uuid} is a non-dict JSON type after parsing: {report_summary.latest_scraped_data_summary[:50]}..."))
                            client_performance_metrics.append("Total Records Scraped: *0*") # Default for malformed
                    except json.JSONDecodeError:
                        self.stdout.write(self.style.WARNING(f"  Warning: latest_scraped_data_summary for Task {report_summary.task.uuid} is a plain string, not dict or valid JSON: {report_summary.latest_scraped_data_summary[:50]}..."))
                        latest_scraped_count = 0
                        client_performance_metrics.append("Total Records Scraped: *0*") # Default for plain string

            latest_enriched_count = 0
            if isinstance(report_summary.latest_data_enrichment_summary, dict):
                latest_enriched_count = report_summary.latest_data_enrichment_summary.get('total_count', 0)
                # Add specific enriched metrics if they exist and are relevant for client
                if 'total_rows' in report_summary.latest_data_enrichment_summary:
                    client_performance_metrics.append(f"Total Rows Enriched: *{report_summary.latest_data_enrichment_summary['total_rows']}*")
                if 'missing_rows' in report_summary.latest_data_enrichment_summary:
                    client_performance_metrics.append(f"Missing Rows After Enrichment: *{report_summary.latest_data_enrichment_summary['missing_rows']}*")
                # Add a general enriched count if no specific ones or if it's the primary metric
                if 'total_count' in report_summary.latest_data_enrichment_summary and 'total_rows' not in report_summary.latest_data_enrichment_summary:
                    client_performance_metrics.append(f"Total Enriched Records: *{report_summary.latest_data_enrichment_summary['total_count']}*")
            elif isinstance(report_summary.latest_data_enrichment_summary, str):
                if "No Data Enrichment Reported" in report_summary.latest_data_enrichment_summary:
                    latest_enriched_count = 0
                    client_performance_metrics.append("Total Records Enriched: *0*")
                else:
                    try:
                        parsed_data = json.loads(report_summary.latest_data_enrichment_summary)
                        if isinstance(parsed_data, dict):
                            latest_enriched_count = parsed_data.get('total_count', 0)
                            if 'total_rows' in parsed_data:
                                client_performance_metrics.append(f"Total Rows Enriched: *{parsed_data['total_rows']}*")
                            if 'missing_rows' in parsed_data:
                                client_performance_metrics.append(f"Missing Rows After Enrichment: *{parsed_data['missing_rows']}*")
                            if 'total_count' in parsed_data and 'total_rows' not in parsed_data:
                                client_performance_metrics.append(f"Total Enriched Records: *{parsed_data['total_count']}*")
                        else:
                             self.stdout.write(self.style.WARNING(f"  Warning: latest_data_enrichment_summary for Task {report_summary.task.uuid} is a non-dict JSON type after parsing: {report_summary.latest_data_enrichment_summary[:50]}..."))
                             client_performance_metrics.append("Total Records Enriched: *0*") # Default for malformed
                    except json.JSONDecodeError:
                        self.stdout.write(self.style.WARNING(f"  Warning: latest_data_enrichment_summary for Task {report_summary.task.uuid} is a plain string, not dict or valid JSON: {report_summary.latest_data_enrichment_summary[:50]}..."))
                        latest_enriched_count = 0
                        client_performance_metrics.append("Total Records Enriched: *0*") # Default for plain string

            # --- Check for Billing Issue ---
            # Ensure the specific issue string is handled for client-facing
            if report_summary.latest_billing_issue_resolution_status and \
               report_summary.latest_billing_issue_resolution_status not in ["N/A (No billing issues encountered)", "Resolved"]:
                should_alert_client = True
                should_alert_manager = True
                # Format for client:
                client_issue_reasons.append(f"Billing Issue: An active billing issue has been detected for '{report_summary.task.name or 'Unnamed Task'}'. Status: *{report_summary.latest_billing_issue_resolution_status}*.")
                manager_reasons.append(f"Billing Issue for task *{report_summary.task.name or report_summary.task.uuid}*: {report_summary.latest_billing_issue_resolution_status}")
                self.stdout.write(self.style.WARNING(f"  [Condition Met] Billing Issue: {report_summary.latest_billing_issue_resolution_status}"))


            if report_summary.latest_overall_task_status == 'Completed' and latest_scraped_count == 0:
                should_alert_dev = True
                should_alert_client = True
                dev_reasons.append("Scraping Completed with 0 Records.")
                client_issue_reasons.append(f"Data Quality Alert: Task *'{report_summary.task.name or 'Unnamed Task'}'* completed with *0 records scraped*.")
                dev_details.append(f"Task completed but `latest_scraped_data_summary` indicates 0 records. Check for data extraction issues.")
                self.stdout.write(self.style.WARNING("  [Condition Met] Completed with 0 Scraped Records"))

            if report_summary.latest_overall_task_status == 'Completed' and latest_scraped_count > 0 and latest_enriched_count == 0:
                should_alert_dev = True
                should_alert_client = True
                dev_reasons.append("Enrichment Completed with 0 Records despite scraping.")
                client_issue_reasons.append(f"Data Quality Alert: Task *'{report_summary.task.name or 'Unnamed Task'}'* scraped records ({latest_scraped_count}) but *yielded 0 enriched records*.")
                dev_details.append(f"Task scraped records (`{latest_scraped_count}`), but `latest_data_enrichment_summary` indicates 0. Check enrichment process.")
                self.stdout.write(self.style.WARNING("  [Condition Met] Scraped >0 but 0 Enriched Records"))

            # --- Alert Dispatch (Deduplication Logic Removed) ---
            any_alert_to_send = should_alert_dev or should_alert_client or should_alert_manager

            if any_alert_to_send:
                self.stdout.write(self.style.SUCCESS("  Alert conditions met! Sending alert (deduplication disabled)."))

                task_name = report_summary.task.name if report_summary.task.name else "Unnamed Task"
                
                # --- Developer Alert ---
                if should_alert_dev and dev_reasons:
                    dev_blocks = [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": f":warning: DEV Alert: Task Issue Detected for {task_name} :warning:"}
                        },
                        {
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": f"*Task Name:* {task_name}"},
                                {"type": "mrkdwn", "text": f"*Task UUID:* `{report_summary.task.uuid}`"},
                                {"type": "mrkdwn", "text": f"*Summary Last Updated:* {report_summary.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"},
                                {"type": "mrkdwn", "text": f"*Overall Status (Summary):* {report_summary.latest_overall_task_status}"},
                                {"type": "mrkdwn", "text": f"*Login Status (Summary):* {report_summary.latest_overall_bot_login_status}"},
                                {"type": "mrkdwn", "text": f"*Total Runs Failed (Ex):* {report_summary.total_runs_failed_exception}"},
                                {"type": "mrkdwn", "text": f"*Total Failed Downloads:* {report_summary.total_failed_download_count}"},
                                {"type": "mrkdwn", "text": f"*Latest Scraped Count:* {latest_scraped_count}"},
                                {"type": "mrkdwn", "text": f"*Latest Enriched Count:* {latest_enriched_count}"},
                            ]
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "*Reasons:*\n" + "\n".join([f"- {reason}" for reason in dev_reasons])}
                        }
                    ]
                    if dev_details:
                        dev_blocks.append({
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "*Developer Details:*\n" + "\n".join(dev_details)}
                        })
                    if report_summary.run_id_of_latest_report:
                        dev_blocks.append({
                            "type": "context",
                            "elements": [{"type": "mrkdwn", "text": (f"Latest Report Run ID: `{report_summary.run_id_of_latest_report}` | "
                                                                     f"End Time: {report_summary.latest_report_end_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if report_summary.latest_report_end_datetime else 'N/A'}")}]
                        })
                    try:
                        send_structured_slack_message(blocks=dev_blocks, channel='DEV')
                        self.stdout.write(self.style.SUCCESS(f"  Successfully sent DEV alert for Task {report_summary.task.uuid}."))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"  Failed to send DEV alert for Task {report_summary.task.uuid}: {e}"))

                # --- Client/Customer Alert ---
                if should_alert_client and (client_performance_metrics or client_issue_reasons):
                    client_blocks = [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": f":bar_chart: Performance Report & Status Update for '{task_name}'"}
                        }
                    ]

                    # Add Performance Report Section if metrics exist
                    if client_performance_metrics:
                        performance_fields = []
                        performance_fields.append({"type": "mrkdwn", "text": f"*Task Name:* {task_name}"})
                        performance_fields.append({"type": "mrkdwn", "text": f"*Latest Run Status:* {report_summary.latest_overall_task_status}"})
                        performance_fields.extend([{"type": "mrkdwn", "text": metric} for metric in client_performance_metrics])

                        client_blocks.append(
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": "*Performance Summary:*\n"},
                                "fields": performance_fields
                            }
                        )

                    # Add Issue Report Section if issues exist
                    if client_issue_reasons:
                        client_blocks.append(
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": "*Issue Report:*\n" + "\n".join([f"- {reason}" for reason in set(client_issue_reasons)])}
                            }
                        )
                    
                    client_blocks.append(
                        {
                            "type": "context",
                            "elements": [{"type": "mrkdwn", "text": "Our automated system is monitoring this task. We'll provide further updates if needed."}]
                        }
                    )
                    
                    try:
                        send_structured_slack_message(blocks=client_blocks, channel='CLIENT')
                        self.stdout.write(self.style.SUCCESS(f"  Successfully sent CLIENT alert for Task {report_summary.task.uuid}."))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"  Failed to send CLIENT alert for Task {report_summary.task.uuid}: {e}"))

                # --- Manager/Ops Alert ---
                if should_alert_manager and manager_reasons:
                    manager_blocks = [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": f":fire: Manager Alert: Operational Issue for {task_name} :fire:"}
                        },
                        {
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": f"*Task Name:* {task_name}"},
                                {"type": "mrkdwn", "text": f"*Task UUID:* `{report_summary.task.uuid}`"},
                                {"type": "mrkdwn", "text": f"*Overall Status:* {report_summary.latest_overall_task_status}"},
                                {"type": "mrkdwn", "text": f"*Login Status:* {report_summary.latest_overall_bot_login_status}"},
                                {"type": "mrkdwn", "text": f"*Total Failed Downloads:* {report_summary.total_failed_download_count}"},
                            ]
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "*Operational Issues:*\n" + "\n".join([f"- {reason}" for reason in manager_reasons])}
                        },
                        {
                            "type": "context",
                            "elements": [{"type": "mrkdwn", "text": "Action may be required for devices, accounts, or servers."}]
                        }
                    ]
                    try:
                        send_structured_slack_message(blocks=manager_blocks, channel='MANAGER')
                        self.stdout.write(self.style.SUCCESS(f"  Successfully sent MANAGER alert for Task {report_summary.task.uuid}."))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"  Failed to send MANAGER alert for Task {report_summary.task.uuid}: {e}"))

                # This line is still here to update last_alerted_at, but it won't affect sending if deduplication is off
                report_summary.last_alerted_at = timezone.now()
                report_summary.save(update_fields=['last_alerted_at'])
                self.stdout.write(self.style.SUCCESS(f"  Updated last_alerted_at for TaskSummaryReport: {report_summary.task.uuid} (No impact on sending with deduplication disabled)"))
            else:
                self.stdout.write("  No alert conditions met.")

        self.stdout.write("\nSynchronous alert check completed.")