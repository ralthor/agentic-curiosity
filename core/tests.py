from django.test import SimpleTestCase


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
