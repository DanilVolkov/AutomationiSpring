from django.urls import path

from order import views

urlpatterns = [
    path('', views.OrderHome.as_view(), name='home'),
    path(
        'partial/folder-items/',
        views.FolderItemsPartialView.as_view(),
        name='folder_items_partial',
    ),
    path(
        'sync/courses/', views.SyncCoursesView.as_view(), name='sync_courses'
    ),
    path(
        'partial/users/',
        views.UsersPartialView.as_view(),
        name='partial_users',
    ),
    path('sync/users/', views.SyncUsersView.as_view(), name='sync_users'),
    path(
        'track/<str:track_id>/',
        views.TrackDetailView.as_view(),
        name='track_detail',
    ),
    path(
        'partial/track/<str:track_id>/',
        views.TrackDetailPartialView.as_view(),
        name='track_detail_partial',
    ),
    path('track/<str:track_id>/export.xlsx/',
             views.TrackExportExcelView.as_view(),
             name='track_export_xlsx'),
    path('track/<str:track_id>/upload-iva/',
             views.TrackUploadIvaView.as_view(),
             name='track_upload_iva'
    ),
]
