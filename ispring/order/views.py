from django.db import connection
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView
from ispring.settings import ISPRING_DEFAULT_FOLDER_ID

from order.models import User
from order.services import get_ispring_api
from order.utils import Table

# class OrderHome(TemplateView):
#     template_name = 'order/index.html'
#
#     def get(self, request, *args, **kwargs):
#         ispring_api = get_ispring_api()
#         if ispring_api.courses_tree is None:
#             ispring_api.set_courses_tree()
#         return super().get(request, *args, **kwargs)
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['title'] = 'Главная страница'
#         ispring_api = get_ispring_api()
#         # breadcrumbs = get_breadcrumbs()
#         item_id = self.request.GET.get('item_id')
#         if item_id:
#             context['items'] = ispring_api.get_folder_items(item_id)
#             context['breadcrumbs'] = ispring_api.get_parents_item(item_id)
#             # breadcrumbs.build_path(ispring_api.get_item_info(item_id))
#         else:
#             context['items'] = ispring_api.get_folder_items(
#                 ISPRING_DEFAULT_FOLDER_ID
#             )
#             context['breadcrumbs'] = []
#
#         return context


class OrderHome(TemplateView):
    template_name = 'order/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Главная страница'
        context['breadcrumbs'] = []
        return context


class SyncCoursesView(View):
    def post(self, request, *args, **kwargs):
        try:
            get_ispring_api().set_courses_tree()

            return JsonResponse({'ok': True})

        except RuntimeError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=502)


class SyncUsersView(View):
    def post(self, request, *args, **kwargs):
        try:
            users = get_ispring_api().get_users()
            objects = [
                User(
                    user_id=user['user_id'],
                    first_name=user['first_name'],
                    last_name=user['last_name'],
                    patronymic=user['patronymic'],
                    email=user['email'],
                )
                for user in users
            ]
            User.objects.all().delete()
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM sqlite_sequence WHERE name = 'order_user'"
                )
            User.objects.bulk_create(objects)
            return JsonResponse({'ok': True, 'count': User.objects.count()})

        except RuntimeError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=502)


class UsersPartialView(View):
    def get(self, request, *args, **kwargs):
        try:
            synced = False
            if not User.objects.exists():
                users = get_ispring_api().get_users()
                objects = [
                    User(
                        user_id=user['user_id'],
                        first_name=user['first_name'],
                        last_name=user['last_name'],
                        patronymic=user['patronymic'],
                        email=user['email'],
                    )
                    for user in users
                ]
                User.objects.bulk_create(objects)
                synced = True

            return JsonResponse({
                'ok': True,
                'count': User.objects.count(),
                'synced': synced,
            })
        except RuntimeError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=502)


class FolderItemsPartialView(View):
    def get(self, request, *args, **kwargs):
        item_id_raw = request.GET.get('item_id') or ''
        item_id = item_id_raw or ISPRING_DEFAULT_FOLDER_ID

        try:
            synced = False
            api = get_ispring_api()
            if api.items_tree is None:
                api.set_courses_tree()
                synced = True

            items = api.get_folder_items(item_id)
            breadcrumbs = api.get_parents_item(item_id) if item_id_raw else []

            list_html = render_to_string(
                'order/partials/_folder_items.html',
                {'items': items},
                request=request,
            )
            breadcrumbs_html = render_to_string(
                'order/partials/_breadcrumbs.html',
                {'breadcrumbs': breadcrumbs},
                request=request,
            )

            return JsonResponse({
                'ok': True,
                'html': list_html,
                'breadcrumbs_html': breadcrumbs_html,
                'synced': synced,
            })

        except RuntimeError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=502)


class TrackDetailView(TemplateView):
    template_name = 'order/track_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Траектория'
        context['track_id'] = self.kwargs['track_id']
        return context


class TrackDetailPartialView(View):
    def get(self, request, track_id, *args, **kwargs):
        try:
            api = get_ispring_api()
            learning_track = api.get_data_courses(track_id)
            # with open("data_results.json", "w", encoding="utf-8") as f:
            #     json.dump(asdict(learning_track), f, ensure_ascii=False,
            #     indent=4)
            breadcrumbs = api.get_parents_item(track_id) if track_id else []

            table_html = Table(learning_track).to_html()

            breadcrumbs_html = render_to_string(
                'order/partials/_breadcrumbs.html',
                {'breadcrumbs': breadcrumbs},
                request=request,
            )

            html = render_to_string(
                'order/partials/_track_detail.html',
                {
                    'learning_track': learning_track,
                    'table_html': table_html,
                },
                request=request,
            )

            return JsonResponse({
                'ok': True,
                'html': html,
                'breadcrumbs_html': breadcrumbs_html,
            })

        except RuntimeError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=502)
