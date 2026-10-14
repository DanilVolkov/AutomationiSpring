import csv
import io
import json
import uuid
from datetime import datetime, timedelta
from io import BytesIO

from django.core.cache import cache
from django.db import connection, transaction
from django.http import FileResponse, HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView
from ispring.settings import ISPRING_DEFAULT_FOLDER_ID

from order.models import Iva, User
from order.services import get_ispring_api
from order.utils import IvaHandler, IvaUser, Table

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

        except RuntimeError:
            return JsonResponse(
                {'ok': False, 'error': 'Произошла непредвиденная ошибка'},
                status=502,
            )


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

        except RuntimeError:
            return JsonResponse(
                {'ok': False, 'error': 'Произошла непредвиденная ошибка'},
                status=502,
            )


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
        except RuntimeError:
            return JsonResponse(
                {'ok': False, 'error': 'Произошла непредвиденная ошибка'},
                status=502,
            )


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

        except RuntimeError:
            return JsonResponse(
                {'ok': False, 'error': 'Произошла непредвиденная ошибка'},
                status=502,
            )


class TrackDetailView(TemplateView):
    template_name = 'order/track_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Траектория'
        context['track_id'] = self.kwargs['track_id']
        api = get_ispring_api()
        breadcrumbs = (
            api.get_parents_item(self.kwargs['track_id'])
            if self.kwargs['track_id']
            else []
        )

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
                # with open('data_results.json', 'w', encoding='utf-8') as f:
                #     json.dump(
                #         asdict(learning_track), f, ensure_ascii=False,
                #         indent=4
                #     )
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
        except User.DoesNotExist as e:
            return JsonResponse(
                {'ok': False, 'error': str(e)},
                status=400,
            )
        except RuntimeError:
            return JsonResponse(
                {'ok': False, 'error': 'Произошла непредвиденная ошибка'},
                status=502,
            )


class TrackShortPageView(TemplateView):
    """Страница сокращённой таблицы."""

    template_name = 'order/track_short.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['track_id'] = self.kwargs['track_id']
        context['table_mode'] = 'short'
        return context


class TrackShortPartialView(View):
    """Отдаёт HTML сокращённой таблицы + крошки."""

    def get(self, request, track_id, *args, **kwargs):
        try:
            table = cache.get('table')
            table_html = table.to_short_html()

            api = get_ispring_api()
            breadcrumbs = api.get_parents_item(track_id) if track_id else []
            breadcrumbs_html = render_to_string(
                'order/partials/_breadcrumbs.html',
                {'breadcrumbs': breadcrumbs},
                request=request,
            )

            return JsonResponse({
                'ok': True,
                'html': table_html,
                'breadcrumbs_html': breadcrumbs_html,
            })

        except RuntimeError:
            return JsonResponse(
                {'ok': False, 'error': 'Произошла непредвиденная ошибка'},
                status=502,
            )


class TrackExportExcelView(View):
    def get(self, request, track_id, *args, **kwargs):
        try:
            table = cache.get('table')
            if table is None or table.track.id != track_id:
                return JsonResponse(
                    {'ok': False, 'error': 'Данных для загрузки нет'},
                    status=502,
                )

            wb = table.to_excel()
            buffer = BytesIO()
            wb.save(buffer)
            buffer.seek(0)
            response = FileResponse(
                buffer,
                as_attachment=True,
                filename=(
                    f'{table.track.title} '
                    f'{datetime.now().strftime("%d.%m.%Y %H.%M.%S")}.xlsx'
                ),
                content_type=(
                    'application/vnd.openxmlformats-officedocument'
                    '.spreadsheetml.sheet'
                ),
            )
            return response

        except RuntimeError:
            return JsonResponse(
                {'ok': False, 'error': 'Произошла непредвиденная ошибка'},
                status=502,
            )


class TrackUploadIvaView(View):
    def post(self, request, track_id, *args, **kwargs):
        table = cache.get('table')
        if table is None or table.track.id != track_id:
            return JsonResponse(
                {'ok': False, 'error': 'Данных для загрузки нет'}, status=502
            )

        csv_file = request.FILES.get('file')
        if not csv_file:
            return JsonResponse(
                {'ok': False, 'error': 'Файл не передан'}, status=400
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
                    {'ok': False, 'error': 'Не удалось определить кодировку'},
                    status=400,
                )

            reader = csv.DictReader(io.StringIO(text), delimiter=';')
            rows = list(reader)
        except Exception as e:
            return JsonResponse(
                {'ok': False, 'error': f'Ошибка чтения CSV: {e}'}, status=400
            )

        track_users = table.track_users

        iva_rows = [
            IvaUser.make(
                id=str(uuid.uuid4()),
                fio=r['Имя участника'],
                email=r['Email/телефон'],
                entry_time=r['Время входа'],
                exit_time=r['Время выхода'],
                duration=r['Длительность'],
                device=r['Тип оборудования'],
                ip_address=r['IP-адрес'],
            )
            for r in rows
        ]

        iva_handler = IvaHandler(iva_rows, track_users)
        iva_handler.del_duplicates()
        iva_handler.find_user_db()
        conflicts = iva_handler.get_user_conflicts()

        cache.set('iva_rows', iva_handler.rows)
        cache.set('iva_conflicts', conflicts)

        return JsonResponse({
            'ok': True,
            'redirect': f'/track/{track_id}/iva-select-course/',
            'rows_count': len(iva_rows),
            'conflicts_count': len(conflicts),
        })


class TrackIvaSelectCoursePageView(TemplateView):
    template_name = 'order/track_iva_select_course.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['track_id'] = self.kwargs['track_id']
        return context


class TrackIvaSelectCourseDataView(View):
    """Отдаёт JSON со списком курсов траектории."""

    def get(self, request, track_id, *args, **kwargs):
        table = cache.get('table')
        if table is None or table.track.id != track_id:
            return JsonResponse(
                {'ok': False, 'error': 'Данных нет'}, status=404
            )

        try:
            courses = [
                {
                    'id': c.id,
                    'title': c.title,
                }
                for c in (table.track.courses or [])
            ]
        except Exception as e:
            return JsonResponse(
                {'ok': False, 'error': f'Ошибка чтения курсов: {e}'},
                status=500,
            )

        return JsonResponse({'ok': True, 'courses': courses})


class TrackIvaSelectCourseApplyView(View):
    """POST: пользователь выбрал курс. Кэширует и возвращает redirect."""

    def post(self, request, track_id, *args, **kwargs):
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse(
                {'ok': False, 'error': 'Некорректный JSON'}, status=400
            )

        course_id = payload.get('course_id')
        if not course_id:
            return JsonResponse(
                {'ok': False, 'error': 'Курс не выбран'}, status=400
            )

        cache.set('course_id', course_id)

        # ---------- Решаем, куда идти ----------
        conflicts = cache.get('iva_conflicts') or []
        if conflicts:
            redirect_url = f'/track/{track_id}/iva-conflicts/'
        else:
            redirect_url = f'/track/{track_id}/iva-final/'

        return JsonResponse({
            'ok': True,
            'redirect': redirect_url,
        })


class TrackIvaConflictsPageView(TemplateView):
    template_name = 'order/track_iva_conflicts.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['track_id'] = self.kwargs['track_id']
        return context


class TrackIvaConflictsDataView(View):
    """Отдаёт JSON со списком конфликтов — пар IvaUser."""

    def get(self, request, track_id, *args, **kwargs):
        conflicts = cache.get('iva_conflicts')
        if conflicts is None:
            return JsonResponse(
                {'ok': False, 'error': 'Конфликтов нет'}, status=404
            )

        def serialize(u: IvaUser) -> dict:
            return {
                'id': u.id,
                'fio': u.fio,
                'email': u.email or '',
                'entry_time': u.entry_time.strftime('%d.%m.%Y %H:%M'),
                'exit_time': u.exit_time.strftime('%d.%m.%Y %H:%M'),
                'duration': self._fmt_duration(u.duration),
                'device': u.device,
                'ip_address': u.ip_address,
                'user_id_ispring': u.user_id_ispring,
            }

        data = []
        for i, pair in enumerate(conflicts):
            left, right = pair[0], pair[1]
            data.append({
                'index': i,
                'left': serialize(left),
                'right': serialize(right),
            })

        return JsonResponse({'ok': True, 'conflicts': data})

    @staticmethod
    def _fmt_duration(td: timedelta) -> str:
        total = int(td.total_seconds())
        h, rem = divmod(total, 3600)
        m = rem // 60
        return f'{h} ч {m} мин'


class TrackIvaConflictsResolveView(View):
    """
    POST: пользователь сделал выбор по каждому конфликту.
    Для каждой пары:
      - выбранный IvaUser остаётся в iva_rows;
      - невыбранный удаляется по id.
    """

    def post(self, request, track_id, *args, **kwargs):
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse(
                {'ok': False, 'error': 'Некорректный JSON'}, status=400
            )

        choices = payload.get('choices', {})  # {index: 'left' | 'right'}

        conflicts = cache.get('iva_conflicts') or []
        iva_rows = cache.get('iva_rows') or []

        if not iva_rows:
            return JsonResponse(
                {'ok': False, 'error': 'Нет данных для разрешения'}, status=404
            )

        # ---------- Собираем id для удаления ----------
        to_remove_ids: set[str] = set()

        for idx_str, side in choices.items():
            try:
                idx = int(idx_str)
                left, right = conflicts[idx][0], conflicts[idx][1]
            except ValueError, IndexError:
                continue

            if side == 'left':
                to_remove_ids.add(right.id)  # удалить правого
            elif side == 'right':
                to_remove_ids.add(left.id)  # удалить левого

        # ---------- Фильтруем по id ----------
        iva_rows = [row for row in iva_rows if row.id not in to_remove_ids]

        # ---------- Обновляем кэш ----------
        cache.set('iva_rows', iva_rows)
        cache.delete('iva_conflicts')

        return JsonResponse({
            'ok': True,
            'redirect': f'/track/{track_id}/iva-final/',
            'removed': len(to_remove_ids),
        })

    @staticmethod
    def _find_pos(iva_rows: list[IvaUser], target: IvaUser) -> int:
        """
        Ищет позицию объекта в списке.
        Сравниваем по ссылке (is), чтобы не поймать ложное совпадение
        по == у dataclass.
        """
        for i, row in enumerate(iva_rows):
            if row is target:
                return i
        return -1


class TrackIvaFinalPageView(TemplateView):
    template_name = 'order/track_iva_final.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['track_id'] = self.kwargs['track_id']
        return context


class TrackIvaFinalDataView(View):
    def get(self, request, track_id, *args, **kwargs):
        iva_rows = cache.get('iva_rows')
        if iva_rows is None:
            return JsonResponse(
                {'ok': False, 'error': 'Нет данных для редактирования'},
                status=404,
            )

        db_users = [
            {
                'id': u.user_id,
                'fio': u.fio,
            }
            for u in cache.get('table').track_users.values()
        ]

        data = [
            {
                'id': row.id,
                'index': i,
                'fio': row.fio,
                'email': row.email or '',
                'entry_time': row.entry_time.strftime('%d.%m.%Y %H:%M'),
                'exit_time': row.exit_time.strftime('%d.%m.%Y %H:%M'),
                'duration_minutes': int(row.duration.total_seconds() // 60),
                # ←
                'device': row.device,
                'ip_address': row.ip_address,
                'user_id_ispring': row.user_id_ispring,
            }
            for i, row in enumerate(iva_rows)
        ]

        return JsonResponse({
            'ok': True,
            'iva_users': data,
            'db_users': db_users,
        })

    @staticmethod
    def _fmt_duration(td):
        total = int(td.total_seconds())
        h, rem = divmod(total, 3600)
        m = rem // 60
        return f'{h} ч {m} мин'


class TrackIvaApplyView(View):
    """POST: пересобирает iva_rows из присланного списка."""

    def post(self, request, track_id, *args, **kwargs):
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse(
                {'ok': False, 'error': 'Некорректный JSON'}, status=400
            )

        rows = payload.get('rows', [])
        if not isinstance(rows, list):
            return JsonResponse(
                {'ok': False, 'error': 'Некорректный формат rows'}, status=400
            )

        iva_rows = cache.get('iva_rows') or []
        by_id = {r.id: r for r in iva_rows}

        new_rows: list[IvaUser] = []

        for item in rows:
            try:
                row = by_id[item['id']]

                # обновляем поля
                row.fio = item.get('fio', row.fio)
                row.email = item.get('email') or None
                row.device = item.get('device', row.device)
                row.ip_address = item.get('ip_address', row.ip_address)
                row.user_id_ispring = item.get('user_id_ispring') or None

                # время
                row.entry_time = self._parse_dt(item.get('entry_time'))
                row.exit_time = self._parse_dt(item.get('exit_time'))

                # длительность
                minutes = int(item.get('duration_minutes') or 0)
                row.duration = timedelta(minutes=minutes)

                new_rows.append(row)

            except KeyError, ValueError, TypeError:
                continue

        track = cache.get('table').track
        cache.set('iva_rows', new_rows)
        course_id = cache.get('course_id')
        course_name = None
        match = list(filter(lambda c: course_id == c.id, track.courses))
        if match:
            course_name = match[0].title

        Iva.objects.filter(
            learning_track_id=track.id, course_id=course_id
        ).delete()
        db_obj = [
            Iva(
                learning_track_id=track.id,
                learning_track_name=track.title,
                course_id=course_id,
                course_name=course_name if course_name is not None else '',
                user_id=iva_user.user_id_ispring,
                fio=iva_user.fio,
                duration=int(iva_user.duration.total_seconds()),
            )
            for iva_user in new_rows
        ]
        Iva.objects.bulk_create(db_obj, batch_size=100)

        return JsonResponse({
            'ok': True,
            'redirect': f'/track/{track_id}/',
        })

    @staticmethod
    def _parse_dt(value: str):
        from datetime import datetime

        return datetime.strptime(' '.join(value.split()), '%d.%m.%Y %H:%M')


class TrackIvaCancelView(View):
    """POST: очищает все данные, связанные с загрузкой IVA."""

    def post(self, request, track_id, *args, **kwargs):
        cache.delete('iva_rows')
        cache.delete('iva_conflicts')
        return JsonResponse({'ok': True})


class IvaDownloadCsvView(View):
    def get(self, request, *args, **kwargs):
        response = HttpResponse(
            content_type='text/csv; charset=utf-8',
        )
        response['Content-Disposition'] = (
            'attachment; filename="iva_reports.csv"'
        )

        # BOM для Excel, чтобы русский корректно открывался
        response.write('\ufeff')

        writer = csv.writer(response, delimiter=';')

        # Заголовки — те же, что ждёт парсер при загрузке
        writer.writerow([
            'ID траектории',
            'Название траектории',
            'ID курса',
            'Название курса',
            'ID пользователя',
            'ФИО пользователя',
            'Длительность',
            'Время добавления',
        ])

        for r in Iva.objects.all():
            writer.writerow([
                r.learning_track_id,
                r.learning_track_name,
                r.course_id,
                r.course_name,
                r.user_id,
                r.fio,
                r.duration,
                r.created_at,
            ])

        return response


class IvaUploadCsvView(View):
    def post(self, request, *args, **kwargs):
        csv_file = request.FILES.get('file')
        if not csv_file:
            return JsonResponse(
                {'ok': False, 'error': 'Файл не передан'}, status=400
            )

        try:
            raw = csv_file.read()
            text = None
            for encoding in ('utf-8-sig', 'utf-8', 'cp1251'):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    pass
            if text is None:
                return JsonResponse(
                    {'ok': False, 'error': 'Не удалось определить кодировку'},
                    status=400,
                )

            reader = csv.DictReader(io.StringIO(text), delimiter=';')
            csv_rows = list(reader)
        except Exception as e:
            return JsonResponse(
                {'ok': False, 'error': f'Ошибка чтения CSV: {e}'}, status=400
            )

        created_count = 0
        updated_count = 0
        errors = []

        with transaction.atomic():
            for i, r in enumerate(csv_rows, start=2):
                try:
                    learning_track_id = r.get('ID траектории')
                    learning_track_name = r.get('Название траектории')
                    course_id = r.get('ID курса')
                    course_name = r.get('Название курса')
                    user_id = r.get('ID пользователя')
                    fio = r.get('ФИО пользователя')
                    duration = r.get('Длительность')
                    created_at = datetime.fromisoformat(
                        r.get('Время добавления')
                    )
                    obj, created = Iva.objects.get_or_create(
                        learning_track_id=learning_track_id,
                        course_id=course_id,
                        user_id=user_id,
                        defaults={
                            'learning_track_name': learning_track_name,
                            'course_name': course_name,
                            'fio': fio,
                            'duration': duration,
                            'created_at': created_at,
                        },
                    )

                    if created:
                        created_count += 1

                    if not created and created_at > obj.created_at:
                        obj.learning_track_name = learning_track_name
                        obj.course_name = course_name
                        obj.fio = fio
                        obj.duration = duration
                        obj.created_at = created_at
                        obj.save(
                            update_fields=[
                                'learning_track_name',
                                'course_name',
                                'fio',
                                'duration',
                                'created_at',
                            ]
                        )
                        updated_count += 1
                except Exception as e:
                    errors.append(f'Строка {i}: {e}')

        return JsonResponse({
            'ok': True,
            'created': created_count,
            'updated': updated_count,
            'errors': errors[:50],
            'total': len(csv_rows),
        })
