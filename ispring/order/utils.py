import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.template.loader import render_to_string
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from order.models import Iva

status_compliance = {
    'not_started': 'Не начато',
    'in_progress': 'В процессе',
    'pending': 'Ожидает проверки',
    'complete': 'Завершено',
    'passed': 'Пройдено',
    'accepted': 'Принято',
    'incomplete': 'Не завершено',
    'failed': 'Не пройдено',
    'declined': 'Отклонено',
}


@dataclass
class IvaUser:
    id: str
    fio: str
    email: str | None
    entry_time: datetime
    exit_time: datetime
    duration: timedelta
    device: str
    ip_address: str
    user_id_ispring: str | None = None

    @staticmethod
    def _str_to_datetime(s: str) -> datetime:
        return datetime.strptime(' '.join(s.split()), '%d.%m.%Y %H:%M')

    @classmethod
    def make(
            cls,
            id: str,
            fio: str,
            email: str,
            entry_time: str,
            exit_time: str,
            duration: str,
            device: str,
            ip_address: str,
    ):
        _entry_time = cls._str_to_datetime(entry_time)
        _exit_time = cls._str_to_datetime(exit_time)
        r = re.compile(r'(\d+)\s*час\w*\s*(\d+)\s*минут\w*', re.IGNORECASE)
        match = r.search(duration)
        if not match:
            _duration = timedelta(0)
        else:
            _duration = timedelta(
                hours=int(match.group(1)), minutes=int(match.group(2))
            )
        return cls(
            id,
            fio,
            email,
            _entry_time,
            _exit_time,
            _duration,
            device,
            ip_address,
        )


@dataclass
class Folder:
    id: str
    type: str
    title: str
    parent_id: str | None = None
    items: list[LearningTrack | Course] | None = None


@dataclass
class LearningTrack:
    id: str
    title: str
    type: str
    added_date: str
    view_url: str
    parent_id: str
    courses: list[Course] = None

    def __post_init__(self):
        self.added_date = datetime.fromisoformat(self.added_date).strftime(
            '%d.%m.%Y'
        )


@dataclass
class Course:
    id: str
    title: str
    type: str
    added_date: str
    view_url: str
    parent_id: str
    modules: list[Module] = None

    def __post_init__(self):
        self.added_date = datetime.fromisoformat(self.added_date).strftime(
            '%d.%m.%Y'
        )


@dataclass
class Module:
    id: str
    title: str
    course_id: str
    result_users: list[UserResults] = None


@dataclass
class UserResults:
    user_id: str
    fio: str
    completion_status: str = None
    progress: float | int | None = None
    awarded_score: float | int | None = None  # только в дз
    passing_score: float | int | None = None  # только в дз


@dataclass
class Cell:
    value: str
    module_id: str = None
    colspan: int = 1
    rowspan: int = 1
    skip: bool = False
    css: str = ''
    note: str = ''


class Table:
    module_stub_fields: list[str] = [
        'Лекция iSpring',
        'Лекция IVA',
        'Лекция итог',
        'ДЗ порог',
        'ДЗ прогресс',
        'ДЗ итог',
    ]

    item_extensions = (
        '.mp4',
        '.avi',
        '.mkv',
        '.mov',
        '.wmv',
        '.flv',
        '.webm',
        '.m4v',
        '.mpg',
        '.mpeg',
        '.3gp',
        '.3g2',
        '.ogv',
        '.ts',
        '.mts',
        '.m2ts',
        '.vob',
        '.rm',
        '.rmvb',
        '.asf',
        '.divx',
        '.f4v',
        '.swf',
    )

    fill_map = {
        'table-success': 'D4EDDA',
        'table-danger': 'F8D7DA',
        'table-warning': 'FFF3CD',
        'table-info': 'CFE2FF',
        'table-primary': 'CFE2FF',
    }

    def __init__(
            self,
            learning_track: LearningTrack,
    ):
        self.track = learning_track
        self.track_users = self._collect_users()

    def to_excel(self):
        header_top, header_bottom, rows = self._build_table()
        wb = Workbook()
        ws = wb.active
        ws.title = 'Подробно'
        self._write_excel(
            ws,
            header_top,
            header_bottom,
            rows
        )
        ws = wb.create_sheet('Посещения', 0)

        header_top, new_header_bottom, new_rows = self._short_table(
            header_top,
            header_bottom,
            rows
        )
        self._write_excel(
            ws,
            header_top,
            new_header_bottom,
            new_rows
        )

        return wb

    def _parse_css(self, css: str):
        fill = border = None
        for item in css.split():
            if item in self.fill_map:
                fill = PatternFill(
                    start_color=self.fill_map[item],
                    end_color=self.fill_map[item],
                    fill_type='solid',
                )

        if 'border-dark' in css:
            medium = Side(style='medium', color='000000')
            if 'border-bottom' in css:
                border = Border(
                    right=medium,
                    bottom=medium,
                )
            else:
                border = Border(
                    right=medium,
                    bottom=Side(style="thin", color='000000')
                )
        else:
            thin = Side(style="thin", color='000000')
            border = Border(
                left=thin,
                right=thin,
                top=thin,
                bottom=thin,
            )

        return fill, border

    def _apply_cell_style(
            self, excel_cell, cell: Cell, is_header: bool = False
    ):
        fill, border = self._parse_css(cell.css)

        if fill:
            excel_cell.fill = fill
        if border:
            excel_cell.border = border

        excel_cell.alignment = Alignment(
            horizontal='center',
            vertical='center',
            wrap_text=True,
        )
        if is_header:
            excel_cell.font = Font(bold=True)

    @staticmethod
    def _autosize_columns(ws):

        def cell_text_len(value):
            s = str(value)
            lines = s.splitlines() or [s]
            return max(len(line) for line in lines)

        max_len = {}

        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                col = cell.column
                cell_length = cell_text_len(cell.value)
                if cell_length > max_len.get(col, 0):
                    max_len[col] = cell_length
        for col_idx, cell_length in max_len.items():
            letter = get_column_letter(col_idx)

            # Эвристика:
            # - +2 символа на `воздух`
            # - масштаб по размеру шрифта
            # - маленький коэффициент для компенсации ширины кириллицы/Calibri
            width = cell_length + 2

            # Ограничим разумными границами, чтобы не улетало
            width = min(max(width, 8), 25)

            ws.column_dimensions[letter].width = width

    def _write_excel(self, ws, header_top, header_bottom, rows):
        # Курсы
        col = 1
        for cell in header_top:
            if cell.skip:
                col += cell.colspan
                continue

            excel_cell = ws.cell(row=1, column=col, value=cell.value)
            self._apply_cell_style(excel_cell, cell, is_header=True)

            end_row = cell.rowspan
            end_col = col + (cell.colspan - 1)

            if cell.colspan > 1 or cell.rowspan > 1:
                ws.merge_cells(
                    start_row=1,
                    start_column=col,
                    end_row=end_row,
                    end_column=end_col,
                )
                # Проставляем стиль всем ячейкам merge — иначе границы пропадут
                for r in range(1, end_row + 1):
                    for c in range(col, end_col + 1):
                        self._apply_cell_style(
                            ws.cell(row=r, column=c), cell, is_header=True
                        )
            col += cell.colspan

        # Модули
        col = 3
        for cell in header_bottom:
            if cell.skip:
                col += cell.colspan
                continue

            excel_cell = ws.cell(row=2, column=col, value=cell.value)
            self._apply_cell_style(excel_cell, cell, is_header=True)

            col += cell.colspan

        # Данные
        start_data_row = 3
        for i, row in enumerate(rows):
            r = start_data_row + i
            col = 1

            for cell in row:
                if cell.skip:
                    col += cell.colspan
                    continue

                v = cell.value
                regex = re.compile(r'^\d+\.?\d*$')
                if regex.match(v):
                    if v.isdigit():
                        v = int(v)
                    else:
                        v = float(v)

                excel_cell = ws.cell(row=r, column=col, value=v)
                self._apply_cell_style(excel_cell, cell, is_header=False)

                col += cell.colspan

        for row in range(1, ws.max_row + 1):
            ws.cell(row=row, column=2).alignment = Alignment(
                horizontal='left',
                vertical='center',
                wrap_text=True,
            )

        self._autosize_columns(ws)
        ws.freeze_panes = 'C3'

    def to_html(self) -> str:
        header_top, header_bottom, rows = self._build_table()

        return render_to_string(
            'order/partials/_track_table.html',
            {
                'header_top': header_top,
                'header_bottom': header_bottom,
                'rows': rows,
            },
        )

    @staticmethod
    def _short_table(header_top, header_bottom, rows):
        new_header_bottom: list[Cell] = []
        new_rows: list[list[Cell]] = []

        counter_colspan = 0
        colspans = [c.colspan for c in header_top[2:]]
        for hb_cell in header_bottom:
            if hb_cell.value in ['Лекция итог', 'ДЗ итог']:
                new_header_bottom.append(hb_cell)
            else:
                colspans[counter_colspan] -= 1
            if hb_cell.note == 'end':
                counter_colspan += 1

        for i, colspan in enumerate(colspans, start=2):
            header_top[i].colspan = colspan

        for row in rows:
            new_row: list[Cell] = []
            for cell in row:
                if cell.note in ['№', 'ФИО', 'Лекция итог', 'ДЗ итог']:
                    new_row.append(cell)
            new_rows.append(new_row)
        return header_top, new_header_bottom, new_rows

    def to_short_html(self) -> str:
        header_top, header_bottom, rows = self._build_table()

        header_top, new_header_bottom, new_rows = self._short_table(header_top,
                                                                    header_bottom,
                                                                    rows)

        return render_to_string(
            'order/partials/_track_table.html',
            {
                'header_top': header_top,
                'header_bottom': new_header_bottom,
                'rows': new_rows,
            },
        )

    def _build_table(self):
        header_bottom, course_headers = self._build_header_bottom()
        header_top = self._build_header_top(course_headers)
        rows = self._build_rows(course_headers)

        return header_top, header_bottom, rows

    def _build_header_top(self, course_headers) -> list[Cell]:
        header: list[Cell] = [
            Cell(
                value='№',
                rowspan=2,
                css='border-dark border-end border-bottom',
            ),
            Cell(
                value='ФИО',
                rowspan=2,
                css='border-dark border-end border-bottom',
            ),
        ]

        for course in self.track.courses:
            header.append(
                Cell(
                    value=course.title,
                    colspan=len(course_headers[course.id]),
                    css='border-dark border-end border-bottom',
                )
            )

        return header

    def _get_type_item(self, module: Module) -> str:
        if module.title.endswith(self.item_extensions):
            return 'video'

        if module.result_users is not None and len(module.result_users) > 0:
            is_hw = any(
                map(
                    lambda x: (
                        True
                        if (
                                x.passing_score is not None
                                and x.awarded_score is not None
                        )
                        else False
                    ),
                    module.result_users,
                )
            )
            if is_hw:
                return 'hw'

        return 'other'

    def _build_header_bottom(self) -> tuple[list[Cell], dict[str, list[Cell]]]:
        header: list[Cell] = []
        course_headers: dict[str, list] = defaultdict(list)
        lecture_headers = tuple(
            map(
                lambda x: Cell(
                    value=x, css='module border-bottom border-dark'
                ),
                self.module_stub_fields[:3],
            )
        )
        hw_headers = tuple(
            map(
                lambda x: Cell(
                    value=x, css='module border-bottom border-dark'
                ),
                self.module_stub_fields[3:],
            )
        )
        for course in self.track.courses:
            if not course.modules:
                # Пустой курс — пустая ячейка в нижней шапке.
                header.append(
                    Cell(value='', css='border-dark border-end border-bottom')
                )
                course_headers[course.id].append(
                    Cell(value='', css='border-dark border-end border-bottom')
                )
                continue

            lecture = []
            hw = []
            others = []
            for module in course.modules:
                module_type = self._get_type_item(module)
                if module_type == 'video' and len(lecture) == 0:
                    for c in lecture_headers:
                        lecture.append(
                            Cell(module_id=module.id, value=c.value, css=c.css)
                        )
                elif module_type == 'hw' and len(hw) == 0:
                    for c in hw_headers:
                        hw.append(
                            Cell(module_id=module.id, value=c.value, css=c.css)
                        )
                else:
                    others.append(
                        Cell(
                            module_id=module.id,
                            value=module.title,
                            css='module border-dark border-bottom',
                        )
                    )

            if len(lecture) > 0:
                header.extend(lecture)
                course_headers[course.id].extend(lecture)
            if len(hw) > 0:
                header.extend(hw)
                course_headers[course.id].extend(hw)
            if len(others) > 0:
                header.extend(others)
                course_headers[course.id].extend(others)
            course_headers[course.id][-1].note = 'end'

        return header, course_headers

    def _collect_users(self) -> dict[str, UserResults]:
        users: dict[str, UserResults] = dict()
        for course in self.track.courses:
            if not course.modules:
                continue
            for module in course.modules:
                for user in module.result_users:
                    if user.user_id not in users:
                        users[user.user_id] = UserResults(
                            user_id=user.user_id, fio=user.fio
                        )
        return dict(
            sorted(users.items(), key=lambda item: (item[1].fio or '').lower())
        )

    def _build_rows(
            self, course_headers: dict[str, list[Cell]]
    ) -> list[list[Cell]]:
        rows: list[list[Cell]] = []

        data_iva = Iva.objects.filter(learning_track_id=self.track.id).values(
            'course_id', 'user_id', 'duration')
        durations: dict[str, dict[str, int]] = {}
        for d in data_iva:
            course_id = str(d['course_id'])
            user_id = str(d['user_id'])
            if course_id in durations:
                if user_id not in durations[course_id]:
                    durations[course_id][user_id] = d['duration']
            else:
                durations[course_id] = {user_id: d['duration']}

        for course_id, course_dict in durations.items():
            durations_sorted = sorted(list(course_dict.values()))
            duration_median = statistics.median(durations_sorted)
            course_dict['duration_median'] = int(duration_median)

        for idx, (user_id, ur) in enumerate(self.track_users.items(), start=1):
            row: list[Cell] = [
                Cell(value=str(idx), css='border-dark border-end', note='№'),
                Cell(value=(ur.fio or ''), css='border-dark border-end',
                     note='ФИО'),
            ]

            for course in self.track.courses:
                if not course.modules:
                    row.append(Cell(value='', css='empty'))
                    continue

                user_duration = None
                duration_median = None
                if durations and course.id in durations and user_id in \
                        durations[course.id]:
                    user_duration = durations[course.id][user_id]
                    duration_median = durations[course.id]['duration_median']

                for header in course_headers[course.id]:
                    module: Module | None = None

                    if header.module_id is None:
                        row.append(Cell(value='', css='empty'))
                        continue

                    for m in course.modules:
                        if header.module_id == m.id:
                            module = m
                            break

                    if module is None:
                        row.append(Cell(value='', css='empty'))
                        continue

                    user_results = self._find_user_results_in_module(
                        module, user_id
                    )
                    row.append(self._make_cell(header.value, user_results,
                                               user_duration, duration_median))
                row[-1].css += ' border-dark border-end'
                row[-1].css.strip()
            rows.append(row)
        return rows

    @staticmethod
    def _find_user_results_in_module(
            module: Module, user_id: str
    ) -> UserResults | None:
        for r in module.result_users:
            if r.user_id == user_id:
                return r
        return None

    @staticmethod
    def parse_duration(duration: int) -> tuple[int, int]:
        h, rem = divmod(duration, 3600)
        m = rem // 60
        return h, m

    @staticmethod
    def _make_cell(header: str, ur: UserResults | None,
                   user_duration: int | None,
                   duration_median: float | None) -> Cell:
        if ur is None:
            return Cell(value='Нет результата', css='empty')

        match header:
            case 'Лекция iSpring':
                return Cell(value=Table._format_value(ur.progress))

            case 'Лекция IVA':
                result = ''
                if user_duration is not None:
                    h, m = Table.parse_duration(user_duration)
                    result = f'{h}:{m:02d}'
                if user_duration is not None and duration_median is not None:
                    duration_result = int(duration_median * 0.7)
                    h, m = Table.parse_duration(duration_result)
                    result += f' / {h}:{m:02d}'
                    diff = user_duration - duration_result + 1
                    h, m = Table.parse_duration(abs(int(diff)))
                    result += ' (+' if int(diff) >= 0 else ' (-'
                    result += f'{h}:{m:02d})'
                return Cell(value=result)

            case 'Лекция итог':
                result = False
                if user_duration is not None and duration_median is not None:
                    if (
                            (
                                    ur.progress is not None and ur.progress >= 74.0) or
                            # 70% времени был на лекции в IVA
                            (user_duration >= (duration_median * 0.7))
                    ):
                        result = True
                elif ur.progress is not None and ur.progress is not None and ur.progress >= 74.0:
                    result = True

                if result:
                    return Cell(value=str(int(result)), css='table-success',
                                note='Лекция итог')
                else:
                    return Cell(value=str(int(result)), css='table-danger',
                                note='Лекция итог')

            case 'ДЗ порог':
                return Cell(value=Table._format_value(ur.passing_score))

            case 'ДЗ прогресс':
                result = ur.progress
                if (ur.progress is None and ur.awarded_score is not None) or (
                        ur.progress is not None
                        and ur.awarded_score is not None
                        and ur.progress != ur.awarded_score
                ):
                    result = ur.awarded_score
                return Cell(value=Table._format_value(result))

            case 'ДЗ итог':
                result = ''
                css = ''
                if ur.completion_status is not None:
                    match ur.completion_status:
                        case 'Не начато':
                            css = 'table-warning'
                        case 'В процессе':
                            css = 'table-info'
                        case 'Принято':
                            css = 'table-success'
                        case 'Отклонено':
                            css = 'table-danger'
                        case 'Ожидает проверки':
                            css = 'table-primary'
                    result = ur.completion_status
                else:
                    ps = Table._format_value(ur.passing_score)
                    p = Table._format_value(ur.progress)
                    if ps != '' and p != '':
                        if ur.progress >= ur.passing_score:
                            result = 'Принято'
                            css = 'table-success'
                        else:
                            result = 'Отклонено'
                            css = 'table-danger'

                return Cell(value=result, css=css, note='ДЗ итог')

        return Cell(value=Table._format_value(ur.progress))

    @staticmethod
    def _format_value(value) -> str:
        if value is None:
            return ''
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)


class IvaHandler:
    def __init__(self, data, track_users):
        self.rows: list[IvaUser] = data
        self.track_users = track_users

    def _del_duplicate_fio(self):
        unique_fio: dict[str, IvaUser] = {}
        for r in self.rows:
            if r.fio in unique_fio:
                unique_fio[r.fio].duration += r.duration
            else:
                unique_fio[r.fio] = r
        return list(unique_fio.values())

    def _del_duplicate_ip(self):
        unique_ip: dict[str, IvaUser] = {}
        for r in self.rows:
            if r.ip_address in unique_ip:
                unique_ip[r.ip_address].duration += r.duration
                if (
                        len(unique_ip[r.ip_address].fio) < len(r.fio)
                        and not unique_ip[r.ip_address].email
                ):
                    unique_ip[r.ip_address].fio = r.fio
            else:
                unique_ip[r.ip_address] = r
        return list(unique_ip.values())

    def find_user_db(self):
        for r in self.rows:
            name_participant = r.fio.split()
            for u in self.track_users.values():
                max_count = len(u.fio.split())
                count = len(
                    list(filter(lambda np: np in u.fio, name_participant))
                )
                if count >= max_count:
                    r.user_id_ispring = u.user_id

    def del_duplicates(self):
        self.rows = self._del_duplicate_fio()
        self.rows = self._del_duplicate_ip()

    def get_user_conflicts(self) -> list[list[IvaUser]]:
        conflicts: list[list[IvaUser]] = []
        for row_1 in self.rows:
            for row_2 in self.rows:
                if row_1 == row_2:
                    continue
                if row_1.fio in row_2.fio:
                    conflicts.append([row_1, row_2])
        return conflicts
