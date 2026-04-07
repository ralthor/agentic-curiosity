from django.test import SimpleTestCase


class HomePageTests(SimpleTestCase):
    def test_home_page_renders_chat_console(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")
        self.assertContains(response, "Start each chat session with the right stored prompt set.")
        self.assertContains(response, "/api/chat/login/")
        self.assertContains(response, "/api/chat/token/")
        self.assertContains(response, "/api/chat/course-topics/")
        self.assertContains(response, "/api/chat/sessions/")
        self.assertContains(response, "/api/chat/chat/")

    def test_course_topics_page_renders(self):
        response = self.client.get("/course-topics/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/course_topics.html")
        self.assertContains(response, "Store reusable prompt sets as course topics.")
        self.assertContains(response, "Create Course Topic")
        self.assertContains(response, "Use Django Session")
