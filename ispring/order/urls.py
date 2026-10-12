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
        'sync/courses/',
        views.SyncCoursesView.as_view(),
        name='sync_courses'
    ),
    path(
        'partial/users/',
        views.UsersPartialView.as_view(),
        name='partial_users',
    ),
    path(
        'sync/users/',
        views.SyncUsersView.as_view(),
        name='sync_users'
    ),
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
    path(
        'track/<str:track_id>/export.xlsx/',
        views.TrackExportExcelView.as_view(),
        name='track_export_xlsx'
    ),
    path('track/<str:track_id>/upload-iva/',
         views.TrackUploadIvaView.as_view(),
         name='track_upload_iva'),

    path('track/<str:track_id>/iva-select-course/',
         views.TrackIvaSelectCoursePageView.as_view(),
         name='track_iva_select_course'),

    path('track/<str:track_id>/iva-select-course/data/',
         views.TrackIvaSelectCourseDataView.as_view(),
         name='track_iva_select_course_data'),

    path('track/<str:track_id>/iva-select-course/apply/',
         views.TrackIvaSelectCourseApplyView.as_view(),
         name='track_iva_select_course_apply'),

    # 2. Страница разрешения конфликтов
    path('track/<str:track_id>/iva-conflicts/',
         views.TrackIvaConflictsPageView.as_view(),
         name='track_iva_conflicts'),

    # 2a. Данные для страницы конфликтов
    path('track/<str:track_id>/iva-conflicts/data/',
         views.TrackIvaConflictsDataView.as_view(),
         name='track_iva_conflicts_data'),

    # 2b. Сохранить решения и перейти к финальной таблице
    path('track/<str:track_id>/iva-conflicts/resolve/',
         views.TrackIvaConflictsResolveView.as_view(),
         name='track_iva_conflicts_resolve'),

    # 3. Финальная таблица IVA (редактируемая)
    path('track/<str:track_id>/iva-final/',
         views.TrackIvaFinalPageView.as_view(),
         name='track_iva_final'),

    # 3a. Данные финальной таблицы
    path('track/<str:track_id>/iva-final/data/',
         views.TrackIvaFinalDataView.as_view(),
         name='track_iva_final_data'),

    # 4. Применить — подгрузить в итоговую таблицу траектории
    path('track/<str:track_id>/iva-apply/',
         views.TrackIvaApplyView.as_view(),
         name='track_iva_apply'),
]
