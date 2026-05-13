from django import forms
from django.conf import settings
from django.forms import modelformset_factory

from FAQ.models import FAQ

from .models import APIKeyConfig


class APIKeyConfigForm(forms.ModelForm):
    """Form for selecting the active OpenRouter API key index."""
    
    active_key_index = forms.ChoiceField(
        label="Active API Key",
        help_text="Select which OpenRouter API key to use for requests",
        widget=forms.RadioSelect,
    )

    class Meta:
        model = APIKeyConfig
        fields = ('active_key_index',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Get available keys from settings
        api_keys = getattr(settings, 'OPENROUTER_API_KEYS', [])
        
        # Build choices: (index, display_label)
        # Show key prefix and status (empty/filled)
        choices = []
        for idx, key in enumerate(api_keys):
            key_preview = key[:20] + '...' if key else '(empty)'
            choice_label = f"Key {idx + 1}: {key_preview}"
            choices.append((str(idx), choice_label))
        
        self.fields['active_key_index'].choices = choices
    
    def clean_active_key_index(self):
        """Validate that the selected index is within bounds and the key is not empty."""
        index_str = self.cleaned_data.get('active_key_index')
        if index_str is None:
            raise forms.ValidationError("Please select an API key.")
        
        try:
            index = int(index_str)
        except (ValueError, TypeError):
            raise forms.ValidationError("Invalid key index.")
        
        api_keys = getattr(settings, 'OPENROUTER_API_KEYS', [])
        
        if index < 0 or index >= len(api_keys):
            raise forms.ValidationError(
                f"Selected key index {index} is out of range (0-{len(api_keys) - 1})."
            )
        
        if not api_keys[index]:
            raise forms.ValidationError(
                f"Selected key {index + 1} is empty. Please select a different key."
            )
        
        return index


class FAQForm(forms.ModelForm):
    """Single FAQ row used inside the manage-FAQs formset.

    The model has an ``order`` field that drives display sequence, but admins
    don't need to think about that on this screen. We hide it from the form
    and let the view auto-assign sensible values on save.
    """

    class Meta:
        model = FAQ
        fields = ("question", "answer")
        widgets = {
            "question": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Question",
            }),
            "answer": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Answer (plain text or simple HTML allowed)",
            }),
        }


FAQFormSet = modelformset_factory(
    FAQ,
    form=FAQForm,
    extra=1,
    can_delete=True,
)

