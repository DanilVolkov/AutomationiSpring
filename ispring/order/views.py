import csv
import io
import json
import tempfile
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from io import BytesIO

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse, FileResponse
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView
from ispring.settings import ISPRING_DEFAULT_FOLDER_ID

from order.models import User
from order.services import get_ispring_api
from order.utils import Table, IvaUser


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
        api = get_ispring_api()
        breadcrumbs = api.get_parents_item(self.kwargs['track_id']) if self.kwargs['track_id'] else []

        context['breadcrumbs'] = breadcrumbs

        return context


class TrackDetailPartialView(View):
    def get(self, request, track_id, *args, **kwargs):
        try:
            cache.set('table', None)
            api = get_ispring_api()
            learning_track = api.get_data_courses(track_id)
            table_html = None
            if learning_track:
                with open("data_results.json", "w", encoding="utf-8") as f:
                    json.dump(asdict(learning_track), f, ensure_ascii=False,
                    indent=4)
                table = Table(learning_track)
                cache.set('table', table)
                table_html = table.to_html()

            breadcrumbs = api.get_parents_item(track_id) if track_id else []
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


class TrackExportExcelView(View):

    def get(self, request, track_id, *args, **kwargs):
        try:
            table = cache.get('table')
            if table is None or table.track.id != track_id:
                return JsonResponse({'ok': False, 'error': 'Данных для загрузки нет'}, status=502)

            wb = table.to_excel()
            buffer = BytesIO()
            wb.save(buffer)
            buffer.seek(0)
            response = FileResponse(
                buffer,
                as_attachment=True,
                filename=f'{table.track.title} {datetime.now().strftime('%d.%m.%Y %H.%M.%S')}.xlsx',
                content_type=(
                    'application/vnd.openxmlformats-officedocument'
                    '.spreadsheetml.sheet'
                ),
            )
            return response

        except RuntimeError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=502)


class TrackUploadIvaView(View):

    def post(self, request, track_id, *args, **kwargs):
        table = cache.get('table')
        if table is None or table.track.id != track_id:
            return JsonResponse(
                {'ok': False, 'error': 'Данных для загрузки нет'}, status=502)

        csv_file = request.FILES.get('file')
        if not csv_file:
            return JsonResponse(
                {'ok': False, 'error': 'Файл не передан'},
                status=400,
            )

        try:
            raw = csv_file.read()
            for encoding in ('utf-8-sig', 'utf-8', 'cp1251'):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    pass
            else:
                return JsonResponse(
                    {'ok': False, 'error': 'Не удалось определить кодировку файла'},
                    status=400,
                )

            reader = csv.DictReader(io.StringIO(text), delimiter=';')
            rows = list(reader)
        except Exception as e:
            return JsonResponse(
                {'ok': False, 'error': f'Ошибка чтения CSV: {e}'},
                status=400,
            )

        # Удаление дубликатов
        track_users = table.track_users
        rows = list(map(
            lambda r: IvaUser.make(
                fio=r['Имя участника'],
                email=r['Email/телефон'],
                entry_time=r['Время входа'],
                exit_time=r['Время выхода'],
                duration=r['Длительность'],
                device=r['Тип оборудования'],
                ip_address=r['IP-адрес']
            ), rows
        ))
        unique_fio: dict[str, IvaUser] = {}
        for r in rows:
            if r.fio in unique_fio:
                unique_fio[r.fio].duration += r.duration
            else:
                unique_fio[r.fio] = r
        rows = list(unique_fio.values())

        unique_ip: dict[str, IvaUser] = {}
        for r in rows:
            if r.ip_address in unique_ip:
                unique_ip[r.ip_address].duration += r.duration
                if len(unique_ip[r.ip_address].fio) < len(r.fio) and not unique_ip[r.ip_address].email:
                    unique_ip[r.ip_address].fio = r.fio
            else:
                unique_ip[r.ip_address] = r
        rows = list(unique_ip.values())

        for r in rows:
            name_participant = r.fio.split()
            for u in track_users.values():
                max_count = len(u.fio.split())
                count = len(list(filter(
                    lambda np: np in u.fio, name_participant
                )))
                if count >= max_count:
                    r.user_id_ispring = u.user_id

        for row in rows:
            print(f'fio: {row.fio}; user_id_ispring: {row.user_id_ispring}')

        conflicts = defaultdict(list)
        for row_1 in rows:
            for row_2 in rows:
                if row_1 == row_2:
                    continue
                if row_1.fio in row_2.fio:
                    conflicts[row_1.fio].append(row_2.fio)

        # TODO: один и тот же человек или нет - решает пользователь в диалоге с ним
        # Диалог в формате опроса на 1 странице - это один и тот же человек или нет?
        # Далее мы получаем от пользователя форму и обрабатываем её.
        # При обработке сопоставляем, какой выбор сделал пользователь и учитываем
        # у кого удалить дубликат и сложить имя, а кого оставить.
        # Далее уже показываем пользователю итоговую таблицу.










        # try:
        #     cleaned_rows, conflicts = validate_iva_rows(rows)
        # except Exception as e:
        #     logger.exception('Ошибка валидации IVA')
        #     return JsonResponse(
        #         {'ok': False, 'error': f'Ошибка валидации: {e}'},
        #         status=500,
        #     )

        # ---------- 3. Если есть конфликты — отдаём диалог ----------
        # if conflicts:
        #     return JsonResponse({
        #         'ok': False,
        #         'dialog': True,
        #         'conflicts': conflicts,        # структура — на твоё усмотрение
        #         'rows_count': len(rows),
        #     })

        # ---------- 4. Конфликтов нет — рендерим таблицу ----------
        try:
            api = get_ispring_api()
            learning_track = api.get_learning_track(track_id)

            # Куда-то применить cleaned_rows — реши сам:
            # например, learning_track.apply_iva(cleaned_rows)
            # или сразу в Table передать, если Table умеет с ними работать.

            table_html = Table(learning_track).to_html()
        except RuntimeError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=502)

        return JsonResponse({
            'ok': True,
            'html': table_html,
            'rows_count': len(rows),
        })
