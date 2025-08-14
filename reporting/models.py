from django.db import models

# Create your models here.
# reporting_and_analytics/models.py

from django.db import models
import uuid

# --- Core Data Ingestion Models ---






class Task(models.Model):
    """
    Represents a bot task, acting as a foreign key target for analysis reports.
    This model assumes you have a central 'Task' definition elsewhere,
    and we're either mirroring key fields or linking directly if possible.
    For this system, it's simplified to capture essential identifying info.
    """
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,
                            help_text="Unique identifier for the task, typically from the main task system.")
    job_uuid = models.UUIDField(db_index=True,
                                help_text="UUID of the job this task belongs to.", null=True)
    name = models.CharField(max_length=255,
                            help_text="Name of the task.")
    task_type = models.CharField(max_length=50,
                                 help_text="Type of the task (e.g., 'scraping', 'interaction', 'email_sending').")
    interact = models.BooleanField(default=False,
                                   help_text="True if this is an interaction-based task.")
    # Add other relevant task fields if needed for analysis (e.g., target_platform, start_date, end_date)

    class Meta:
        verbose_name = "Bot Task"
        verbose_name_plural = "Bot Tasks"
        # Consider a unique_together constraint if (job_uuid, name) or (job_uuid, task_type) should be unique
        # Eg. unique_together = ('job_uuid', 'name',)

    def __str__(self):
        return f"Task {self.name} ({str(self.uuid)[:8]}...) in Job ..."


class TaskReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    task = models.ForeignKey(
        'Task',
        on_delete=models.CASCADE,
        related_name='reports',
        db_index=True,
        null=False,  # or `null=True` if you're still setting up
        help_text="Reference to the associated Task object."
    )
    run_id = models.UUIDField(help_text="Unique ID for this specific run of the task.")

    service = models.CharField(max_length=50, null=True, blank=True)
    end_point = models.CharField(max_length=50, null=True, blank=True)
    data_point = models.CharField(max_length=50, null=True, blank=True)

    report_start_datetime = models.DateTimeField(null=True, blank=True)
    report_end_datetime = models.DateTimeField(null=True, blank=True)

    full_report = models.JSONField(help_text="Complete nested data report.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('run_id', 'task', 'data_point')
        verbose_name = "Task Report"
        verbose_name_plural = "Task Reports"

    def __str__(self):
        return f"{self.service} / {self.data_point} ({self.run_id})"

class TaskSummaryReportNew(models.Model):
    
    task = models.OneToOneField('Task', on_delete=models.CASCADE, related_name='new_summary_report',null=True,blank=True)

    # --- Aggregated counts and summaries ---
    total_critical_events = models.IntegerField(default=0)
    critical_events_summary = models.JSONField(default=list, blank=True)

    total_login_attempts = models.IntegerField(default=0)
    successful_logins = models.IntegerField(default=0)
    failed_logins = models.IntegerField(default=0)
    total_login_time = models.FloatField(default=0.0)

    total_2fa_attempts = models.IntegerField(default=0)
    total_2fa_successes = models.IntegerField(default=0)
    total_2fa_failures = models.IntegerField(default=0)
    total_2fa_time = models.FloatField(default=0.0)

    total_attempt_failed = models.IntegerField(default=0)
    attempt_failed_errors = models.JSONField(default=list, blank=True)
    failed_attempt_error_logs = models.JSONField(default=list, blank=True)

    login_exceptions_summary = models.JSONField(default=list, blank=True)
    login_exceptions_count = models.IntegerField(default=0)

    page_detection_exceptions_summary = models.JSONField(default=list, blank=True)
    page_detection_exceptions_count = models.IntegerField(default=0)

    locate_element_exceptions_summary = models.JSONField(default=list, blank=True)
    locate_element_exceptions_count = models.IntegerField(default=0)

    page_load_details = models.JSONField(default=dict, blank=True)

    # --- Meta-Information about the aggregation ---
    total_reports_considered = models.IntegerField(default=0)
    first_report_datetime = models.DateTimeField(null=True, blank=True)
    last_report_datetime = models.DateTimeField(null=True, blank=True)

    has_next_page_info = models.BooleanField(default=None, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_alerted_at = models.DateTimeField(null=True, blank=True)

    # --- Latest States from latest TaskReport ---
    latest_task_status = models.CharField(max_length=255, null=True, blank=True)
    latest_login_status = models.CharField(max_length=64, null=True, blank=True)

    latest_report_start_datetime = models.DateTimeField(null=True, blank=True)
    latest_report_end_datetime = models.DateTimeField(null=True, blank=True)
    latest_total_task_runtime = models.FloatField(default=0.0)
    run_id_of_latest_report = models.CharField(max_length=255, null=True, blank=True)


    # Scrape-related summary fields

    # Count of users scraped
    total_users_scraped = models.IntegerField(default=0)

    # File and upload stats
    total_downloaded_files = models.IntegerField(default=0)
    total_storage_uploads = models.IntegerField(default=0)
    failed_to_download_file_count = models.IntegerField(default=0)

    # Next page info detection
    found_next_page_info_count = models.IntegerField(default=0)
    next_page_info_not_found_count = models.IntegerField(default=0)
    has_next_page_info = models.BooleanField(null=True, blank=True)  # Latest report info

    # Detailed failures and exceptions
    failed_downloads_details = models.JSONField(default=list, blank=True)  # List of dicts or strings
    storage_upload_failed = models.BooleanField(default=False)
    task_completion_status = models.CharField(max_length=255, blank=True, default='')  # Optional status
    has_billing_exception = models.BooleanField(default=False)
    specific_exception_reason = models.CharField(max_length=255, blank=True, default='')  # Optional description

    class Meta:
        verbose_name = "Task Summary Report"
        verbose_name_plural = "Task Summary Reports"
        ordering = ['-updated_at']

    def __str__(self):
        return f"TaskSummaryReport(task_id={self.task})"



class TaskAnalysisReport(models.Model):

    task=models.ForeignKey(Task,null=False,on_delete=models.CASCADE)
    run_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,
                            )
    overall_task_status = models.CharField(max_length=50)
    report_start_datetime = models.DateTimeField(null=True, blank=True)
    report_end_datetime = models.DateTimeField(null=True, blank=True)
    total_task_runtime_text = models.CharField(max_length=100)
    total_task_runtime_seconds = models.FloatField()
    runs_initiated = models.IntegerField()
    runs_completed = models.IntegerField()
    runs_failed_exception = models.IntegerField()
    runs_incomplete = models.IntegerField()
    found_next_page_info_count = models.IntegerField()
    next_page_info_not_found_count = models.IntegerField()
    saved_file_count = models.IntegerField()
    downloaded_file_count = models.IntegerField()
    failed_download_count = models.IntegerField()
    overall_bot_login_status = models.CharField(max_length=50)
    last_status_of_task = models.CharField(max_length=255)
    billing_issue_resolution_status = models.CharField(max_length=255)

    # You might use JSONField for scraped data, errors, exceptions if using PostgreSQL
    # For other databases, you might store these as JSON strings in a TextField
    scraped_data_summary = models.JSONField(default=dict)
    data_enrichment_summary = models.JSONField(default=dict)  # If using PostgreSQL
    # For other databases: scraped_data_summary_json = models.TextField(default='{}')

    non_fatal_errors_summary = models.TextField()
    exceptions_summary = models.TextField()
    specific_exception_reasons = models.TextField()
    failed_downloads_summary = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for {self.report_start_datetime} - {self.overall_task_status}"
    

# reporting_and_analytics/models.py
# (Assuming other necessary imports like uuid, models, and timezone are at the top of the file)
# (Also assuming the Task model is defined elsewhere in this file)

import uuid
from django.db import models
from django.utils import timezone


class TaskSummaryReport(models.Model):
    """
    Stores an aggregated summary of all TaskAnalysisReports for a specific Task,
    providing overall metrics and the latest status.
    """
    # One-to-one relationship with Task. The task's PK will be this model's PK.
    task = models.OneToOneField('Task', on_delete=models.CASCADE, primary_key=True, related_name='summary_report')

    # --- Aggregated Metrics ---
    total_runs_initiated = models.IntegerField(default=0)
    total_runs_completed = models.IntegerField(default=0)
    total_runs_failed_exception = models.IntegerField(default=0)
    total_runs_incomplete = models.IntegerField(default=0)
    total_found_next_page_info_count = models.IntegerField(default=0)
    total_next_page_info_not_found_count = models.IntegerField(default=0)
    total_saved_file_count = models.IntegerField(default=0)
    total_downloaded_file_count = models.IntegerField(default=0)
    total_failed_download_count = models.IntegerField(default=0)
    cumulative_total_runtime_seconds = models.FloatField(default=0.0)
    average_runtime_seconds_per_run = models.FloatField(default=0.0)

    # --- Latest States (from the most recent TaskAnalysisReport) ---
    latest_overall_task_status = models.CharField(max_length=50, blank=True, null=True)
    latest_overall_bot_login_status = models.CharField(max_length=50, blank=True, null=True)
    latest_last_status_of_task = models.CharField(max_length=255, blank=True, null=True)
    latest_billing_issue_resolution_status = models.CharField(max_length=255, blank=True, null=True)
    latest_report_start_datetime = models.DateTimeField(blank=True, null=True)
    latest_report_end_datetime = models.DateTimeField(blank=True, null=True)
    latest_total_task_runtime_text = models.CharField(max_length=100, blank=True, null=True)
    run_id_of_latest_report = models.UUIDField(blank=True, null=True)

    # --- Specific metrics from the LAST RUN ---
    latest_scraped_data_summary = models.JSONField(default=dict)
    latest_data_enrichment_summary = models.JSONField(default=dict)

    # --- Aggregated JSON & Text Summaries (these aggregate across ALL runs) ---
    aggregated_scraped_data = models.JSONField(default=dict)
    aggregated_data_enrichment = models.JSONField(default=dict)
    all_non_fatal_errors = models.JSONField(default=list)  # Storing list of unique errors
    all_exceptions = models.JSONField(default=list)
    all_specific_exception_reasons = models.JSONField(default=list)
    all_failed_downloads_summary = models.JSONField(default=list)

    # --- Meta-Information about the aggregation ---
    total_reports_considered = models.IntegerField(default=0)
    first_report_datetime = models.DateTimeField(blank=True, null=True)
    last_report_datetime = models.DateTimeField(blank=True, null=True)

    # --- Calculated Boolean Field (Nullable) ---
    has_next_page_info = models.BooleanField(default=None, null=True, blank=True)

    # When this summary was last updated/generated
    updated_at = models.DateTimeField(auto_now=True)
    last_alerted_at = models.DateTimeField(null=True, blank=True,
        help_text="Timestamp when the last alert for this summary's status was sent.")

    class Meta:
        verbose_name = "Task Summary Report"
        verbose_name_plural = "Task Summary Reports"
        ordering = ['-updated_at']

    def __str__(self):
        return f"Summary for Task '{self.task.name}'"
    




class JobAnalysisReport(models.Model):
    """
    Stores consolidated analysis results for an entire bot job, aggregated from TaskAnalysisReports.
    This is the primary output of Phase 5.
    """
    job_uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,
                                help_text="Unique identifier for the bot job.")
    name = models.CharField(max_length=255, blank=True, null=True,
                            help_text="Name of the job (if applicable from source system).")
    
    # --- Consolidated Metrics (aggregated from TaskAnalysisReports) ---
    total_tasks_in_job = models.IntegerField(default=0,
                                             help_text="Total number of tasks associated with this job.")
    tasks_completed_successfully = models.IntegerField(default=0,
                                                       help_text="Number of tasks in the job that completed successfully.")
    total_users_scraped = models.IntegerField(default=0,
                                              help_text="Total users scraped across all tasks in this job.")
    total_posts_scraped = models.IntegerField(default=0,
                                              help_text="Total posts scraped across all tasks in this job.")
    total_comments_scraped = models.IntegerField(default=0,
                                                 help_text="Total comments scraped across all tasks in this job.")
    total_interactions = models.IntegerField(default=0,
                                             help_text="Total interactions (follows, likes, etc.) across all tasks in this job.")
    total_data_downloaded_kb = models.BigIntegerField(default=0,
                                                     help_text="Total data downloaded in KB for the entire job.")
    total_data_uploaded_kb = models.BigIntegerField(default=0,
                                                   help_text="Total data uploaded in KB for the entire job.")
    total_requests_failed = models.IntegerField(default=0,
                                                help_text="Total failed requests across all tasks in this job.")
    
    # --- Billing & Cost ---
    has_any_billing_issue = models.BooleanField(default=False,
                                                help_text="True if any task in this job had a billing issue.")
    billing_issue_tasks = models.JSONField(default=list, blank=True, null=True,
                                           help_text="List of task_uuids with billing issues in this job.")
    total_job_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000,
                                         help_text="Total calculated cost for this entire job.")
    
    # --- Device Metrics (aggregated or summarized) ---
    total_device_usage_time_minutes = models.IntegerField(default=0,
                                                          help_text="Total minutes devices were active for this job.")
    total_device_connection_failures = models.IntegerField(default=0,
                                                           help_text="Total device connection failures for this job.")
    
    created_at = models.DateTimeField(auto_now_add=True,
                                      help_text="Timestamp when this report was created.")
    updated_at = models.DateTimeField(auto_now=True,
                                      help_text="Timestamp when this report was last updated.")

    class Meta:
        verbose_name = "Job Analysis Report"
        verbose_name_plural = "Job Analysis Reports"
        ordering = ['-created_at']

    def __str__(self):
        return f"Job Report: {self.job_uuid} ({self.name})"


# --- Configuration Model for Cost Analysis ---

class CostUnitConfig(models.Model):
    """
    Defines the cost per unit for various activities and resources,
    used in the job-level cost analysis.
    """
    unit_name = models.CharField(max_length=100, unique=True,
                                help_text="Name of the cost unit (e.g., 'per_user_scraped', 'per_gb_downloaded', 'per_device_minute').")
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=6,
                                        help_text="The cost associated with one unit of this item.")
    description = models.TextField(blank=True, null=True,
                                   help_text="Description of what this cost unit represents.")

    class Meta:
        verbose_name = "Cost Unit Configuration"
        verbose_name_plural = "Cost Unit Configurations"

    def __str__(self):
        return f"{self.unit_name}: {self.cost_per_unit}"