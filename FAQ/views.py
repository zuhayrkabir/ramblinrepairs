from django.shortcuts import render

from .models import FAQ


def index(request):
    template_data = {'title': "Ramblin' Repairs"}
    faqs = FAQ.objects.all()
    return render(
        request,
        'FAQ/index.html',
        {'template_data': template_data, 'faqs': faqs},
    )
