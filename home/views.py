from django.shortcuts import render
def index(request):
    template_data = {}
    template_data['title'] = 'Ramblin\' Repairs'
    return render(request, 'home/index.html', {'template_data': template_data})

# Create your views here.
