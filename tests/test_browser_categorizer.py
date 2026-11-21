import pytest

from app_tracker.browser.categorizer import categorize_url


@pytest.mark.parametrize(
    "url, title, expected",
    [
        ("https://university.kz/materials/lecture.pdf", "Lecture 4", "Учёба"),
        ("https://youtube.com/watch?v=1", "Physics Lecture 4", "Учёба"),
        ("https://youtube.com/watch?v=1", "Funny cats", "Развлечения"),
        ("https://m.youtube.com/watch?v=1", "Funny cats", "Развлечения"),
        ("https://www.netflix.com/", "Netflix", "Развлечения"),
        ("https://github.com/a/b", "b", "Код / Разработка"),
        ("https://vk.com/feed", "VK", "Соцсети"),
        ("https://moodle.univer.kz/course/1", "Course", "Учёба"),
        ("https://example.com", "Example", "Другое"),
        ("https://example.com", "", "Другое"),
        ("https://example.com", "Exam results", "Учёба"),
        ("https://example.com", "Лекции по физике", "Учёба"),
    ],
)
def test_categories(url, title, expected):
    assert categorize_url(url, title) == expected


def test_x_com_does_not_match_inside_other_names():
    # "x.com" must not match "netflix.com" or "box.com".
    assert categorize_url("https://box.com/", "Box") == "Другое"
