from django.http import HttpResponse


def home(request):
    return HttpResponse("Agentic Curiosity is running.")
