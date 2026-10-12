from django.db import models


class User(models.Model):
    user_id = models.UUIDField(verbose_name='ID пользователя')
    first_name = models.CharField(
        max_length=255, verbose_name='Имя', blank=True
    )
    last_name = models.CharField(
        max_length=255, verbose_name='Фамилия', blank=True
    )
    patronymic = models.CharField(
        max_length=255, verbose_name='Отчество', blank=True
    )

    class Meta:
        ordering = ['last_name', 'first_name', 'patronymic']

    def __str__(self):
        return (
            f'{self.user_id} '
            f'({self.first_name} {self.last_name} {self.patronymic})'
        )


class Iva(models.Model):
    learning_track_id = models.UUIDField(verbose_name='ID траектории')
    learning_track_name = models.CharField(
        verbose_name='Название траектории', blank=True
    )
    course_id = models.UUIDField(verbose_name='ID курса')
    course_name = models.CharField(verbose_name='Название курса', blank=True)
    user_id = models.UUIDField(verbose_name='ID пользователя')
    fio = models.CharField(verbose_name='ФИО пользователя', blank=True)
    duration = models.IntegerField(verbose_name='Длительность в минутах')

    def __str__(self):
        return (
            f'{self.learning_track_name} ({self.learning_track_id}) -> '
            f'{self.course_id} ({self.course_name}) -> '
            f'{self.user_id} ({self.fio}) - {self.duration}'
        )
