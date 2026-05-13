from django.db import migrations


INITIAL_FAQS = [
    (
        10,
        "Do you guarantee repairs?",
        "We do our best to diagnose and fix issues, but we can\u2019t guarantee outcomes because some problems "
        "are caused by underlying hardware failure, liquid damage, or software issues outside our control.",
    ),
    (
        20,
        "Can my data be lost during repair?",
        "Data loss is always a possibility during troubleshooting or OS work. You\u2019re responsible for backing "
        "up your files before service. If you need help backing up, ask us and we can discuss options.",
    ),
    (
        30,
        "Who works on my device?",
        "Repairs may be performed by the business owner or a student technician working under the business. "
        "We aim to keep processes consistent, documented, and transparent.",
    ),
    (
        40,
        "Are you affiliated with Georgia Tech?",
        "No. We\u2019re an independent business serving the GT area. We are not officially affiliated with "
        "Georgia Tech.",
    ),
    (
        50,
        "What if my device already has damage?",
        "We\u2019re not responsible for pre-existing issues (cracked screens, liquid indicators, stripped screws, "
        "etc.). If we notice obvious damage before work, we\u2019ll document it and tell you.",
    ),
    (
        60,
        "Do you offer refunds?",
        "Refunds are evaluated case-by-case. If work has been performed (time spent diagnosing, parts ordered, "
        "etc.) refunds may not be available. If you\u2019re unhappy, contact us and we\u2019ll try to make it right.",
    ),
    (
        70,
        "How do I contact you?",
        "Use the contact form on our website, or email us at "
        "<span class=\"fw-semibold\">ramblinrepairsgt@gmail.com</span>.",
    ),
    (
        80,
        "How do I find my CPU platform?",
        "<ul class=\"mb-0\">"
        "<li><strong>Windows:</strong> Press <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>Esc</kbd> "
        "\u2192 <strong>Performance</strong> tab \u2192 click <strong>CPU</strong> "
        "(you\u2019ll see the CPU name like \u201cIntel Core i7\u2026\u201d or \u201cAMD Ryzen\u2026\u201d). "
        "Ask online which platform that model is.</li>"
        "<li><strong>Windows (quick command):</strong> Press <kbd>Windows</kbd> + <kbd>R</kbd>, type "
        "<code>msinfo32</code>, press Enter \u2192 look for <strong>Processor</strong>.</li>"
        "<li><strong>macOS:</strong> Apple menu (\uf8ff) \u2192 <strong>About This Mac</strong> \u2192 "
        "check <strong>Chip</strong> (Apple Silicon) or <strong>Processor</strong> (Intel).</li>"
        "<li><strong>Linux:</strong> Open Terminal \u2192 run <code>lscpu</code> "
        "(or <code>cat /proc/cpuinfo | head</code>) to see your CPU model.</li>"
        "<li><strong>Not sure what to enter?</strong> Just copy/paste the CPU name into the issue description "
        "(e.g., \u201cIntel Core i5-1135G7\u201d or \u201cApple M2\u201d).</li>"
        "</ul>",
    ),
    (
        90,
        "How do I find my GPU brand?",
        "<ul class=\"mb-0\">"
        "<li><strong>Windows:</strong> Press <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>Esc</kbd> \u2192 "
        "<strong>Performance</strong> tab \u2192 click <strong>GPU</strong> "
        "(you\u2019ll see NVIDIA, AMD, or Intel listed).</li>"
        "<li><strong>Windows (Device Manager):</strong> Right-click Start \u2192 "
        "<strong>Device Manager</strong> \u2192 expand <strong>Display adapters</strong>.</li>"
        "<li><strong>macOS:</strong> Apple menu (\uf8ff) \u2192 <strong>About This Mac</strong> \u2192 "
        "<strong>System Report</strong> \u2192 <strong>Graphics/Displays</strong>.</li>"
        "<li><strong>Linux:</strong> Open Terminal \u2192 run <code>lspci | grep -i vga</code> "
        "(or <code>lshw -C display</code>).</li>"
        "<li><strong>Laptops:</strong> You may see <em>two GPUs</em> (integrated + dedicated). "
        "Listing either is fine.</li>"
        "<li><strong>Not sure what to enter?</strong> Copy the GPU name into the issue description "
        "(e.g., \u201cNVIDIA RTX 3060,\u201d \u201cAMD Radeon,\u201d or \u201cIntel Iris Xe\u201d).</li>"
        "</ul>",
    ),
]


def seed_faqs(apps, schema_editor):
    FAQ = apps.get_model("FAQ", "FAQ")
    # Only seed if the table is empty so re-running migrations on populated DBs is safe.
    if FAQ.objects.exists():
        return
    for order, question, answer in INITIAL_FAQS:
        FAQ.objects.create(order=order, question=question, answer=answer)


def unseed_faqs(apps, schema_editor):
    FAQ = apps.get_model("FAQ", "FAQ")
    FAQ.objects.filter(question__in=[q for _, q, _ in INITIAL_FAQS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("FAQ", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_faqs, unseed_faqs),
    ]
