# reporting/management/commands/send_client_alerts.py

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
import datetime
import json
import logging

# Import models from the 'reporting' app
from reporting.models import TaskSummaryReport, Task
from reporting.slack_utils import send_structured_slack_message

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sends client-specific performance reports and critical issue alerts, with deduplication disabled.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--task_uuid',
            type=str,
            help='Optional: Filter for a specific Task UUID to check alerts for.',
            default=None
        )
        # Force alert flag is maintained for consistency, though deduplication is off
        parser.add_argument(
            '--force-alert',
            action='store_true',
            help='This flag has no effect as deduplication is currently disabled.',
        )

    def handle(self, *args, **kwargs):
        task_uuid_filter = kwargs.get('task_uuid')
        # force_alert = kwargs.get('force_alert') # Not directly used as deduplication is disabled

        self.stdout.write(f"Starting client alert check (Deduplication disabled)...")
        if task_uuid_filter:
            self.stdout.write(f"Filtering for Task UUID: {task_uuid_filter}")

        # Define the time window for recently updated summaries (last 24 hours)
        # You might adjust this based on how frequently clients expect updates.
        recent_update_threshold = timezone.now() - datetime.timedelta(hours=24)

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
            self.stdout.write(self.style.WARNING("No recently updated TaskSummaryReports found to check for client alerts."))
            return

        for report_summary in reports_to_check:
            self.stdout.write(f"\n--- Checking Task for Client: {report_summary.task.name or report_summary.task.uuid} (Summary ID: {report_summary.pk}) ---")

            client_performance_metrics = []
            client_health_statuses = []
            client_critical_issues = []

            task_name = report_summary.task.name if report_summary.task.name else "Unnamed Task"

            # --- 1. Client Performance Metrics ---
            # Task Name, Last Run Info
            last_report_end_time = report_summary.latest_report_end_datetime.strftime('%Y-%m-%d %H:%M:%S UTC') if report_summary.latest_report_end_datetime else 'N/A'
            total_task_runtime = report_summary.latest_total_task_runtime_text if report_summary.latest_total_task_runtime_text else 'N/A' # Fixed: Used task.latest_total_task_runtime_text

            client_performance_metrics.append(f"*Task:* {task_name}")
            client_performance_metrics.append(f"  *Last Run Time:* {last_report_end_time}")
            client_performance_metrics.append(f"  *Duration:* {total_task_runtime}")
            client_performance_metrics.append(f"  *Overall Status:* {report_summary.latest_overall_task_status}")

            # Aggregated Scraped Data
            aggregated_scraped_data = report_summary.aggregated_scraped_data
            if isinstance(aggregated_scraped_data, dict) and aggregated_scraped_data:
                client_performance_metrics.append(f"  *Aggregated Scraped Records:*")
                # Prioritize specific keys, then total, then general dict items
                found_agg_scraped_metrics = False
                if 'total_users_scraped' in aggregated_scraped_data:
                    client_performance_metrics.append(f"    - Total Users: *{aggregated_scraped_data['total_users_scraped']}*")
                    found_agg_scraped_metrics = True
                if 'total_posts_scraped' in aggregated_scraped_data:
                    client_performance_metrics.append(f"    - Total Posts: *{aggregated_scraped_data['total_posts_scraped']}*")
                    found_agg_scraped_metrics = True
                if 'total_count' in aggregated_scraped_data: # Always include total count if present
                    client_performance_metrics.append(f"    - Overall Total: *{aggregated_scraped_data['total_count']}*")
                    found_agg_scraped_metrics = True
                
                # Add any other generic items in the dict if no specific ones were found
                if not found_agg_scraped_metrics:
                    for key, value in aggregated_scraped_data.items():
                        client_performance_metrics.append(f"    - {key.replace('_', ' ').title()}: *{value}*")
                        found_agg_scraped_metrics = True # Mark that at least one item was added

                if not found_agg_scraped_metrics:
                    client_performance_metrics.append(f"    - No specific metrics reported in aggregated data.")
            else:
                client_performance_metrics.append(f"  *Aggregated Scraped Records:* No data reported")


            # Latest Scraped Data - FIX APPLIED HERE
            scraped_data_reported = False
            if isinstance(report_summary.latest_scraped_data_summary, dict) and report_summary.latest_scraped_data_summary:
                client_performance_metrics.append(f"  *Latest Run Scraped Records:*")
                if 'total_count' in report_summary.latest_scraped_data_summary:
                    client_performance_metrics.append(f"    - Total: *{report_summary.latest_scraped_data_summary['total_count']}*")
                    scraped_data_reported = True
                if 'total_users_scraped' in report_summary.latest_scraped_data_summary:
                    client_performance_metrics.append(f"    - Users: *{report_summary.latest_scraped_data_summary['total_users_scraped']}*")
                    scraped_data_reported = True
                if 'total_posts_scraped' in report_summary.latest_scraped_data_summary:
                    client_performance_metrics.append(f"    - Posts: *{report_summary.latest_scraped_data_summary['total_posts_scraped']}*")
                    scraped_data_reported = True
                # Add more specific scraped metrics here if needed

                if not scraped_data_reported: # If dict was present but had none of our expected keys
                    client_performance_metrics.append(f"    - No specific metrics reported in dict")

            elif isinstance(report_summary.latest_scraped_data_summary, str) and "No scraped data reported" in report_summary.latest_scraped_data_summary:
                 client_performance_metrics.append(f"  *Latest Run Scraped Records:* 0")
            elif report_summary.latest_scraped_data_summary is None: # Explicitly handle None
                 client_performance_metrics.append(f"  *Latest Run Scraped Records:* N/A")
            else: # Fallback for unhandled string formats (e.g., malformed JSON)
                 client_performance_metrics.append(f"  *Latest Run Scraped Records:* Could not parse")
                 logger.warning(f"  Warning: latest_scraped_data_summary for Task {report_summary.task.uuid} is an unhandled format: {report_summary.latest_scraped_data_summary[:100]}...")


            # Aggregated Enriched Data
            aggregated_enrichment_data = report_summary.aggregated_data_enrichment
            if isinstance(aggregated_enrichment_data, dict) and aggregated_enrichment_data:
                client_performance_metrics.append(f"  *Aggregated Enriched Records:*")
                found_agg_enriched_metrics = False
                if 'total_rows' in aggregated_enrichment_data:
                    client_performance_metrics.append(f"    - Total Rows: *{aggregated_enrichment_data['total_rows']}*")
                    found_agg_enriched_metrics = True
                if 'missing_rows' in aggregated_enrichment_data:
                    client_performance_metrics.append(f"    - Missing Rows: *{aggregated_enrichment_data['missing_rows']}*")
                    found_agg_enriched_metrics = True
                if 'total_count' in aggregated_enrichment_data:
                    client_performance_metrics.append(f"    - Overall Total: *{aggregated_enrichment_data['total_count']}*")
                    found_agg_enriched_metrics = True
                
                if not found_agg_enriched_metrics:
                    for key, value in aggregated_enrichment_data.items():
                        client_performance_metrics.append(f"    - {key.replace('_', ' ').title()}: *{value}*")
                        found_agg_enriched_metrics = True

                if not found_agg_enriched_metrics:
                    client_performance_metrics.append(f"    - No specific metrics reported in aggregated data.")
            else:
                client_performance_metrics.append(f"  *Aggregated Enriched Records:* No data reported")


            # Latest Enriched Data - FIX APPLIED HERE
            enriched_data_reported = False
            if isinstance(report_summary.latest_data_enrichment_summary, dict) and report_summary.latest_data_enrichment_summary:
                client_performance_metrics.append(f"  *Latest Run Enriched Records:*")
                if 'total_count' in report_summary.latest_data_enrichment_summary:
                    client_performance_metrics.append(f"    - Total: *{report_summary.latest_data_enrichment_summary['total_count']}*")
                    enriched_data_reported = True
                if 'total_rows' in report_summary.latest_data_enrichment_summary:
                    client_performance_metrics.append(f"    - Total Rows: *{report_summary.latest_data_enrichment_summary['total_rows']}*")
                    enriched_data_reported = True
                if 'missing_rows' in report_summary.latest_data_enrichment_summary:
                    client_performance_metrics.append(f"    - Missing Rows: *{report_summary.latest_data_enrichment_summary['missing_rows']}*")
                    enriched_data_reported = True
                # Add more specific enriched metrics here if needed

                if not enriched_data_reported: # If dict was present but had none of our expected keys
                    client_performance_metrics.append(f"    - No specific metrics reported in dict")

            elif isinstance(report_summary.latest_data_enrichment_summary, str) and "No Data Enrichment Reported" in report_summary.latest_data_enrichment_summary:
                 client_performance_metrics.append(f"  *Latest Run Enriched Records:* 0")
            elif report_summary.latest_data_enrichment_summary is None: # Explicitly handle None
                 client_performance_metrics.append(f"  *Latest Run Enriched Records:* N/A")
            else: # Fallback for unhandled string formats (e.g., malformed JSON)
                 client_performance_metrics.append(f"  *Latest Run Enriched Records:* Could not parse")
                 logger.warning(f"  Warning: latest_data_enrichment_summary for Task {report_summary.task.uuid} is an unhandled format: {report_summary.latest_data_enrichment_summary[:100]}...")


            # --- 2. Client Bot Health Status ---
            # Assumption 1: latest_overall_bot_login_status reflects the health of the bot for this task
            bot_login_status = report_summary.latest_overall_bot_login_status
            client_health_statuses.append(f"  Bot for Task '{task_name}': *{bot_login_status}*")
            if bot_login_status == 'Logged Out':
                # This is also a critical issue, so add it there too
                client_critical_issues.append(f"Bot Issue: Your bot for task '{task_name}' is currently *Logged Out*.")


            # --- 3. Client Critical Issues (Actionable by Client) ---
            # Storage House Down Check (total_saved_file_count == 0 AND runs completed > 0)
            if report_summary.total_runs_completed > 0 and report_summary.total_saved_file_count == 0:
                client_critical_issues.append(
                    f"Storage Alert: No files were saved for Task '{task_name}' despite completed runs. Please check your storage systems."
                )
                self.stdout.write(self.style.WARNING(f"  [Condition Met] Storage issue: 0 files saved for completed runs."))

            # Billing Issue Check
            if report_summary.latest_billing_issue_resolution_status and \
               report_summary.latest_billing_issue_resolution_status not in ["N/A (No billing issues encountered)", "Resolved"]:
                client_critical_issues.append(
                    f"Billing Alert: An active billing issue has been detected. Status: *{report_summary.latest_billing_issue_resolution_status}*."
                )
                self.stdout.write(self.style.WARNING(f"  [Condition Met] Billing Issue: {report_summary.latest_billing_issue_resolution_status}"))


            # --- Alert Dispatch ---
            # Only send if there's performance data or any critical issues/health statuses to report
            if client_performance_metrics or client_health_statuses or client_critical_issues:
                self.stdout.write(self.style.SUCCESS("  Client alert conditions met! Sending alert..."))

                client_blocks = [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f":bar_chart: Performance & Status Update: {task_name}"}
                    }
                ]

                # Add Performance Summary Section
                client_blocks.append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "*--- Performance Summary ---*\n" + "\n".join(client_performance_metrics)}
                    }
                )

                # Add Bot Health Status Section
                client_blocks.append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "*--- Bot Health Status ---*\n" + "\n".join(client_health_statuses)}
                    }
                )

                # Add Critical Issue Report Section (only if issues exist)
                if client_critical_issues:
                    client_blocks.append(
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "*--- Important Issues Detected ---*\n" + "\n".join([f"- {reason}" for reason in set(client_critical_issues)])} # Use set for unique issues
                        }
                    )
                
                client_blocks.append(
                    {
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": "Our automated system is monitoring your tasks. Please reach out if you have any questions."}]
                    }
                )
                
                try:
                    send_structured_slack_message(blocks=client_blocks, channel='CLIENT')
                    self.stdout.write(self.style.SUCCESS(f"  Successfully sent CLIENT alert for Task {report_summary.task.uuid}."))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  Failed to send CLIENT alert for Task {report_summary.task.uuid}: {e}"))

                # Update last_alerted_at, even though deduplication is off, for tracking
                report_summary.last_alerted_at = timezone.now()
                report_summary.save(update_fields=['last_alerted_at'])
                self.stdout.write(self.style.SUCCESS(f"  Updated last_alerted_at for TaskSummaryReport: {report_summary.task.uuid}"))
            else:
                self.stdout.write("  No client-relevant performance data or critical issues found to report.")

        self.stdout.write("\nClient alert check completed.")