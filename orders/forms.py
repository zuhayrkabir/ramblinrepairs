from django import forms
from .models import Order

class OrderCreateForm(forms.ModelForm):
    class Meta:
        model = Order

        # Only include fields a user should fill out when submitting a ticket
        fields = [
            "device_type",
            "cpu_platform",
            "gpu_brand",
            "issue_title",
            "issue_description",
            "priority",
            "location",
            "contact_email",
            "contact_phone",
        ]

        widgets = {
            "device_type": forms.Select(attrs={"class": "form-select"}),
            "cpu_platform": forms.Select(attrs={"class": "form-select"}),
            "gpu_brand": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),

            "issue_title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., Blue screen on startup / laptop overheats / won't charge"
            }),
            "issue_description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Describe what's happening, when it started, and anything you've tried."
            }),
            "location": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., North Ave, West Campus dorm, CULC, etc."
            }),
            "contact_email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "name@gatech.edu"
            }),
            "contact_phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "(optional) 404-xxx-xxxx"
            }),
        }

    def clean_contact_phone(self):
        """
        Optional: basic cleanup so users can type anything reasonable.
        """
        phone = (self.cleaned_data.get("contact_phone") or "").strip()
        return phone