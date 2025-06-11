from django.contrib import admin

# Register your models here.
# reporting_and_analytics/admin.py

from django.contrib import admin
from .models import  Task, TaskAnalysisReport, JobAnalysisReport, CostUnitConfig



@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'name', 'job_uuid', 'task_type', 'interact')
    list_filter = ('task_type', 'interact')
    search_fields = ('name', 'uuid', 'job_uuid')
    readonly_fields = ('uuid',)



@admin.register(JobAnalysisReport)
class JobAnalysisReportAdmin(admin.ModelAdmin):
    list_display = ('job_uuid', 'name', 'total_tasks_in_job', 'total_job_cost', 'has_any_billing_issue', 'created_at')
    list_filter = ('has_any_billing_issue', 'created_at')
    search_fields = ('job_uuid', 'name')
    readonly_fields = ('job_uuid', 'created_at', 'updated_at')

@admin.register(CostUnitConfig)
class CostUnitConfigAdmin(admin.ModelAdmin):
    list_display = ('unit_name', 'cost_per_unit')
    search_fields = ('unit_name',)
    # This model will likely be populated manually or via fixtures/data migrations

# reporting_and_analytics/admin.py
from django.contrib import admin
from .models import TaskAnalysisReport, Task # Ensure Task is imported if not already

@admin.register(TaskAnalysisReport)
class TaskAnalysisReportAdmin(admin.ModelAdmin):
    # 1. Fields to display in the list view of the admin
    list_display = (
        'run_id',
        'task_link',  # Custom method for a clickable task link
        'overall_task_status',
        'total_task_runtime_text',
        'runs_initiated',
        'runs_completed',
        'runs_failed_exception',
        'report_start_datetime',
        'report_end_datetime',
        'created_at',
    )

    # 2. Fields to use for searching
    search_fields = (
        'run_id__contains', # Use __contains for partial UUID search (careful with performance on large UUIDs)
        'overall_task_status',
        'task__name', # Search by the related Task's name
        'last_status_of_task',
    )

    # 3. Fields to use for filtering in the right sidebar
    list_filter = (
        'overall_task_status',
        'overall_bot_login_status',
        'task', # Filter by the related Task
        'runs_failed_exception',
        'runs_incomplete',
        'billing_issue_resolution_status',
        'report_start_datetime', # Date filter
        'report_end_datetime',   # Date filter
    )

    # 4. Fields that are read-only in the detail view (cannot be edited)
    readonly_fields = (
        'run_id',
        'created_at',
        'total_task_runtime_text',
        'total_task_runtime_seconds',
        'scraped_data_summary_display', # Display formatted JSON
        'data_enrichment_summary_display', # Display formatted JSON
    )

    # 5. Fieldsets for organizing fields in the detail view
    fieldsets = (
        (None, {
            'fields': (
                'task',
                'run_id',
                'overall_task_status',
                'report_start_datetime',
                'report_end_datetime',
                'created_at',
            )
        }),
        ('Runtime Metrics', {
            'fields': (
                'total_task_runtime_text',
                'total_task_runtime_seconds',
                'runs_initiated',
                'runs_completed',
                'runs_failed_exception',
                'runs_incomplete',
            ),
            'classes': ('collapse',) # Makes this section collapsible
        }),
        ('Data Collection Summary', {
            'fields': (
                'found_next_page_info_count',
                'next_page_info_not_found_count',
                'saved_file_count',
                'downloaded_file_count',
                'failed_download_count',
            ),
            'classes': ('collapse',)
        }),
        ('Bot Status & Issues', {
            'fields': (
                'overall_bot_login_status',
                'last_status_of_task',
                'billing_issue_resolution_status',
            ),
            'classes': ('collapse',)
        }),
        ('Detailed Summaries', {
            'fields': (
                'non_fatal_errors_summary',
                'exceptions_summary',
                'specific_exception_reasons',
                'failed_downloads_summary',
                'scraped_data_summary_display', # Use the custom method for display
                'data_enrichment_summary_display', # Use the custom method for display
            ),
            'classes': ('wide', 'extrapretty') # 'wide' uses more horizontal space
        }),
    )

    # 6. Custom method to create a clickable link to the related Task in the list display
    def task_link(self, obj):
        if obj.task:
            # Reverses the URL to the admin change view for the linked Task object
            from django.urls import reverse
            from django.utils.html import format_html
            link = reverse("admin:%s_%s_change" % (obj.task._meta.app_label, obj.task._meta.model_name), args=[obj.task.pk])
            return format_html('<a href="{}">{}</a>', link, obj.task.__str__()) # Displays Task's __str__ method
        return "-"
    task_link.short_description = 'Related Task' # Column header in admin list

    # 7. Custom methods for displaying JSONField data in a readable format
    def scraped_data_summary_display(self, obj):
        # Use json.dumps for pretty printing if the data is complex
        import json
        return json.dumps(obj.scraped_data_summary, indent=2)
    scraped_data_summary_display.short_description = 'Scraped Data Summary'
    scraped_data_summary_display.allow_tags = True # Allow HTML for pre tag

    def data_enrichment_summary_display(self, obj):
        import json
        return json.dumps(obj.data_enrichment_summary, indent=2)
    data_enrichment_summary_display.short_description = 'Data Enrichment Summary'
    data_enrichment_summary_display.allow_tags = True

    # 8. Override save_model for any pre-save logic (if needed, e.g., calculating runtime)
    # This example assumes total_task_runtime_text and total_task_runtime_seconds are pre-calculated.
    # def save_model(self, request, obj, form, change):
    #     if obj.report_start_datetime and obj.report_end_datetime and not obj.total_task_runtime_seconds:
    #         duration = obj.report_end_datetime - obj.report_start_datetime
    #         obj.total_task_runtime_seconds = duration.total_seconds()
    #         obj.total_task_runtime_text = str(duration)
    #     super().save_model(request, obj, form, change)

# reporting_and_analytics/admin.py

# reporting_and_analytics/admin.py

from django.contrib import admin
from .models import TaskSummaryReport, Task, TaskAnalysisReport

@admin.register(TaskSummaryReport)
class TaskSummaryReportAdmin(admin.ModelAdmin):
    # 1. Display Fields in List View
    list_display = (
        'task_uuid_short', # Custom method to display a truncated Task UUID
        'total_runs_completed',
        'total_runs_failed_exception',
        'latest_overall_task_status',
        'latest_report_end_datetime',
        'has_next_page_info',
        'updated_at',
    )

    # 2. Fields to use for searching
    search_fields = (
        'task__uuid', # Search directly by Task's UUID
        'latest_overall_task_status',
        'latest_last_status_of_task',
        'task__name', # Keep if names might exist sometimes and be searchable
    )

    # 3. Fields to filter results in the right sidebar
    list_filter = (
        'latest_overall_task_status',
        'latest_overall_bot_login_status',
        'latest_billing_issue_resolution_status',
        'has_next_page_info',
        'updated_at',
        'total_runs_completed',
    )

    # 4. Fields to make clickable links to the detail view
    # The truncated UUID will now be the clickable link
    list_display_links = (
        'task_uuid_short',
    )

    # 5. Grouping fields in the detail view
    fieldsets = (
        (None, {
            'fields': ('task', 'task_uuid_display',), # Display the related task object and its full UUID
        }),
        ('Overall Task Summary Metrics', {
            'fields': (
                'total_runs_initiated',
                'total_runs_completed',
                'total_runs_failed_exception',
                'total_runs_incomplete',
                'cumulative_total_runtime_seconds',
                'average_runtime_seconds_per_run',
                'total_reports_considered',
                'first_report_datetime',
                'last_report_datetime',
            ),
            'description': 'Aggregated counts and durations across all runs for this task.',
        }),
        ('Latest Run Status & Info', {
            'fields': (
                'latest_overall_task_status',
                'latest_overall_bot_login_status',
                'latest_last_status_of_task',
                'latest_billing_issue_resolution_status',
                'latest_report_start_datetime',
                'latest_report_end_datetime',
                'latest_total_task_runtime_text',
                'run_id_of_latest_report',
                'has_next_page_info',
            ),
            'description': 'Status and details from the most recent Task Analysis Report.',
        }),
        ('File & Next Page Info', {
            'fields': (
                'total_saved_file_count',
                'total_downloaded_file_count',
                'total_failed_download_count',
                'total_found_next_page_info_count',
                'total_next_page_info_not_found_count',
            ),
            'description': 'Aggregated counts related to file operations and next page discovery.',
        }),
        ('Latest Data Summaries', {
            'classes': ('collapse',),
            'fields': (
                'latest_scraped_data_summary',
                'latest_data_enrichment_summary',
            ),
            'description': 'Raw JSON summaries from the latest Task Analysis Report.',
        }),
        ('Aggregated Data Summaries', {
            'classes': ('collapse',),
            'fields': (
                'aggregated_scraped_data',
                'aggregated_data_enrichment',
            ),
            'description': 'Aggregated numerical data from all scraped/enriched reports.',
        }),
        ('Aggregated Errors & Exceptions', {
            'classes': ('collapse',),
            'fields': (
                'all_non_fatal_errors',
                'all_exceptions',
                'all_specific_exception_reasons',
                'all_failed_downloads_summary',
            ),
            'description': 'Unique lists of errors, exceptions, and failed downloads across all runs.',
        }),
        ('Metadata', {
            'fields': ('updated_at',),
            'description': 'When this summary report was last updated.',
        }),
    )

    # 6. Make JSON fields non-editable and display nicely
    readonly_fields = [
        'task', # Still show the foreign key, but it's not editable
        'task_uuid_display', # This new method is just for display
        'total_runs_initiated', 'total_runs_completed', 'total_runs_failed_exception',
        'total_runs_incomplete', 'total_found_next_page_info_count',
        'total_next_page_info_not_found_count', 'total_saved_file_count',
        'total_downloaded_file_count', 'total_failed_download_count',
        'cumulative_total_runtime_seconds', 'average_runtime_seconds_per_run',
        'latest_overall_task_status', 'latest_overall_bot_login_status',
        'latest_last_status_of_task', 'latest_billing_issue_resolution_status',
        'latest_report_start_datetime', 'latest_report_end_datetime',
        'latest_total_task_runtime_text', 'run_id_of_latest_report',
        'total_reports_considered', 'first_report_datetime',
        'last_report_datetime', 'has_next_page_info', 'updated_at',
        'latest_scraped_data_summary',
        'latest_data_enrichment_summary',
        'aggregated_scraped_data',
        'aggregated_data_enrichment',
        'all_non_fatal_errors',
        'all_exceptions',
        'all_specific_exception_reasons',
        'all_failed_downloads_summary',
    ]

    # Custom method to display a truncated Task UUID for list view
    def task_uuid_short(self, obj):
        return str(obj.task.uuid)[:8] + '...' if obj.task.uuid else 'N/A'
    task_uuid_short.short_description = 'Task UUID'
    task_uuid_short.admin_order_field = 'task__uuid' # Allows sorting by the full UUID

    # Custom method to display the full Task UUID in the detail view
    def task_uuid_display(self, obj):
        return str(obj.task.uuid)
    task_uuid_display.short_description = 'Full Task UUID'

    # Optional: Display a link to associated TaskAnalysisReports
    def view_task_analysis_reports(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse('admin:reporting_and_analytics_taskanalysisreport_changelist') + f'?task__uuid={obj.task.uuid}'
        return format_html('<a href="{}">View Reports ({})</a>', url, obj.total_reports_considered)
    view_task_analysis_reports.short_description = 'Associated Runs'
    # Consider adding 'view_task_analysis_reports' to list_display or a fieldset if desired.