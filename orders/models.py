from django.db import models
from django.contrib.auth.models import User

class Order(models.Model):
    # ---- Ownership ----
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders"
    )

    # ---- Device Info ----
    DEVICE_CHOICES = [
        ("laptop", "Laptop"),
        ("desktop", "Desktop"),
        ("other", "Other"),
    ]

    device_type = models.CharField(
        max_length=20,
        choices=DEVICE_CHOICES
    )
    
    # ---- Hardware Info ----
    CPU_PLATFORM_CHOICES = [
        ("am4", "AMD AM4"),
        ("am5", "AMD AM5"),
        ("intel_8_9", "Intel 8th–9th Gen"),
        ("intel_10_11", "Intel 10th–11th Gen"),
        ("intel_12_13_14", "Intel 12th–14th Gen"),
        ("apple_silicon", "Apple Silicon (M-series)"),
        ("unknown", "Not sure"),
    ]

    cpu_platform = models.CharField(
        max_length=30,
        choices=CPU_PLATFORM_CHOICES,
        default="unknown"
    )

    GPU_BRAND_CHOICES = [
        ("nvidia", "NVIDIA"),
        ("amd", "AMD"),
        ("intel", "Intel"),
        ("apple", "Apple (Integrated)"),
        ("none", "No dedicated GPU / Integrated"),
        ("unknown", "Not sure"),
    ]

    gpu_brand = models.CharField(
        max_length=20,
        choices=GPU_BRAND_CHOICES,
        default="unknown"
    )

    # ---- Problem Description ----
    issue_title = models.CharField(
        max_length=100
    )

    issue_description = models.TextField()

    # ---- Urgency & Status ----
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="medium"
    )

    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("in_progress", "In Progress"),
        ("waiting_parts", "Waiting for Parts"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="submitted"
    )

    # ---- Logistics ----
    location = models.CharField(
        max_length=100,
        help_text="Dorm, apartment, or campus location"
    )

    contact_email = models.EmailField()
    contact_phone = models.CharField(
        max_length=20,
        blank=True
    )

    # ---- Pricing ----
    estimated_cost = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )

    final_cost = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )

    # ---- Timestamps ----
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    completed = models.BooleanField(default=False)

    def __str__(self):
        return f"Order #{self.id} - {self.issue_title}"

# Create your models here.
