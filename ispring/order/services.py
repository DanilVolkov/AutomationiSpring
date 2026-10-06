import functools
import time
from collections import defaultdict
from functools import lru_cache

import requests
from ispring.settings import ISPRING_DEFAULT_FOLDER_ID
from requests import HTTPError

from ispring import settings
from order.models import User
from order.utils import (
    Course,
    Folder,
    LearningTrack,
    Module,
    UserResults,
    status_compliance,
)


class IspringApi:
    def __init__(
        self, host_token: str, host: str, client_id: str, client_secret: str
    ):
        self._host_token = host_token
        self._host = host
        self._client_id = client_id
        self._client_secret = client_secret
        self._set_token()
        # словарь, где ключ - id, а значение - список id потомков
        self.items_tree = None
        self._all_items_info = {}
        self._learning_track_ids = []

    def _set_token(self):
        url = f'{self._host_token}/api/v3/token'
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }
        data = {
            'client_id': self._client_id,
            'client_secret': self._client_secret,
            'grant_type': 'client_credentials',
        }
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        result = response.json()
        self._token = result.get('access_token')

    @staticmethod
    def request_with_token(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            for i in range(2):
                try:
                    return func(self, *args, **kwargs)
                except HTTPError as e:
                    if e.response is not None and e.response.status_code in [
                        400,
                        401,
                    ]:
                        self._set_token()
                        if i == 1:  # 2 попытка - вызываем исключение
                            raise HTTPError(
                                'Токен доступа неверный или '
                                'срок его действия истек'
                            ) from e
                        time.sleep(1)
                    else:
                        raise

        return wrapper

    def get_folder_items(self, folder_id):
        if self.items_tree is not None and folder_id in self.items_tree:
            folder_items = self.items_tree[folder_id]
            info_items = list(
                map(
                    lambda item_id: self._all_items_info.get(item_id, ''),
                    folder_items,
                )
            )
            return info_items
        return []

    def get_parents_item(self, item_id):
        result = []

        def search_parents_folder(i_id):
            item = self._all_items_info.get(i_id)
            if (
                item.parent_id is not None
                and item.parent_id != ISPRING_DEFAULT_FOLDER_ID
            ):
                search_parents_folder(item.parent_id)
            result.append(item)

        if item_id in self._all_items_info:
            search_parents_folder(item_id)

        return result

    def set_courses_tree(self):
        items = list(
            filter(
                lambda x: x['type'] in ['Folder', 'LearningTrack', 'Course'],
                self._get_courses_tree(),
            )
        )
        self.items_tree = defaultdict(list)
        for item in items:
            if item.get('type') == 'LearningTrack':
                self._all_items_info[item['itemId']] = LearningTrack(
                    id=item['itemId'],
                    title=item['title'],
                    type=item['type'],
                    added_date=item['addedDate'],
                    view_url=item['viewUrl'],
                    parent_id=item['parentId'],
                )
            elif item.get('type') == 'Folder':
                self._all_items_info[item['itemId']] = Folder(
                    id=item['itemId'],
                    title=item['title'],
                    type=item['type'],
                    parent_id=item.get('parentId'),
                )
            else:
                self._all_items_info[item['itemId']] = Course(
                    id=item['itemId'],
                    title=item['title'],
                    type=item['type'],
                    added_date=item['addedDate'],
                    view_url=item['viewUrl'],
                    parent_id=item['parentId'],
                )

            if 'parentId' in item and item['type'] != 'Course':
                self.items_tree[item['parentId']].append(item['itemId'])

        # Отбор только тех данных, что есть в папке ISPRING_DEFAULT_FOLDER_ID

        filtered_items = {}

        def search_children_folder(folder_id) -> dict:
            if folder_id in self.items_tree:
                children_ids = self.items_tree[folder_id]
                for children_id in children_ids:
                    search_children_folder(children_id)
                filtered_items[folder_id] = children_ids

        if ISPRING_DEFAULT_FOLDER_ID in self.items_tree:
            search_children_folder(ISPRING_DEFAULT_FOLDER_ID)
            items_no_empty = defaultdict(list)
            for k, v in filtered_items.items():
                for item_id in v:
                    item = self._all_items_info.get(item_id)
                    if not (
                        isinstance(item, Folder)
                        and item_id not in self.items_tree  # папка пустая
                    ):
                        items_no_empty[k].append(item_id)
                        if isinstance(item, LearningTrack):
                            self._learning_track_ids.append(item.id)

            self.items_tree = items_no_empty

        else:
            raise KeyError(
                f'Папки с id={ISPRING_DEFAULT_FOLDER_ID} не существует'
            )

        track_courses = self._get_learning_track_courses()

        # Дополнение структуры
        for folder_id, id_childs in self.items_tree.items():
            folder = self._all_items_info.get(folder_id)
            if isinstance(folder, Folder):
                folder.items = list(
                    map(lambda x: self._all_items_info[x], id_childs)
                )

        for track_id, id_courses in track_courses.items():
            track = self._all_items_info[track_id]
            courses = list(map(lambda x: self._all_items_info[x], id_courses))
            track.courses = courses

        # with open("get_courses_tree.json", "w", encoding="utf-8") as f:
        #     json.dump(
        #     {k: asdict(v) for k, v in self._all_items_info.items()},
        #     f, ensure_ascii=False, indent=4)

    @request_with_token
    def _get_courses_tree(self):
        url = f'{self._host}/course/tree'
        headers = {
            'Authorization': self._token,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        response = requests.post(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def _clean_users(self, users):
        cleaned_users = []
        for user in users:
            raw_fields = user.get('fields', [])

            fields = {}
            for item in raw_fields:
                name_key = str(item.get('name', '')).strip().upper()
                fields[name_key] = str(item.get('value', '') or '').strip()

            cleaned_user = {
                'user_id': user.get('userId'),
                'first_name': fields.get('FIRST_NAME', ''),
                'last_name': fields.get('LAST_NAME', ''),
                'patronymic': fields.get('PATRONYMIC', ''),
                'email': fields.get('EMAIL', ''),
            }

            if not cleaned_user['patronymic'] and cleaned_user['first_name']:
                name_parts = cleaned_user['first_name'].split()
                if len(name_parts) == 2:
                    cleaned_user['first_name'], cleaned_user['patronymic'] = (
                        name_parts[0],
                        name_parts[1],
                    )

            cleaned_users.append(cleaned_user)

        return cleaned_users

    @request_with_token
    def get_users(self):
        users = []
        url = f'{self._host}/users'
        headers = {
            'Authorization': self._token,
            'Accept': 'application/json',
        }

        count = 1
        next_token = None
        while count < 100:
            count += 1
            params = {'pageToken': next_token}
            response = requests.get(
                url, headers=headers, params=params, timeout=30
            )
            response.raise_for_status()
            data = response.json()

            users.extend(self._clean_users(data.get('userProfiles')))

            next_token = data.get('nextPageToken')
            if not next_token:
                break

            time.sleep(0.1)

        return users

    @request_with_token
    def _get_learning_track_courses(self):
        url = f'{self._host}/api/v2/learning_track/courses'
        headers = {
            'Authorization': self._token,
            'Accept': 'application/json',
        }
        result = defaultdict(list)
        for i in range(0, len(self._learning_track_ids), 50):
            batch = self._learning_track_ids[i : i + 50]
            params = {'learningTrackIds': ','.join(batch)}

            response = requests.get(
                url, headers=headers, params=params, timeout=30
            )
            response.raise_for_status()
            tracks_data = response.json()
            for item in tracks_data:
                result[item['learningTrackId']].append(item['courseId'])
            time.sleep(0.1)
        return result

    def get_data_courses(self, learning_track_id: str) -> LearningTrack:
        """Получение информации о курсах определенной траектории.

        Args:
            learning_track_id: ID курса.

        Returns:
            Возвращает данные о результатах пользователя по модулям всех курсов
            траектории.
        """
        courses = self._all_items_info[learning_track_id].courses
        id_courses = list(map(lambda x: x.id, courses))
        results = self._get_lessons_and_materials_results(id_courses)[
            'results'
        ]

        # with open("data_courses.json", "w", encoding="utf-8") as f:
        #     json.dump(results, f, ensure_ascii=False, indent=4)

        self._set_user_results(results)

        return self._all_items_info[learning_track_id]

    def _set_user_results(self, data):
        users = {}
        modules = {}
        courses = defaultdict(list)
        for item in data:
            if item['userId'] in users:
                user = users[item['userId']]
            else:
                user = User.objects.get(user_id=item['userId'])
                users[item['userId']] = user

            user_results = UserResults(
                user_id=item['userId'],
                fio=f'{user.last_name} '
                f'{user.first_name} '
                f'{user.patronymic}'.strip(),
                completion_status=status_compliance.get(
                    item['completionStatus'], item['completionStatus']
                ),
                progress=item.get('progress'),
                awarded_score=item.get('awardedScore'),
                passing_score=item.get('passingScore'),
            )
            if item['moduleId'] in modules:
                module = modules[item['moduleId']]
            else:
                module = Module(
                    id=item['moduleId'],
                    title=item['moduleTitle'],
                    course_id=item['courseId'],
                )
                modules[item['moduleId']] = module

            if module.result_users:
                module.result_users.append(user_results)
            else:
                module.result_users = [user_results]

            if module not in courses[item['courseId']]:
                courses[item['courseId']].append(module)

        for course_id, modules in courses.items():
            self._all_items_info[course_id].modules = modules

    @request_with_token
    def _get_lessons_and_materials_results(self, courses_id):
        """Получает результаты пользователей по материалам курсов.

        Args:
            courses_id: ID курсов.
        """
        url = f'{self._host}/learners/modules/results'
        headers = {
            'Authorization': self._token,
            'Accept': 'application/json',
        }
        params = {
            'courseIds[]': courses_id,
        }
        response = requests.get(
            url, headers=headers, params=params, timeout=30
        )
        response.raise_for_status()
        return response.json()


@lru_cache(maxsize=1)
def get_ispring_api() -> IspringApi:
    return IspringApi(
        host_token=settings.ISPRING_API_HOST_TOKEN,
        host=settings.ISPRING_API_HOST,
        client_id=settings.ISPRING_CLIENT_ID,
        client_secret=settings.ISPRING_CLIENT_SECRET,
    )
