from django.urls import path
from .views import update_task_summaries,TaskAnalysisReportListCreateAPIView,TaskSummaryReportListView,TaskSummaryReportDetailViewNew

urlpatterns = [
    # This single endpoint now handles both POST (ingestion) and GET (consumption)
    # for TaskAnalysisReport instances.
    path('task-reports/', TaskAnalysisReportListCreateAPIView.as_view(), name='task_report_list_create'),
    path('task-summaries/', TaskSummaryReportListView.as_view(), name='task_summary_list'),

    # 2. Retrieves a single TaskSummaryReport instance.
    #    The lookup is performed using the 'task_uuid' (UUID of the related Task).
    #    The '<uuid:task_uuid>' part captures a UUID from the URL and passes it as 'task_uuid' to the view.
    path('task-summaries/<uuid:task_uuid>/', TaskSummaryReportDetailViewNew.as_view(), name='task_summary_detail'),
    path('task-summaries/update/', update_task_summaries, name='update_task_summaries')
]