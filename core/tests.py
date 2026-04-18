from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from chat_api.models import LoginRateLimit


class HomePageTests(SimpleTestCase):
    def test_home_page_renders_question_first_console(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")
        self.assertContains(response, "Question-first tutoring sessions")
        self.assertContains(response, "/api/chat/login/")
        self.assertContains(response, "/api/chat/token/")
        self.assertContains(response, "/api/chat/courses/")
        self.assertContains(response, "/api/chat/sessions/")
        self.assertContains(response, "/api/chat/chat/")
        self.assertContains(response, "answerPhotosUrl")
        self.assertContains(response, "Submit Answer")
        self.assertContains(response, "Upload / Take Photos")
        self.assertContains(response, 'capture="environment"', html=False)
        self.assertContains(response, "Hint</button>")
        self.assertContains(response, "Skip</button>")
        self.assertContains(response, "Full Answer</button>")
        self.assertContains(response, "pending-photos")
        self.assertContains(response, "sessionDetailBaseUrl")
        self.assertContains(response, "marked.min.js")
        self.assertContains(response, "renderMarkdown")
        self.assertContains(response, "/course-questions/")
        self.assertContains(response, "/attempts/")

    def test_course_topics_page_renders_course_studio(self):
        response = self.client.get("/course-topics/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/course_topics.html")
        self.assertContains(response, "Course Studio")
        self.assertContains(response, "Create Course")
        self.assertContains(response, "Import Questions")
        self.assertContains(response, "Import Questions</button>")
        self.assertContains(response, "/api/chat/courses/")
        self.assertContains(response, "let availableCourses = [];")

    def test_attempts_page_renders_attempt_history_ui(self):
        response = self.client.get("/attempts/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/attempts.html")
        self.assertContains(response, "Question Attempts")
        self.assertContains(response, "Load Attempts")
        self.assertContains(response, "/api/chat/attempts/")
        self.assertContains(response, "let attempts = [];")
        self.assertContains(response, "Attached Photos")
        self.assertContains(response, "function renderPhotoGallery")

    def test_course_questions_page_renders_question_editor_ui(self):
        response = self.client.get("/course-questions/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/course_questions.html")
        self.assertContains(response, "Course Questions")
        self.assertContains(response, "Question Lookup")
        self.assertContains(response, "Search Question Text")
        self.assertContains(response, "Add Question")
        self.assertContains(response, "Update Question")
        self.assertContains(response, "Questions load automatically for the selected course.")
        self.assertContains(response, "--accent: #7a1838;")
        self.assertNotContains(response, "Import Key")
        self.assertContains(response, "/api/chat/courses/")
        self.assertContains(response, "loadSelectedCourseQuestions = true")
        self.assertContains(response, "function filteredQuestions()")
        self.assertContains(response, "question-lookup-select")
        self.assertContains(response, "let selectedQuestionId = null;")


class AdminLoginRateLimitTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="wonderland",
        )

    @override_settings(LOGIN_RATE_LIMIT_ATTEMPTS=2, LOGIN_RATE_LIMIT_WINDOW_SECONDS=60)
    def test_admin_login_rate_limit_blocks_after_repeated_failed_attempts(self):
        first_response = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})
        second_response = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})
        blocked_response = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(blocked_response.status_code, 429)
        self.assertTemplateUsed(blocked_response, "admin/login.html")
        self.assertContains(blocked_response, "Too many login attempts. Try again in", status_code=429)
        self.assertGreater(int(blocked_response["Retry-After"]), 0)

    @override_settings(LOGIN_RATE_LIMIT_ATTEMPTS=2, LOGIN_RATE_LIMIT_WINDOW_SECONDS=60)
    def test_successful_admin_login_clears_failed_attempts(self):
        first_failure = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})
        success_response = self.client.post("/admin/login/", {"username": "admin", "password": "wonderland"})

        self.assertEqual(first_failure.status_code, 200)
        self.assertEqual(success_response.status_code, 302)
        self.assertFalse(LoginRateLimit.objects.exists())

        self.client.logout()
        second_failure = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})
        third_failure = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})
        blocked_response = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})

        self.assertEqual(second_failure.status_code, 200)
        self.assertEqual(third_failure.status_code, 200)
        self.assertEqual(blocked_response.status_code, 429)

    @override_settings(LOGIN_RATE_LIMIT_ATTEMPTS=2, LOGIN_RATE_LIMIT_WINDOW_SECONDS=20)
    def test_admin_login_rate_limit_expires_after_window(self):
        start = timezone.now()
        request_times = [
            start,
            start + timedelta(seconds=1),
            start + timedelta(seconds=2),
            start + timedelta(seconds=22),
        ]

        with patch("core.views.get_rate_limit_now", side_effect=request_times):
            first_response = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})
            second_response = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})
            blocked_response = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})
            post_window_response = self.client.post("/admin/login/", {"username": "admin", "password": "wrong"})

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(blocked_response.status_code, 429)
        self.assertEqual(post_window_response.status_code, 200)
