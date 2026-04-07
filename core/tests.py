from django.test import SimpleTestCase


class HomePageTests(SimpleTestCase):
    def test_home_page_renders_chat_console(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")
        self.assertContains(response, "Talk to the chat API from the Django home page.")
        self.assertContains(response, "/api/chat/login/")
        self.assertContains(response, "/api/chat/token/")
        self.assertContains(response, "/api/chat/sessions/")
        self.assertContains(response, "/api/chat/chat/")
